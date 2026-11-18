#Hier wird die Seite Journal codiert.
"""Seite Journal: Hier hält der Winzer fest, wann er was gespritzt hat.

Kommt man von der Dosierung («Ins Journal übernehmen»), sind die Felder
schon ausgefüllt. Man prüft sie nur noch und speichert.
Die Spritzungen werden in derselben Datenbank gespeichert wie die Parzellen.
"""

import datetime
import sqlite3
import pandas as pd
import streamlit as st

st.title("Journal – was habe ich gespritzt?")
st.caption("Jede Spritzung mit Datum, Parzelle, Mittel und Menge.")

# Verbindung zur Datenbank (dieselbe wie auf der Seite Parzelle)
con = sqlite3.connect("daten/spritzplaner.db")

# Tabelle für die Spritzungen erstellen (nur wenn es sie noch nicht gibt)
con.execute("""
    CREATE TABLE IF NOT EXISTS spritzungen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datum TEXT,
        parzelle TEXT,
        mittel TEXT,
        stadium TEXT,
        wasser_l_ha REAL,
        menge REAL,
        einheit TEXT,
        notiz TEXT
    )
""")

# Parzellen holen, damit man sie im Formular auswählen kann.
# try/except: Gibt es die Tabelle noch nicht, nehmen wir eine leere Liste.
try:
    parzellen_namen = list(pd.read_sql_query("SELECT name FROM parzellen", con)["name"])
except Exception:
    parzellen_namen = []

# Vorschlag aus der Dosierung holen.
# Gibt es keinen, ist «vorschlag» ein leeres Dictionary {} und die Felder bleiben leer.
vorschlag = st.session_state.get("dosierung_vorschlag", {})

if vorschlag:
    st.info("Die Werte aus der Dosierung wurden übernommen. Bitte prüfen und speichern.")


# Formular: neue Spritzung erfassen
st.subheader("Spritzung erfassen")

with st.form("neue_spritzung", border=True):
    links, rechts = st.columns(2)   # Formular in zwei Spalten

    # Startwert: der Spritztag aus der Dosierung, sonst das Datum aus der Seitenleiste
    heute = st.session_state.get("heute", datetime.date.today())
    datum = links.date_input("Datum", value=vorschlag.get("datum", heute), format="DD.MM.YYYY")

    # Parzelle: Liste der gespeicherten Parzellen. Die Parzelle aus der
    # Dosierung ist vorausgewählt, falls es sie gibt.
    if parzellen_namen:
        if vorschlag.get("parzelle") in parzellen_namen:
            start = parzellen_namen.index(vorschlag["parzelle"])
        else:
            start = 0
        parzelle = rechts.selectbox("Parzelle", parzellen_namen, index=start)
    else:
        parzelle = rechts.text_input("Parzelle", placeholder="z. B. Sonnenhalde")

    # vorschlag.get("mittel", "") heisst: den Wert aus der Dosierung nehmen,
    # und wenn es keinen gibt, ein leeres Feld zeigen.
    mittel = links.text_input("Mittel", value=vorschlag.get("mittel", ""))
    stadium = rechts.text_input("Rebstadium", value=vorschlag.get("stadium", ""))
    wasser = links.number_input("Wasser (l/ha)", min_value=0, value=int(vorschlag.get("wasser_pro_ha", 0)))
    menge = rechts.number_input("Menge Mittel total", min_value=0.0, value=float(vorschlag.get("menge", 0.0)))
    einheit = links.selectbox("Einheit", ["kg", "l"], index=["kg", "l"].index(vorschlag.get("einheit", "kg")))
    notiz = rechts.text_input("Notiz", placeholder="z. B. Wind leicht, alles gespritzt")

    gespeichert = st.form_submit_button("Spritzung speichern", type="primary")


# Nur wenn auf den Button geklickt wurde
if gespeichert:
    if parzelle == "" or mittel == "" or menge == 0:
        st.error("Bitte mindestens Parzelle, Mittel und Menge eingeben.")
    else:
        con.execute(
            "INSERT INTO spritzungen (datum, parzelle, mittel, stadium, wasser_l_ha, menge, einheit, notiz) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(datum), parzelle, mittel, stadium, wasser, menge, einheit, notiz),
        )
        con.commit()    # wirklich speichern
        # Den Vorschlag löschen, damit er beim nächsten Mal nicht wieder erscheint
        st.session_state.pop("dosierung_vorschlag", None)
        st.rerun()      # Seite neu laden, damit die Spritzung in der Tabelle erscheint


# Alle Spritzungen aus der Datenbank holen, die neuste zuoberst
spritzungen = pd.read_sql_query("SELECT * FROM spritzungen ORDER BY datum DESC", con)

st.subheader("Alle Spritzungen")

if spritzungen.empty:
    st.info("Es gibt noch keine Spritzungen. Erfasse oben deine erste.")
else:
    st.dataframe(
        spritzungen[["datum", "parzelle", "mittel", "stadium", "wasser_l_ha", "menge", "einheit", "notiz"]],
        hide_index=True,                                         # Zeilennummern ausblenden
        column_config={                                          # schönere Spaltentitel
            "datum": "Datum",
            "parzelle": "Parzelle",
            "mittel": "Mittel",
            "stadium": "Stadium",
            "wasser_l_ha": "Wasser (l/ha)",
            "menge": st.column_config.NumberColumn("Menge", format="%.2f"),
            "einheit": "Einheit",
            "notiz": "Notiz",
        },
    )

    # Eine Spritzung löschen (aufklappbar, damit man nicht aus Versehen löscht)
    with st.expander("Spritzung löschen"):
        # Jede Spritzung als lesbarer Text, z. B. "2026-05-17 · Sonnenhalde · Folpet 80 WG"
        texte = spritzungen["datum"] + " · " + spritzungen["parzelle"] + " · " + spritzungen["mittel"]
        auswahl = st.selectbox("Welche Spritzung?", texte)
        if st.button("Löschen"):
            # Die id der gewählten Zeile suchen und diese Zeile löschen
            id_loeschen = int(spritzungen[texte == auswahl]["id"].iloc[0])
            con.execute("DELETE FROM spritzungen WHERE id = ?", (id_loeschen,))
            con.commit()
            st.rerun()

st.divider()
st.caption("Die Spritzungen sind in der Datenbank gespeichert und gelten als Nachweis (ÖLN).")