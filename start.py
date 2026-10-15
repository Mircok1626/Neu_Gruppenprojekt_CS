#Hier wird die Startseite codiert.
import streamlit as st

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