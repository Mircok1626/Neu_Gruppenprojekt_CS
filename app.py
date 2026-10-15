#Hauptdokument, d.h. hier wird alles zusammengefügt, so dass streamlit ein App erstellen kann
import streamlit as st

st.set_page_config(page_title="Spritzplaner", page_icon="🍇", layout="wide")

seiten = [
    st.Page("start.py", title="Start", icon=":material/home:", default=True),
    st.Page("pages/dashboard.py", title="Dashboard", icon=":material/bar_chart:"),
    st.Page("pages/dosierung.py", title="Dosierung", icon=":material/science:"),
    st.Page("pages/journal.py", title="Journal", icon=":material/description:"),
    st.Page("pages/kalender.py", title="Kalender", icon=":material/calendar_month:"),
    st.Page("pages/parzelle.py", title="Parzelle", icon=":material/map:"),
    st.Page("pages/wetter.py", title="Wetter", icon=":material/cloud:"),
]

st.navigation(seiten).run()
