
# Hier wird die Seite Kalender codiert.
"""Kalender: Wann kann ich spritzen?

Die Seite erkennt Infektionen mit einem eigenen Machine-Learning-Modell:
Das Modell hat aus den Agrometeo-Daten 2019 bis 2025 gelernt, bei welchem
Wetter es eine Infektion gibt. Für vergangene Tage nimmt die Seite die
gemessenen Infektionen von Agrometeo (mit der echten Inkubationsdauer).
Für die Prognose-Tage schaut das Modell sich das Wetter von Open-Meteo an
und sagt, an welchen Tagen es eine Infektion gibt. Zusammen mit dem stündlichen Wetter zeigt die Seite für
14 Tage eine Ampel, wann man spritzen kann.

Das Datum («Heute ist der»), die Agrometeo-Daten, die Keimbereitschaft und das
Modell kommen aus gemeinsam.py, damit Kalender und Wetter-Seite gleich rechnen.

KI-Hinweis: Dieser Code wurde mit Claude (Anthropic, Claude Opus 5.5) am
17.11.2026 generiert und danach von uns geprüft und angepasst.
"""

import altair as alt
import pandas as pd
import streamlit as st

import gemeinsam as g   # gemeinsame Daten und Funktionen (Datum, Agrometeo, Modell, Saison)

# Farben und Wochentage stehen in gemeinsam.py, damit Kalender und Dashboard gleich aussehen
WEINROT = g.WEINROT
GOLD = g.GOLD
WOCHENTAGE = g.WOCHENTAGE

# Wir spritzen nur mit Folpet 80 WG (wie auf der Seite Dosierung).
# Folpet ist nicht hitzeempfindlich, darum zählen in der Ampel nur Regen und Wind.

# Startwerte der Ampel und Schutzdauer stehen in gemeinsam.py (g.STANDARD, g.SCHUTZ_TAGE)


# ---------------------------------------------------------------------------
# Ampel (Spritzungen, Infektionen, Wetter und Bewertung kommen aus gemeinsam.py)
# ---------------------------------------------------------------------------
def standardwerte():
    """Setzt die Grenzwerte der Ampel auf die Startwerte zurück."""
    for name, (gelb, rot, einheit) in g.STANDARD.items():
        st.session_state[name + "_gelb"] = gelb
        st.session_state[name + "_rot"] = rot


# Beim ersten Öffnen der Seite die Startwerte setzen
if "Rain_gelb" not in st.session_state:
    standardwerte()

st.title("Calendar: When can I spray?")

# Das Datum wird links in der Seitenleiste gewählt und gilt für alle Seiten
heute = g.heute()
sonntag_sperren = st.checkbox("Block Sundays", value=True)

# Platzhalter, damit Ampel und Inkubationen oberhalb der Grenzwerte erscheinen
bereich_ampel = st.container()
bereich_inkubation = st.container()

with st.expander("Traffic light thresholds"):
    for name, (gelb, rot, einheit) in g.STANDARD.items():
        g1, g2 = st.columns(2)
        g1.number_input(f"{name} yellow from ({einheit})", key=name + "_gelb", step=0.5)
        g2.number_input(f"{name} red from ({einheit})", key=name + "_rot", step=0.5)
    st.button("Default values", on_click=standardwerte)

# Modell trainieren (passiert nur beim ersten Mal, danach ist es gespeichert)
modell, dauer_pro_monat, ergebnis = g.trainiere_modell()

# Daten laden
tage = pd.date_range(heute, periods=14)
try:
    wetter = g.lade_wetter(heute, tage[-1].date())
except Exception:
    st.error("The weather from Open-Meteo could not be loaded.")
    st.stop()

# Tageswerte vom 1.1. bis 14 Tage nach heute (aus gemeinsam.py):
# bis heute gemessen von Agrometeo, danach Prognose von Open-Meteo mit dem Modell
tageswetter = g.wetter_seit_neujahr(heute)
# Die Spritzsaison beginnt mit der Keimbereitschaft (Temperatursumme 140, siehe Wetter-Seite)
keimbereit = g.keimbereitschaft(tageswetter)

# Spritzungen aus dem Journal und alle Infektionen mit Frist und Status (aus gemeinsam.py)
spritzungen = g.lade_spritzungen(heute)
infektionen = g.lade_infektionen(heute)
# Nur die Infektionen der letzten 14 Tage und der nächsten 14 Tage
infektionen = infektionen[infektionen["start"] >= pd.Timestamp(heute) - pd.Timedelta(days=14)]

# Laufende Inkubationen: Balken, die in die 14 Tage hineinreichen
laufend = infektionen[(infektionen["start"] <= tage[-1]) & (infektionen["ende"] > tage[0])].copy()
# Schon passierte Infektionen, deren Frist noch nicht vorbei ist
aktuell = laufend[(laufend["start"] <= tage[0]) & (laufend["frist"] >= tage[0])]
# Offen sind davon nur die, gegen die noch nicht gespritzt wurde
offen = aktuell[aktuell["status"] == "open"]
abgedeckt = aktuell[aktuell["status"] == "sprayed"]

# Bis wann schützt die letzte Spritzung? (keine Spritzung: dann schützt nichts)
if len(spritzungen) > 0:
    geschuetzt_bis = spritzungen["datum"].iloc[-1] + pd.Timedelta(days=g.SCHUTZ_TAGE)
else:
    geschuetzt_bis = None

# Jeden Tag bewerten
bewertung = [g.bewerte_tag(tag, wetter, sonntag_sperren) for tag in tage]

with bereich_ampel:
    # Letzte Spritzung aus dem Journal anzeigen
    if len(spritzungen) > 0:
        letzte = spritzungen.iloc[-1]
        if geschuetzt_bis >= pd.Timestamp(heute):
            st.success(f"Last spraying according to journal: {letzte['datum']:%d.%m.} with {letzte['mittel']} "
                       f"→ protected until {geschuetzt_bis:%d.%m.}")
        else:
            st.warning(f"Last spraying according to journal: {letzte['datum']:%d.%m.} with {letzte['mittel']} "
                       f"→ protection ended on {geschuetzt_bis:%d.%m.}")
    else:
        st.caption("No spraying recorded in the journal yet.")

    # Frist-Box (weinrot): die nächste Frist bestimmt die Planung
    if len(offen) > 0:
        infektion = offen.sort_values("frist").iloc[0]
        frist = infektion["frist"]
        gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= frist]
        if len(gute) > 0:
            start = bewertung[list(tage).index(gute[0])][1]
            empfehlung = f"Recommended: {WOCHENTAGE[gute[0].weekday()]}, {gute[0]:%d.%m.} from {start}:00"
        else:
            empfehlung = "No green day before the deadline. Check the yellow days."
        # Das Wetter am Tag der Infektion (von Open-Meteo), damit man sieht, warum gewarnt wird
        wetter_text = f"{infektion['niederschlag_mm']:.1f} mm rain, {infektion['temp_mittel']:.0f} °C"
        # Gibt es noch weitere offene Infektionen? Dann darauf hinweisen.
        if len(offen) > 1:
            weitere = f"<br>Plus {len(offen) - 1} more infection(s), see «Ongoing incubations»."
        else:
            weitere = ""
        st.markdown(f"""
        <div style="background-color: {WEINROT}; color: white; padding: 20px; border-radius: 15px;">
            <p style="margin: 0; color: #F3D9DF;">Infection on {infektion['start']:%d.%m.} · Weather on that day: {wetter_text}</p>
            <h3 style="margin: 0; color: white;">Spray by {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h3>
            <p style="margin: 0;">{empfehlung}{weitere}</p>
        </div>""", unsafe_allow_html=True)
        st.caption("Deadline = last safe spray day before the disease breaks out.")
    else:
        frist, gute = None, []
        if g.in_saison(pd.Series([pd.Timestamp(heute)]), keimbereit).iloc[0]:
            if len(abgedeckt) > 0:
                st.info(f"No open infection. {len(abgedeckt)} infection(s) are covered by "
                        "your sprayings. Spraying is not necessary at the moment.")
            else:
                st.info("No open infection. Spraying is not necessary at the moment.")
        else:
            if keimbereit is None or pd.Timestamp(heute) < keimbereit:
                st.info("The spray season has not started yet: the spores are not yet "
                        "ready to germinate (temperature sum below 140, see Weather page).")
            else:
                st.info("The spray season is over (from the end of August). "
                        "No spraying against downy mildew now.")

    # Spritzfenster: 14 Tage (dieselbe Anzeige wie auf dem Dashboard, aus gemeinsam.py)
    g.zeige_spritzfenster("Spray windows: 14 days", tage, bewertung, gute, frist,
                          offen, geschuetzt_bis, spritzungen)

with bereich_inkubation:
    st.subheader("Ongoing incubations")
    if len(laufend) == 0:
        st.write("No ongoing incubations in these 14 days.")
    else:
        # Name des Balkens, z. B. "06.08. · open" oder "20.07. · sprayed (forecast)"
        laufend["name"] = (laufend["start"].dt.strftime("%d.%m.") + " · " + laufend["status"]
                           + laufend["quelle"].map({"measured": "", "estimated": " (estimated)", "forecast": " (forecast)"}))
        # Farbe: gemessen offen = weinrot, gemessen gespritzt = grün,
        # geschätzt (Prognose) = dieselben Farben, aber heller
        laufend["art"] = laufend["status"]
        prognose_zeile = laufend["quelle"] != "measured"   # vom Modell geschätzt
        laufend.loc[prognose_zeile & (laufend["status"] == "open"), "art"] = "open (forecast)"
        laufend.loc[prognose_zeile & (laufend["status"] == "sprayed"), "art"] = "sprayed (forecast)"
        laufend["frist_text"] = "spray by " + laufend["frist"].dt.strftime("%d.%m.")

        achse = alt.X("start:T", title=None, scale=alt.Scale(domain=[tage[0], tage[-1] + pd.Timedelta(days=1)]),
                      axis=alt.Axis(format="%d.%m.", tickCount=14, grid=True))
        zeile = alt.Y("name:N", title=None, sort=alt.SortField("start"))  # nach Datum sortiert
        farben = alt.Scale(domain=["open", "sprayed", "open (forecast)", "sprayed (forecast)"],
                           range=[WEINROT, "#6AA84F", "#D9A5B3", "#C5E0B4"])
        # Was beim Darüberfahren mit der Maus erscheint (ohne «art», mit schönen Titeln)
        info_balken = [alt.Tooltip("start:T", title="Start", format="%d.%m."),
                       alt.Tooltip("name:N", title="Name"),
                       alt.Tooltip("ende:T", title="End", format="%d.%m.")]
        info_frist = [alt.Tooltip("name:N", title="Name"),
                      alt.Tooltip("frist:T", title="Spray by", format="%d.%m.")]

        # Balken vom Infektionstag bis zum Ende der Inkubation
        balken = alt.Chart(laufend).mark_bar(height=18, cornerRadius=4, clip=True).encode(
            x=achse, x2="ende:T", y=zeile,
            color=alt.Color("art:N", scale=farben, title=None, legend=alt.Legend(orient="bottom")),
            tooltip=info_balken)
        # Goldener Strich bei der Frist, Beschriftung rechts daneben
        striche = alt.Chart(laufend).mark_tick(color=GOLD, thickness=3, size=24, clip=True).encode(
            x="frist:T", y=zeile, tooltip=info_frist)
        # Auf dem dunkelroten Balken weisse Schrift, sonst dunkle Schrift (besser lesbar)
        texte = alt.Chart(laufend).mark_text(align="left", dx=6, fontWeight="bold", clip=True).encode(
            x="frist:T", y=zeile, text="frist_text:N",
            color=alt.condition(alt.datum.art == "open", alt.value("white"), alt.value("#5C4A12")),
            tooltip=info_frist)

        diagramm = (balken + striche + texte).properties(height=40 * len(laufend) + 20)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Bar: from the day of infection to the end of incubation. "
                   "Gold line: spraying must be done by then.")

# Erklärung des Modells (aufklappbar)
with st.expander("How does the calendar detect infections? (Machine Learning)"):
    st.markdown(
        "A **Random Forest** (300 decision trees) learned from the Agrometeo data "
        "**2019 to 2025** (7 years) which weather leads to an infection: "
        "temperature (min, mean, max), rain on the day and the day before, and the time of year. "
        "For past days with Agrometeo data, the calendar uses the measured infections from Agrometeo. "
        "For all other days (past days without Agrometeo data and the forecast), the model looks at "
        "the weather from Open-Meteo and says whether there will be an infection: yes or no. Warnings are only given during the spray season: "
        "from germination readiness (temperature sum 140) until the end of August."
    )
    st.markdown(f"**Test with the {g.TESTJAHR} season** (days the model never saw during training):")
    k1, k2, k3 = st.columns(3)
    k1.metric("Infections detected", f"{ergebnis['erkannt']} of {ergebnis['total']}")
    k2.metric("Missed", ergebnis["verpasst"])
    k3.metric("False alarms", ergebnis["fehlalarme"])
    st.caption("A missed infection is more dangerous than a false alarm. "
               "The model learns from the station's measurements, but in the calendar it gets "
               "the weather from Open-Meteo. These values differ slightly.")

# Fusszeile
st.divider()
st.caption("Data sources: weather from Open-Meteo, training data for the model from Agrometeo (Zizers station). "
           "The app is a decision aid and not official crop protection advice.")
