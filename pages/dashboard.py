#Hier wird die Seite Dashboard codiert.
"""Dashboard: alles Wichtige auf einen Blick.
 
Das Dashboard rechnet nichts selbst, es holt die Zahlen von den anderen Seiten
(Kalender, Wetter, Journal und Parzellen) über gemeinsam.py und die Datenbank.
"""
 
import sqlite3
 
import pandas as pd
import streamlit as st
 
import gemeinsam as g
 
WEINROT = "#7B1E3A"
GOLD = "#C9A227"
 
# Daten holen
heute = pd.Timestamp(g.heute())                       # Datum aus der Seitenleiste
tage = pd.date_range(heute, periods=14)               # 14 Tage wie im Kalender
tageswetter = g.wetter_seit_neujahr(heute.date())     # Wetter-Seite
infektionen, spritzungen = g.infektionen_mit_frist(heute.date())   # Kalender + Journal
wetter = g.lade_stundenwetter(heute.date(), tage[-1].date())
bewertung = [g.bewerte_tag(tag, wetter, sonntag_sperren=True) for tag in tage]
keimbereit = g.keimbereitschaft(tageswetter)
 
try:
    parzellen = pd.read_sql_query("SELECT flaeche_ha FROM parzellen", sqlite3.connect("daten/spritzplaner.db"))
except Exception:
    parzellen = pd.DataFrame(columns=["flaeche_ha"])
 
# Offene Infektionen: schon passiert, Frist noch nicht vorbei, noch nicht gespritzt
offen = infektionen[(infektionen["start"] <= heute) & (infektionen["frist"] >= heute)
                    & (infektionen["status"] == "offen")]
laufend = infektionen[(infektionen["start"] <= heute) & (infektionen["ende"] > heute)]
 
# Titel
st.caption(f"Station Zizers · Saison {heute.year}")
if len(offen) > 0:
    st.title("Guten Tag. Heute ist Handeln gefragt.")
else:
    st.title("Guten Tag. Alles im grünen Bereich.")
 
# Alarm-Box mit der nächsten Frist und dem ersten grünen Tag davor (wie im Kalender)
gute = []
if len(offen) > 0:
    infektion = offen.sort_values("frist").iloc[0]
    frist = infektion["frist"]
    gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= frist]
    if gute:
        start = bewertung[list(tage).index(gute[0])][1]
        naechster = f"Nächster geeigneter Tag: {g.WOCHENTAGE[gute[0].weekday()]}, {gute[0]:%d.%m.} ab {start} Uhr."
    else:
        naechster = "Kein grüner Tag vor der Frist. Prüfe die gelben Tage im Kalender."
    st.markdown(f"""
    <div style="background-color:{WEINROT}; color:white; padding:24px 32px; border-radius:20px;">
        <p style="margin:0; letter-spacing:2px; color:#F3D9DF;">INFEKTIONS-ALARM</p>
        <h2 style="margin:0; color:white;">Infektion am {infektion['start']:%d.%m.} –
            spritzen bis {g.WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h2>
        <p style="margin:0;">Kein Spritzbelag aktiv. {naechster}</p>
    </div>""", unsafe_allow_html=True)
else:
    st.info("Keine offene Infektion. Spritzen ist im Moment nicht nötig.")
 
# Knöpfe zu den anderen Seiten
k1, k2, _ = st.columns([1, 1, 3])
k1.page_link("pages/kalender.py", label="Spritzfenster ansehen", icon=":material/calendar_month:")
k2.page_link("pages/dosierung.py", label="Brühe berechnen", icon=":material/science:")
 
# Vier Kennzahlen
s1, s2, s3, s4 = st.columns(4)
if keimbereit is not None and keimbereit <= heute:
    s1.metric("Keimbereit seit", f"{keimbereit:%d.%m.}", border=True)
else:
    s1.metric("Keimbereit seit", "noch nicht", border=True)
s2.metric("Parzellen", f"{len(parzellen)} · {parzellen['flaeche_ha'].sum():.2f} ha", border=True)
s3.metric("Laufende Inkubationen", len(laufend), border=True)
if len(spritzungen) > 0:
    letzte = spritzungen["datum"].iloc[-1]
    geschuetzt = letzte + pd.Timedelta(days=g.SCHUTZ_TAGE) >= heute
    s4.metric("Letzte Spritzung", f"{letzte:%d.%m.}", border=True,
              delta="geschützt" if geschuetzt else "nicht geschützt",
              delta_color="normal" if geschuetzt else "inverse")
else:
    s4.metric("Letzte Spritzung", "–", border=True)
 
# Spritzfenster: die nächsten 7 Tage (gleiche Farben wie im Kalender)
st.subheader("Spritzfenster – nächste 7 Tage")
for spalte, tag, (stufe, start, gruende) in zip(st.columns(7), tage, bewertung):
    rahmen = f"3px solid {GOLD}" if gute and tag == gute[0] else "1px solid #CCCCCC"
    spalte.markdown(f"""
    <div style="background-color:{g.FARBEN[stufe]}; border:{rahmen}; border-radius:10px;
                padding:8px; min-height:110px; font-size:13px;">
        <b>{g.WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}</b><br>{g.AMPEL[stufe]}<br>
        <small>{", ".join(gruende)}</small>
    </div>""", unsafe_allow_html=True)