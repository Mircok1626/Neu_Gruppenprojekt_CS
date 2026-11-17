#Hier wird die Seite Kalender codiert.
"""Kalender: Wann kann ich spritzen?

Die Seite verbindet die Frist jeder Infektion (Agrometeo-Daten) mit der
Wetterprognose (Open-Meteo API) und zeigt für 14 Tage eine Ampel mit Startzeit.

Hinweis zur KI: Dieser Code wurde mit Hilfe von Claude (Anthropic, Modell
Claude Opus 5.5, 17.11.2026) erstellt und von uns geprüft und angepasst.
"""

import datetime as dt

import pandas as pd
import requests
import streamlit as st

# Mittel und ob sie hitzeempfindlich sind (nur dann zählt Hitze in der Ampel)
MITTEL = {"Folpet 80 WG": False, "Kupfer": False, "Schwefel": True}
EINHEITEN = {"Regen": "mm", "Wind": "km/h", "Hitze": "°C"}
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
FARBEN = ["#C8E6C9", "#FFF59D", "#FFCDD2"]  # grün = geeignet, gelb = knapp, rot = nicht möglich


@st.cache_data
def lade_infektionen(jahr):
    """Liest die Agrometeo-Daten und gibt jede Infektion mit Inkubationsende und Frist zurück."""
    daten = pd.read_csv(f"daten/zizers_{jahr}.csv", parse_dates=["datum"])
    daten = daten[daten["infektion_staerke"] > 0]

    infektionen = []
    for _, zeile in daten.iterrows():
        start = zeile["datum"].date()
        if pd.isna(zeile["inkubation_aktuell"]):
            ende = start + dt.timedelta(days=10)  # Annahme, wenn Agrometeo noch kein Ende angibt
        else:
            tag, monat = zeile["inkubation_aktuell"].split(".")[:2]  # z. B. "20.05."
            ende = dt.date(jahr, int(monat), int(tag))
        dauer = (ende - start).days
        infektionen.append({
            "start": start,
            "ende": ende,
            "frist": start + dt.timedelta(days=int(dauer * 0.8)),  # spritzen bis = 80 % der Inkubation
            "stufe": "!" * int(zeile["infektion_staerke"]),
            "prognose": zeile["aus_wettervorhersage"] == 1,
        })
    return infektionen


@st.cache_data
def lade_wetter(von, bis):
    """Lädt das stündliche Wetter für Zizers von Open-Meteo."""
    if bis < dt.date.today():
        url = "https://historical-forecast-api.open-meteo.com/v1/forecast"  # vergangene Tage
    else:
        url = "https://api.open-meteo.com/v1/forecast"  # aktuelle Prognose
    parameter = {"latitude": 46.94, "longitude": 9.56, "timezone": "Europe/Zurich",
                 "hourly": "precipitation,wind_speed_10m,temperature_2m",
                 "start_date": str(von), "end_date": str(bis)}
    wetter = pd.DataFrame(requests.get(url, params=parameter, timeout=10).json()["hourly"])
    wetter["datum"] = pd.to_datetime(wetter["time"]).dt.date
    return wetter


def bewerte_tag(stunden, tag, grenzen, sonntag_sperren, hitze_zaehlt):
    """Gibt für einen Tag die Ampelstufe (0, 1, 2), die beste Startzeit und die Gründe zurück."""
    regen = stunden["precipitation"].tolist()
    wind = stunden["wind_speed_10m"].tolist()
    temp = stunden["temperature_2m"].tolist()

    # Beste Startzeit: Stunde zwischen 6 und 14 Uhr mit am wenigsten Regen in den 6 Stunden danach
    start = 6
    for stunde in range(7, 15):
        if sum(regen[stunde:stunde + 6]) < sum(regen[start:start + 6]):
            start = stunde

    werte = {"Regen": sum(regen[start:start + 6]), "Wind": max(wind[start:start + 6])}
    if hitze_zaehlt:
        werte["Hitze"] = max(temp[start:start + 6])

    # Der schlechteste Wert bestimmt die Farbe
    stufe = 0
    gruende = []
    for name, wert in werte.items():
        gelb, rot = grenzen[name]
        if wert >= gelb:
            stufe = max(stufe, 2 if wert >= rot else 1)
            gruende.append(f"{name} {wert:.1f} {EINHEITEN[name]}")
    if sonntag_sperren and tag.weekday() == 6:
        stufe = 2
        gruende.append("Sonntag")
    return stufe, start, gruende


st.title("Kalender: Wann kann ich spritzen?")

# Planungsleiste
spalte1, spalte2, spalte3 = st.columns(3)
heute = spalte1.date_input("Heute ist der …", value=dt.date(2026, 5, 9), format="DD.MM.YYYY",
                           min_value=dt.date(2024, 1, 1), max_value=dt.date.today())
mittel = spalte2.selectbox("Geplantes Mittel", list(MITTEL))
sonntag_sperren = spalte3.checkbox("Sonntag sperren", value=True)

with st.expander("Grenzwerte der Ampel (gelb ab, rot ab)"):
    grenzen = {"Regen": st.slider("Regen in den 6 Stunden nach Start (mm)", 0.0, 10.0, (0.5, 2.0)),
               "Wind": st.slider("Wind (km/h)", 0, 50, (15, 25)),
               "Hitze": st.slider("Hitze (°C)", 15, 40, (25, 30))}

# Daten laden
tage = [heute + dt.timedelta(days=i) for i in range(14)]
infektionen = lade_infektionen(heute.year)
try:
    wetter = lade_wetter(tage[0], tage[-1])
except Exception:
    st.error("Die Wetterdaten von Open-Meteo konnten nicht geladen werden.")
    st.stop()

# Infektionen, die in diesen 14 Tagen in der Inkubation sind, und die nächste offene Frist
laufend = [i for i in infektionen if i["start"] <= tage[-1] and i["ende"] >= heute]
offen = [i for i in laufend if i["start"] <= heute <= i["frist"]]
frist = min([i["frist"] for i in offen]) if offen else None

# Jeden Tag bewerten und die grünen Tage vor der Frist suchen
bewertung = {}
for tag in tage:
    bewertung[tag] = bewerte_tag(wetter[wetter["datum"] == tag], tag, grenzen,
                                 sonntag_sperren, MITTEL[mittel])
gruene = [t for t in tage if frist and t <= frist and bewertung[t][0] == 0]

# Frist-Box
if frist is None:
    st.success("Keine offene Infektion. Im Moment muss nicht gespritzt werden.")
elif gruene:
    st.error(f"**Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}**. "
             f"Davor gibt es noch {len(gruene)} gute Tage. Empfohlen: "
             f"**{WOCHENTAGE[gruene[0].weekday()]}, {gruene[0]:%d.%m.} ab {bewertung[gruene[0]][1]} Uhr**.")
else:
    st.error(f"**Spritzen bis {frist:%d.%m.}**. Vor der Frist gibt es keinen grünen Tag, prüfe die gelben Tage.")

# Spritzfenster: 14 Kacheln in zwei Reihen
st.subheader("Spritzfenster: 14 Tage")
for woche in [tage[:7], tage[7:]]:
    for spalte, tag in zip(st.columns(7), woche):
        stufe, start, gruende = bewertung[tag]
        empfohlen = gruene and tag == gruene[0]

        marken = []
        if tag == heute:
            marken.append("heute")
        if empfohlen:
            marken.append("⭐ empfohlen")
        elif gruene and tag == gruene[-1]:
            marken.append("letzte Chance")
        if tag == frist:
            marken.append("Frist")
        elif frist and tag > frist:
            marken.append("nach Frist")

        farbe = "#E0E0E0" if frist and tag > frist else FARBEN[stufe]
        rahmen = "3px solid #C9A227" if empfohlen else "1px solid #BBBBBB"
        startzeit = f"ab {start} Uhr" if stufe < 2 else "nicht möglich"
        text = ", ".join(gruende)
        markierung = "<br>".join(marken)
        spalte.markdown(f"""
        <div style="background-color: {farbe}; border: {rahmen}; border-radius: 10px;
                    padding: 8px; height: 160px; color: black; font-size: 14px;">
            <b>{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}</b><br>{startzeit}<br>
            <small>{text}</small><br><b><small>{markierung}</small></b>
        </div>""", unsafe_allow_html=True)
st.caption("Grün = geeignet, gelb = knapp, rot = nicht möglich, grau = nach Frist. "
           "Goldener Rahmen = empfohlener Tag (erster grüner Tag vor der Frist).")

# Laufende Inkubationen: ein Balken pro Infektion, die 14 Tage als Spalten
st.subheader("Laufende Inkubationen")
if laufend:
    zeilen = {}
    for i in laufend:
        balken = "░░░░" if i["prognose"] or i["start"] > heute else "████"
        zeile = []
        for tag in tage:
            if tag == i["frist"]:
                zeile.append("🟡")
            elif i["start"] <= tag <= i["ende"]:
                zeile.append(balken)
            else:
                zeile.append("")
        zeilen[f"Infektion {i['start']:%d.%m.} {i['stufe']}"] = zeile
    st.dataframe(pd.DataFrame.from_dict(zeilen, orient="index", columns=[f"{t:%d.%m.}" for t in tage]))
    st.caption("████ berechnete Infektion, ░░░░ Infektion aus der Prognose (unsicher), "
               "🟡 spritzen bis (80 % der Inkubation)")
else:
    st.info("In diesen 14 Tagen läuft keine Inkubation.")

st.divider()
st.caption("Datenquellen: Wetter stündlich von Open-Meteo, Infektionen von Agrometeo (Station Zizers). "
           "Die App ist eine Entscheidungshilfe und keine offizielle Pflanzenschutzberatung.")
