#Hier wird die Startseite codiert.
"""Startseite des Spritzplaners mit Banner und Navigationskacheln."""

import base64
import streamlit as st


def lade_bild(pfad):
    """Liest ein Bild ein und wandelt es in Text (Base64) um.

    HTML in Streamlit kann Bilder aus dem Projektordner nicht direkt laden.
    Darum wird das Bild in Text umgewandelt und direkt ins HTML geschrieben.
    """
    with open(pfad, "rb") as datei:          # "rb" = als Bild-Datei lesen
        return base64.b64encode(datei.read()).decode()


def zeige_banner():
    """Zeigt den weinroten Willkommens-Banner mit dem Rebberg-Foto im Hintergrund.

    Über dem Foto liegt ein Farbverlauf: links kräftiges Weinrot (dort steht
    der Text), nach rechts immer durchsichtiger, damit man das Foto sieht.
    """
    bild = lade_bild("bilder/rebberg.jpg")

    st.markdown(f"""
    <div style="
        background-image:
            linear-gradient(90deg, rgba(123,30,58,0.95) 0%, rgba(123,30,58,0.75) 45%, rgba(123,30,58,0.15) 100%),
            url(data:image/jpeg;base64,{bild});
        background-size: cover;
        background-position: center 62%;
        color: white;
        padding: 80px 40px;
        border-radius: 20px;
        margin-bottom: 24px;
    ">
        <p style="margin: 0; font-size: 14px; letter-spacing: 2px; text-transform: uppercase; color: #F3D9DF;">
            Welcome back
        </p>
        <h1 style="margin: 0; padding: 8px 0; font-size: 52px; color: white;">
            Spray Planner
        </h1>
        <p style="margin: 0; font-size: 19px; color: #F8E8EC;">
            Your crop protection planning in one place: plots, dosage, dates and weather.
        </p>
    </div>
    """, unsafe_allow_html=True)


def zeige_kacheln():
    """Zeigt sechs Kacheln, die zu den einzelnen Seiten der App führen.

    Die Kacheln werden in zwei Reihen mit je drei Spalten angeordnet.
    Jede Kachel enthält ein Icon, einen Titel, eine kurze Beschreibung
    und einen Link zur entsprechenden Seite.
    """
    st.subheader("Where would you like to go?")

    kacheln = [
        {"titel": "Dashboard", "text": "Overview of everything at a glance", "icon": "bar_chart", "seite": "pages/dashboard.py"},
        {"titel": "Dosage", "text": "Calculate products and amounts", "icon": "science", "seite": "pages/dosierung.py"},
        {"titel": "Journal", "text": "Record treatments", "icon": "description", "seite": "pages/journal.py"},
        {"titel": "Calendar", "text": "Plan spray dates", "icon": "calendar_month", "seite": "pages/kalender.py"},
        {"titel": "Plots", "text": "Manage areas", "icon": "map", "seite": "pages/parzellen.py"},
        {"titel": "Weather", "text": "Check conditions before spraying", "icon": "cloud", "seite": "pages/wetter.py"},
    ]

    spalten = st.columns(3) + st.columns(3)

    for spalte, kachel in zip(spalten, kacheln):
        with spalte:
            with st.container(border=True):
                st.markdown(f"#### :material/{kachel['icon']}: {kachel['titel']}")
                st.caption(kachel["text"])
                st.page_link(kachel["seite"], label="Open", icon=":material/arrow_forward:")


zeige_banner()
zeige_kacheln()
