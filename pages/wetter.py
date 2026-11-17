#hier kommt der Code für das Wetter hinein
import streamlit as st
st.title("Wetter")

# Hier wird die Wetter-Seite codiert.
"""Wetter-Seite des Spritzplaners: Warum warnt die App?"""

import pandas as pd #pandas: Tabellen (DataFrames) für die Wetterdaten
import requests #requests: damit Python eine Internetseite/API abfragen kann
import streamlit as st 

#Koordinaten der Station Zizers (für die Open-Meteo-Abfrage)
ZIZERS_LAT = 46.93
ZIZERS_LON = 9.57

def zeige_banner():
    """Zeigt den weinroten Banner mit dem Titel der Wetter-Seite. 

    Der Banner hat den gleichen Stil wie auf der Startseite 
    (Weinrot #7B1E3A, weisse Schrift, runde Ecken).
    """

    #HTML und CSS im Markdown, damit wir den Banner selbst gestalten können
    st.markdown("""
    <div style="
        background-color: #7B1E3A;
        color: white;
        padding: 32px 40px;
        border-radius: 20px;
        margin-bottom: 24px;
    ">
        <h1 style=*margin: 0; font-size: 36px; color: white;">
            Wetter
        </h1>
        <p style="margin: 8px 0 0 0; font-size: 18p<; color: #F8E8EC;">
            Warum warnt die App? Hier siehst du die Ursachen hinter jedem Alarm.
        </p>
    </div>
    """, unsafe_allow_html=True) #unsafe_allow_html=True erlaubt HTML