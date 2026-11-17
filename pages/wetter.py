#hier kommt der Code für das Wetter hinein 
import streamlit as st
import pandas as pd
import requests 

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
        <h1 style="margin: 0; font-size: 36px; color: white;">
            Wetter
        </h1>
        <p style="margin: 8px 0 0 0; font-size: 18px; color: #F8E8EC;">
            Warum warnt die App? Hier siehst du die Ursachen hinter jedem Alarm.
        </p>
    </div>
    """, unsafe_allow_html=True) #unsafe_allow_html=True erlaubt HTML


#st.cache_data merkt sich das Ergebnis für 1 Stunde (3600 Sekunden).
#So fragen wir Open-Meteo nicht bei jedem Klick neu ab. 
@st.cache_data(ttl=3600)
def lade_wetter (tage_zurueck=21, tage_voraus=14):
    """Holt Tageswerte (Temperatur, Regen) für Zizers von Open-Meteo. 

    tage_zurueck: wie viele vergangene Tage geladen werden 
    tage_voraus: wie viele Tage Prognose geladen werden 
    Gibt eine Tabelle mit den Spalten, datum, temperatur, regen_mm
    und ist_prognose zurück. 
    """
    #Adresse der Open-Meteo-Schnittstelle (kein API-Key nötig)
    url = "https://api.open-meteo.com/v1/forecast"

    #Das fragen wir ab: Ort, Tageswerte, Zeitraum und Zeitzone
    parameter = {
        "latitude": ZIZERS_LAT, 
        "longitude": ZIZERS_LON, 
        "daily": "temperature_2m_mean,precipitation_sum",
        "past_days": tage_zurueck, 
        "forecast_days": tage_voraus, 
        "timezone": "Europe/Zurich", 
    }
    #Anfrage senden; timeout=10 heisst: nach 10 Sekunden aufgeben 
    antwort = requests.get(url, params=parameter, timeout=10)
    antwort.raise_for_status() #löst einen Fehler aus, falls etwas schiefging

    #Die Antwort ist JSON; wir brauchen nur den Teil "daily"
    daten = antwort.json()["daily"]

    #Daraus bauen wir eine übersichtliche Tabelle 
    tabelle = pd.DataFrame({
        "datum": pd.to_datetime(daten["time"]),
        "temperatur": daten["temperature_2m_mean"],
        "regen_mm": daten["precipitation_sum"]
    })

    #Alles nach heute ist Prognose (brauchen wir später für die "heut"-Linie)
    heute = pd.Timestamp.today().normalize()
    tabelle["ist_prognose"] = tabelle["datum"] > heute

    return tabelle 

def zeige_wetterdaten():
    """Lädt die Wetterdaten und zeigt sie vorerst als einfache Tabelle."""
    st.subheader("Wetterdaten Zizers")

    #try/except: Wenn die Abfrage scheitert (z. B. kein Internet),
    #zeigen wir eine Meldung statt einer roten Fehlerseite.
    try:
        tabelle = lade_wetter()
        st.dataframe(tabelle, use_container_width=True)
        st.caption("Quelle: Open-Meteo")
    except requests.RequestException:
        st.error("Wetterdaten konnten nicht geladen werden. Bitte später erneut versuchen.")

#Hier wird die Seite aufgebaut (Reihenfolge = Reienfolge auf der Seite)
zeige_banner()
zeige_wetterdaten()