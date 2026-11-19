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

import sqlite3

import altair as alt
import pandas as pd
import requests
import streamlit as st

import gemeinsam as g   # gemeinsame Daten und Funktionen (Datum, Agrometeo, Modell, Saison)

# Farben aus dem Konzept
WEINROT = "#7B1E3A"
GOLD = "#C9A227"
FARBEN = ["#D9EAD3", "#FFF2CC", "#F4CCCC"]  # grün, gelb, rot
AMPEL = ["geeignet", "knapp", "nicht möglich"]
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Wir spritzen nur mit Folpet 80 WG (wie auf der Seite Dosierung).
# Folpet ist nicht hitzeempfindlich, darum zählen in der Ampel nur Regen und Wind.

# Startwerte der Ampel: (gelb ab, rot ab, Einheit), noch mit dem Winzer bestätigen
STANDARD = {"Regen": (0.5, 2.0, "mm"), "Wind": (15.0, 25.0, "km/h")}

# Farbe für Tage, an denen der Belag der letzten Spritzung noch schützt
GRAU = "#EEEEEE"

# Formel 4 aus der Fachlogik: Ein Spritzbelag schützt etwa 10 Tage (mit dem Winzer bestätigen)
SCHUTZ_TAGE = 10


# ---------------------------------------------------------------------------
# Verbindung zum Journal: Wurde schon gespritzt?
# ---------------------------------------------------------------------------
def lade_spritzungen():
    """Holt alle Spritzungen aus dem Journal (gleiche Datenbank wie die Seite Journal)."""
    try:
        con = sqlite3.connect("daten/spritzplaner.db")
        df = pd.read_sql_query("SELECT datum, mittel FROM spritzungen", con)
        con.close()
    except Exception:
        # Gibt es die Tabelle noch nicht, ist einfach noch nichts gespritzt
        df = pd.DataFrame(columns=["datum", "mittel"])
    df["datum"] = pd.to_datetime(df["datum"])
    return df.sort_values("datum")


def pruefe_schutz(infektionen, spritzungen):
    """Gibt jeder Infektion einen Status: «gespritzt» oder «offen».

    gespritzt: Es wurde in den 10 Tagen vor der Infektion gespritzt (der Belag war schon da)
               oder nach der Infektion, aber noch vor der Frist.
    offen:     Weder noch, der Winzer muss noch spritzen.
    """
    status = []
    for _, infektion in infektionen.iterrows():
        ergebnis = "offen"
        for spritztag in spritzungen["datum"]:
            vorher_geschuetzt = spritztag <= infektion["start"] <= spritztag + pd.Timedelta(days=SCHUTZ_TAGE)
            rechtzeitig_nachher = infektion["start"] < spritztag <= infektion["frist"]
            if vorher_geschuetzt or rechtzeitig_nachher:
                ergebnis = "gespritzt"
        status.append(ergebnis)
    infektionen["status"] = status
    return infektionen


# ---------------------------------------------------------------------------
# Wetter von Open-Meteo
# ---------------------------------------------------------------------------
@st.cache_data
def lade_wetter(von, bis):
    """Lädt das stündliche Wetter von Open-Meteo."""

    parameter = {
        "latitude": g.ZIZERS_LAT,
        "longitude": g.ZIZERS_LON,
        "timezone": "Europe/Zurich",
        "hourly": "precipitation,wind_speed_10m",
        "start_date": str(von),
        "end_date": str(bis)
    }

    antwort = requests.get(
        g.open_meteo_url(bis),
        params=parameter,
        timeout=10
    )

    st.write("API-Status:", antwort.status_code)
    st.write("API-Antwort:", antwort.json())

    antwort.raise_for_status()

    daten = antwort.json()["hourly"]
    wetter = pd.DataFrame(daten)
    wetter["time"] = pd.to_datetime(wetter["time"])

    return wetter


# ---------------------------------------------------------------------------
# Ampel
# ---------------------------------------------------------------------------
def bewerte_tag(tag, wetter, sonntag_sperren):
    """Gibt Ampelstufe (0 grün, 1 gelb, 2 rot), beste Startzeit und Gründe für einen Tag zurück."""
    stunden = wetter[wetter["time"].dt.date == tag.date()].reset_index()

    # Beste Startzeit: Stunde zwischen 6 und 14 Uhr mit am wenigsten Regen in den 6 Stunden danach
    start, wenig_regen = 6, 999
    for h in range(6, 15):
        regen = stunden["precipitation"][h:h + 6].sum()
        if regen < wenig_regen:
            start, wenig_regen = h, regen

    fenster = stunden[start:start + 6]
    werte = {"Regen": fenster["precipitation"].sum(),
             "Wind": fenster["wind_speed_10m"].max()}

    stufe, gruende = 0, []
    for name, wert in werte.items():
        gelb, rot = st.session_state[name + "_gelb"], st.session_state[name + "_rot"]
        if wert >= gelb:
            stufe = max(stufe, 2 if wert >= rot else 1)  # der schlechteste Wert bestimmt die Farbe
            gruende.append(f"{name} {wert:.1f} {STANDARD[name][2]}")
    if sonntag_sperren and tag.weekday() == 6:
        stufe = 2
        gruende.append("Sonntag")
    return stufe, start, gruende


def standardwerte():
    """Setzt die Grenzwerte der Ampel auf die Startwerte zurück."""
    for name, (gelb, rot, einheit) in STANDARD.items():
        st.session_state[name + "_gelb"] = gelb
        st.session_state[name + "_rot"] = rot


# Beim ersten Öffnen der Seite die Startwerte setzen
if "Regen_gelb" not in st.session_state:
    standardwerte()

st.title("Kalender: Wann kann ich spritzen?")

# Das Datum wird links in der Seitenleiste gewählt und gilt für alle Seiten
heute = g.heute()
sonntag_sperren = st.checkbox("Sonntag sperren", value=True)

# Platzhalter, damit Ampel und Inkubationen oberhalb der Grenzwerte erscheinen
bereich_ampel = st.container()
bereich_inkubation = st.container()

with st.expander("Grenzwerte der Ampel"):
    for name, (gelb, rot, einheit) in STANDARD.items():
        g1, g2 = st.columns(2)
        g1.number_input(f"{name} gelb ab ({einheit})", key=name + "_gelb", step=0.5)
        g2.number_input(f"{name} rot ab ({einheit})", key=name + "_rot", step=0.5)
    st.button("Standardwerte", on_click=standardwerte)

# Modell trainieren (passiert nur beim ersten Mal, danach ist es gespeichert)
modell, dauer_pro_monat, ergebnis = g.trainiere_modell()

# Daten laden
tage = pd.date_range(heute, periods=14)
try:
    wetter = lade_wetter(heute, tage[-1].date())
except Exception as e:
    st.error(f"Fehler beim Laden: {type(e).__name__}: {e}")
    st.stop()

# Tageswerte vom 1.1. bis 14 Tage nach heute (aus gemeinsam.py):
# bis heute gemessen von Agrometeo, danach Prognose von Open-Meteo mit dem Modell
tageswetter = g.wetter_seit_neujahr(heute)
# Die Spritzsaison beginnt mit der Keimbereitschaft (Temperatursumme 140, siehe Wetter-Seite)
keimbereit = g.keimbereitschaft(tageswetter)
saison = g.in_saison(tageswetter["datum"], keimbereit)

# Infektionen der letzten 14 Tage und der nächsten 14 Tage, nur in der Spritzsaison
infektionen = tageswetter[tageswetter["infektion"] & saison
                          & (tageswetter["datum"] >= pd.Timestamp(heute) - pd.Timedelta(days=14))].copy()
infektionen["start"] = infektionen["datum"]
# Inkubationsdauer: echte Dauer von Agrometeo, für die Prognose der gelernte Monats-Durchschnitt
dauer = infektionen["dauer"] if "dauer" in infektionen else pd.Series(index=infektionen.index, dtype=float)
dauer = dauer.fillna(infektionen["datum"].dt.month.map(dauer_pro_monat)).fillna(10)
infektionen["ende"] = infektionen["start"] + pd.to_timedelta(dauer, unit="D")
# Formel 3: spritzen bis = Infektion + 80 % der Inkubationsdauer
infektionen["frist"] = (infektionen["start"] + (infektionen["ende"] - infektionen["start"]) * 0.8).dt.floor("D")

# Spritzungen aus dem Journal holen (nur bis «heute», wichtig für den Demo-Modus)
spritzungen = lade_spritzungen()
spritzungen = spritzungen[spritzungen["datum"] <= pd.Timestamp(heute)]
# Für jede Infektion prüfen: geschützt, behandelt oder offen?
infektionen = pruefe_schutz(infektionen, spritzungen)

# Laufende Inkubationen: Balken, die in die 14 Tage hineinreichen
laufend = infektionen[(infektionen["start"] <= tage[-1]) & (infektionen["ende"] > tage[0])].copy()
# Schon passierte Infektionen, deren Frist noch nicht vorbei ist
aktuell = laufend[(laufend["start"] <= tage[0]) & (laufend["frist"] >= tage[0])]
# Offen sind davon nur die, gegen die noch nicht gespritzt wurde
offen = aktuell[aktuell["status"] == "offen"]
abgedeckt = aktuell[aktuell["status"] == "gespritzt"]

# Bis wann schützt die letzte Spritzung? (keine Spritzung: dann schützt nichts)
if len(spritzungen) > 0:
    geschuetzt_bis = spritzungen["datum"].iloc[-1] + pd.Timedelta(days=SCHUTZ_TAGE)
else:
    geschuetzt_bis = None

# Jeden Tag bewerten
bewertung = [bewerte_tag(tag, wetter, sonntag_sperren) for tag in tage]

with bereich_ampel:
    # Letzte Spritzung aus dem Journal anzeigen
    if len(spritzungen) > 0:
        letzte = spritzungen.iloc[-1]
        if geschuetzt_bis >= pd.Timestamp(heute):
            st.success(f"Letzte Spritzung laut Journal: {letzte['datum']:%d.%m.} mit {letzte['mittel']} "
                       f"→ geschützt bis {geschuetzt_bis:%d.%m.}")
        else:
            st.warning(f"Letzte Spritzung laut Journal: {letzte['datum']:%d.%m.} mit {letzte['mittel']} "
                       f"→ Schutz vorbei seit {geschuetzt_bis:%d.%m.}")
    else:
        st.caption("Noch keine Spritzung im Journal erfasst.")

    # Frist-Box (weinrot): die nächste Frist bestimmt die Planung
    if len(offen) > 0:
        infektion = offen.sort_values("frist").iloc[0]
        frist = infektion["frist"]
        gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= frist]
        if len(gute) > 0:
            start = bewertung[list(tage).index(gute[0])][1]
            empfehlung = f"Empfohlen: {WOCHENTAGE[gute[0].weekday()]}, {gute[0]:%d.%m.} ab {start} Uhr"
        else:
            empfehlung = "Kein grüner Tag vor der Frist. Prüfe die gelben Tage."
        # Das Wetter am Tag der Infektion (von Open-Meteo), damit man sieht, warum gewarnt wird
        wetter_text = f"{infektion['niederschlag_mm']:.1f} mm Regen, {infektion['temp_mittel']:.0f} °C"
        # Gibt es noch weitere offene Infektionen? Dann darauf hinweisen.
        if len(offen) > 1:
            weitere = f"<br>Dazu {len(offen) - 1} weitere Infektion(en), siehe «Laufende Inkubationen»."
        else:
            weitere = ""
        st.markdown(f"""
        <div style="background-color: {WEINROT}; color: white; padding: 20px; border-radius: 15px;">
            <p style="margin: 0; color: #F3D9DF;">Infektion am {infektion['start']:%d.%m.} · Wetter an diesem Tag: {wetter_text}</p>
            <h3 style="margin: 0; color: white;">Spritzen bis {WOCHENTAGE[frist.weekday()]}, {frist:%d.%m.}</h3>
            <p style="margin: 0;">{empfehlung}{weitere}</p>
        </div>""", unsafe_allow_html=True)
        st.caption("Frist = letzter sicherer Spritztag, bevor die Krankheit ausbricht.")
    else:
        frist, gute = None, []
        if g.in_saison(pd.Series([pd.Timestamp(heute)]), keimbereit).iloc[0]:
            if len(abgedeckt) > 0:
                st.info(f"Keine offene Infektion. {len(abgedeckt)} Infektion(en) sind durch "
                        "deine Spritzungen abgedeckt. Spritzen ist im Moment nicht nötig.")
            else:
                st.info("Keine offene Infektion. Spritzen ist im Moment nicht nötig.")
        else:
            if keimbereit is None or pd.Timestamp(heute) < keimbereit:
                st.info("Die Spritzsaison hat noch nicht begonnen: Die Sporen sind noch nicht "
                        "keimbereit (Temperatursumme unter 140, siehe Wetter-Seite).")
            else:
                st.info("Die Spritzsaison ist vorbei (ab Ende August). "
                        "Gegen Falschen Mehltau wird jetzt nicht gespritzt.")

    # Spritzfenster: Überschrift links, Legende der Farben rechts
    titel, legende = st.columns([1, 2], vertical_alignment="bottom")
    titel.subheader("Spritzfenster: 14 Tage")

    def kaestchen(farbe, rand="1px solid #CCCCCC"):
        """Kleines farbiges Quadrat für die Legende."""
        return (f"<span style='display:inline-block; width:12px; height:12px; background:{farbe}; "
                f"border:{rand}; border-radius:3px; margin:0 4px 0 14px; vertical-align:middle;'></span>")

    legende.markdown(
        "<div style='text-align:right; font-size:13px;'>"
        + kaestchen(FARBEN[0]) + "Geeignet"
        + kaestchen(FARBEN[1]) + "Knapp"
        + kaestchen(FARBEN[2]) + "Nicht möglich"
        + kaestchen(GRAU) + "Geschützt"
        + kaestchen("white", f"3px solid {GOLD}") + "Empfohlen"
        + "</div>", unsafe_allow_html=True)

    spalten = st.columns(7) + st.columns(7)
    for spalte, tag, (stufe, start, gruende) in zip(spalten, tage, bewertung):
        marken = []
        if tag == tage[0]:
            marken.append("heute")
        if len(gute) > 0 and tag == gute[-1] and tag != gute[0]:
            marken.append("letzte Chance")
        if tag == frist:
            marken.append("Frist")
        if tag in list(spritzungen["datum"]):
            marken.append("gespritzt")

        # Noch geschützt und keine offene Infektion: Spritzen ist nicht nötig, also keine Ampel
        if len(offen) == 0 and geschuetzt_bis is not None and tag <= geschuetzt_bis:
            farbe, text, gruende = GRAU, "geschützt<br>nicht nötig", []
        else:
            farbe, text = FARBEN[stufe], AMPEL[stufe] + (f"<br>ab {start} Uhr" if stufe < 2 else "")
        rahmen = f"3px solid {GOLD}" if len(gute) > 0 and tag == gute[0] else "1px solid #CCCCCC"

        spalte.markdown(f"""
        <div style="background-color: {farbe}; border: {rahmen}; border-radius: 10px;
                    padding: 8px; min-height: 150px; font-size: 13px; margin-bottom: 8px;">
            <b>{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}</b><br>{text}<br>
            <small>{", ".join(gruende)}</small><br>
            <b style="color: {WEINROT};">{" · ".join(marken)}</b>
        </div>""", unsafe_allow_html=True)

with bereich_inkubation:
    st.subheader("Laufende Inkubationen")
    if len(laufend) == 0:
        st.write("Keine laufenden Inkubationen in diesen 14 Tagen.")
    else:
        # Name des Balkens, z. B. "06.08. · offen" oder "20.07. · gespritzt (Prognose)"
        laufend["name"] = (laufend["start"].dt.strftime("%d.%m.") + " · " + laufend["status"]
                           + laufend["quelle"].map({"gemessen": "", "geschätzt": " (geschätzt)", "Prognose": " (Prognose)"}))
        # Farbe: gemessen offen = weinrot, gemessen gespritzt = grün,
        # geschätzt (Prognose) = dieselben Farben, aber heller
        laufend["art"] = laufend["status"]
        prognose_zeile = laufend["quelle"] != "gemessen"   # vom Modell geschätzt
        laufend.loc[prognose_zeile & (laufend["status"] == "offen"), "art"] = "offen (Prognose)"
        laufend.loc[prognose_zeile & (laufend["status"] == "gespritzt"), "art"] = "gespritzt (Prognose)"
        laufend["frist_text"] = "spritzen bis " + laufend["frist"].dt.strftime("%d.%m.")

        achse = alt.X("start:T", title=None, scale=alt.Scale(domain=[tage[0], tage[-1] + pd.Timedelta(days=1)]),
                      axis=alt.Axis(format="%d.%m.", tickCount=14, grid=True))
        zeile = alt.Y("name:N", title=None, sort=alt.SortField("start"))  # nach Datum sortiert
        farben = alt.Scale(domain=["offen", "gespritzt", "offen (Prognose)", "gespritzt (Prognose)"],
                           range=[WEINROT, "#6AA84F", "#D9A5B3", "#C5E0B4"])
        # Was beim Darüberfahren mit der Maus erscheint (ohne «art», mit schönen Titeln)
        info_balken = [alt.Tooltip("start:T", title="Start", format="%d.%m."),
                       alt.Tooltip("name:N", title="Name"),
                       alt.Tooltip("ende:T", title="Ende", format="%d.%m.")]
        info_frist = [alt.Tooltip("name:N", title="Name"),
                      alt.Tooltip("frist:T", title="Spritzen bis", format="%d.%m.")]

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
            color=alt.condition(alt.datum.art == "offen", alt.value("white"), alt.value("#5C4A12")),
            tooltip=info_frist)

        diagramm = (balken + striche + texte).properties(height=40 * len(laufend) + 20)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Balken: vom Infektionstag bis zum Ende der Inkubation. "
                   "Goldener Strich: bis dann muss gespritzt sein.")

# Erklärung des Modells (aufklappbar)
with st.expander("Wie erkennt der Kalender Infektionen? (Machine Learning)"):
    st.markdown(
        "Ein **Random Forest** (300 Entscheidungsbäume) hat aus den Agrometeo-Daten "
        "**2019 bis 2025** (7 Jahre) gelernt, bei welchem Wetter es eine Infektion gibt: "
        "Temperatur (min, Mittel, max), Regen am Tag und am Vortag sowie die Jahreszeit. "
        "Für vergangene Tage nimmt der Kalender die gemessenen Infektionen von Agrometeo. "
        "Für die Prognose-Tage schaut das Modell sich das Wetter von Open-Meteo an und sagt, "
        "ob es eine Infektion gibt: ja oder nein. Gewarnt wird nur in der Spritzsaison: "
        "ab der Keimbereitschaft (Temperatursumme 140) bis Ende August."
    )
    st.markdown(f"**Test mit der Saison {g.TESTJAHR}** (Tage, die das Modell beim Lernen nie gesehen hat):")
    k1, k2, k3 = st.columns(3)
    k1.metric("Infektionen erkannt", f"{ergebnis['erkannt']} von {ergebnis['total']}")
    k2.metric("Verpasst", ergebnis["verpasst"])
    k3.metric("Fehlalarme", ergebnis["fehlalarme"])
    st.caption("Eine verpasste Infektion ist gefährlicher als ein Fehlalarm. "
               "Das Modell lernt mit den Messungen der Station, bekommt im Kalender aber "
               "das Wetter von Open-Meteo. Diese Werte weichen leicht voneinander ab.")

# Fusszeile
st.divider()
st.caption("Datenquellen: Wetter von Open-Meteo, Lerndaten für das Modell von Agrometeo (Station Zizers). "
           "Die App ist eine Entscheidungshilfe und keine offizielle Pflanzenschutzberatung.")