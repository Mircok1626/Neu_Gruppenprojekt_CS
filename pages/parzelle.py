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
        station TEXT
    )
""")

# Alle Parzellen aus der Datenbank holen und als Tabelle anzeigen
parzellen = pd.read_sql_query("SELECT * FROM parzellen", con)
st.dataframe(parzellen)

#Formular für eine neue Parzelle
st.subheader("Neue Parzelle anlegen")

with st.form("neue_parzelle"):
    name = st.text_input("Name")
    sorte = st.text_input("Sorte")
    flaeche = st.number_input("Fläche (ha)", min_value=0.0, step=0.1)
    station = st.selectbox("Wetterstation", list(STATIONEN.keys()))
    gespeichert = st.form_submit_button("Parzelle speichern")

#Nur wenn auf den Button geklickt wurde 
if gespeichert:
    if name == "" or flaeche == 0:
        st.error("Bitte Name und Fläche eingeben.")
    else:
        con.execute(
            "INSERT INTO parzellen (name, sorte, flaeche_ha, station) VALUES (?, ?, ?, ?)",
            (name, sorte, flaeche, station),
        )
        con.commit()    #wirklich speichern
        st.rerun()      #Seite neu laden, damit die Parzelle in der Tabelle erscheint