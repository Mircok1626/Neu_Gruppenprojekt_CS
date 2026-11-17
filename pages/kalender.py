# Hier wird die Seite Kalender codiert.
"""Kalender: Wann kann ich spritzen?

Die Seite verbindet die Frist der Infektionen (Agrometeo, CSV im Ordner daten)
mit dem stündlichen Wetter von Open-Meteo und zeigt für 14 Tage eine Ampel.

KI-Hinweis: Dieser Code wurde mit Claude (Anthropic, Claude Opus 5.5) am
17.11.2026 generiert und danach von uns geprüft und angepasst.
"""

import datetime as dt

import altair as alt
import pandas as pd
import requests
import streamlit as st

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


@st.cache_data
def lade_infektionen(jahr):
    """Liest die Agrometeo-Tabelle und gibt alle Infektionen mit Frist zurück."""
    df = pd.read_csv(f"daten/zizers_{jahr}.csv")
    df = df[(df["infektion_staerke"] > 0) & df["inkubation_aktuell"].notna()].copy()
    df["start"] = pd.to_datetime(df["datum"])
    # Ende der Inkubation steht als "20.05." in der Tabelle, darum hängen wir das Jahr an
    df["ende"] = pd.to_datetime(df["inkubation_aktuell"] + str(jahr), format="%d.%m.%Y")
    # Formel 3: spritzen bis = Infektionsdatum + 80 % der Inkubationsdauer
    df["frist"] = (df["start"] + (df["ende"] - df["start"]) * 0.8).dt.floor("D")
    df["stufe"] = df["infektion_staerke"].map({1: "!", 2: "!!", 3: "!!!"})
    return df


@st.cache_data
def lade_wetter(von, bis):
    """Lädt das stündliche Wetter (Regen, Wind, Temperatur) für Zizers von Open-Meteo."""
    if bis < dt.date.today():
        url = "https://historical-forecast-api.open-meteo.com/v1/forecast"  # Vergangenheit
    else:
        url = "https://api.open-meteo.com/v1/forecast"  # Prognose
    parameter = {"latitude": 46.94, "longitude": 9.56, "timezone": "Europe/Zurich",
                 "hourly": "precipitation,wind_speed_10m,temperature_2m",
                 "start_date": str(von), "end_date": str(bis)}
    daten = requests.get(url, params=parameter, timeout=10).json()["hourly"]
    wetter = pd.DataFrame(daten)
    wetter["time"] = pd.to_datetime(wetter["time"])
    return wetter


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

# Daten laden
tage = pd.date_range(heute, periods=14)
infektionen = lade_infektionen(heute.year)
try:
    wetter = lade_wetter(heute, tage[-1].date())
except Exception:
    st.error("Das Wetter von Open-Meteo konnte nicht geladen werden.")
    st.stop()

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
            <p style="margin: 0; color: #F3D9DF;">Infektion {infektion['stufe']} am {infektion['start']:%d.%m.}</p>
            <h3 style="margin: 0; color: white;">Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h3>
            <p style="margin: 0;">Noch {len(gute)} gute Tage vor der Frist. {empfehlung}</p>
        </div>""", unsafe_allow_html=True)
    else:
        frist, gute = None, []
        st.info("Keine offene Infektion. Spritzen ist im Moment nicht nötig.")

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
        laufend["name"] = laufend["stufe"] + " am " + laufend["start"].dt.strftime("%d.%m.")
        laufend["art"] = "berechnet"
        laufend.loc[laufend["start"] > tage[0], "art"] = "Prognose"
        achse = alt.X("start:T", title=None, scale=alt.Scale(domain=[tage[0], tage[-1] + pd.Timedelta(days=1)]),
                      axis=alt.Axis(format="%d.%m.", tickCount=14))
        balken = alt.Chart(laufend).mark_bar(color=WEINROT, stroke=WEINROT, clip=True, height=20).encode(
            x=achse, x2="ende:T", y=alt.Y("name:N", title="Infektion"),
            opacity=alt.Opacity("art:N", title=None, scale=alt.Scale(domain=["berechnet", "Prognose"], range=[0.9, 0.2])),
            strokeDash=alt.StrokeDash("art:N", title=None, scale=alt.Scale(domain=["berechnet", "Prognose"], range=[[1, 0], [5, 3]])))
        striche = alt.Chart(laufend).mark_tick(color=GOLD, thickness=4, size=20, clip=True).encode(
            x="frist:T", y="name:N")
        st.altair_chart(balken + striche)
        st.caption("Balken: vom Infektionstag bis zum Ende der Inkubation. Goldener Strich: spritzen bis "
                   "(80 % der Inkubation). Voller Balken: berechnet, heller gestrichelter Balken: Prognose.")

# Fusszeile
st.divider()
st.caption("Datenquellen: Wetter stündlich von Open-Meteo, Infektionen von Agrometeo (Station Zizers). "
           "Die App ist eine Entscheidungshilfe und keine offizielle Pflanzenschutzberatung.")
