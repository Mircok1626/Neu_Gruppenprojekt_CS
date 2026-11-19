"""Gemeinsame Daten und Funktionen, die mehrere Seiten brauchen (Dashboard, Kalender, Wetter).

Hier steht alles nur einmal, damit alle Seiten gleich rechnen:
- das Datum aus der Seitenleiste («Heute ist der»)
- die Agrometeo-Daten (gemessen) und das Wetter von Open-Meteo (Prognose)
- Temperatursumme und Keimbereitschaft (= Beginn der Spritzsaison)
- das Machine-Learning-Modell, das Infektionen aus dem Wetter erkennt
- die Ampel, die Spritzungen aus dem Journal und die Fristen der Infektionen
"""

import datetime as dt
import sqlite3

import pandas as pd
import requests
import streamlit as st
from sklearn.ensemble import RandomForestClassifier

# Station Zizers
ZIZERS_LAT = 46.94
ZIZERS_LON = 9.56

# Ab dieser Temperatursumme (seit 1.1., nur der Teil über 8 °C) sind die Sporen keimbereit
KEIMBEREIT_AB = 140

# Ende der Spritzsaison: Weichwerden der Trauben. PLATZHALTER, mit dem Winzer bestätigen.
SAISON_ENDE = (8, 31)    # 31. August

# Ab so vielen Gradstunden bei Blattnässe gibt es eine Infektion (Fachlogik, Agrometeo)
GRADSTUNDEN_INFEKTION = 70

# Machine Learning: Wettermerkmale, Lern- und Testjahre, Warnschwelle
MERKMALE = ["temp_min", "temp_mittel", "temp_max", "niederschlag_mm", "regen_vortag", "tag_im_jahr"]
LERNJAHRE = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
TESTJAHR = 2026
# Das Modell besteht aus 300 Bäumen, die abstimmen. Sagen mindestens 25 % davon
# «Infektion», gilt der Tag als Infektion. Gewählt mit 2025 (Modell aus 2019 bis 2024).
WARNSCHWELLE = 0.25


# ---------------------------------------------------------------------------
# Datum aus der Seitenleiste
# ---------------------------------------------------------------------------
def heute():
    """Das Datum, das links in der Seitenleiste gewählt ist (Standard: heute)."""
    return st.session_state.get("heute", dt.date.today())


# ---------------------------------------------------------------------------
# Agrometeo (gemessen)
# ---------------------------------------------------------------------------
def ergaenze_merkmale(df):
    """Ergänzt zwei Merkmale, die das Modell braucht.

    regen_vortag: Regen am Tag davor (nasser Boden und nasse Blätter wirken nach)
    tag_im_jahr:  1 bis 365, damit das Modell die Jahreszeit kennt
    """
    df["niederschlag_mm"] = df["niederschlag_mm"].fillna(0)   # leeres Feld heisst: kein Regen
    df["regen_vortag"] = df["niederschlag_mm"].shift(1).fillna(0)
    df["tag_im_jahr"] = df["datum"].dt.dayofyear
    return df


@st.cache_data
def lade_agrometeo(jahr):
    """Liest die Agrometeo-Tabelle eines Jahres (nur gemessene Tage, keine Prognose)."""
    df = pd.read_csv(f"daten/zizers_{jahr}.csv")
    df = df[df["aus_wettervorhersage"] == 0].copy()
    df["datum"] = pd.to_datetime(df["datum"])
    df = ergaenze_merkmale(df)
    df = df.dropna(subset=["temp_min", "temp_mittel", "temp_max"])
    # Die richtige Antwort, die das Modell lernen soll: 1 = Infektion, 0 = keine
    df["infektion"] = (df["infektion_staerke"] > 0).astype(int)
    # Dauer der Inkubation in Tagen. errors="coerce": ungültige Einträge (z. B. "79%") werden leer
    ende = pd.to_datetime(df["inkubation_aktuell"] + str(jahr), format="%d.%m.%Y", errors="coerce")
    df["dauer"] = (ende - df["datum"]).dt.days
    return df


# ---------------------------------------------------------------------------
# Open-Meteo (Prognose)
# ---------------------------------------------------------------------------
def open_meteo_url(bis):
    """Vergangenheit und Prognose liegen bei Open-Meteo unter verschiedenen Adressen."""
    if bis < dt.date.today():
        return "https://historical-forecast-api.open-meteo.com/v1/forecast"  # Vergangenheit
    return "https://api.open-meteo.com/v1/forecast"  # Prognose


@st.cache_data(ttl=3600)
def lade_tageswetter(von, bis):
    """Lädt das Wetter pro Tag von Open-Meteo, mit denselben Spalten wie bei Agrometeo."""
    parameter = {"latitude": ZIZERS_LAT, "longitude": ZIZERS_LON, "timezone": "Europe/Zurich",
                 "daily": "temperature_2m_min,temperature_2m_mean,temperature_2m_max,precipitation_sum",
                 "start_date": str(von), "end_date": str(bis)}
    daten = requests.get(open_meteo_url(bis), params=parameter, timeout=10).json()["daily"]
    df = pd.DataFrame({
        "datum": pd.to_datetime(daten["time"]),
        "temp_min": daten["temperature_2m_min"],
        "temp_mittel": daten["temperature_2m_mean"],
        "temp_max": daten["temperature_2m_max"],
        "niederschlag_mm": daten["precipitation_sum"],
    })
    return ergaenze_merkmale(df)


# ---------------------------------------------------------------------------
# Machine Learning
# ---------------------------------------------------------------------------
@st.cache_resource   # das Modell nur einmal trainieren, nicht bei jedem Klick
def trainiere_modell():
    """Trainiert das Modell mit den Lernjahren und prüft es mit dem Testjahr.

    Rückgabe: das Modell, die Inkubationsdauer pro Monat und die Ergebnisse des Tests.
    """
    # Alle Lernjahre untereinander in eine grosse Tabelle
    lernen = pd.concat([lade_agrometeo(jahr) for jahr in LERNJAHRE])

    # Random Forest: 300 Entscheidungsbäume, die gemeinsam abstimmen.
    # class_weight="balanced": Infektionstage sind seltener, zählen darum stärker.
    modell = RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                    class_weight="balanced", random_state=0)
    modell.fit(lernen[MERKMALE], lernen["infektion"])

    # Wie lange dauert die Inkubation im Schnitt? Je Monat aus den Lerndaten.
    infektionen = lernen[(lernen["infektion"] == 1) & lernen["dauer"].notna()]
    dauer_pro_monat = infektionen.groupby(infektionen["datum"].dt.month)["dauer"].mean().round().to_dict()

    # Test mit dem Testjahr (nur Tage in der Spritzsaison): das Modell kennt sie nicht
    test = lade_agrometeo(TESTJAHR)
    test = test[in_saison(test["datum"], keimbereitschaft(test))]
    vorhersage = (modell.predict_proba(test[MERKMALE])[:, 1] >= WARNSCHWELLE).astype(int)
    echt = test["infektion"]
    ergebnis = {
        "erkannt": int(((vorhersage == 1) & (echt == 1)).sum()),
        "total": int(echt.sum()),
        "verpasst": int(((vorhersage == 0) & (echt == 1)).sum()),
        "fehlalarme": int(((vorhersage == 1) & (echt == 0)).sum()),
    }
    return modell, dauer_pro_monat, ergebnis


def modell_sagt_infektion(df):
    """Gibt für jeden Tag True (Infektion) oder False zurück, laut Modell."""
    if df.empty:
        return pd.Series([], dtype=bool)
    modell, _, _ = trainiere_modell()
    stimmen = modell.predict_proba(df[MERKMALE])[:, 1]   # Anteil der Bäume, die «Infektion» sagen
    return pd.Series(stimmen >= WARNSCHWELLE, index=df.index)


# ---------------------------------------------------------------------------
# Wetter vom 1.1. bis heute + 14 Tage (für Wetter-Seite und Kalender)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def wetter_seit_neujahr(stichtag):
    """Tageswerte vom 1.1. bis 14 Tage nach dem Stichtag.

    Bis zum Stichtag: Agrometeo (gemessen, mit Blattnässe, Gradstunden und Infektionen).
    Danach: Prognose von Open-Meteo. Infektionen sagt dort das Modell voraus.
    Fehlen bei Agrometeo Tage vor dem Stichtag, kommen auch diese von Open-Meteo.
    Spalte «quelle»: "gemessen" (Agrometeo), "geschätzt" (Open-Meteo, vor dem Stichtag)
    oder "Prognose" (Open-Meteo, nach dem Stichtag).
    """
    stichtag = pd.Timestamp(stichtag)
    bis = stichtag + pd.Timedelta(days=14)

    # 1) Gemessene Tage von Agrometeo bis zum Stichtag
    try:
        gemessen = lade_agrometeo(stichtag.year)
        gemessen = gemessen[gemessen["datum"] <= stichtag].copy()
    except FileNotFoundError:
        gemessen = pd.DataFrame(columns=["datum"])
    gemessen["quelle"] = "gemessen"
    gemessen["infektion"] = gemessen.get("infektion", pd.Series(dtype=int)).astype(bool)

    # 2) Alles danach (oder was bei Agrometeo fehlt) von Open-Meteo
    if len(gemessen) > 0:
        ab = gemessen["datum"].max() + pd.Timedelta(days=1)
    else:
        ab = pd.Timestamp(year=stichtag.year, month=1, day=1)
    try:
        prognose = lade_tageswetter(ab.date(), bis.date())
    except Exception:
        prognose = pd.DataFrame(columns=["datum"])
    # Nach dem Stichtag: Prognose. Davor (falls Agrometeo fehlt): vom Modell geschätzt
    prognose["quelle"] = ["Prognose" if d > stichtag else "geschätzt" for d in prognose["datum"]]
    prognose["infektion"] = modell_sagt_infektion(prognose) if len(prognose) > 0 else pd.Series(dtype=bool)

    df = pd.concat([gemessen, prognose], ignore_index=True).sort_values("datum").reset_index(drop=True)
    # Spalten, die nur Agrometeo hat, sicher anlegen (bei der Prognose bleiben sie leer)
    for spalte in ["blattnaesse_std", "gradstunden_bn", "dauer", "infektion_staerke"]:
        if spalte not in df:
            df[spalte] = float("nan")

    # 3) Temperatursumme seit 1.1.: jeder Tag zählt mit, so viel er über 8 °C warm ist
    df["temperatursumme"] = (df["temp_mittel"] - 8).clip(lower=0).cumsum()
    df["keimbereit"] = df["temperatursumme"] >= KEIMBEREIT_AB
    # Vor der Keimbereitschaft gibt es keine Infektion
    df["infektion"] = df["infektion"].astype(bool) & df["keimbereit"]
    return df


def keimbereitschaft(df):
    """Erster Tag, an dem die Temperatursumme 140 erreicht (None, wenn noch nicht erreicht)."""
    summe = (df["temp_mittel"] - 8).clip(lower=0).cumsum()
    tage = df.loc[summe >= KEIMBEREIT_AB, "datum"]
    if len(tage) == 0:
        return None
    return tage.min()


def in_saison(daten, keimbereit):
    """True für Tage in der Spritzsaison: ab Keimbereitschaft bis zum Saisonende (31.8.)."""
    if keimbereit is None:
        return pd.Series(False, index=daten.index)
    zahl = daten.dt.month * 100 + daten.dt.day   # z. B. 15. Mai = 515
    return (daten >= keimbereit) & (zahl <= SAISON_ENDE[0] * 100 + SAISON_ENDE[1])

# ---------------------------------------------------------------------------
# Ampel, Journal und Infektionen (für Kalender und Dashboard)
# ---------------------------------------------------------------------------
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
FARBEN = ["#D9EAD3", "#FFF2CC", "#F4CCCC"]  # grün, gelb, rot
AMPEL = ["geeignet", "knapp", "nicht möglich"]

# Folpet ist nicht hitzeempfindlich, darum zählen in der Ampel nur Regen und Wind.
# Startwerte der Ampel: (gelb ab, rot ab, Einheit), noch mit dem Winzer bestätigen
STANDARD = {"Regen": (0.5, 2.0, "mm"), "Wind": (15.0, 25.0, "km/h")}

# Formel 4 aus der Fachlogik: Ein Spritzbelag schützt etwa 10 Tage (mit dem Winzer bestätigen)
SCHUTZ_TAGE = 10


def lade_spritzungen():
    """Holt alle Spritzungen aus dem Journal (gleiche Datenbank wie die Seite Journal)."""
    try:
        con = sqlite3.connect("daten/spritzplaner.db")
        df = pd.read_sql_query("SELECT datum, mittel FROM spritzungen", con)
        con.close()
    except Exception:
        # Gibt es die Tabelle noch nicht, ist einfach noch nichts gespritzt
        df = pd.DataFrame(columns=["datum", "mittel"])
    df["datum"] = pd.to_datetime(df["datum"])
    return df.sort_values("datum")


def pruefe_schutz(infektionen, spritzungen):
    """Gibt jeder Infektion einen Status: «gespritzt» oder «offen».

    gespritzt: Es wurde in den 10 Tagen vor der Infektion gespritzt (der Belag war schon da)
               oder nach der Infektion, aber noch vor der Frist.
    offen:     Weder noch, der Winzer muss noch spritzen.
    """
    status = []
    for _, infektion in infektionen.iterrows():
        ergebnis = "offen"
        for spritztag in spritzungen["datum"]:
            vorher_geschuetzt = spritztag <= infektion["start"] <= spritztag + pd.Timedelta(days=SCHUTZ_TAGE)
            rechtzeitig_nachher = infektion["start"] < spritztag <= infektion["frist"]
            if vorher_geschuetzt or rechtzeitig_nachher:
                ergebnis = "gespritzt"
        status.append(ergebnis)
    infektionen["status"] = status
    return infektionen


def infektionen_mit_frist(heute):
    """Infektionen der letzten und nächsten 14 Tage (nur in der Spritzsaison).

    Für jede Infektion: Start, Ende der Inkubation, Frist (spritzen bis) und Status.
    Gibt auch die Spritzungen aus dem Journal zurück (nur bis «heute», wichtig für den Demo-Modus).
    """
    tageswetter = wetter_seit_neujahr(heute)
    saison = in_saison(tageswetter["datum"], keimbereitschaft(tageswetter))
    _, dauer_pro_monat, _ = trainiere_modell()

    infektionen = tageswetter[tageswetter["infektion"] & saison
                              & (tageswetter["datum"] >= pd.Timestamp(heute) - pd.Timedelta(days=14))].copy()
    infektionen["start"] = infektionen["datum"]
    # Inkubationsdauer: echte Dauer von Agrometeo, für die Prognose der gelernte Monats-Durchschnitt
    dauer = infektionen["dauer"].fillna(infektionen["datum"].dt.month.map(dauer_pro_monat)).fillna(10)
    infektionen["ende"] = infektionen["start"] + pd.to_timedelta(dauer, unit="D")
    # Formel 3: spritzen bis = Infektion + 80 % der Inkubationsdauer
    infektionen["frist"] = (infektionen["start"] + (infektionen["ende"] - infektionen["start"]) * 0.8).dt.floor("D")

    spritzungen = lade_spritzungen()
    spritzungen = spritzungen[spritzungen["datum"] <= pd.Timestamp(heute)]
    infektionen = pruefe_schutz(infektionen, spritzungen)
    return infektionen, spritzungen


@st.cache_data
def lade_stundenwetter(von, bis):
    """Lädt das stündliche Wetter (Regen, Wind) für Zizers von Open-Meteo."""
    parameter = {"latitude": ZIZERS_LAT, "longitude": ZIZERS_LON, "timezone": "Europe/Zurich",
                 "hourly": "precipitation,wind_speed_10m",
                 "start_date": str(von), "end_date": str(bis)}
    daten = requests.get(open_meteo_url(bis), params=parameter, timeout=10).json()["hourly"]
    wetter = pd.DataFrame(daten)
    wetter["time"] = pd.to_datetime(wetter["time"])
    return wetter


def bewerte_tag(tag, wetter, sonntag_sperren):
    """Gibt Ampelstufe (0 grün, 1 gelb, 2 rot), beste Startzeit und Gründe für einen Tag zurück.

    Die Grenzwerte kommen aus dem Kalender («Grenzwerte der Ampel»), sonst die Startwerte.
    """
    stunden = wetter[wetter["time"].dt.date == tag.date()].reset_index()

    # Beste Startzeit: Stunde zwischen 6 und 14 Uhr mit am wenigsten Regen in den 6 Stunden danach
    start, wenig_regen = 6, 999
    for h in range(6, 15):
        regen = stunden["precipitation"][h:h + 6].sum()
        if regen < wenig_regen:
            start, wenig_regen = h, regen

    fenster = stunden[start:start + 6]
    werte = {"Regen": fenster["precipitation"].sum(),
             "Wind": fenster["wind_speed_10m"].max()}

    stufe, gruende = 0, []
    for name, wert in werte.items():
        gelb = st.session_state.get(name + "_gelb", STANDARD[name][0])
        rot = st.session_state.get(name + "_rot", STANDARD[name][1])
        if wert >= gelb:
            stufe = max(stufe, 2 if wert >= rot else 1)  # der schlechteste Wert bestimmt die Farbe
            gruende.append(f"{name} {wert:.1f} {STANDARD[name][2]}")
    if sonntag_sperren and tag.weekday() == 6:
        stufe = 2
        gruende.append("Sonntag")
    return stufe, start, gruende