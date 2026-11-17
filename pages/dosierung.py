#Hier wird die Seite Dosierung codiert.
"""Dosierung: Rechnet aus Rebstadium, Mittel und Fläche ein Tankrezept aus.

Die Seite ist eigenständig. Sie braucht keine anderen Seiten der App.
Quelle der Zahlen: Agroscope Transfer Nr. 626, Pflanzenschutzmittelliste
für den Rebbau 2026, Mittel gegen Falschen Mehltau.
"""

import math
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

# Titel und Untertitel
st.title("Dosierung – wie viel Mittel und Wasser brauche ich?")
st.caption("Aus Rebstadium, Mittel und Fläche wird ein Tankrezept berechnet.")

# Die Seite wird in zwei Spalten geteilt: links Eingaben, rechts Resultat.
links, rechts = st.columns(2, gap="large")

# Die Seite wird in zwei Spalten geteilt: links Eingaben, rechts Resultat.
links, rechts = st.columns(2, gap="large")

with links:
    st.subheader("Eingaben")

    # Auswahlfelder: Der Benutzer wählt einen Eintrag aus der Liste.
    # index=3 heisst: «Blüte» (4. Eintrag) ist vorausgewählt.
    stadium = st.selectbox("Rebstadium", list(STADIEN.keys()), index=3)
    mittel_name = st.selectbox("Mittel", list(MITTEL.keys()))

    # Zahlenfelder: min_value = kleinster Wert, value = Startwert
    flaeche = st.number_input("Fläche (ha)", min_value=0.01, value=0.8, step=0.1)
    wasser_pro_ha = st.number_input("Wasser des Sprühgeräts (l/ha)", min_value=50, value=300, step=25)
    tank = st.number_input("Tankgrösse (l)", min_value=20, value=200, step=10)
    temperatur = st.number_input("Höchsttemperatur am Spritztag (°C)", value=24)

    st.caption("Fläche, Wasser und Temperatur werden später automatisch "
               "von den Seiten Parzelle und Kalender übernommen.")

# Die Angaben zum gewählten Mittel und Stadium aus Schritt 1 holen.
mittel = MITTEL[mittel_name]
basis = STADIEN[stadium]
einheit = mittel["einheit"]