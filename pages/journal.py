#Hier kommt der Code für das Journal hinein
import streamlit as st
st.title("Journal")

# Hier wird die Seite "Journal" codiert.
"""Journal – was habe ich gespritzt?

Das Journal speichert jede Spritzung in der Datenbank (daten/spritzplaner.db)
und zeigt daraus, bis wann die Reben geschützt sind und wie viel Mittel
und Kupfer dieses Jahr schon gebraucht wurde.

KI-Hinweis: Der Grundaufbau dieses Codes wurde mit Claude (Anthropic,
Modell Claude Opus 5.5, 17.11.2026) generiert und danach von uns angepasst.
"""

import datetime as dt
import sqlite3

import pandas as pd


# Feste Werte (Konstanten)

SCHUTZ_TAGE = 10      # so lange schützt ein Belag im Modell (fix)
KUPFER_LIMITE = 4.0   # kg Kupfer pro ha und Jahr (ÖLN)

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Gleiche Rebstadien wie auf der Seite Dosierung
STADIEN = ["3–5 Blätter", "1. Vorblüte", "2. Vorblüte", "Blüte", "Nachblüte", "nur Traubenzone"]

# Gleiche Mittel wie auf der Seite Dosierung (nur die Angaben, die das Journal braucht).
# max_behandlungen = wie oft pro Jahr erlaubt (0 = keine Limite)
# kupfer           = kg Kupfer pro kg oder l Mittel (0 = kein Kupfer)
MITTEL = {
    "Folpet 80 WG": {"einheit": "kg", "max_behandlungen": 0, "kupfer": 0},
    "Quadris Max": {"einheit": "l", "max_behandlungen": 3, "kupfer": 0},
    "Ridomil Vino": {"einheit": "kg", "max_behandlungen": 3, "kupfer": 0},
    "Kocide Opti (Kupfer)": {"einheit": "kg", "max_behandlungen": 0, "kupfer": 0.30},
}

st.caption("Das Gedächtnis der App: Hier wird jede Spritzung festgehalten.")

heute = dt.date.today()


# Datenbank

# Gleiche Datenbank wie auf der Seite Parzelle
con = sqlite3.connect("daten/spritzplaner.db")

# Tabelle Parzellen (gleich wie in parzelle.py), falls diese Seite zuerst geöffnet wird
con.execute("""
    CREATE TABLE IF NOT EXISTS parzellen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        sorte TEXT,
        flaeche_ha REAL,
        station TEXT
    )
""")

# Neue Tabelle für die Spritzungen (nur wenn es sie noch nicht gibt)
con.execute("""
    CREATE TABLE IF NOT EXISTS spritzungen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datum TEXT,
        parzelle TEXT,
        flaeche_ha REAL,
        mittel TEXT,
        stadium TEXT,
        wasser_l_ha REAL,
        menge REAL,
        einheit TEXT,
        notiz TEXT
    )
""")

parzellen = pd.read_sql_query("SELECT * FROM parzellen", con)

# Ohne Parzelle kann man keine Spritzung erfassen
if parzellen.empty:
    st.warning("Es gibt noch keine Parzellen. Lege zuerst auf der Seite Parzelle eine an.")
    st.page_link("pages/parzelle.py", label="Zur Seite Parzelle", icon=":material/map:")
    st.stop()  # Rest der Seite nicht ausführen

# Alle Spritzungen holen, die neuste zuoberst
journal = pd.read_sql_query("SELECT * FROM spritzungen ORDER BY datum DESC", con)

# Datum ist in der Datenbank als Text gespeichert (z.B. "2026-05-09").
# Hier wird es wieder in ein richtiges Datum umgewandelt.
journal["datum"] = pd.to_datetime(journal["datum"]).dt.date

# Nur die Spritzungen von diesem Jahr
dieses_jahr = journal[journal["datum"] >= dt.date(heute.year, 1, 1)]


# Parzelle wählen (gilt für Schutzstatus und Jahresmengen)

parzelle = st.selectbox("Parzelle", list(parzellen["name"]))
eintraege = journal[journal["parzelle"] == parzelle]


# 1. Schutzstatus

st.subheader("Schutzstatus")

if eintraege.empty:
    st.info("Für diese Parzelle ist noch keine Spritzung erfasst.")
else:
    letzte = eintraege.iloc[0]  # die neuste Spritzung (Liste ist nach Datum sortiert)
    geschuetzt_bis = letzte["datum"] + dt.timedelta(days=SCHUTZ_TAGE)
    tage_noch = (geschuetzt_bis - heute).days
    bis_text = f"{WOCHENTAGE[geschuetzt_bis.weekday()]}, {geschuetzt_bis:%d.%m.}"

    if tage_noch >= 0:
        st.success(f"**Geschützt bis {bis_text} – noch {tage_noch} Tage**  \n"
                   f"Letzte Spritzung am {letzte['datum']:%d.%m.} mit {letzte['mittel']}.")
    else:
        st.error(f"**Nicht mehr geschützt** – der Belag ist seit {bis_text} abgelaufen.  \n"
                 f"Letzte Spritzung am {letzte['datum']:%d.%m.} mit {letzte['mittel']}.")

    # Balken: wie viele der 10 Tage schon vorbei sind
    vorbei = (heute - letzte["datum"]).days
    vorbei = min(max(vorbei, 0), SCHUTZ_TAGE)  # zwischen 0 und 10 halten
    st.progress(vorbei / SCHUTZ_TAGE, text=f"{vorbei} von {SCHUTZ_TAGE} Tagen vorbei")


# 2. Spritzung erfassen

st.subheader("Spritzung erfassen")

# Startwerte für das Formular
start_mittel = 0
start_stadium = 3      # «Blüte»
start_wasser = 300
start_menge = 0.0

# Hat jemand auf der Seite Dosierung «Ins Journal übernehmen» geklickt?
vorschlag = st.session_state.get("dosierung_vorschlag")
if vorschlag is not None:
    st.info("Die Werte aus der Dosierung wurden übernommen. Bitte nur noch prüfen.")
    start_mittel = list(MITTEL.keys()).index(vorschlag["mittel"])
    start_stadium = STADIEN.index(vorschlag["stadium"])
    start_wasser = int(vorschlag["wasser_pro_ha"])
    start_menge = float(vorschlag["menge"])

with st.form("neue_spritzung", clear_on_submit=True):
    links, rechts = st.columns(2)
    with links:
        datum = st.date_input("Datum", value=heute, format="DD.MM.YYYY")
        parzelle_neu = st.selectbox("Parzelle", list(parzellen["name"]),
                                    index=list(parzellen["name"]).index(parzelle),
                                    key="parzelle_formular")
        mittel = st.selectbox("Mittel", list(MITTEL.keys()), index=start_mittel)
        stadium = st.selectbox("Rebstadium", STADIEN, index=start_stadium)
    with rechts:
        wasser = st.number_input("Wasser (l/ha)", min_value=0, value=start_wasser, step=25)
        menge = st.number_input("Menge Mittel total (kg bzw. l)", min_value=0.0,
                                value=start_menge, step=0.1)
        notiz = st.text_input("Notiz")
    speichern = st.form_submit_button("Spritzung speichern")

# Nur wenn auf den Button geklickt wurde
if speichern:
    if menge == 0:
        st.error("Bitte die Menge eingeben.")
    else:
        # Fläche der gewählten Parzelle nachschauen (für Kupfer pro ha)
        flaeche = parzellen[parzellen["name"] == parzelle_neu]["flaeche_ha"].iloc[0]

        con.execute(
            "INSERT INTO spritzungen (datum, parzelle, flaeche_ha, mittel, stadium, "
            "wasser_l_ha, menge, einheit, notiz) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datum.isoformat(), parzelle_neu, float(flaeche), mittel, stadium,
             wasser, menge, MITTEL[mittel]["einheit"], notiz),
        )
        con.commit()  # wirklich speichern

        # Der Vorschlag aus der Dosierung ist erledigt und wird gelöscht
        if "dosierung_vorschlag" in st.session_state:
            del st.session_state["dosierung_vorschlag"]

        st.rerun()  # Seite neu laden, damit der Eintrag überall erscheint


# 3. Alle Spritzungen dieses Jahr

st.subheader(f"Alle Spritzungen {heute.year}")

if dieses_jahr.empty:
    st.info("Dieses Jahr wurde noch nichts gespritzt.")
else:
    anzeige = dieses_jahr[["datum", "parzelle", "mittel", "stadium",
                           "wasser_l_ha", "menge", "einheit", "notiz"]]
    st.dataframe(anzeige, hide_index=True)

    # Einen falschen Eintrag löschen
    # Dictionary: Beschriftung in der Auswahl -> id in der Datenbank
    auswahl_liste = {}
    for i, zeile in dieses_jahr.iterrows():
        text = f"{zeile['datum']:%d.%m.%Y} – {zeile['parzelle']} – {zeile['mittel']} (Nr. {zeile['id']})"
        auswahl_liste[text] = zeile["id"]

    auswahl = st.selectbox("Falschen Eintrag löschen", list(auswahl_liste.keys()))
    if st.button("🗑️ Eintrag löschen"):
        con.execute("DELETE FROM spritzungen WHERE id = ?", (int(auswahl_liste[auswahl]),))
        con.commit()
        st.rerun()


# 4. Jahresmengen der gewählten Parzelle

st.subheader(f"Jahresmengen {heute.year} – {parzelle}")

jahr_parzelle = dieses_jahr[dieses_jahr["parzelle"] == parzelle]

# Kupfer pro ha zusammenzählen: Menge ÷ Fläche × Kupfergehalt des Mittels
kupfer = 0
for i, zeile in jahr_parzelle.iterrows():
    if zeile["mittel"] in MITTEL and zeile["flaeche_ha"] > 0:
        kupfer = kupfer + zeile["menge"] / zeile["flaeche_ha"] * MITTEL[zeile["mittel"]]["kupfer"]

k1, k2 = st.columns(2)
k1.metric("Spritzungen total", len(jahr_parzelle))
k2.metric("Kupfer", f"{kupfer:.2f} von {KUPFER_LIMITE} kg/ha")
if kupfer > KUPFER_LIMITE:
    st.error("Die Kupferlimite ist überschritten.")

# Behandlungen pro Mittel zählen und mit der Limite vergleichen
st.write("**Behandlungen pro Mittel**")
namen = []
anzahlen = []
for name in MITTEL:
    anzahl = len(jahr_parzelle[jahr_parzelle["mittel"] == name])
    maximum = MITTEL[name]["max_behandlungen"]
    namen.append(name)
    anzahlen.append(anzahl)

    if maximum > 0:
        st.write(f"- {name}: {anzahl} von max. {maximum}")
        if anzahl > maximum:
            st.error(f"{name}: Die maximale Anzahl Behandlungen ist überschritten.")
    else:
        st.write(f"- {name}: {anzahl} (keine Limite)")

# Diagramm: wie oft jedes Mittel gebraucht wurde
st.bar_chart({"Mittel": namen, "Behandlungen": anzahlen},
             x="Mittel", y="Behandlungen", color="#7B1E3A", sort=False)


# Fusszeile

st.divider()
st.caption("Die Daten sind in der lokalen Datenbank gespeichert (daten/spritzplaner.db). "
           f"Hinweis: Der Belag schützt im Modell fix {SCHUTZ_TAGE} Tage. Dass starker Regen "
           "ihn abwäscht und neue Blätter ungeschützt nachwachsen, wird noch nicht berücksichtigt.")