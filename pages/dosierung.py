#Hier wird die Seite Dosierung codiert.
"""Dosierung: Rechnet aus Rebstadium, Mittel und Fläche ein Tankrezept aus.

Die Fläche kann aus den gespeicherten Parzellen (Seite Parzelle) übernommen
oder als Notfall von Hand eingegeben werden.
Quelle der Zahlen: Agroscope Transfer Nr. 626, Pflanzenschutzmittelliste
für den Rebbau 2026, Mittel gegen Falschen Mehltau.
"""

import datetime
import math
import sqlite3
import pandas as pd
import requests
import streamlit as st

# Rebstadien und ihre Basisbrühmenge in Liter pro Hektare.
# Je mehr Blätter die Rebe hat, desto grösser ist die Basisbrühmenge.
STADIEN = {
    "3–5 Blätter": 600,
    "1. Vorblüte": 800,
    "2. Vorblüte": 1000,
    "Blüte": 1200,
    "Nachblüte": 1600,
    "nur Traubenzone": 1200,
}

# Hilfslisten: in welchen Stadien ein Mittel erlaubt ist.
ALLE = ["3–5 Blätter", "1. Vorblüte", "2. Vorblüte", "Blüte", "Nachblüte", "nur Traubenzone"]
NACH_BLUETE = ["Nachblüte", "nur Traubenzone"]

# Mittel gegen Falschen Mehltau.
# konzentration    = Konzentration in Prozent
# einheit          = "kg" oder "l"
# max_behandlungen = wie oft pro Jahr erlaubt (0 = keine Limite)
# kupfer           = kg Kupfer pro kg oder l Mittel (0 = kein Kupfer)
# hitzeempfindlich = PLATZHALTER, noch mit dem Winzer bestätigen
# stadien          = in welchen Stadien das Mittel erlaubt ist
# hinweis          = besondere Auflage aus der Agroscope-Liste
MITTEL = {
    "Folpet 80 WG": {
        "konzentration": 0.125, "einheit": "kg", "max_behandlungen": 0,
        "kupfer": 0, "hitzeempfindlich": False, "stadien": ALLE,
        "hinweis": "",
    },
    "Quadris Max": {
        "konzentration": 0.2, "einheit": "l", "max_behandlungen": 3,
        "kupfer": 0, "hitzeempfindlich": False, "stadien": ALLE,
        "hinweis": "Nicht in Grundwasserschutzzonen S2 ausbringen.",
    },
    "Ridomil Vino": {
        "konzentration": 0.225, "einheit": "kg", "max_behandlungen": 3,
        "kupfer": 0, "hitzeempfindlich": False,
        "stadien": ["1. Vorblüte", "2. Vorblüte", "Blüte", "Nachblüte"],
        "hinweis": "Nur bis spätestens Ende Juli einsetzen.",
    },
    "Kocide Opti (Kupfer)": {
        "konzentration": 0.0625, "einheit": "kg", "max_behandlungen": 0,
        "kupfer": 0.30, "hitzeempfindlich": True, "stadien": NACH_BLUETE,
        "hinweis": "Kupfer erst nach der Blüte und bis spätestens Mitte August. "
                   "Nur in Mischung mit Folpet.",
    },
}

KUPFER_LIMITE = 4.0   # kg Kupfer pro ha und Jahr (ÖLN)
HITZE_GRENZE = 30     # °C, PLATZHALTER

# Koordinaten der Station Zizers, gleich wie auf der Wetter-Seite
ZIZERS_LAT = 46.93
ZIZERS_LON = 9.57


@st.cache_data(ttl=3600)   # Daten 1 Stunde merken, damit nicht bei jedem Klick neu geladen wird
def lade_hoechsttemperaturen():
    """Holt die Höchsttemperatur pro Tag von Open-Meteo (gleiche Quelle wie die Wetter-Seite).

    Rückgabe: ein Dictionary, z. B. {"2026-05-17": 24.3, "2026-05-18": 27.1, ...}
    """
    url = "https://api.open-meteo.com/v1/forecast"
    parameter = {
        "latitude": ZIZERS_LAT,
        "longitude": ZIZERS_LON,
        "daily": "temperature_2m_max",   # Höchsttemperatur pro Tag
        "forecast_days": 16,             # heute und die nächsten 15 Tage
        "timezone": "Europe/Zurich",
    }
    antwort = requests.get(url, params=parameter, timeout=15)
    antwort.raise_for_status()
    daten = antwort.json()["daily"]
    # zip verbindet die Liste der Daten mit der Liste der Temperaturen zu Paaren
    return dict(zip(daten["time"], daten["temperature_2m_max"]))

# Titel und Untertitel
st.title("Dosierung – wie viel Mittel und Wasser brauche ich?")
st.caption("Aus Rebstadium, Mittel und Fläche wird ein Tankrezept berechnet.")

# Parzellen aus der Datenbank holen (dieselbe Datenbank wie auf der Seite Parzelle).
# try/except: Gibt es die Tabelle noch nicht, stürzt die Seite nicht ab,
# sondern arbeitet einfach mit einer leeren Tabelle weiter.
con = sqlite3.connect("daten/spritzplaner.db")
try:
    parzellen = pd.read_sql_query("SELECT name, flaeche_ha FROM parzellen", con)
except Exception:
    parzellen = pd.DataFrame(columns=["name", "flaeche_ha"])

# Die Seite wird in zwei Spalten geteilt: links Eingaben, rechts Resultat.
links, rechts = st.columns(2, gap="large")

with links:
    st.subheader("Eingaben")

    # Parzelle: Normalerweise wählt man eine gespeicherte Parzelle aus.
    # Mit dem Häkchen «Manuell ausfüllen» gibt man die Fläche selbst ein (Notfall).
    if parzellen.empty:
        # Gibt es noch keine Parzellen, geht nur die Eingabe von Hand.
        manuell = True
        st.caption("Noch keine Parzellen gespeichert. Bitte die Fläche von Hand eingeben.")
    else:
        manuell = st.checkbox("Manuell ausfüllen")

    if manuell:
        parzelle = ""   # keine Parzelle gewählt
        flaeche = st.number_input("Fläche (ha)", min_value=0.01, value=0.8, step=0.1)
    else:
        parzelle = st.selectbox("Parzelle", list(parzellen["name"]))
        # Die Zeile der gewählten Parzelle suchen und die Fläche daraus lesen.
        zeile = parzellen[parzellen["name"] == parzelle].iloc[0]
        flaeche = float(zeile["flaeche_ha"])
        st.info(f"Fläche aus der Parzelle «{parzelle}»: **{flaeche:.2f} ha**")

    # Auswahlfelder: Der Benutzer wählt einen Eintrag aus der Liste.
    # index=3 heisst: «Blüte» (4. Eintrag) ist vorausgewählt.
    stadium = st.selectbox("Rebstadium", list(STADIEN.keys()), index=3)
    mittel_name = st.selectbox("Mittel", list(MITTEL.keys()))

    # Zahlenfelder: min_value = kleinster Wert, value = Startwert
    # help= zeigt ein ? neben dem Feld mit einer Erklärung
    wasser_pro_ha = st.number_input(
        "Wie viele Liter versprüht dein Gerät pro Hektare?",
        min_value=50, value=300, step=25,
        help="Wenn du eine Hektare fertig gespritzt hast: Wie viele Liter sind aus dem Tank weg? "
             "Früh in der Saison oft ca. 150 l, bei voller Laubwand ca. 400 l.",
    )
    tank = st.number_input("Tankgrösse (l)", min_value=20, value=200, step=10)

    # Spritztag: heute oder einer der nächsten 15 Tage (so weit reicht die Wetterprognose)
    heute = datetime.date.today()
    spritztag = st.date_input(
        "Geplanter Spritztag",
        value=heute,
        min_value=heute,
        max_value=heute + datetime.timedelta(days=15),
        format="DD.MM.YYYY",
    )

    # Temperatur am Spritztag aus der Wetterprognose holen.
    # try/except: Klappt das Laden nicht (z. B. kein Internet), stürzt die Seite nicht ab.
    try:
        temperaturen = lade_hoechsttemperaturen()
    except Exception:
        temperaturen = {}
    # str(spritztag) ergibt z. B. "2026-05-17", genau so heissen die Schlüssel im Dictionary.
    temperatur = temperaturen.get(str(spritztag))

    if temperatur is None:
        # Notfall: keine Wetterdaten, also Temperatur von Hand eingeben
        st.warning("Wetterdaten konnten nicht geladen werden. Bitte die Temperatur von Hand eingeben.")
        temperatur = st.number_input("Höchsttemperatur am Spritztag (°C)", value=24)
    else:
        st.info(f"Höchsttemperatur am {spritztag:%d.%m.%Y} laut Wetterprognose: **{temperatur:.0f} °C**")


# Die Angaben zum gewählten Mittel und Stadium aus Schritt 1 holen.
mittel = MITTEL[mittel_name]
basis = STADIEN[stadium]
einheit = mittel["einheit"]


# Formel 1: Mittel pro Hektare
mittel_pro_ha = mittel["konzentration"] / 100 * basis

# Formel 2: Mittel für die ganze Parzelle
mittel_total = mittel_pro_ha * flaeche

# Formel 3: Wasser für die ganze Parzelle
wasser_total = wasser_pro_ha * flaeche

# Formel 4: Wie oft muss der Tank gefüllt werden? math.ceil rundet auf.
tankfuellungen = math.ceil(wasser_total / tank)

# Formel 5: Mittel pro volle Tankfüllung
mittel_pro_tank = mittel_pro_ha * tank / wasser_pro_ha

# Kupfer, das mit dieser Spritzung pro Hektare ausgebracht wird
kupfer_pro_ha = mittel_pro_ha * mittel["kupfer"]

with rechts:
    # Zuerst prüfen: Ist das Mittel in diesem Stadium erlaubt?
    if stadium not in mittel["stadien"]:
        st.error(f"{mittel_name} ist im Stadium «{stadium}» nicht erlaubt.")

    else:
        # Weinrote Box wie auf der Startseite (HTML mit f-String)
        st.markdown(f"""
<div style="background-color:#7B1E3A; color:white; padding:24px 32px; border-radius:20px;">
<p style="margin:0; letter-spacing:2px; color:#F3D9DF;">TANKREZEPT · {mittel_name}</p>
<h2 style="color:white;">{tankfuellungen} Tankfüllungen</h2>
<p style="font-size:18px; margin:0;">
Pro volle Füllung: <b>{tank} l Wasser + {mittel_pro_tank:.2f} {einheit} Mittel</b><br>
Total: {mittel_total:.2f} {einheit} Mittel in {wasser_total:.0f} l Wasser
</p>
</div>
""", unsafe_allow_html=True)

        st.write("")  # etwas Abstand

        # Button 1: Werte für das Journal merken.
        # st.session_state ist ein Speicher, den alle Seiten lesen können.
        if st.button("Ins Journal übernehmen"):
            st.session_state["dosierung_vorschlag"] = {
                "datum": spritztag,
                "parzelle": parzelle,
                "stadium": stadium,
                "mittel": mittel_name,
                "flaeche": flaeche,
                "wasser_pro_ha": wasser_pro_ha,
                "menge": round(mittel_total, 2),
                "einheit": einheit,
            }
            st.switch_page("pages/journal.py")   # direkt zum Journal wechseln

        # Button 2: Rezept als HTML-Datei herunterladen.
        # Eine HTML-Datei öffnet sich auf jedem Computer im Browser.
        # <script>window.print()</script> öffnet beim Öffnen direkt das Druckfenster.
        # Wurde keine Parzelle gewählt, steht im Rezept «keine gewählt».
        if parzelle == "":
            parzelle_text = "keine gewählt"
        else:
            parzelle_text = parzelle

        rezept_html = f"""
<html>
<head><meta charset="utf-8"><title>Tankrezept</title></head>
<body style="font-family: Arial, sans-serif; padding: 40px;">
<h1 style="color:#7B1E3A;">Tankrezept</h1>
<p>Spritztag: <b>{spritztag:%d.%m.%Y}</b><br>
Parzelle: <b>{parzelle_text}</b> ({flaeche:.2f} ha)<br>
Mittel: <b>{mittel_name}</b><br>
Rebstadium: <b>{stadium}</b></p>
<h2>{tankfuellungen} Tankfüllungen</h2>
<p style="font-size:20px;">Pro volle Füllung: <b>{tank} l Wasser + {mittel_pro_tank:.2f} {einheit} Mittel</b></p>
<p>Total: {mittel_total:.2f} {einheit} Mittel in {wasser_total:.0f} l Wasser</p>
<p style="color:gray;">Immer die Etikette des Mittels beachten.</p>
<script>window.print()</script>
</body>
</html>
"""
        st.download_button(
            "Rezept drucken",
            data=rezept_html,
            file_name="tankrezept.html",
            mime="text/html",
        )


st.subheader("Hinweise")

# Hinweis 1: Hitze
if temperatur >= HITZE_GRENZE and mittel["hitzeempfindlich"]:
    st.warning(f"Hitzeempfindliches Mittel: Bei {temperatur:.0f} °C kann {mittel_name} die Blätter verbrennen.")
else:
    st.success(f"Hitze ok ({temperatur:.0f} °C am Spritztag).")

# Hinweis 2: Besondere Auflage des Mittels (nur wenn es eine gibt)
if mittel["hinweis"] != "":
    st.info(mittel["hinweis"])

# Hinweis 3: Jahreslimite
# Die bisherigen Werte kommen später aus dem Journal. Bis dahin von Hand.
bisher_behandlungen = st.number_input("Bisherige Behandlungen mit diesem Mittel dieses Jahr", min_value=0, value=0)
bisher_kupfer = st.number_input("Bisher ausgebrachtes Kupfer dieses Jahr (kg/ha)", min_value=0.0, value=0.0)

if mittel["max_behandlungen"] > 0:
    st.write(f"Behandlungen: {bisher_behandlungen + 1} von max. {mittel['max_behandlungen']}")
    if bisher_behandlungen + 1 > mittel["max_behandlungen"]:
        st.error("Die maximale Anzahl Behandlungen wäre überschritten.")

kupfer_neu = bisher_kupfer + kupfer_pro_ha
st.write(f"Kupfer: {kupfer_neu:.2f} von max. {KUPFER_LIMITE} kg/ha")
if kupfer_neu > KUPFER_LIMITE:
    st.error("Die Kupferlimite wäre überschritten.")



st.subheader(f"{mittel_name}: Menge pro ha je Stadium")

# Zwei leere Listen: eine für die Namen, eine für die Mengen.
stadien_namen = []
mengen = []
for name in mittel["stadien"]:
    stadien_namen.append(name)
    mengen.append(mittel["konzentration"] / 100 * STADIEN[name])

# Das Diagramm bekommt die Mengen als Säulen und die Namen als x-Achse.
st.bar_chart({"Stadium": stadien_namen, "Menge": mengen},
             x="Stadium", y="Menge", y_label=f"{einheit} pro ha",
             color="#7B1E3A", sort=False)
with st.expander("So wird gerechnet"):
    st.markdown(f"""
1. Mittel pro ha = Konzentration ÷ 100 × Basisbrühmenge = **{mittel_pro_ha:.2f} {einheit}**
2. Mittel total = Mittel pro ha × Fläche = **{mittel_total:.2f} {einheit}**
3. Wasser total = Wasser pro ha × Fläche = **{wasser_total:.0f} l**
4. Tankfüllungen = Wasser total ÷ Tankgrösse, aufgerundet = **{tankfuellungen}**
5. Mittel pro Tank = Mittel pro ha × Tankgrösse ÷ Wasser pro ha = **{mittel_pro_tank:.2f} {einheit}**
""")

st.divider()
st.caption("Quelle: Agroscope, Pflanzenschutzmittelliste für den Rebbau 2026. "
           "Immer die Etikette des Mittels beachten. Die App ist eine Entscheidungshilfe.")