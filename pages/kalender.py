#hier kommt der Code für den Kalender hinein
import streamlit as st
st.title("Kalender")

# Hier wird die Seite "Kalender" codiert.
"""Kalender-Seite des Spritzplaners: Wann kann ich spritzen?

Die Seite verbindet die Frist einer Infektion mit der Wetterprognose
(Open-Meteo API) und zeigt fuer die naechsten 14 Tage eine Ampel:
gruen = geeignet, gelb = knapp, rot = nicht moeglich.

KI-Hinweis: Der Grundaufbau dieses Codes wurde mit Claude (Anthropic,
Modell Claude Opus 5.5, 17.11.2026) generiert und danach von uns angepasst.
"""

import datetime as dt

import pandas as pd
import requests
import streamlit as st


# ---------------------------------------------------------------------------
# Feste Werte (Konstanten)
# ---------------------------------------------------------------------------

# Koordinaten der Agrometeo-Station Zizers (Buendner Herrschaft)
BREITE = 46.94
LAENGE = 9.56

# Moegliche Mittel. True = hitzeempfindlich (nur dann zaehlt Hitze in der Ampel)
MITTEL = {
    "Kupfer": False,
    "Folpet": False,
    "Schwefel (hitzeempfindlich)": True,
}

# Startwerte fuer die Grenzwerte der Ampel (noch mit dem Winzer bestaetigen)
STANDARD_GRENZEN = {
    "regen_gelb": 0.5,   # mm Regen in den 6 Stunden nach dem Start
    "regen_rot": 2.0,
    "wind_gelb": 15,     # km/h, staerkste Windgeschwindigkeit
    "wind_rot": 25,
    "hitze_gelb": 25,    # Grad Celsius, hoechste Temperatur
    "hitze_rot": 30,
}

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
AMPEL = ["🟢 geeignet", "🟡 knapp", "🔴 nicht möglich"]


# ---------------------------------------------------------------------------
# Funktionen
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)  # Wetter hoechstens einmal pro Stunde neu laden
def lade_wetter():
    """Laedt die stuendliche Wetterprognose fuer 14 Tage von Open-Meteo.

    Gibt eine Tabelle (DataFrame) mit einer Zeile pro Stunde zurueck.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    parameter = {
        "latitude": BREITE,
        "longitude": LAENGE,
        "hourly": "temperature_2m,precipitation,wind_speed_10m",
        "forecast_days": 14,
        "timezone": "Europe/Zurich",
    }
    antwort = requests.get(url, params=parameter, timeout=10)
    antwort.raise_for_status()  # Fehler, falls die API nicht antwortet

    wetter = pd.DataFrame(antwort.json()["hourly"])
    wetter["time"] = pd.to_datetime(wetter["time"])
    wetter["datum"] = wetter["time"].dt.date
    wetter["stunde"] = wetter["time"].dt.hour
    return wetter


def stufe(wert, gelb, rot):
    """Uebersetzt einen Messwert in eine Ampelstufe: 0 = gruen, 1 = gelb, 2 = rot."""
    if wert >= rot:
        return 2
    elif wert >= gelb:
        return 1
    else:
        return 0


def beste_startzeit(tag):
    """Sucht die beste Startzeit zwischen 6 und 14 Uhr.

    Das ist die Stunde, nach der in den 6 Stunden danach am wenigsten
    Regen faellt, damit der Belag antrocknen kann.
    Gibt die Stunde und die Wetterdaten dieser 6 Stunden zurueck.
    """
    beste_stunde = 6
    wenigster_regen = 9999

    for stunde in range(6, 15):
        fenster = tag[(tag["stunde"] >= stunde) & (tag["stunde"] < stunde + 6)]
        regen = fenster["precipitation"].sum()
        if regen < wenigster_regen:
            wenigster_regen = regen
            beste_stunde = stunde

    bestes_fenster = tag[(tag["stunde"] >= beste_stunde) & (tag["stunde"] < beste_stunde + 6)]
    return beste_stunde, bestes_fenster


def bewerte_tag(datum, tag, grenzen, sonntag_sperren, hitze_zaehlt):
    """Bewertet einen Tag mit der Ampel.

    Der schlechteste Wert (Regen, Wind, Hitze, Sonntag) bestimmt die Farbe.
    Gibt ein Dictionary mit Datum, Stufe, Startzeit und Gruenden zurueck.
    """
    startzeit, fenster = beste_startzeit(tag)
    regen = fenster["precipitation"].sum()
    wind = fenster["wind_speed_10m"].max()
    hitze = fenster["temperature_2m"].max()

    stufen = []
    gruende = []

    # Regen
    s = stufe(regen, grenzen["regen_gelb"], grenzen["regen_rot"])
    stufen.append(s)
    if s > 0:
        gruende.append(f"Regen {regen:.1f} mm")

    # Wind
    s = stufe(wind, grenzen["wind_gelb"], grenzen["wind_rot"])
    stufen.append(s)
    if s > 0:
        gruende.append(f"Wind {wind:.0f} km/h")

    # Hitze (zaehlt nur bei hitzeempfindlichem Mittel)
    if hitze_zaehlt:
        s = stufe(hitze, grenzen["hitze_gelb"], grenzen["hitze_rot"])
        stufen.append(s)
        if s > 0:
            gruende.append(f"Hitze {hitze:.0f} °C")

    # Sonntag (weekday() == 6 bedeutet Sonntag)
    if sonntag_sperren and datum.weekday() == 6:
        stufen.append(2)
        gruende.append("Sonntag")

    if len(gruende) == 0:
        gruende.append("trocken, ruhig")

    return {
        "datum": datum,
        "stufe": max(stufen),  # der schlechteste Wert bestimmt die Farbe
        "start": startzeit,
        "gruende": gruende,
    }


# ---------------------------------------------------------------------------
# Seite aufbauen
# ---------------------------------------------------------------------------

st.title("Kalender – wann kann ich spritzen?")
st.write("Die Ampel verbindet die Frist der Infektion mit der Wetterprognose "
         "und zeigt den besten Tag vor Ablauf der Frist.")

heute = dt.date.today()

# --- Planungsleiste --------------------------------------------------------
st.subheader("Planung")
spalte1, spalte2, spalte3 = st.columns(3)

with spalte1:
    mittel = st.selectbox("Geplantes Mittel", list(MITTEL.keys()))
with spalte2:
    frist = st.date_input("Spritzen bis (Frist)",
                          value=heute + dt.timedelta(days=7),
                          format="DD.MM.YYYY")
with spalte3:
    st.write("")  # kleiner Abstand, damit das Haekchen auf gleicher Hoehe ist
    sonntag_sperren = st.checkbox("Sonntag sperren", value=True)

hitze_zaehlt = MITTEL[mittel]
if hitze_zaehlt:
    st.warning(f"{mittel} kann bei Hitze die Blätter verbrennen. Hitze zählt deshalb in der Ampel.")

# --- Grenzwerte der Ampel (aufklappbar) ------------------------------------
with st.expander("Grenzwerte der Ampel anpassen"):
    g1, g2, g3 = st.columns(3)
    grenzen = {}
    with g1:
        grenzen["regen_gelb"] = st.number_input("Regen gelb ab (mm)", value=STANDARD_GRENZEN["regen_gelb"], step=0.5)
        grenzen["regen_rot"] = st.number_input("Regen rot ab (mm)", value=STANDARD_GRENZEN["regen_rot"], step=0.5)
    with g2:
        grenzen["wind_gelb"] = st.number_input("Wind gelb ab (km/h)", value=STANDARD_GRENZEN["wind_gelb"], step=1)
        grenzen["wind_rot"] = st.number_input("Wind rot ab (km/h)", value=STANDARD_GRENZEN["wind_rot"], step=1)
    with g3:
        grenzen["hitze_gelb"] = st.number_input("Hitze gelb ab (°C)", value=STANDARD_GRENZEN["hitze_gelb"], step=1)
        grenzen["hitze_rot"] = st.number_input("Hitze rot ab (°C)", value=STANDARD_GRENZEN["hitze_rot"], step=1)

# --- Wetter laden ----------------------------------------------------------
try:
    wetter = lade_wetter()
except Exception:
    st.error("Die Wetterdaten von Open-Meteo konnten nicht geladen werden. Bitte später nochmals versuchen.")
    st.stop()  # Rest der Seite nicht ausfuehren

# --- Jeden Tag bewerten ----------------------------------------------------
tage = []
for datum in sorted(wetter["datum"].unique()):
    tag = wetter[wetter["datum"] == datum]
    tage.append(bewerte_tag(datum, tag, grenzen, sonntag_sperren, hitze_zaehlt))

# Gruene Tage vor (oder an) der Frist suchen
gute_tage = [t for t in tage if t["stufe"] == 0 and heute <= t["datum"] <= frist]

empfohlen = None
letzte_chance = None
if len(gute_tage) > 0:
    empfohlen = gute_tage[0]["datum"]       # erster gruener Tag vor der Frist
    letzte_chance = gute_tage[-1]["datum"]  # letzter gruener Tag vor der Frist

# --- Frist-Box -------------------------------------------------------------
if frist < heute:
    st.error(f"Die Frist ({frist:%d.%m.}) ist bereits abgelaufen.")
elif empfohlen is not None:
    start = gute_tage[0]["start"]
    st.success(
        f"**Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}** – "
        f"noch {len(gute_tage)} gute Tage. "
        f"Empfohlen: **{WOCHENTAGE[empfohlen.weekday()]}, {empfohlen:%d.%m.} ab {start} Uhr**."
    )
else:
    st.error(f"Spritzen bis {frist:%d.%m.}: Vor der Frist gibt es keinen grünen Tag. "
             "Prüfe die gelben Tage.")

# --- Spritzfenster: 14 Kacheln (2 Reihen mit je 7 Tagen) -------------------
st.subheader("Spritzfenster – 14 Tage")

for reihe in range(2):
    spalten = st.columns(7)
    for i in range(7):
        index = reihe * 7 + i
        if index >= len(tage):
            break
        tag = tage[index]
        datum = tag["datum"]

        with spalten[i]:
            with st.container(border=True):
                st.markdown(f"**{WOCHENTAGE[datum.weekday()]} {datum:%d.%m.}**")

                if datum > frist:
                    st.write("⚪ nach Frist")
                else:
                    st.write(AMPEL[tag["stufe"]])
                    if tag["stufe"] < 2:
                        st.caption(f"ab {tag['start']} Uhr")

                st.caption(", ".join(tag["gruende"]))

                # Markierungen
                if datum == heute:
                    st.caption("📍 heute")
                if datum == empfohlen:
                    st.caption("⭐ empfohlen")
                elif datum == letzte_chance:
                    st.caption("⏳ letzte Chance")
                if datum == frist:
                    st.caption("🏁 Frist")

# --- Grafik: Wetter der naechsten 14 Tage ----------------------------------
st.subheader("Wetterprognose – 14 Tage")
pro_tag = wetter.groupby("datum").agg(
    regen_mm=("precipitation", "sum"),
    max_wind_kmh=("wind_speed_10m", "max"),
    max_temp_c=("temperature_2m", "max"),
)
pro_tag.index = [f"{d:%d.%m.}" for d in pro_tag.index]

grafik1, grafik2 = st.columns(2)
with grafik1:
    st.caption("Regen pro Tag (mm)")
    st.bar_chart(pro_tag["regen_mm"])
with grafik2:
    st.caption("Höchsttemperatur (°C) und stärkster Wind (km/h)")
    st.line_chart(pro_tag[["max_temp_c", "max_wind_kmh"]])

# --- Fusszeile -------------------------------------------------------------
st.divider()
st.caption("Datenquellen: Wetter stündlich von Open-Meteo, Infektionen von Agrometeo. "
           "Die App ist eine Entscheidungshilfe und keine offizielle Pflanzenschutzberatung.")