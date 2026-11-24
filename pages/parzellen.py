"""Seite Parzellen: Hier speichert der Winzer seine Rebberge."""

import sqlite3
import pandas as pd
import streamlit as st

# Wetterstationen mit ihren Koordinaten (Breite, Länge).
# Die Wetter-Seite kann hier nachschauen, wo eine Station liegt.
STATIONEN = {
    "Zizers": (46.93, 9.56),
}

st.title("Vineyards – which vineyards do I have?")
st.caption("Your vineyards with area, variety and weather station.")

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

# Meldung nach dem Speichern: Sie wird gemerkt, weil die Seite danach neu lädt.
# st.toast blendet die Meldung für ein paar Sekunden unten rechts ein.
if st.session_state.pop("parzellen_gespeichert", False):
    st.toast("Changes saved.", icon=":material/check_circle:")

# Drei Kennzahlen nebeneinander, jede in einem Kasten mit Rahmen
spalte1, spalte2, spalte3 = st.columns(3)
with spalte1.container(border=True):
    st.metric("Vineyards", len(parzellen))
with spalte2.container(border=True):
    st.metric("Total area", f"{parzellen['flaeche_ha'].sum():.2f} ha")
with spalte3.container(border=True):
    st.metric("Weather stations", parzellen["station"].nunique())

# Parzellen als Tabelle anzeigen, die man direkt bearbeiten kann
st.subheader("Overview")

if parzellen.empty:
    st.info("There are no Vineyards yet. Create your first one below.")
else:
    st.caption("To change a value, click a cell, type the new value and then click «Save changes».")
    # st.data_editor zeigt eine Tabelle, in der man die Felder ändern kann.
    # Die Spalte «id» braucht es zum Speichern, sie wird aber nicht angezeigt (None).
    bearbeitet = st.data_editor(
        parzellen[["id", "name", "sorte", "flaeche_ha", "station"]],
        hide_index=True,                                         # Zeilennummern 0, 1, 2 ausblenden
        column_config={                                          # schönere Spaltentitel
            "id": None,
            "name": "Name",
            "sorte": "Variety",
            "flaeche_ha": st.column_config.NumberColumn("Area (ha)", format="%.2f", min_value=0.01, step=0.01),
            "station": st.column_config.SelectboxColumn("Weather station", options=list(STATIONEN.keys())),
        },
        key="parzellen_tabelle",
    )

    if st.button("Save changes"):
        # Prüfen: Jede Parzelle braucht einen Namen und eine Fläche
        namen_fehlen = bearbeitet["name"].fillna("").str.strip().eq("").any()
        flaeche_fehlt = bearbeitet["flaeche_ha"].isna().any() or (bearbeitet["flaeche_ha"] <= 0).any()
        if namen_fehlen or flaeche_fehlt:
            st.error("Every vineyard needs a name and an area.")
        else:
            # Jede Zeile in der Datenbank mit den Werten aus der Tabelle überschreiben
            for _, zeile in bearbeitet.iterrows():
                con.execute(
                    "UPDATE parzellen SET name = ?, sorte = ?, flaeche_ha = ?, station = ? WHERE id = ?",
                    (zeile["name"], zeile["sorte"], float(zeile["flaeche_ha"]), zeile["station"], int(zeile["id"])),
                )
            con.commit()    #wirklich speichern
            st.session_state["parzellen_gespeichert"] = True
            del st.session_state["parzellen_tabelle"]   # Tabelle zurücksetzen, damit keine alten Änderungen bleiben
            st.rerun()      #Seite neu laden, damit auch die Kennzahlen oben stimmen

# Formular für eine neue Parzelle
st.subheader("New vineyard")

with st.form("neue_parzelle", border=True):
    links, rechts = st.columns(2)   # Formular in zwei Spalten
    name = links.text_input("Name", placeholder="e.g. Sunny Slope")
    sorte = rechts.text_input("Variety", placeholder="e.g. Pinot Noir")
    flaeche = links.number_input("Area (ha)", min_value=0.0, step=0.1)
    station = rechts.selectbox("Weather station", list(STATIONEN.keys()))
    gespeichert = st.form_submit_button("Save vineyard", type="primary")


# Nur wenn auf den Button geklickt wurde
if gespeichert:
    if name == "" or flaeche == 0:
        st.error("Please enter name and area.")
    else:
        con.execute(
            "INSERT INTO parzellen (name, sorte, flaeche_ha, station) VALUES (?, ?, ?, ?)",
            (name, sorte, flaeche, station),
        )
        con.commit()    #wirklich speichern
        st.rerun()      #Seite neu laden, damit die Parzelle in der Tabelle erscheint

# Eine Parzelle löschen (aufklappbar, damit man nicht aus Versehen löscht)
if not parzellen.empty:
    with st.expander("Delete vineyard"):
        auswahl = st.selectbox("Which vineyard?", parzellen["name"])
        if st.button("Delete"):
            con.execute("DELETE FROM parzellen WHERE name = ?", (auswahl,))
            con.commit()
            st.rerun()
