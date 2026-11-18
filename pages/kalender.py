# Hier wird die Seite Kalender codiert.
"""Kalender: Wann kann ich spritzen?

Die Seite erkennt Infektionen mit einem eigenen Machine-Learning-Modell:
Das Modell hat aus den Agrometeo-Daten 2019 bis 2025 gelernt, bei welchem
Wetter es eine Infektion gibt. Danach schaut es sich das Wetter von Open-Meteo
an (die letzten 14 Tage und die Prognose) und sagt, an welchen Tagen es eine
Infektion gibt. Zusammen mit dem stündlichen Wetter zeigt die Seite für
14 Tage eine Ampel, wann man spritzen kann.

KI-Hinweis: Dieser Code wurde mit Claude (Anthropic, Claude Opus 5.5) am
17.11.2026 generiert und danach von uns geprüft und angepasst.
"""

import datetime as dt
import sqlite3

import altair as alt
import pandas as pd
import requests
import streamlit as st
from sklearn.ensemble import RandomForestClassifier

# Farben aus dem Konzept
WEINROT = "#7B1E3A"
GOLD = "#C9A227"
FARBEN = ["#D9EAD3", "#FFF2CC", "#F4CCCC"]  # grün, gelb, rot
AMPEL = ["geeignet", "knapp", "nicht möglich"]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Wir spritzen nur mit Folpet 80 WG (wie auf der Seite Dosierung).
# Folpet ist nicht hitzeempfindlich, darum zählen in der Ampel nur Regen und Wind.

# Startwerte der Ampel: (gelb ab, rot ab, Einheit), noch mit dem Winzer bestätigen
STANDARD = {"Regen": (0.5, 2.0, "mm"), "Wind": (15.0, 25.0, "km/h")}

# Farbe für Tage, an denen der Belag der letzten Spritzung noch schützt
GRAU = "#EEEEEE"

# Wettermerkmale, aus denen das Modell lernt. Diese Werte gibt es sowohl in den
# Agrometeo-Daten (Vergangenheit) als auch bei Open-Meteo (Prognose).
MERKMALE = ["temp_min", "temp_mittel", "temp_max", "niederschlag_mm", "regen_vortag", "tag_im_jahr"]

# Jahre zum Lernen und Jahr zum Testen (das Testjahr sieht das Modell beim Lernen nie)
LERNJAHRE = [2019, 2020, 2021, 2022, 2023, 2024, 2025]
TESTJAHR = 2026

# Das Modell besteht aus 300 Bäumen, die abstimmen. Sagen mindestens 25 % davon
# «Infektion», gilt der Tag als Infektion. Bewusst vorsichtig (nicht erst ab 50 %):
# Eine verpasste Infektion kostet Ernte, ein Fehlalarm nur einen Kontrollgang.
# Gewählt mit 2025: Modell aus 2019 bis 2024 gelernt, ab 25 % erkennt es 95 % der Infektionen.
WARNSCHWELLE = 0.25

# Spritzsaison gegen Falschen Mehltau: ab Austrieb bis zum Weichwerden der Trauben.
# Ausserhalb der Saison wird nicht gespritzt, also warnt der Kalender auch nicht.
# PLATZHALTER: Das Saisonende (Weichwerden) noch mit dem Winzer bestätigen.
SAISON_START = (4, 1)    # 1. April
SAISON_ENDE = (8, 31)    # 31. August


# Formel 4 aus der Fachlogik: Ein Spritzbelag schützt etwa 10 Tage (mit dem Winzer bestätigen)
SCHUTZ_TAGE = 10


def in_saison(daten):
    """Gibt für jedes Datum True (in der Spritzsaison) oder False (ausserhalb) zurück."""
    # Monat und Tag als eine Zahl, z. B. 15. Mai = 515, damit man einfach vergleichen kann
    zahl = daten.dt.month * 100 + daten.dt.day
    return (zahl >= SAISON_START[0] * 100 + SAISON_START[1]) & (zahl <= SAISON_ENDE[0] * 100 + SAISON_ENDE[1])


# ---------------------------------------------------------------------------
# Machine Learning: aus den Agrometeo-Daten lernen
# ---------------------------------------------------------------------------
def ergaenze_merkmale(df):
    """Ergänzt zwei Merkmale, die das Modell braucht.

    regen_vortag: Regen am Tag davor (nasser Boden und nasse Blätter wirken nach)
    tag_im_jahr:  1 bis 365, damit das Modell die Saison kennt (im Winter keine Infektion)
    """
    df["niederschlag_mm"] = df["niederschlag_mm"].fillna(0)   # leeres Feld heisst: kein Regen
    df["regen_vortag"] = df["niederschlag_mm"].shift(1).fillna(0)
    df["tag_im_jahr"] = df["datum"].dt.dayofyear
    return df


def lade_agrometeo(jahr):
    """Liest die Agrometeo-Tabelle eines Jahres und bereitet sie für das Modell vor."""
    df = pd.read_csv(f"daten/zizers_{jahr}.csv")
    df = df[df["aus_wettervorhersage"] == 0].copy()   # nur gemessene Tage, keine Prognose
    df["datum"] = pd.to_datetime(df["datum"])
    df = ergaenze_merkmale(df)
    df = df.dropna(subset=["temp_min", "temp_mittel", "temp_max"])
    # Die richtige Antwort, die das Modell lernen soll: 1 = Infektion, 0 = keine
    df["infektion"] = (df["infektion_staerke"] > 0).astype(int)
    # Dauer der Inkubation in Tagen. errors="coerce": ungültige Einträge (z. B. "79%") werden leer
    ende = pd.to_datetime(df["inkubation_aktuell"] + str(jahr), format="%d.%m.%Y", errors="coerce")
    df["dauer"] = (ende - df["datum"]).dt.days
    return df


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

    # Test mit dem Testjahr: Tage, die das Modell beim Lernen nie gesehen hat
    test = lade_agrometeo(TESTJAHR)
    test = test[in_saison(test["datum"])]   # gezählt werden nur Tage in der Spritzsaison
    vorhersage = (modell.predict_proba(test[MERKMALE])[:, 1] >= WARNSCHWELLE).astype(int)
    echt = test["infektion"]
    ergebnis = {
        "erkannt": int(((vorhersage == 1) & (echt == 1)).sum()),
        "total": int(echt.sum()),
        "verpasst": int(((vorhersage == 0) & (echt == 1)).sum()),
        "fehlalarme": int(((vorhersage == 1) & (echt == 0)).sum()),
    }
    return modell, dauer_pro_monat, ergebnis


def erkenne_infektionen(tageswetter, modell, dauer_pro_monat):
    """Das Modell schaut sich jeden Tag an und sagt, ob es eine Infektion gibt."""
    df = tageswetter.dropna(subset=MERKMALE).copy()
    df = df[in_saison(df["datum"])]   # ausserhalb der Saison keine Warnung
    if df.empty:   # keine Wetterdaten: dann auch keine Infektionen
        return pd.DataFrame(columns=["start", "ende", "frist"])
    # Das Modell entscheidet für jeden Tag: Infektion ja oder nein
    stimmen = modell.predict_proba(df[MERKMALE])[:, 1]   # Anteil der Bäume, die «Infektion» sagen
    df = df[stimmen >= WARNSCHWELLE].copy()               # nur die Tage mit Infektion behalten

    df["start"] = df["datum"]
    # Inkubationsdauer aus dem gelernten Durchschnitt des Monats (falls unbekannt: 10 Tage)
    dauer = df["datum"].dt.month.map(dauer_pro_monat).fillna(10)
    df["ende"] = df["start"] + pd.to_timedelta(dauer, unit="D")
    # Formel 3: spritzen bis = Infektionsdatum + 80 % der Inkubationsdauer
    df["frist"] = (df["start"] + (df["ende"] - df["start"]) * 0.8).dt.floor("D")
    return df


# ---------------------------------------------------------------------------
# Verbindung zum Journal: Wurde schon gespritzt?
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Wetter von Open-Meteo
# ---------------------------------------------------------------------------
def open_meteo_url(bis):
    """Vergangenheit und Prognose liegen bei Open-Meteo unter verschiedenen Adressen."""
    if bis < dt.date.today():
        return "https://historical-forecast-api.open-meteo.com/v1/forecast"  # Vergangenheit
    return "https://api.open-meteo.com/v1/forecast"  # Prognose


@st.cache_data
def lade_wetter(von, bis):
    """Lädt das stündliche Wetter (Regen, Wind, Temperatur) für Zizers von Open-Meteo."""
    parameter = {"latitude": 46.94, "longitude": 9.56, "timezone": "Europe/Zurich",
                 "hourly": "precipitation,wind_speed_10m",
                 "start_date": str(von), "end_date": str(bis)}
    daten = requests.get(open_meteo_url(bis), params=parameter, timeout=10).json()["hourly"]
    wetter = pd.DataFrame(daten)
    wetter["time"] = pd.to_datetime(wetter["time"])
    return wetter


@st.cache_data
def lade_tageswetter(von, bis):
    """Lädt das Wetter pro Tag von Open-Meteo, mit denselben Spalten wie bei Agrometeo."""
    parameter = {"latitude": 46.94, "longitude": 9.56, "timezone": "Europe/Zurich",
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
# Ampel
# ---------------------------------------------------------------------------
def bewerte_tag(tag, wetter, sonntag_sperren):
    """Gibt Ampelstufe (0 grün, 1 gelb, 2 rot), beste Startzeit und Gründe für einen Tag zurück."""
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
        gelb, rot = st.session_state[name + "_gelb"], st.session_state[name + "_rot"]
        if wert >= gelb:
            stufe = max(stufe, 2 if wert >= rot else 1)  # der schlechteste Wert bestimmt die Farbe
            gruende.append(f"{name} {wert:.1f} {STANDARD[name][2]}")
    if sonntag_sperren and tag.weekday() == 6:
        stufe = 2
        gruende.append("Sonntag")
    return stufe, start, gruende


def standardwerte():
    """Setzt die Grenzwerte der Ampel auf die Startwerte zurück."""
    for name, (gelb, rot, einheit) in STANDARD.items():
        st.session_state[name + "_gelb"] = gelb
        st.session_state[name + "_rot"] = rot


# Beim ersten Öffnen der Seite die Startwerte setzen
if "Regen_gelb" not in st.session_state:
    standardwerte()

st.title("Kalender: Wann kann ich spritzen?")

# Planungsleiste
spalte1, spalte2 = st.columns(2)
heute = spalte1.date_input("Heute ist der", value=dt.date.today(), min_value=dt.date(2024, 1, 1),
                           max_value=dt.date.today(), format="DD.MM.YYYY", key="heute")
spalte2.write("")
sonntag_sperren = spalte2.checkbox("Sonntag sperren", value=True)

# Platzhalter, damit Ampel und Inkubationen oberhalb der Grenzwerte erscheinen
bereich_ampel = st.container()
bereich_inkubation = st.container()

with st.expander("Grenzwerte der Ampel"):
    for name, (gelb, rot, einheit) in STANDARD.items():
        g1, g2 = st.columns(2)
        g1.number_input(f"{name} gelb ab ({einheit})", key=name + "_gelb", step=0.5)
        g2.number_input(f"{name} rot ab ({einheit})", key=name + "_rot", step=0.5)
    st.button("Standardwerte", on_click=standardwerte)

# Modell trainieren (passiert nur beim ersten Mal, danach ist es gespeichert)
modell, dauer_pro_monat, ergebnis = trainiere_modell()

# Daten laden
tage = pd.date_range(heute, periods=14)
try:
    wetter = lade_wetter(heute, tage[-1].date())
    # Für die Infektionen auch 14 Tage zurück: Eine Infektion von letzter Woche kann noch offen sein
    tageswetter = lade_tageswetter(heute - dt.timedelta(days=14), tage[-1].date())
except Exception:
    st.error("Das Wetter von Open-Meteo konnte nicht geladen werden.")
    st.stop()

# Das Modell sagt, an welchen Tagen es eine Infektion gibt
infektionen = erkenne_infektionen(tageswetter, modell, dauer_pro_monat)

# Spritzungen aus dem Journal holen (nur bis «heute», wichtig für den Demo-Modus)
spritzungen = lade_spritzungen()
spritzungen = spritzungen[spritzungen["datum"] <= pd.Timestamp(heute)]
# Für jede Infektion prüfen: geschützt, behandelt oder offen?
infektionen = pruefe_schutz(infektionen, spritzungen)

# Laufende Inkubationen: Balken, die in die 14 Tage hineinreichen
laufend = infektionen[(infektionen["start"] <= tage[-1]) & (infektionen["ende"] > tage[0])].copy()
# Schon passierte Infektionen, deren Frist noch nicht vorbei ist
aktuell = laufend[(laufend["start"] <= tage[0]) & (laufend["frist"] >= tage[0])]
# Offen sind davon nur die, gegen die noch nicht gespritzt wurde
offen = aktuell[aktuell["status"] == "offen"]
abgedeckt = aktuell[aktuell["status"] == "gespritzt"]

# Bis wann schützt die letzte Spritzung? (keine Spritzung: dann schützt nichts)
if len(spritzungen) > 0:
    geschuetzt_bis = spritzungen["datum"].iloc[-1] + pd.Timedelta(days=SCHUTZ_TAGE)
else:
    geschuetzt_bis = None

# Jeden Tag bewerten
bewertung = [bewerte_tag(tag, wetter, sonntag_sperren) for tag in tage]

with bereich_ampel:
    # Letzte Spritzung aus dem Journal anzeigen
    if len(spritzungen) > 0:
        letzte = spritzungen.iloc[-1]
        if geschuetzt_bis >= pd.Timestamp(heute):
            st.success(f"Letzte Spritzung laut Journal: {letzte['datum']:%d.%m.} mit {letzte['mittel']} "
                       f"→ geschützt bis {geschuetzt_bis:%d.%m.}")
        else:
            st.warning(f"Letzte Spritzung laut Journal: {letzte['datum']:%d.%m.} mit {letzte['mittel']} "
                       f"→ Schutz vorbei seit {geschuetzt_bis:%d.%m.}")
    else:
        st.caption("Noch keine Spritzung im Journal erfasst.")

    # Frist-Box (weinrot): die nächste Frist bestimmt die Planung
    if len(offen) > 0:
        infektion = offen.sort_values("frist").iloc[0]
        frist = infektion["frist"]
        gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= frist]
        if len(gute) > 0:
            start = bewertung[list(tage).index(gute[0])][1]
            empfehlung = f"Empfohlen: {WOCHENTAGE[gute[0].weekday()]}, {gute[0]:%d.%m.} ab {start} Uhr"
        else:
            empfehlung = "Kein grüner Tag vor der Frist. Prüfe die gelben Tage."
        # Das Wetter am Tag der Infektion (von Open-Meteo), damit man sieht, warum gewarnt wird
        wetter_text = f"{infektion['niederschlag_mm']:.1f} mm Regen, {infektion['temp_mittel']:.0f} °C"
        # Gibt es noch weitere offene Infektionen? Dann darauf hinweisen.
        if len(offen) > 1:
            weitere = f"<br>Dazu {len(offen) - 1} weitere Infektion(en), siehe «Laufende Inkubationen»."
        else:
            weitere = ""
        st.markdown(f"""
        <div style="background-color: {WEINROT}; color: white; padding: 20px; border-radius: 15px;">
            <p style="margin: 0; color: #F3D9DF;">Infektion am {infektion['start']:%d.%m.} · Wetter an diesem Tag: {wetter_text}</p>
            <h3 style="margin: 0; color: white;">Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h3>
            <p style="margin: 0;">{empfehlung}{weitere}</p>
        </div>""", unsafe_allow_html=True)
        st.caption("Frist = letzter sicherer Spritztag, bevor die Krankheit ausbricht.")
    else:
        frist, gute = None, []
        if in_saison(pd.Series([pd.Timestamp(heute)])).iloc[0]:
            if len(abgedeckt) > 0:
                st.info(f"Keine offene Infektion. {len(abgedeckt)} Infektion(en) sind durch "
                        "deine Spritzungen abgedeckt. Spritzen ist im Moment nicht nötig.")
            else:
                st.info("Keine offene Infektion. Spritzen ist im Moment nicht nötig.")
        else:
            st.info("Ausserhalb der Spritzsaison (April bis August). "
                    "Gegen Falschen Mehltau wird jetzt nicht gespritzt.")

    # Spritzfenster: Überschrift links, Legende der Farben rechts
    titel, legende = st.columns([1, 2], vertical_alignment="bottom")
    titel.subheader("Spritzfenster: 14 Tage")

    def kaestchen(farbe, rand="1px solid #CCCCCC"):
        """Kleines farbiges Quadrat für die Legende."""
        return (f"<span style='display:inline-block; width:12px; height:12px; background:{farbe}; "
                f"border:{rand}; border-radius:3px; margin:0 4px 0 14px; vertical-align:middle;'></span>")

    legende.markdown(
        "<div style='text-align:right; font-size:13px;'>"
        + kaestchen(FARBEN[0]) + "Geeignet"
        + kaestchen(FARBEN[1]) + "Knapp"
        + kaestchen(FARBEN[2]) + "Nicht möglich"
        + kaestchen(GRAU) + "Geschützt"
        + kaestchen("white", f"3px solid {GOLD}") + "Empfohlen"
        + "</div>", unsafe_allow_html=True)

    spalten = st.columns(7) + st.columns(7)
    for spalte, tag, (stufe, start, gruende) in zip(spalten, tage, bewertung):
        marken = []
        if tag == tage[0]:
            marken.append("heute")
        if len(gute) > 0 and tag == gute[-1] and tag != gute[0]:
            marken.append("letzte Chance")
        if tag == frist:
            marken.append("Frist")
        if tag in list(spritzungen["datum"]):
            marken.append("gespritzt")

        # Noch geschützt und keine offene Infektion: Spritzen ist nicht nötig, also keine Ampel
        if len(offen) == 0 and geschuetzt_bis is not None and tag <= geschuetzt_bis:
            farbe, text, gruende = GRAU, "geschützt<br>nicht nötig", []
        else:
            farbe, text = FARBEN[stufe], AMPEL[stufe] + (f"<br>ab {start} Uhr" if stufe < 2 else "")
        rahmen = f"3px solid {GOLD}" if len(gute) > 0 and tag == gute[0] else "1px solid #CCCCCC"

        spalte.markdown(f"""
        <div style="background-color: {farbe}; border: {rahmen}; border-radius: 10px;
                    padding: 8px; min-height: 150px; font-size: 13px; margin-bottom: 8px;">
            <b>{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}</b><br>{text}<br>
            <small>{", ".join(gruende)}</small><br>
            <b style="color: {WEINROT};">{" · ".join(marken)}</b>
        </div>""", unsafe_allow_html=True)

with bereich_inkubation:
    st.subheader("Laufende Inkubationen")
    if len(laufend) == 0:
        st.write("Keine laufenden Inkubationen in diesen 14 Tagen.")
    else:
        # Name des Balkens, z. B. "06.08. · offen" oder "06.08. · gespritzt"
        laufend["name"] = laufend["start"].dt.strftime("%d.%m.") + " · " + laufend["status"]
        # Farbe: offen = weinrot, gespritzt = grün, Infektion erst in der Prognose = hell
        laufend["art"] = laufend["status"]
        laufend.loc[(laufend["start"] > tage[0]) & (laufend["status"] == "offen"), "art"] = "Prognose"
        laufend["frist_text"] = "spritzen bis " + laufend["frist"].dt.strftime("%d.%m.")

        achse = alt.X("start:T", title=None, scale=alt.Scale(domain=[tage[0], tage[-1] + pd.Timedelta(days=1)]),
                      axis=alt.Axis(format="%d.%m.", tickCount=14, grid=True))
        zeile = alt.Y("name:N", title=None, sort=alt.SortField("start"))  # nach Datum sortiert
        farben = alt.Scale(domain=["offen", "gespritzt", "Prognose"], range=[WEINROT, "#6AA84F", "#D9A5B3"])
        # Was beim Darüberfahren mit der Maus erscheint (ohne «art», mit schönen Titeln)
        info_balken = [alt.Tooltip("start:T", title="Start", format="%d.%m."),
                       alt.Tooltip("name:N", title="Name"),
                       alt.Tooltip("ende:T", title="Ende", format="%d.%m.")]
        info_frist = [alt.Tooltip("name:N", title="Name"),
                      alt.Tooltip("frist:T", title="Spritzen bis", format="%d.%m.")]

        # Balken vom Infektionstag bis zum Ende der Inkubation
        balken = alt.Chart(laufend).mark_bar(height=18, cornerRadius=4, clip=True).encode(
            x=achse, x2="ende:T", y=zeile,
            color=alt.Color("art:N", scale=farben, title=None, legend=alt.Legend(orient="bottom")),
            tooltip=info_balken)
        # Goldener Strich bei der Frist, Beschriftung rechts daneben
        striche = alt.Chart(laufend).mark_tick(color=GOLD, thickness=3, size=24, clip=True).encode(
            x="frist:T", y=zeile, tooltip=info_frist)
        # Auf dem dunkelroten Balken weisse Schrift, sonst dunkle Schrift (besser lesbar)
        texte = alt.Chart(laufend).mark_text(align="left", dx=6, fontWeight="bold", clip=True).encode(
            x="frist:T", y=zeile, text="frist_text:N",
            color=alt.condition(alt.datum.art == "offen", alt.value("white"), alt.value("#5C4A12")),
            tooltip=info_frist)

        diagramm = (balken + striche + texte).properties(height=40 * len(laufend) + 20)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Balken: vom Infektionstag bis zum Ende der Inkubation. "
                   "Goldener Strich: bis dann muss gespritzt sein.")

# Erklärung des Modells (aufklappbar)
with st.expander("Wie erkennt der Kalender Infektionen? (Machine Learning)"):
    st.markdown(
        "Ein **Random Forest** (300 Entscheidungsbäume) hat aus den Agrometeo-Daten "
        "**2019 bis 2025** (7 Jahre) gelernt, bei welchem Wetter es eine Infektion gibt: "
        "Temperatur (min, Mittel, max), Regen am Tag und am Vortag sowie die Jahreszeit. "
        "Jetzt schaut er sich das Wetter von Open-Meteo an und sagt für jeden Tag, "
        "ob es eine Infektion gibt: ja oder nein. Gewarnt wird nur in der Spritzsaison "
        "(April bis August)."
    )
    st.markdown(f"**Test mit der Saison {TESTJAHR}** (Tage, die das Modell beim Lernen nie gesehen hat):")
    k1, k2, k3 = st.columns(3)
    k1.metric("Infektionen erkannt", f"{ergebnis['erkannt']} von {ergebnis['total']}")
    k2.metric("Verpasst", ergebnis["verpasst"])
    k3.metric("Fehlalarme", ergebnis["fehlalarme"])
    st.caption("Eine verpasste Infektion ist gefährlicher als ein Fehlalarm. "
               "Das Modell lernt mit den Messungen der Station, bekommt im Kalender aber "
               "das Wetter von Open-Meteo. Diese Werte weichen leicht voneinander ab.")

# Fusszeile
st.divider()
st.caption("Datenquellen: Wetter von Open-Meteo, Lerndaten für das Modell von Agrometeo (Station Zizers). "
           "Die App ist eine Entscheidungshilfe und keine offizielle Pflanzenschutzberatung.")