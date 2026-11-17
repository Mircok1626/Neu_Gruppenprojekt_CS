"""Seite Parzellen: Hier speichert der Winzer seine Rebberge."""

import sqlite3
import pandas as pd
import streamlit as st

# Wetterstationen mit ihren Koordinaten (Breite, Länge).
# Die Wetter-Seite kann hier nachschauen, wo eine Station liegt.
STATIONEN = {
    "Zizers": (46.93, 9.56),
}

st.title("Parzellen")

# Verbindung zur Datenbank. Gibt es die Datei noch nicht, wird sie erstellt. ->über con mit Datenbank sprechen
con = sqlite3.connect("daten/spritzplaner.db")

# Tabelle erstellen (nur wenn es sie noch nicht gibt)
con.execute("""
    CREATE TABLE IF NOT EXISTS parzellen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        sorte TEXT,
        flaeche_ha REAL,
        wasser_l_ha REAL,
        station TEXT
    )
""")

# Alle Parzellen aus der Datenbank holen und als Tabelle anzeigen
parzellen = pd.read_sql_query("SELECT * FROM parzellen", con)
st.dataframe(parzellen)

st.subheader("Neue Parzelle anlegen")

with st.form("neue_parzelle"):
    name = st.text_input("Name")
    sorte = st.text_input("Sorte")
    flaeche = st.number_input("Fläche (ha)", min_value=0.0, step=0.1)
    wasser = st.number_input("Wasser (l/ha)", min_value=0, value=300, step=50)
    station = st.selectbox("Wetterstation", list(STATIONEN.keys()))
    gespeichert = st.form_submit_button("Parzelle speichern")

if gespeichert:
    if name == "" or flaeche == 0:
        st.error("Bitte Name und Fläche eingeben.")
    else:
        con.execute(
            "INSERT INTO parzellen (name, sorte, flaeche_ha, wasser_l_ha, station) VALUES (?, ?, ?, ?, ?)",
            (name, sorte, flaeche, wasser, station),
        )
        con.commit()
        st.rerun()