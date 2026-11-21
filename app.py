#Hauptdokument, d.h. hier wird alles zusammengefügt, so dass streamlit ein App erstellen kann
import datetime as dt

import streamlit as st

st.set_page_config(page_title="Spray Planner", page_icon="🍇", layout="wide")

seiten = [
    st.Page("start.py", title="Home", icon=":material/home:", default=True),
    st.Page("pages/dashboard.py", title="Dashboard", icon=":material/bar_chart:"),
    st.Page("pages/dosierung.py", title="Dosage", icon=":material/science:"),
    st.Page("pages/journal.py", title="Journal", icon=":material/description:"),
    st.Page("pages/kalender.py", title="Calendar", icon=":material/calendar_month:"),
    st.Page("pages/parzellen.py", title="Plots", icon=":material/map:"),
    st.Page("pages/wetter.py", title="Weather", icon=":material/cloud:"),
]

# Navigation zuerst, damit das Menü oben in der Seitenleiste steht
navigation = st.navigation(seiten)

# Datum links in der Seitenleiste. Es gilt für alle Seiten (key="heute").
# Die Seiten lesen es mit gemeinsam.heute() bzw. st.session_state["heute"].
# Ein früheres Datum zeigt, was die App damals angezeigt hätte (Demo).
st.sidebar.date_input("Today is", value=dt.date.today(), min_value=dt.date(2024, 1, 1),
                      max_value=dt.date.today(), format="DD.MM.YYYY", key="heute")
st.sidebar.caption("Applies to all pages. An earlier date shows what the app would have displayed back then.")

navigation.run()
