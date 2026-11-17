"""Seite Parzellen: Hier speichert der Winzer seine Rebberge."""

import sqlite3
import pandas as pd
import streamlit as st

# Wetterstationen mit ihren Koordinaten (Breite, Länge).
# Die Wetter-Seite kann hier nachschauen, wo eine Station liegt.
STATIONEN = {
    "Zizers": (46.93, 9.56),
}

st.title("Parzellen – welche Rebberge habe ich?")
st.caption("Deine Rebberge mit Fläche, Sorte und Wetterstation.")

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

# Alle Parzellen aus der Datenbank holen
parzellen = pd.read_sql_query("SELECT * FROM parzellen", con)

# Drei Kennzahlen nebeneinander, jede in einem Kasten mit Rahmen
spalte1, spalte2, spalte3 = st.columns(3)
with spalte1.container(border=True):
    st.metric("Parzellen", len(parzellen))
with spalte2.container(border=True):
    st.metric("Fläche total", f"{parzellen['flaeche_ha'].sum():.2f} ha")
with spalte3.container(border=True):
    st.metric("Wetterstationen", parzellen["station"].nunique())

# Parzellen als Tabelle anzeigen
st.subheader("Übersicht")

if parzellen.empty:
    st.info("Es gibt noch keine Parzellen. Lege unten deine erste an.")
else:
    st.dataframe(
        parzellen[["name", "sorte", "flaeche_ha", "station"]],   # nur diese Spalten zeigen
        hide_index=True,                                         # Zeilennummern 0, 1, 2 ausblenden
        column_config={                                          # schönere Spaltentitel
            "name": "Name",
            "sorte": "Sorte",
            "flaeche_ha": st.column_config.NumberColumn("Fläche (ha)", format="%.2f"),
            "station": "Wetterstation",
        },
    )

# Formular für eine neue Parzelle
st.subheader("Neue Parzelle")

with st.form("neue_parzelle", border=True):
    links, rechts = st.columns(2)   # Formular in zwei Spalten
    name = links.text_input("Name", placeholder="z. B. Sonnenhalde")
    sorte = rechts.text_input("Sorte", placeholder="z. B. Blauburgunder")
    flaeche = links.number_input("Fläche (ha)", min_value=0.0, step=0.1)
    station = rechts.selectbox("Wetterstation", list(STATIONEN.keys()))
    gespeichert = st.form_submit_button("Parzelle speichern", type="primary")


# Nur wenn auf den Button geklickt wurde 
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

# Eine Parzelle löschen (aufklappbar, damit man nicht aus Versehen löscht)
if not parzellen.empty:
    with st.expander("Parzelle löschen"):
        auswahl = st.selectbox("Welche Parzelle?", parzellen["name"])
        if st.button("Löschen"):
            con.execute("DELETE FROM parzellen WHERE name = ?", (auswahl,))
            con.commit()
            st.rerun()