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