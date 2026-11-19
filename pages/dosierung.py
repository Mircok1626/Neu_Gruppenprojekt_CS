#Hier wird die Seite Dosierung codiert.
"""Dosierung: Rechnet aus Rebstadium, Parzelle und Gerät ein Tankrezept für Folpet aus.

Die Fläche kann aus den gespeicherten Parzellen (Seite Parzelle) übernommen
oder als Notfall von Hand eingegeben werden.
Quelle der Zahlen: Agroscope Transfer Nr. 626, Pflanzenschutzmittelliste
für den Rebbau 2026, Mittel gegen Falschen Mehltau.
"""

import datetime
import math
import sqlite3
import altair as alt
import pandas as pd
import streamlit as st

# Rebstadien und ihre Basisbrühmenge in Liter pro Hektare.
# Je mehr Blätter die Rebe hat, desto grösser ist die Basisbrühmenge.
STADIEN = {
    "3–5 Blätter": 600,
    "1. Vorblüte": 800,
    "2. Vorblüte": 1000,
    "Blüte": 1200,
    "Nachblüte": 1600,
    "nur Traubenzone": 1200,
}

# Wir verwenden nur ein Mittel: Folpet 80 WG.
# Es ist laut Agroscope in allen Stadien erlaubt und nicht hitzeempfindlich.
MITTEL = "Folpet 80 WG"
KONZENTRATION = 0.125   # Konzentration in Prozent
EINHEIT = "kg"          # Folpet 80 WG ist ein Granulat und wird abgewogen


# Titel und Untertitel
st.title("Dosierung – wie viel Mittel und Wasser brauche ich?")
st.caption(f"Aus Rebstadium, Parzelle und Gerät wird ein Tankrezept für {MITTEL} berechnet.")

# Parzellen aus der Datenbank holen (dieselbe Datenbank wie auf der Seite Parzelle).
# try/except: Gibt es die Tabelle noch nicht, stürzt die Seite nicht ab,
# sondern arbeitet einfach mit einer leeren Tabelle weiter.
con = sqlite3.connect("daten/spritzplaner.db")
try:
    parzellen = pd.read_sql_query("SELECT name, flaeche_ha FROM parzellen", con)
except Exception:
    parzellen = pd.DataFrame(columns=["name", "flaeche_ha"])

# Die Seite wird in zwei Spalten geteilt: links Eingaben, rechts Resultat.
links, rechts = st.columns(2, gap="large")

with links:
    st.subheader("Eingaben")

    # Parzelle: Normalerweise wählt man eine gespeicherte Parzelle aus.
    # Mit dem Häkchen «Manuell ausfüllen» gibt man die Fläche selbst ein (Notfall).
    if parzellen.empty:
        # Gibt es noch keine Parzellen, geht nur die Eingabe von Hand.
        manuell = True
        st.caption("Noch keine Parzellen gespeichert. Bitte die Fläche von Hand eingeben.")
    else:
        manuell = st.checkbox("Manuell ausfüllen")

    if manuell:
        parzelle = ""   # keine Parzelle gewählt
        flaeche = st.number_input("Fläche (ha)", min_value=0.01, value=0.8, step=0.1)
    else:
        parzelle = st.selectbox("Parzelle", list(parzellen["name"]))
        # Die Zeile der gewählten Parzelle suchen und die Fläche daraus lesen.
        zeile = parzellen[parzellen["name"] == parzelle].iloc[0]
        flaeche = float(zeile["flaeche_ha"])

    # Spritztag: wird ins Journal übernommen.
    # Startwert ist das Datum links in der Seitenleiste («Heute ist der»), das für alle Seiten gilt.
    spritztag = st.date_input("Geplanter Spritztag", value=st.session_state.get("heute", datetime.date.today()),
                              format="DD.MM.YYYY")

    # Rebstadium: Der Winzer muss es selbst wählen. index=None: Das Feld ist am Anfang leer,
    # damit nicht aus Versehen ein falsches Stadium (und damit eine falsche Menge) stehen bleibt.
    stadium = st.selectbox("Rebstadium", list(STADIEN.keys()), index=None, placeholder="Bitte wählen")

    # Zahlenfelder: min_value = kleinster Wert, value = Startwert
    wasser_pro_ha = st.number_input("Wie viele Liter versprüht dein Gerät pro Hektare?",
                                    min_value=50, value=300, step=25)
    tank = st.number_input("Tankgrösse (l)", min_value=20, value=200, step=10)


# Diagramm: Menge pro ha für jedes Stadium. Es hängt nicht vom gewählten Stadium ab,
# darum steht es vor dem Stopp und ist immer sichtbar (auf der Seite erscheint es unter den Spalten).
st.subheader(f"{MITTEL}: Menge pro ha je Stadium")

# Zwei leere Listen: eine für die Namen, eine für die Mengen.
stadien_namen = []
mengen = []
for name in STADIEN:
    stadien_namen.append(name)
    mengen.append(KONZENTRATION / 100 * STADIEN[name])

# Aus den zwei Listen eine Tabelle machen (Altair braucht eine Tabelle)
tabelle = pd.DataFrame({"Stadium": stadien_namen, "Menge": mengen})

# Säulen: x = Stadium, y = Menge. Die y-Achse geht fest von 0 bis etwas über
# die grösste Menge (× 1.2), damit nichts ins Minus geht und oben Platz für die Zahlen bleibt.
balken = alt.Chart(tabelle).mark_bar(color="#7B1E3A", cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
    x=alt.X("Stadium:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),   # Namen waagrecht
    y=alt.Y("Menge:Q", title=f"{EINHEIT} pro ha", scale=alt.Scale(domain=[0, max(mengen) * 1.2])),
    tooltip=[alt.Tooltip("Stadium:N"), alt.Tooltip("Menge:Q", title=f"{EINHEIT} pro ha", format=".2f")],
)

# Die Zahl direkt über jede Säule schreiben (z. B. «1.50»)
zahlen = alt.Chart(tabelle).mark_text(dy=-10, fontWeight="bold", color="#7B1E3A").encode(
    x=alt.X("Stadium:N", sort=None),
    y="Menge:Q",
    text=alt.Text("Menge:Q", format=".2f"),
)

# Säulen und Zahlen übereinanderlegen und anzeigen
st.altair_chart((balken + zahlen).properties(height=320), width="stretch")

st.divider()
st.caption("Quelle: Agroscope, Pflanzenschutzmittelliste für den Rebbau 2026. "
           "Immer die Etikette des Mittels beachten. Die App ist eine Entscheidungshilfe.")


# Ohne Stadium kann nicht gerechnet werden: Hinweis zeigen und hier aufhören
if stadium is None:
    rechts.info("Bitte links zuerst das Rebstadium wählen.")
    st.stop()

# Die Basisbrühmenge zum gewählten Stadium holen
basis = STADIEN[stadium]

# Formel 1: Mittel pro Hektare
mittel_pro_ha = KONZENTRATION / 100 * basis

# Formel 2: Mittel für die ganze Parzelle
mittel_total = mittel_pro_ha * flaeche

# Formel 3: Wasser für die ganze Parzelle
# round(..., 1): auf 0,1 Liter runden, sonst rechnet der Computer z. B. 200,00000001 l
wasser_total = round(wasser_pro_ha * flaeche, 1)

# Formel 4: Wie oft muss der Tank gefüllt werden? math.ceil rundet auf.
tankfuellungen = math.ceil(wasser_total / tank)

# Formel 5: Wasser und Mittel für jede einzelne Füllung.
# Jede Füllung ist voll, nur die letzte bekommt den Rest.
fuellungen = []
rest_wasser = wasser_total
for nummer in range(1, tankfuellungen + 1):
    wasser = min(tank, rest_wasser)                    # voller Tank oder der Rest
    mittel = mittel_pro_ha * wasser / wasser_pro_ha    # Mittel passend zu diesem Wasser
    fuellungen.append((nummer, wasser, mittel))
    rest_wasser = rest_wasser - wasser


with rechts:
    # Einzahl oder Mehrzahl: «1 Tankfüllung» oder «2 Tankfüllungen»
    if tankfuellungen == 1:
        titel = "1 Tankfüllung"
    else:
        titel = f"{tankfuellungen} Tankfüllungen"

    # Jede Füllung als eigene Zeile in der weinroten Box
    zeilen = ""
    for nummer, wasser, mittel in fuellungen:
        zeilen += f"<b>{nummer}. Füllung:</b> {wasser:.0f} l Wasser + {mittel:.2f} {EINHEIT} {MITTEL}<br>"

    # Weinrote Box wie auf der Startseite (HTML mit f-String)
    st.markdown(f"""
<div style="background-color:#7B1E3A; color:white; padding:24px 32px; border-radius:20px;">
<p style="margin:0; letter-spacing:2px; color:#F3D9DF;">TANKREZEPT · {MITTEL}</p>
<h2 style="color:white;">{titel}</h2>
<p style="font-size:18px; margin:0 0 12px 0;">
{zeilen}
</p>
<p style="margin:0; color:#F3D9DF;">
Total: {mittel_total:.2f} {EINHEIT} {MITTEL} in {wasser_total:.0f} l Wasser
</p>
</div>
""", unsafe_allow_html=True)

    st.write("")  # etwas Abstand

    # Die Formeln zum Aufklappen, direkt unter dem Tankrezept
    with st.expander("So wird gerechnet"):
        st.markdown("""
1. Mittel pro ha = Konzentration ÷ 100 × Basisbrühmenge
2. Mittel total = Mittel pro ha × Fläche
3. Wasser total = Wasser pro ha × Fläche
4. Tankfüllungen = Wasser total ÷ Tankgrösse, aufgerundet
5. Mittel pro Füllung = Mittel pro ha × Wasser in dieser Füllung ÷ Wasser pro ha
""")

    # Button: Werte für das Journal merken.
    # st.session_state ist ein Speicher, den alle Seiten lesen können.
    if st.button("Ins Journal übernehmen"):
        st.session_state["dosierung_vorschlag"] = {
            "datum": spritztag,
            "parzelle": parzelle,
            "stadium": stadium,
            "mittel": MITTEL,
            "flaeche": flaeche,
            "wasser_pro_ha": wasser_pro_ha,
            "menge": round(mittel_total, 2),
            "einheit": EINHEIT,
        }
        st.switch_page("pages/journal.py")   # direkt zum Journal wechseln