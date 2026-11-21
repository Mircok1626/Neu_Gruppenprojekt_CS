#Hier wird die Seite Dashboard codiert.
"""Dashboard: Das Wichtigste von allen Seiten auf einen Blick.

Das Dashboard rechnet nichts Eigenes. Alle Werte kommen aus gemeinsam.py
(Wetter, Keimbereitschaft, Infektionen, Ampel, Modell) und aus dem Journal
(Datenbank). Darum zeigt es genau dasselbe wie Kalender, Wetter und Journal.
"""

import datetime

import altair as alt
import pandas as pd
import streamlit as st

import gemeinsam as g   # gemeinsame Daten und Funktionen (Datum, Agrometeo, Modell, Saison)

# Farben und Wochentage wie im Kalender (aus gemeinsam.py)
WEINROT = g.WEINROT
WOCHENTAGE = g.WOCHENTAGE


# ---------------------------------------------------------------------------
# Daten von den anderen Seiten holen
# ---------------------------------------------------------------------------
heute = g.heute()                              # Datum aus der Seitenleiste
heute_ts = pd.Timestamp(heute)                 # dasselbe Datum zum Vergleichen mit Tabellen

tageswetter = g.wetter_seit_neujahr(heute)     # wie auf der Seite Wetter
keimbereit = g.keimbereitschaft(tageswetter)   # wie auf der Seite Wetter
infektionen = g.lade_infektionen(heute)        # wie im Kalender
spritzungen = g.lade_spritzungen(heute)        # aus dem Journal

# Ampel für die nächsten 14 Tage (wie im Kalender, Sonntag gesperrt)
tage = pd.date_range(heute, periods=14)
try:
    wetter = g.lade_wetter(heute, tage[-1].date())
except Exception:
    st.error("The weather from Open-Meteo could not be loaded.")
    st.stop()
bewertung = [g.bewerte_tag(tag, wetter, True) for tag in tage]

# Offene Infektionen: schon passiert, Frist noch nicht vorbei, noch nicht gespritzt
aktuell = infektionen[(infektionen["start"] <= heute_ts) & (infektionen["frist"] >= heute_ts)]
offen = aktuell[aktuell["status"] == "open"]

# Bis wann schützt die letzte Spritzung? (keine Spritzung: dann schützt nichts)
if len(spritzungen) > 0:
    geschuetzt_bis = spritzungen["datum"].iloc[-1] + pd.Timedelta(days=g.SCHUTZ_TAGE)
else:
    geschuetzt_bis = None

# Die nächste Frist und die grünen Tage davor
if len(offen) > 0:
    infektion = offen.sort_values("frist").iloc[0]
    frist = infektion["frist"]
    gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= frist]
else:
    frist, gute = None, []


# ---------------------------------------------------------------------------
# Titel
# ---------------------------------------------------------------------------
st.caption(f"Zizers Halde · Season {heute.year}")
if len(offen) > 0:
    st.title("Good morning. Action is needed today.")
else:
    st.title("Good morning. Everything is under control.")
if heute != datetime.date.today():
    st.caption("Demo mode: the app shows what it would have displayed on the date in the sidebar.")


# ---------------------------------------------------------------------------
# Infektions-Alarm (weinrote Box wie auf den anderen Seiten)
# ---------------------------------------------------------------------------
if len(offen) > 0:
    # Woher kommt die Infektion? Gemessen (mit Gradstunden) oder vom Modell vorausgesagt
    if pd.notna(infektion["gradstunden_bn"]):
        herkunft = f"{infektion['gradstunden_bn']:.0f} degree hours with leaf wetness."
    else:
        herkunft = "Predicted by the model."
    # Nächster grüner Tag vor der Frist
    if len(gute) > 0:
        start = bewertung[list(tage).index(gute[0])][1]
        naechster = f"Next suitable day: {WOCHENTAGE[gute[0].weekday()]}, {gute[0]:%d.%m.} from {start}:00."
    else:
        naechster = "No suitable day before the deadline. Check the calendar."

    st.markdown(f"""
    <div style="background-color: {WEINROT}; color: white; padding: 24px 32px; border-radius: 20px;">
        <p style="margin: 0; letter-spacing: 2px; color: #F3D9DF;">INFECTION ALERT</p>
        <h2 style="margin: 0; color: white;">Infection on {infektion['start']:%d.%m.} – spray by
            {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h2>
        <p style="margin: 0;">{herkunft} {naechster}</p>
    </div>""", unsafe_allow_html=True)

    # Zwei Links zu den passenden Seiten
    link1, link2, _ = st.columns([1, 1, 3])
    link1.page_link("pages/kalender.py", label="View spray windows", icon=":material/calendar_month:")
    link2.page_link("pages/dosierung.py", label="Calculate spray mix", icon=":material/science:")
else:
    st.success("No open infection. Spraying is not necessary at the moment.", icon=":material/check_circle:")


# ---------------------------------------------------------------------------
# Drei Kennzahlen
# ---------------------------------------------------------------------------
spalte1, spalte2, spalte3 = st.columns(3)

# 1) Keimbereitschaft (Seite Wetter)
with spalte1.container(border=True):
    if keimbereit is not None and keimbereit <= heute_ts:
        st.metric("Ready to germinate since", f"{keimbereit:%d.%m.}")
    else:
        st.metric("Ready to germinate since", "not yet")
    summe = tageswetter.loc[tageswetter["datum"] <= heute_ts, "temperatursumme"].max()
    st.caption(f"Temperature sum {summe:.0f} / {g.KEIMBEREIT_AB}")

# 2) Laufende Inkubationen: Infektion passiert, Inkubation noch nicht fertig
with spalte2.container(border=True):
    laufend = infektionen[(infektionen["start"] <= heute_ts) & (infektionen["ende"] > heute_ts)]
    st.metric("Ongoing incubations", len(laufend))
    if len(laufend) > 0:
        st.caption(f"Oil spots from {laufend['ende'].min():%d.%m.}")
    else:
        st.caption("None")

# 3) Letzte Spritzung (Journal)
with spalte3.container(border=True):
    if len(spritzungen) > 0:
        letzte = spritzungen["datum"].iloc[-1]
        st.metric("Last spraying", f"{letzte:%d.%m.}")
        if geschuetzt_bis >= heute_ts:
            st.caption(f"Protected until {geschuetzt_bis:%d.%m.}")
        else:
            st.caption("Not protected")
    else:
        st.metric("Last spraying", "–")
        st.caption("Not protected")


# ---------------------------------------------------------------------------
# Spritzfenster: genau dieselbe Anzeige wie im Kalender, aber nur die ersten 7 Tage
# ---------------------------------------------------------------------------
with st.container(border=True):
    g.zeige_spritzfenster("Spray windows – next 7 days", tage[:7], bewertung[:7], gute, frist,
                          offen, geschuetzt_bis, spritzungen)


# ---------------------------------------------------------------------------
# Unten zwei Spalten: Tabelle der Infektionen und Risiko laut Modell
# ---------------------------------------------------------------------------
links, rechts = st.columns([3, 2])

# Links: Infektionen der letzten 3 Wochen (und die vorausgesagten)
with links.container(border=True):
    st.subheader("Infections of the last 3 weeks")
    drei_wochen = infektionen[infektionen["start"] >= heute_ts - pd.Timedelta(days=21)]
    if drei_wochen.empty:
        st.write("No infections in the last 3 weeks.")
    else:
        tabelle = pd.DataFrame({
            "Date": drei_wochen["start"].dt.strftime("%d.%m.%Y"),
            "Incubation end": drei_wochen["ende"].dt.strftime("%d.%m."),
            "Spray by": drei_wochen["frist"].dt.strftime("%d.%m."),
            "Status": drei_wochen["status"],
            "Source": drei_wochen["quelle"],
        })
        st.dataframe(tabelle, hide_index=True, width="stretch")

# Rechts: Wie sicher ist sich das Modell? (Anteil der Bäume, die «Infektion» sagen)
with rechts.container(border=True):
    st.subheader("Infection risk (model)")
    st.caption("Random Forest based on the weather forecast")
    naechste = tageswetter[tageswetter["datum"] >= heute_ts].head(7).copy()
    if naechste.empty:
        st.write("No weather data for the next days.")
    else:
        modell, _, _ = g.trainiere_modell()
        naechste["Risk"] = modell.predict_proba(naechste[g.MERKMALE])[:, 1] * 100
        naechste["Day"] = [WOCHENTAGE[d.weekday()] for d in naechste["datum"]]
        naechste["hoechster"] = naechste["Risk"] == naechste["Risk"].max()

        # Säulen: der Tag mit dem höchsten Risiko ist dunkel, die anderen hell
        balken = alt.Chart(naechste).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("Day:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Risk:Q", title="Risk (%)", scale=alt.Scale(domain=[0, 110]), axis=alt.Axis(values=[0, 25, 50, 75, 100])),
            color=alt.condition(alt.datum.hoechster, alt.value(WEINROT), alt.value("#D9A5B3")),
        )
        # Die Zahl über jede Säule schreiben
        zahlen = alt.Chart(naechste).mark_text(dy=-8, fontWeight="bold", color=WEINROT).encode(
            x=alt.X("Day:N", sort=None), y="Risk:Q", text=alt.Text("Risk:Q", format=".0f"),
        )
        st.altair_chart((balken + zahlen).properties(height=220), width="stretch")

        hoch = naechste[naechste["hoechster"]].iloc[0]
        st.caption(f"Highest risk on {hoch['Day']}, {hoch['datum']:%d.%m.} ({hoch['Risk']:.0f} %). "
                   f"The model warns from {g.WARNSCHWELLE * 100:.0f} %.")


# Fusszeile
st.divider()
st.caption("Data: Agrometeo station Zizers · Open-Meteo. "
           "The app is a decision aid and not official crop protection advice.")

