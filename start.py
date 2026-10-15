#Hier wird die Startseite codiert.
"""Startseite des Spritzplaners mit Banner und Navigationskacheln."""

import streamlit as st

"""Zeigt den weinroten Willkommens-Banner oben auf der Startseite. Der Banner wird mit HTML und CSS gestaltet und enthält eine kleine
    Begrüssungszeile, den Titel der App und einen kurzen Untertitel."""

st.markdown("""
<div style="
    background-color: #7B1E3A;
    color: white;
    padding: 48px 40px;
    border-radius: 20px;
    margin-bottom: 24px;
">
    <p style="margin: 0; font-size: 14px; letter-spacing: 2px; text-transform: uppercase; color: #F3D9DF;">
        Willkommen zurück
    </p>
    <h1 style="margin: 0; padding: 8px 0; font-size: 52px; color: white;">
        Spritzplaner
    </h1>
    <p style="margin: 0; font-size: 19px; color: #F8E8EC;">
        Deine Pflanzenschutz-Planung an einem Ort: Parzellen, Dosierung, Termine und Wetter.
    </p>
</div>
""", unsafe_allow_html=True)

"""Zeigt sechs Kacheln, die zu den einzelnen Seiten der App führen. Die Kacheln werden in zwei Reihen mit je drei Spalten angeordnet. 
    Jede Kachel enthält ein Icon, einen Titel, eine kurze Beschreibung und einen Link zur entsprechenden Seite."""


st.subheader("Wohin möchtest du?")

kacheln = [
    {"titel": "Dashboard", "text": "Überblick über alles auf einen Blick", "icon": "bar_chart", "seite": "pages/dashboard.py"},
    {"titel": "Dosierung", "text": "Mittel und Mengen berechnen", "icon": "science", "seite": "pages/dosierung.py"},
    {"titel": "Journal", "text": "Behandlungen festhalten", "icon": "description", "seite": "pages/journal.py"},
    {"titel": "Kalender", "text": "Spritztermine planen", "icon": "calendar_month", "seite": "pages/kalender.py"},
    {"titel": "Parzelle", "text": "Flächen verwalten", "icon": "map", "seite": "pages/parzelle.py"},
    {"titel": "Wetter", "text": "Bedingungen vor dem Spritzen prüfen", "icon": "cloud", "seite": "pages/wetter.py"},
]

spalten = st.columns(3) + st.columns(3)

for spalte, kachel in zip(spalten, kacheln):
    with spalte:
        with st.container(border=True):
            st.markdown(f"#### :material/{kachel['icon']}: {kachel['titel']}")
            st.caption(kachel["text"])
            st.page_link(kachel["seite"], label="Öffnen", icon=":material/arrow_forward:")