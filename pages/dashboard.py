# Hier wird die Seite Dashboard codiert.
"""Dashboard: Übersicht über alles Wichtige auf einen Blick.

Die Seite beantwortet in erster Linie eine Frage: Muss ich spritzen, und bis wann?
Darunter stehen vier Kennzahlen, das Spritzfenster der nächsten 7 Tage, die
Infektionen der letzten 3 Wochen und der Ausblick des Modells.

Die Seite rechnet gleich wie der Kalender (gleiche Frist-Formel, gleiche Ampel,
gleiche Daten aus gemeinsam.py), damit beide Seiten immer dasselbe sagen.

KI-Hinweis: Dieser Code wurde mit Claude (Anthropic, Claude Sonnet 5.5) am
21.11.2026 generiert und danach von uns geprüft und angepasst.
"""

import datetime
import sqlite3

import pandas as pd
import requests
import streamlit as st

import gemeinsam as g   # gemeinsame Daten und Funktionen (Datum, Agrometeo, Modell, Saison)

# Farben aus dem Konzept
WEINROT = "#7B1E3A"
GOLD = "#C9A227"
GRUEN = "#3B6B3F"
GELB = "#E6C16B"
ROT = "#9B2D2D"
GRAU = "#E4DFD6"
RAND = "#E8E2D8"
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Startwerte der Ampel (gleich wie im Kalender). Hat der Winzer sie im Kalender
# geändert, nehmen wir seine Werte aus st.session_state.
STANDARD = {"Regen": (0.5, 2.0, "mm"), "Wind": (15.0, 25.0, "km/h")}

# Formel 4 aus der Fachlogik: Ein Spritzbelag schützt etwa 10 Tage
SCHUTZ_TAGE = 10

# Farben der Status-Schilder in der Infektionsliste: (Hintergrund, Schrift)
STATUS_FARBEN = {
    "offen": ("#F4D6D6", ROT),
    "verpasst": (ROT, "white"),
    "geschützt": ("#DDEBDD", "#2F5E34"),
    "behandelt": ("#DDEBDD", "#2F5E34"),
    "Prognose": ("#E8E1EE", "#5B3A6B"),
}
ADJEKTIV = {"!!!": "Starke", "!!": "Mittlere", "!": "Geringe", "?": "Mögliche"}


def html(text):
    """Zeigt HTML an (Kurzform, damit der Code unten übersichtlich bleibt)."""
    st.markdown(text, unsafe_allow_html=True)


def tag_lang(tag):
    """Datum als Text, z. B. «Sa, 09.05.»."""
    return f"{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.}"


def stufe_text(gradstunden):
    """Gibt Ausrufezeichen und Name der Infektionsstufe zurück (70 / 100 / 200 Gradstunden).

    Für Prognose-Tage gibt es keine gemessenen Gradstunden, dort ist die Stufe unbekannt.
    """
    if pd.isna(gradstunden):
        return "?", "unbekannt"
    if gradstunden >= 200:
        return "!!!", "stark"
    if gradstunden >= 100:
        return "!!", "mittel"
    return "!", "gering"


# ---------------------------------------------------------------------------
# Daten aus der Datenbank (gleiche Datenbank wie Parzellen und Journal)
# ---------------------------------------------------------------------------
def lade_spritzungen():
    """Holt alle Spritzungen aus dem Journal. Gibt es noch keine, kommt eine leere Tabelle zurück."""
    try:
        con = sqlite3.connect("daten/spritzplaner.db")
        df = pd.read_sql_query("SELECT datum, mittel FROM spritzungen", con)
        con.close()
    except Exception:
        df = pd.DataFrame(columns=["datum", "mittel"])
    df["datum"] = pd.to_datetime(df["datum"])
    return df.sort_values("datum")


def lade_parzellenname():
    """Name der ersten Parzelle für den Untertitel (sonst nur «Zizers»)."""
    try:
        con = sqlite3.connect("daten/spritzplaner.db")
        namen = pd.read_sql_query("SELECT name FROM parzellen", con)["name"]
        con.close()
        if len(namen) > 0:
            return f"Zizers {namen.iloc[0]}"
    except Exception:
        pass
    return "Zizers"


# ---------------------------------------------------------------------------
# Wetter von Open-Meteo und Ampel (gleich wie im Kalender)
# ---------------------------------------------------------------------------
@st.cache_data
def lade_wetter(von, bis):
    """Lädt das stündliche Wetter (Regen, Wind) für Zizers von Open-Meteo."""
    parameter = {"latitude": g.ZIZERS_LAT, "longitude": g.ZIZERS_LON, "timezone": "Europe/Zurich",
                 "hourly": "precipitation,wind_speed_10m",
                 "start_date": str(von), "end_date": str(bis)}
    daten = requests.get(g.open_meteo_url(bis), params=parameter, timeout=10).json()["hourly"]
    wetter = pd.DataFrame(daten)
    wetter["time"] = pd.to_datetime(wetter["time"])
    return wetter


def bewerte_tag(tag, wetter, sonntag_sperren=True):
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
        gelb = st.session_state.get(name + "_gelb", STANDARD[name][0])
        rot = st.session_state.get(name + "_rot", STANDARD[name][1])
        if wert >= gelb:
            stufe = max(stufe, 2 if wert >= rot else 1)   # der schlechteste Wert bestimmt die Farbe
            gruende.append(f"{name} {wert:.1f} {STANDARD[name][2]}".replace(".", ","))
    if sonntag_sperren and tag.weekday() == 6:
        stufe = 2
        gruende.append("Sonntag")
    return stufe, start, gruende


def bestimme_status(infektion, spritzungen, heute):
    """Status einer Infektion: Prognose, geschützt, behandelt, verpasst oder offen."""
    if infektion["start"] > heute:
        return "Prognose"
    for spritztag in spritzungen["datum"]:
        if spritztag <= infektion["start"] <= spritztag + pd.Timedelta(days=SCHUTZ_TAGE):
            return "geschützt"      # der Belag war schon da, als die Infektion kam
        if infektion["start"] < spritztag <= infektion["frist"]:
            return "behandelt"      # rechtzeitig nach der Infektion gespritzt
    if infektion["frist"] < heute:
        return "verpasst"           # Frist abgelaufen, ohne dass gespritzt wurde
    return "offen"                  # man muss noch handeln


# ---------------------------------------------------------------------------
# Daten laden und berechnen
# ---------------------------------------------------------------------------
heute = pd.Timestamp(g.heute())   # das Datum aus der Seitenleiste («Heute ist der»)
demo = g.heute() != datetime.date.today()

# Modell (nur für die durchschnittliche Inkubationsdauer pro Monat bei Prognose-Infektionen)
modell, dauer_pro_monat, ergebnis = g.trainiere_modell()

# Tageswerte vom 1.1. bis 14 Tage nach heute: bis heute gemessen, danach Prognose
tageswetter = g.wetter_seit_neujahr(heute.date())
keimbereit = g.keimbereitschaft(tageswetter)
saison = g.in_saison(tageswetter["datum"], keimbereit)

# Alle Infektionen der Spritzsaison, mit Inkubationsende und Frist
infektionen = tageswetter[tageswetter["infektion"] & saison].copy()
infektionen["start"] = infektionen["datum"]
# Inkubationsdauer: echte Dauer von Agrometeo, für die Prognose der gelernte Monats-Durchschnitt
dauer = infektionen["dauer"] if "dauer" in infektionen else pd.Series(index=infektionen.index, dtype=float)
dauer = dauer.fillna(infektionen["datum"].dt.month.map(dauer_pro_monat)).fillna(10)
infektionen["ende"] = infektionen["start"] + pd.to_timedelta(dauer, unit="D")
# Formel 3: spritzen bis = Infektion + 80 % der Inkubationsdauer
infektionen["frist"] = (infektionen["start"] + (infektionen["ende"] - infektionen["start"]) * 0.8).dt.floor("D")

# Spritzungen aus dem Journal (nur bis «heute», wichtig für den Demo-Modus)
spritzungen = lade_spritzungen()
spritzungen = spritzungen[spritzungen["datum"] <= heute]
infektionen["status"] = [bestimme_status(zeile, spritzungen, heute) for _, zeile in infektionen.iterrows()]

# Wichtigste Gruppen
offen = infektionen[infektionen["status"] == "offen"].sort_values("frist")
laufend = infektionen[(infektionen["start"] <= heute) & (infektionen["ende"] > heute)]
abgedeckt = infektionen[infektionen["status"].isin(["geschützt", "behandelt"]) & (infektionen["frist"] >= heute)]

# Bis wann schützt die letzte Spritzung?
if len(spritzungen) > 0:
    letzte = spritzungen.iloc[-1]
    geschuetzt_bis = letzte["datum"] + pd.Timedelta(days=SCHUTZ_TAGE)
else:
    letzte, geschuetzt_bis = None, None
belag_aktiv = geschuetzt_bis is not None and geschuetzt_bis >= heute

# Spritzfenster: 7 Tage Ampel
tage = pd.date_range(heute, periods=7)
try:
    wetter = lade_wetter(heute.date(), tage[-1].date())
    bewertung = [bewerte_tag(tag, wetter) for tag in tage]
except Exception:
    wetter, bewertung = None, None

# Der wichtigste Fall: die Infektion mit der nächsten Frist
fokus = offen.iloc[0] if len(offen) > 0 else None
if fokus is not None and bewertung is not None:
    gute = [tag for tag, b in zip(tage, bewertung) if b[0] == 0 and tag <= fokus["frist"]]
else:
    gute = []


# ---------------------------------------------------------------------------
# Hauptmeldung: drei Varianten (rot = handeln, grün = geschützt, neutral = kein Risiko)
# ---------------------------------------------------------------------------
if fokus is not None:
    variante = "rot"
    zeichen, stufe_name = stufe_text(fokus["gradstunden_bn"])
    belag = f"Spritzbelag aktiv bis {tag_lang(geschuetzt_bis)}." if belag_aktiv else "Kein Spritzbelag aktiv."
    if len(gute) > 0:
        start = bewertung[list(tage).index(gute[0])][1]
        empfehlung = f"Nächster geeigneter Tag: {tag_lang(gute[0])} ab {start} Uhr."
    elif bewertung is None:
        empfehlung = "Das Wetter konnte nicht geladen werden."
    else:
        empfehlung = "Kein grüner Tag vor der Frist. Prüfe die gelben Tage im Kalender."
    gradstunden = fokus["gradstunden_bn"]
    if pd.isna(gradstunden):
        staerke = f"{ADJEKTIV[zeichen]} Infektion."
    else:
        staerke = f"{ADJEKTIV[zeichen]} Infektion ({gradstunden:.0f} Gradstunden)."
    weitere = f" Dazu {len(offen) - 1} weitere offene Infektion(en)." if len(offen) > 1 else ""

    kicker = "INFEKTIONS-ALARM"
    titel = f"Infektion {zeichen} am {fokus['start']:%d.%m.} – spritzen bis {tag_lang(fokus['frist'])}"
    text = f"{staerke} {belag} {empfehlung}{weitere}"
    ueberschrift = "Guten Morgen. Heute ist Handeln gefragt."
    hintergrund, schrift, knopf_hell = WEINROT, "white", "#F3D9DF"

elif belag_aktiv:
    variante = "grün"
    kicker = "GESCHÜTZT"
    titel = f"Geschützt bis {tag_lang(geschuetzt_bis)}"
    if len(abgedeckt) > 0:
        text = (f"Letzte Spritzung am {letzte['datum']:%d.%m.} mit {letzte['mittel']}. "
                f"{len(abgedeckt)} Infektion(en) sind damit abgedeckt. Es gibt keine offene Infektion.")
    else:
        text = f"Letzte Spritzung am {letzte['datum']:%d.%m.} mit {letzte['mittel']}. Es gibt keine offene Infektion."
    ueberschrift = "Guten Morgen. Alles unter Kontrolle."
    hintergrund, schrift, knopf_hell = GRUEN, "white", "#DDEBDD"

else:
    variante = "neutral"
    kicker = "KEIN RISIKO"
    if keimbereit is None or heute < keimbereit:
        titel = "Die Spritzsaison hat noch nicht begonnen"
        text = (f"Die Sporen sind noch nicht keimbereit (Temperatursumme unter {g.KEIMBEREIT_AB}). "
                "Es muss nichts gespritzt werden.")
    elif not g.in_saison(pd.Series([heute]), keimbereit).iloc[0]:
        titel = "Die Spritzsaison ist vorbei"
        text = "Gegen Falschen Mehltau wird jetzt nicht mehr gespritzt."
    else:
        titel = "Keine offene Infektion"
        text = "Spritzen ist im Moment nicht nötig."
    ueberschrift = "Guten Morgen. Heute ist kein Handeln nötig."
    hintergrund, schrift, knopf_hell = "#EFEAE2", "#3A2A30", "#5A4A50"


# ---------------------------------------------------------------------------
# Darstellung
# ---------------------------------------------------------------------------
# Styles für die Hauptmeldung und ihre Buttons (Streamlit-Buttons kann man nicht in HTML einbauen,
# darum bekommt der Container einen Namen (key) und wird per CSS eingefärbt)
knopf_text = WEINROT if variante == "rot" else (GRUEN if variante == "grün" else "#3A2A30")
st.markdown(f"""<style>
.st-key-alarm {{ background:{hintergrund}; border-radius:20px; padding:26px 30px; }}
.st-key-btn_kalender button {{ background:white; border:none; border-radius:10px; }}
.st-key-btn_kalender button p {{ color:{knopf_text}; font-weight:700; }}
.st-key-btn_dosierung button {{ background:transparent; border:1px solid {knopf_hell}; border-radius:10px; }}
.st-key-btn_dosierung button p {{ color:{schrift}; font-weight:700; }}
.st-key-btn_kalender button:hover, .st-key-btn_dosierung button:hover {{ opacity:0.85; }}
</style>""", unsafe_allow_html=True)

# Kopf: Ort und Saison, grosse Begrüssung, Demo-Schild
schild = ("<span style='background:#EADFC3; color:#5C4A12; padding:6px 14px; border-radius:20px; "
          "font-size:13px; font-weight:600;'>Demo-Modus · Beispielwerte</span>") if demo else ""
html(f"<div style='display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:12px;'>"
     f"<div><div style='color:#6B5D63; font-size:14px;'>{lade_parzellenname()} · Saison {heute.year}</div>"
     f"<div style='font-family:Georgia,serif; font-size:40px; font-weight:700; color:#3A1A28; line-height:1.15;'>"
     f"{ueberschrift}</div></div><div>{schild}</div></div>")

# Hauptmeldung
with st.container(key="alarm"):
    html(f"<div style='display:flex; gap:18px; align-items:flex-start; color:{schrift};'>"
         f"<div style='min-width:48px; height:48px; border-radius:50%; background:white; color:{hintergrund}; "
         f"display:flex; align-items:center; justify-content:center; font-size:24px;'>"
         f"{'⚠' if variante == 'rot' else ('✓' if variante == 'grün' else 'ℹ')}</div>"
         f"<div><div style='letter-spacing:2px; font-size:12px; opacity:0.85;'>{kicker}</div>"
         f"<div style='font-family:Georgia,serif; font-size:30px; font-weight:700; line-height:1.2; margin:4px 0 8px 0;'>{titel}</div>"
         f"<div style='font-size:15px;'>{text}</div></div></div>")
    knopf1, knopf2, _ = st.columns([1.3, 1.1, 3])
    if knopf1.button("Spritzfenster ansehen", key="btn_kalender"):
        st.switch_page("pages/kalender.py")
    if knopf2.button("Brühe berechnen", key="btn_dosierung"):
        st.switch_page("pages/dosierung.py")

st.write("")


# Vier Kennzahlen
def karte(titel, gross, klein, klein_farbe="#6B5D63"):
    """Eine Kennzahl als weisse Karte."""
    return (f"<div style='background:white; border:1px solid {RAND}; border-radius:16px; padding:16px 20px; min-height:112px;'>"
            f"<div style='color:#6B5D63; font-size:14px;'>{titel}</div>"
            f"<div style='font-family:Georgia,serif; font-size:32px; font-weight:700; color:#3A1A28; margin:4px 0;'>{gross}</div>"
            f"<div style='font-size:13px; color:{klein_farbe};'>{klein}</div></div>")


# 1. Keimbereit seit
bis_heute = tageswetter[tageswetter["datum"] <= heute]
summe = bis_heute["temperatursumme"].iloc[-1] if len(bis_heute) > 0 else 0
if keimbereit is not None and keimbereit <= heute:
    karte1 = karte("Keimbereit seit", f"{keimbereit:%d.%m.}", f"Temperatursumme {summe:.0f} / {g.KEIMBEREIT_AB}", GRUEN)
else:
    karte1 = karte("Keimbereit seit", "noch nicht", f"Temperatursumme {summe:.0f} / {g.KEIMBEREIT_AB}")

# 2. Infektionen im Jahr
dieses_jahr = infektionen[infektionen["start"].dt.year == heute.year]
bisher = (dieses_jahr["start"] <= heute).sum()
prognose = (dieses_jahr["start"] > heute).sum()
karte2 = karte(f"Infektionen {heute.year}", bisher, f"+ {prognose} in der Prognose")

# 3. Laufende Inkubationen
if len(laufend) > 0:
    karte3 = karte("Laufende Inkubationen", len(laufend), f"Ende ab ca. {laufend['ende'].min():%d.%m.}")
else:
    karte3 = karte("Laufende Inkubationen", 0, "Keine Infektion in Entwicklung")

# 4. Letzte Spritzung
if letzte is None:
    karte4 = karte("Letzte Spritzung", "–", "Nicht geschützt", ROT)
elif belag_aktiv:
    karte4 = karte("Letzte Spritzung", f"{letzte['datum']:%d.%m.}", f"Geschützt bis {geschuetzt_bis:%d.%m.}", GRUEN)
else:
    karte4 = karte("Letzte Spritzung", f"{letzte['datum']:%d.%m.}", "Nicht geschützt", ROT)

for spalte, inhalt in zip(st.columns(4), [karte1, karte2, karte3, karte4]):
    spalte.markdown(inhalt, unsafe_allow_html=True)

st.write("")


# Spritzfenster: nächste 7 Tage
with st.container(border=True):
    titel_spalte, legende_spalte = st.columns([1, 1], vertical_alignment="center")
    titel_spalte.markdown("<div style='font-family:Georgia,serif; font-size:24px; font-weight:700; color:#3A1A28;'>"
                          "Spritzfenster – nächste 7 Tage</div>", unsafe_allow_html=True)

    def kaestchen(farbe):
        """Kleines farbiges Quadrat für die Legende."""
        return (f"<span style='display:inline-block; width:12px; height:12px; background:{farbe}; "
                f"border-radius:3px; margin:0 5px 0 16px; vertical-align:middle;'></span>")

    legende_spalte.markdown("<div style='text-align:right; font-size:13px;'>"
                            + kaestchen(GRUEN) + "Geeignet" + kaestchen(GELB) + "Knapp"
                            + kaestchen(ROT) + "Nicht möglich" + kaestchen(GRAU) + "Geschützt" + "</div>",
                            unsafe_allow_html=True)

    if bewertung is None:
        st.error("Das Wetter von Open-Meteo konnte nicht geladen werden.")
    else:
        ampel_farben = [GRUEN, GELB, ROT]
        ampel_namen = ["Geeignet", "Knapp", "Nicht möglich"]
        for spalte, tag, (stufe, start, gruende) in zip(st.columns(7), tage, bewertung):
            # Noch geschützt und keine offene Infektion: Spritzen ist nicht nötig, also keine Ampel
            if fokus is None and belag_aktiv and tag <= geschuetzt_bis:
                farbe, schriftfarbe = GRAU, "#3A2A30"
                zeile2, zeile3 = "Geschützt", "nicht nötig"
            else:
                farbe = ampel_farben[stufe]
                schriftfarbe = "#3A2A30" if stufe == 1 else "white"
                zeile2 = ampel_namen[stufe] + (f" · ab {start} Uhr" if stufe < 2 else "")
                zeile3 = ", ".join(gruende) if gruende else "trocken"

            # Goldener Rahmen: der empfohlene Tag (erster grüner Tag vor der Frist)
            empfohlen = len(gute) > 0 and tag == gute[0]
            rahmen = f"3px solid {GOLD}" if empfohlen else "3px solid transparent"
            marken = []
            if empfohlen:
                marken.append("Empfohlen")
            if fokus is not None and tag == fokus["frist"]:
                marken.append("Frist")
            marken_text = f"<div style='font-weight:700; margin-top:4px;'>{' · '.join(marken)}</div>" if marken else ""

            spalte.markdown(
                f"<div style='background:{farbe}; color:{schriftfarbe}; border:{rahmen}; border-radius:12px; "
                f"padding:12px; min-height:128px; font-size:13px;'>"
                f"<div style='font-weight:700; font-size:15px; margin-bottom:6px;'>{WOCHENTAGE[tag.weekday()]} {tag:%d.%m.}</div>"
                f"<div>{zeile2}</div><div>{zeile3}</div>{marken_text}</div>",
                unsafe_allow_html=True)

    # Inkubationsbalken der wichtigsten Infektion (offene, sonst die nächste laufende)
    balken_infektion = fokus
    if balken_infektion is None and len(laufend) > 0:
        balken_infektion = laufend.sort_values("frist").iloc[0]
    if balken_infektion is not None:
        gesamt = max((balken_infektion["ende"] - balken_infektion["start"]).days, 1)
        vergangen = min(max((heute - balken_infektion["start"]).days, 0), gesamt)
        anteil = vergangen / gesamt * 100
        tag_nr = min(vergangen + 1, gesamt)
        html(f"<div style='margin-top:14px; font-size:13px; color:#6B5D63; display:flex; justify-content:space-between;'>"
             f"<span>Inkubation Infektion {balken_infektion['start']:%d.%m.} · Tag {tag_nr} von {gesamt}</span>"
             f"<span style='color:#3A1A28; font-weight:700;'>spritzen bis {balken_infektion['frist']:%d.%m.} (80 %)</span></div>"
             f"<div style='position:relative; height:12px; background:#EFEAE2; border-radius:6px; margin:6px 0;'>"
             f"<div style='width:{max(anteil, 3):.0f}%; height:12px; background:{WEINROT}; border-radius:6px;'></div>"
             f"<div style='position:absolute; left:80%; top:-4px; width:3px; height:20px; background:{GOLD};'></div></div>"
             f"<div style='font-size:12px; color:#6B5D63; display:flex; justify-content:space-between;'>"
             f"<span>{balken_infektion['start']:%d.%m.} Infektion</span>"
             f"<span>{balken_infektion['ende']:%d.%m.} Ende der Inkubation</span></div>")

st.write("")


# Unten: links die Infektionsliste, rechts das Modell
links, rechts = st.columns([1.35, 1])

with links.container(border=True):
    html("<div style='font-family:Georgia,serif; font-size:24px; font-weight:700; color:#3A1A28; margin-bottom:8px;'>"
         "Infektionen der letzten 3 Wochen</div>")

    # Letzte 3 Wochen und die Prognose der nächsten 7 Tage
    liste = infektionen[(infektionen["start"] >= heute - pd.Timedelta(days=21))
                        & (infektionen["start"] <= heute + pd.Timedelta(days=7))].sort_values("start")
    if len(liste) == 0:
        st.info("In den letzten 3 Wochen gab es keine Infektion.")
    else:
        kopf = "".join(f"<th style='text-align:left; padding:8px 6px; font-weight:500; color:#6B5D63; "
                       f"border-bottom:1px solid {RAND};'>{name}</th>"
                       for name in ["Datum", "Stufe", "Inkubationsende", "Spritzen bis", "Status", "Agrometeo"])
        zeilen = ""
        for _, zeile in liste.iterrows():
            zeichen_z, name_z = stufe_text(zeile["gradstunden_bn"])
            gemessen = zeile["quelle"] == "gemessen"
            ca = "" if gemessen else "ca. "     # bei geschätzten Infektionen nur ungefähre Daten
            hintergrund_s, schrift_s = STATUS_FARBEN[zeile["status"]]
            # Agrometeo-Kontrolle: nur gemessene Infektionen hat die Station selbst gemeldet
            agro = "✓ bestätigt" if gemessen else "–"
            zelle = f"padding:10px 6px; border-bottom:1px solid #F1ECE4; font-size:14px;"
            zeilen += (f"<tr><td style='{zelle} font-weight:700;'>{zeile['start']:%d.%m.%Y}</td>"
                       f"<td style='{zelle} color:{WEINROT};'>{zeichen_z} {name_z}</td>"
                       f"<td style='{zelle}'>{ca}{zeile['ende']:%d.%m.}</td>"
                       f"<td style='{zelle} font-weight:700;'>{ca}{zeile['frist']:%d.%m.}</td>"
                       f"<td style='{zelle}'><span style='background:{hintergrund_s}; color:{schrift_s}; padding:3px 10px; "
                       f"border-radius:12px; font-size:12px; font-weight:600;'>{zeile['status']}</span></td>"
                       f"<td style='{zelle}'>{agro}</td></tr>")
        html(f"<table style='width:100%; border-collapse:collapse;'><tr>{kopf}</tr>{zeilen}</table>")
    st.caption("Status: geschützt · behandelt · offen · verpasst · Prognose")

with rechts.container(border=True):
    html("<div style='font-family:Georgia,serif; font-size:24px; font-weight:700; color:#3A1A28;'>"
         "Infektionsrisiko (Modell)</div>"
         "<div style='font-size:13px; color:#6B5D63; margin-bottom:10px;'>Random Forest aus der Wetterprognose</div>")

    # Die nächsten 7 Tage: Erwartet das Modell eine Infektion? (Ja = hoher Balken)
    # TODO: Sobald gemeinsam.py die Wahrscheinlichkeit pro Tag liefert (predict_proba),
    # hier statt Ja/Nein die Prozentwerte als Säulen zeigen.
    kommende = pd.date_range(heute + pd.Timedelta(days=1), periods=7)
    erwartet = [tag for tag in kommende
                if ((infektionen["start"] == tag) & (infektionen["quelle"] != "gemessen")).any()]
    saeulen = ""
    for tag in kommende:
        ja = tag in erwartet
        hoehe = 110 if ja else 18
        farbe = WEINROT if ja else "#DCCBD2"
        beschriftung = "Infektion" if ja else "–"
        saeulen += (f"<div style='flex:1; text-align:center; font-size:12px; color:#6B5D63;'>"
                    f"<div style='height:120px; display:flex; flex-direction:column; justify-content:flex-end; align-items:center;'>"
                    f"<div style='font-size:11px; margin-bottom:2px; color:{WEINROT if ja else '#6B5D63'};'>{beschriftung}</div>"
                    f"<div style='width:70%; height:{hoehe}px; background:{farbe}; border-radius:4px 4px 0 0;'></div></div>"
                    f"<div style='margin-top:6px;'>{WOCHENTAGE[tag.weekday()]}</div></div>")
    html(f"<div style='display:flex; gap:6px; align-items:flex-end;'>{saeulen}</div>")

    # Hinweisbox: Das Ergebnis in eine Handlung übersetzen
    if len(erwartet) == 0:
        hinweis = "Das Modell erwartet in den nächsten 7 Tagen keine Infektion."
    else:
        erste = erwartet[0]
        if len(gute) > 0 and gute[0] <= erste <= gute[0] + pd.Timedelta(days=SCHUTZ_TAGE):
            hinweis = (f"Erste erwartete Infektion am <b>{tag_lang(erste)}</b> – "
                       f"eine Spritzung am {tag_lang(gute[0])} würde sie bereits abdecken.")
        elif belag_aktiv and erste <= geschuetzt_bis:
            hinweis = (f"Erste erwartete Infektion am <b>{tag_lang(erste)}</b> – "
                       f"der aktuelle Belag schützt noch bis {tag_lang(geschuetzt_bis)}.")
        else:
            hinweis = (f"Erste erwartete Infektion am <b>{tag_lang(erste)}</b> – "
                       "dafür ist noch kein Belag geplant. Im Kalender ein Spritzfenster suchen.")
    html(f"<div style='background:#F6F0F2; border-radius:10px; padding:12px 14px; font-size:13px; margin-top:12px;'>{hinweis}</div>")

# Fusszeile
st.divider()
st.caption("Daten: Agrometeo Station Zizers · Open-Meteo. "
           "Entscheidungshilfe – ersetzt keine Pflanzenschutzberatung.")