# Hier wird die Seite Kalender codiert.
"""Kalender: Wann kann ich spritzen?

Die Seite erkennt Infektionen mit einem eigenen Machine-Learning-Modell:
Das Modell hat aus den Agrometeo-Daten 2024 und 2025 gelernt, bei welchem
Wetter es eine Infektion gibt. Danach schaut es sich das Wetter von Open-Meteo
an (die letzten 14 Tage und die Prognose) und sagt, an welchen Tagen es eine
Infektion gibt. Zusammen mit dem stündlichen Wetter zeigt die Seite für
14 Tage eine Ampel, wann man spritzen kann.

KI-Hinweis: Dieser Code wurde mit Claude (Anthropic, Claude Opus 5.5) am
17.11.2026 generiert und danach von uns geprüft und angepasst.
"""

import datetime as dt

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

# Mittel: True heisst hitzeempfindlich, nur dann zählt Hitze in der Ampel (Platzhalter)
MITTEL = {"Folpet 80 WG": False, "Kupfer": False, "Schwefel": True}

# Startwerte der Ampel: (gelb ab, rot ab, Einheit), noch mit dem Winzer bestätigen
STANDARD = {"Regen": (0.5, 2.0, "mm"), "Wind": (15.0, 25.0, "km/h"), "Hitze": (25.0, 30.0, "°C")}

# Wettermerkmale, aus denen das Modell lernt. Diese Werte gibt es sowohl in den
# Agrometeo-Daten (Vergangenheit) als auch bei Open-Meteo (Prognose).
MERKMALE = ["temp_min", "temp_mittel", "temp_max", "niederschlag_mm", "regen_vortag", "tag_im_jahr"]

# Ab diesem Risiko zählt ein Tag als Infektion. Bewusst tief (30 % statt 50 %):
# Eine verpasste Infektion kostet Ernte, ein Fehlalarm nur einen Kontrollgang.
WARNSCHWELLE = 0.3

# Spritzsaison gegen Falschen Mehltau: ab Austrieb bis zum Weichwerden der Trauben.
# Ausserhalb der Saison wird nicht gespritzt, also warnt der Kalender auch nicht.
# PLATZHALTER: Das Saisonende (Weichwerden) noch mit dem Winzer bestätigen.
SAISON_START = (4, 1)    # 1. April
SAISON_ENDE = (8, 31)    # 31. August


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
    """Trainiert das Modell mit 2024 und 2025 und prüft es mit 2026.

    Rückgabe: das Modell, die Inkubationsdauer pro Monat und die Ergebnisse des Tests.
    """
    lernen = pd.concat([lade_agrometeo(2024), lade_agrometeo(2025)])

    # Random Forest: 300 Entscheidungsbäume, die gemeinsam abstimmen.
    # class_weight="balanced": Infektionstage sind seltener, zählen darum stärker.
    modell = RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                    class_weight="balanced", random_state=0)
    modell.fit(lernen[MERKMALE], lernen["infektion"])

    # Wie lange dauert die Inkubation im Schnitt? Je Monat aus den Lerndaten.
    infektionen = lernen[(lernen["infektion"] == 1) & lernen["dauer"].notna()]
    dauer_pro_monat = infektionen.groupby(infektionen["datum"].dt.month)["dauer"].mean().round().to_dict()

    # Test mit 2026: Tage, die das Modell beim Lernen nie gesehen hat
    test = lade_agrometeo(2026)
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
        return pd.DataFrame(columns=["start", "ende", "frist", "stufe"])
    # Wahrscheinlichkeit für eine Infektion (0 bis 1). Ab der Warnschwelle zählt es als Infektion.
    df["risiko"] = modell.predict_proba(df[MERKMALE])[:, 1]
    df = df[df["risiko"] >= WARNSCHWELLE].copy()

    df["start"] = df["datum"]
    # Inkubationsdauer aus dem gelernten Durchschnitt des Monats (falls unbekannt: 10 Tage)
    dauer = df["datum"].dt.month.map(dauer_pro_monat).fillna(10)
    df["ende"] = df["start"] + pd.to_timedelta(dauer, unit="D")
    # Formel 3: spritzen bis = Infektionsdatum + 80 % der Inkubationsdauer
    df["frist"] = (df["start"] + (df["ende"] - df["start"]) * 0.8).dt.floor("D")
    df["stufe"] = (df["risiko"] * 100).round().astype(int).astype(str) + " %"
    return df


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
                 "hourly": "precipitation,wind_speed_10m,temperature_2m",
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
def bewerte_tag(tag, wetter, hitze_zaehlt, sonntag_sperren):
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
             "Wind": fenster["wind_speed_10m"].max(),
             "Hitze": fenster["temperature_2m"].max()}

    stufe, gruende = 0, []
    for name, wert in werte.items():
        if name == "Hitze" and not hitze_zaehlt:
            continue
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
spalte1, spalte2, spalte3 = st.columns(3)
heute = spalte1.date_input("Heute ist der", value=dt.date.today(), min_value=dt.date(2024, 1, 1),
                           max_value=dt.date.today(), format="DD.MM.YYYY", key="heute")
mittel = spalte2.selectbox("Geplantes Mittel", list(MITTEL.keys()))
spalte3.write("")
sonntag_sperren = spalte3.checkbox("Sonntag sperren", value=True)

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

# Laufende Inkubationen: Balken, die in die 14 Tage hineinreichen
laufend = infektionen[(infektionen["start"] <= tage[-1]) & (infektionen["ende"] >= tage[0])].copy()
# Offene Infektionen: schon passiert und Frist noch nicht vorbei
offen = laufend[(laufend["start"] <= tage[0]) & (laufend["frist"] >= tage[0])]

# Jeden Tag bewerten
bewertung = [bewerte_tag(tag, wetter, MITTEL[mittel], sonntag_sperren) for tag in tage]

with bereich_ampel:
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
        st.markdown(f"""
        <div style="background-color: {WEINROT}; color: white; padding: 20px; border-radius: 15px;">
            <p style="margin: 0; color: #F3D9DF;">Infektion am {infektion['start']:%d.%m.} (Risiko {infektion['stufe']})</p>
            <h3 style="margin: 0; color: white;">Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h3>
            <p style="margin: 0;">Noch {len(gute)} gute Tage vor der Frist. {empfehlung}</p>
        </div>""", unsafe_allow_html=True)
    else:
        frist, gute = None, []
        if in_saison(pd.Series([pd.Timestamp(heute)])).iloc[0]:
            st.info("Keine offene Infektion. Spritzen ist im Moment nicht nötig.")
        else:
            st.info("Ausserhalb der Spritzsaison (April bis August). "
                    "Gegen Falschen Mehltau wird jetzt nicht gespritzt.")

    # Spritzfenster: 14 Kacheln in 2 Reihen
    st.subheader("Spritzfenster: 14 Tage")
    spalten = st.columns(7) + st.columns(7)
    for spalte, tag, (stufe, start, gruende) in zip(spalten, tage, bewertung):
        marken = []
        if tag == tage[0]:
            marken.append("heute")
        if len(gute) > 0 and tag == gute[-1] and tag != gute[0]:
            marken.append("letzte Chance")
        if tag == frist:
            marken.append("Frist")

        if frist is not None and tag > frist:
            farbe, text = "#EEEEEE", "nach Frist"
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
    st.caption("Goldener Rahmen: empfohlener Tag (erster grüner Tag vor der Frist).")

with bereich_inkubation:
    st.subheader("Laufende Inkubationen")
    if len(laufend) == 0:
        st.write("Keine laufenden Inkubationen in diesen 14 Tagen.")
    else:
        laufend["name"] = laufend["start"].dt.strftime("%d.%m.") + " (" + laufend["stufe"] + ")"
        laufend["art"] = "berechnet"
        laufend.loc[laufend["start"] > tage[0], "art"] = "Prognose"
        achse = alt.X("start:T", title=None, scale=alt.Scale(domain=[tage[0], tage[-1] + pd.Timedelta(days=1)]),
                      axis=alt.Axis(format="%d.%m.", tickCount=14))
        zeile = alt.Y("name:N", title="Infektion", sort=alt.SortField("start"))  # nach Datum sortiert
        laufend["frist_text"] = "spritzen bis " + laufend["frist"].dt.strftime("%d.%m.")
        balken = alt.Chart(laufend).mark_bar(color=WEINROT, stroke=WEINROT, clip=True, height=20).encode(
            x=achse, x2="ende:T", y=zeile,
            opacity=alt.Opacity("art:N", title=None, scale=alt.Scale(domain=["berechnet", "Prognose"], range=[0.9, 0.2])),
            strokeDash=alt.StrokeDash("art:N", title=None, scale=alt.Scale(domain=["berechnet", "Prognose"], range=[[1, 0], [5, 3]])))
        striche = alt.Chart(laufend).mark_tick(color=GOLD, thickness=4, size=20, clip=True).encode(
            x="frist:T", y=zeile)
        # Beschriftung über dem goldenen Strich, damit man sofort sieht, dass er die Frist ist
        texte = alt.Chart(laufend).mark_text(dy=-17, color="#8A6D1F", fontWeight="bold", clip=True).encode(
            x="frist:T", y=zeile, text="frist_text:N")
        st.altair_chart((balken + striche + texte).properties(height=50 * len(laufend)))
        st.caption("Balken: vom Infektionstag bis zum Ende der Inkubation. "
                   "Voller Balken: schon passiert, heller gestrichelter Balken: Prognose. "
                   "In Klammern: wie sicher sich das Modell ist.")

# Erklärung des Modells (aufklappbar)
with st.expander("Wie erkennt der Kalender Infektionen? (Machine Learning)"):
    st.markdown(
        "Ein **Random Forest** (300 Entscheidungsbäume) hat aus den Agrometeo-Daten "
        "**2024 und 2025** gelernt, bei welchem Wetter es eine Infektion gibt: "
        "Temperatur (min, Mittel, max), Regen am Tag und am Vortag sowie die Jahreszeit. "
        "Jetzt schaut er sich das Wetter von Open-Meteo an und sagt für jeden Tag, "
        "ob es eine Infektion gibt. Ab einem Risiko von 30 % warnt der Kalender, "
        "aber nur in der Spritzsaison (April bis August)."
    )
    st.markdown("**Test mit der Saison 2026** (Tage, die das Modell beim Lernen nie gesehen hat):")
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