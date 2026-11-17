import streamlit as st
import pandas as pd
import requests
# >>> NEU: Altair für kombinierte Diagramme & Schwellenwert-Linien <<<
import altair as alt

# Koordinaten der Station Zizers (für die Open-Meteo-Abfrage)
ZIZERS_LAT = 46.93
ZIZERS_LON = 9.57

def zeige_banner():
    """Zeigt den weinroten Banner oben auf der Wetter-Seite."""
    # >>> GEÄNDERT: Ort/Saison-Zeile & angepasster Titel wie im Mockup <<<
    st.markdown("""
    <div style="
        background-color: #7B1E3A;
        color: white;
        padding: 32px 40px;
        border-radius: 20px;
        margin-bottom: 24px;
    ">
        <p style="margin: 0 0 6px 0; font-size: 14px; color: #F8E8EC; letter-spacing: 0.5px;">
            Zizers Halde · Saison 2026
        </p>
        <h1 style="margin: 0; font-size: 36px; color: white;">
            Wetter – warum warnt die App?
        </h1>
        <p style="margin: 8px 0 0 0; font-size: 18px; color: #F8E8EC;">
            Temperatur, Niederschlag, Blattnässe und Infektionsrisiko auf einen Blick.
        </p>
    </div>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
# >>> GEÄNDERT: Lädt jetzt die komplette Saison ab 1.1. statt nur 21 Tage <<<
def lade_wetter_saison():
    """Lädt alle Wetterdaten ab dem 1. Januar des aktuellen Jahres bis +14 Tage Prognose."""
    heute = pd.Timestamp.today().normalize()
    jahresstart = pd.Timestamp(year=heute.year, month=1, day=1)
    tage_seit_jahresstart = (heute - jahresstart).days

    url = "https://api.open-meteo.com/v1/forecast"
    parameter = {
        "latitude": ZIZERS_LAT,
        "longitude": ZIZERS_LON,
        "daily": "temperature_2m_mean,precipitation_sum",
        "past_days": tage_seit_jahresstart,
        "forecast_days": 14,
        "timezone": "Europe/Zurich",
    }

    antwort = requests.get(url, params=parameter, timeout=15)
    antwort.raise_for_status()
    daten = antwort.json()["daily"]

    df = pd.DataFrame({
        "datum": pd.to_datetime(daten["time"]),
        "temperatur": daten["temperature_2m_mean"],
        "regen_mm": daten["precipitation_sum"]
    })

    df["temperatur"] = df["temperatur"].fillna(0.0)
    df["regen_mm"] = df["regen_mm"].fillna(0.0)
    df["ist_prognose"] = df["datum"] > heute

    # >>> NEU: Berechnung der Temperatursumme seit 1.1. (Tage > 8 °C) <<<
    df["temp_ueber_8"] = (df["temperatur"] - 8.0).clip(lower=0.0)
    df["temperatursumme"] = df["temp_ueber_8"].cumsum()
    df["keimbereit"] = df["temperatursumme"] >= 140.0

    # >>> NEU: Berechnung der Gradstunden bei Blattnässe & Infektions-Logik <<<
    blattnaesse_stunden = df["regen_mm"].apply(lambda r: min(24.0, r * 3.5) if r > 0.2 else 0.0)
    df["gradstunden"] = (blattnaesse_stunden * df["temperatur"].clip(lower=0.0)).round(0)
    df["infektion"] = df["keimbereit"] & (df["gradstunden"] >= 160)

    return df

# >>> NEU: Komplette Funktion für Diagramm 1 (Temperatur + Regen + Infektionspunkte) <<<
def zeige_kombi_diagramm(df_anzeige, heute):
    """Diagramm 1: Temperatur (Linie), Regen (Balken) und Infektions-Punkte."""
    with st.container(border=True):
        st.subheader("Temperatur, Regen und Infektionen")
        st.caption("Tagesmittel (°C), Niederschlag (mm) sowie markierte Infektionsereignisse")

        basis = alt.Chart(df_anzeige).encode(x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m.")))

        regen_balken = basis.mark_bar(color="#5B8DBE", opacity=0.75, width=10).encode(
            y=alt.Y("regen_mm:Q", title="Regen (mm)", axis=alt.Axis(orient="right")),
            tooltip=["datum:T", "temperatur:Q", "regen_mm:Q"]
        )

        temp_linie = basis.mark_line(color="#7B1E3A", strokeWidth=2.5).encode(
            y=alt.Y("temperatur:Q", title="Temperatur (°C)", axis=alt.Axis(orient="left")),
            tooltip=["datum:T", "temperatur:Q", "regen_mm:Q"]
        )

        infektionen = basis.transform_filter(alt.datum.infektion == True).mark_circle(
            color="#5C162E", size=140
        ).encode(
            y=alt.value(15),
            tooltip=[alt.Tooltip("datum:T", title="Infektion am"), "gradstunden:Q"]
        )

        heute_linie = alt.Chart(pd.DataFrame({"heute": [heute]})).mark_rule(
            color="#333333", strokeDash=[4, 4]
        ).encode(x="heute:T")

        chart = alt.layer(regen_balken, temp_linie, infektionen, heute_linie).resolve_scale(
            y="independent"
        ).properties(height=280)

        st.altair_chart(chart, use_container_width=True)

# >>> NEU: Komplette Funktion für Diagramm 2 (Gradstunden bei Blattnässe) <<<
def zeige_gradstunden_diagramm(df_anzeige, heute):
    """Diagramm 2: Gradstunden bei Blattnässe mit Schwellenwerten."""
    with st.container(border=True):
        st.subheader("Gradstunden bei Blattnässe")
        st.caption("Summe der Temperaturen aller Stunden mit nassem Blatt. Ab 160 Gradstunden (bei Keimbereitschaft) zählt es als Infektion.")

        basis = alt.Chart(df_anzeige).encode(x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m.")))

        balken = basis.mark_bar(width=12).encode(
            y=alt.Y("gradstunden:Q", title="Gradstunden"),
            color=alt.condition(
                alt.datum.infektion == True,
                alt.value("#7B1E3A"),
                alt.value("#C9A3B0")
            ),
            tooltip=["datum:T", "gradstunden:Q", "keimbereit:N", "infektion:N"]
        )

        schwelle_160 = alt.Chart(pd.DataFrame({"y": [160]})).mark_rule(
            color="#7B1E3A", strokeDash=[4, 4]
        ).encode(y="y:Q")

        heute_linie = alt.Chart(pd.DataFrame({"heute": [heute]})).mark_rule(
            color="#333333", strokeDash=[4, 4]
        ).encode(x="heute:T")

        chart = alt.layer(balken, schwelle_160, heute_linie).properties(height=250)
        st.altair_chart(chart, use_container_width=True)

# >>> NEU: Komplette Funktion für Diagramm 3 (Temperatursumme seit 1.1.) <<<
def zeige_temperatursumme_diagramm(df_gesamt):
    """Diagramm 3: Temperatursumme seit 1.1. mit 140-Grad-Linie."""
    with st.container(border=True):
        st.subheader("Temperatursumme seit 1.1.")
        st.caption("Jeder Tag zählt mit, so viel er über 8 °C warm ist. Ab 140 sind die Wintersporen keimbereit.")

        basis = alt.Chart(df_gesamt).encode(x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m.")))

        kurve = basis.mark_line(color="#7B1E3A", strokeWidth=2.5).encode(
            y=alt.Y("temperatursumme:Q", title="Temperatursumme (°C)"),
            tooltip=["datum:T", "temperatursumme:Q"]
        )

        linie_140 = alt.Chart(pd.DataFrame({"y": [140]})).mark_rule(
            color="#2E6B3E", strokeDash=[5, 5], strokeWidth=2
        ).encode(y="y:Q")

        chart = alt.layer(kurve, linie_140).properties(height=250)
        st.altair_chart(chart, use_container_width=True)

# >>> GEÄNDERT: Hauptfunktion steuert jetzt Zeitraum-Filter und alle 3 Diagramme <<<
def hauptseite():
    """Baut die komplette Wetter-Seite auf."""
    zeige_banner()

    # Zeitraum-Buttons oben
    zeitraum = st.radio(
        "Zeitraum",
        ["Saison", "3 Wochen + Prognose", "14 Tage voraus"],
        index=1,
        horizontal=True,
        label_visibility="collapsed"
    )

    try:
        with st.spinner("Lade Wetterdaten und berechne Infektionsmodell..."):
            df_gesamt = lade_wetter_saison()

        heute = pd.Timestamp.today().normalize()

        # Filter für die oberen zwei Diagramme
        if zeitraum == "3 Wochen + Prognose":
            start_datum = heute - pd.Timedelta(days=21)
            df_anzeige = df_gesamt[df_gesamt["datum"] >= start_datum]
        elif zeitraum == "14 Tage voraus":
            df_anzeige = df_gesamt[df_gesamt["datum"] >= heute]
        else:
            df_anzeige = df_gesamt

        # Alle 3 Karten/Diagramme untereinander darstellen
        zeige_kombi_diagramm(df_anzeige, heute)
        zeige_gradstunden_diagramm(df_anzeige, heute)
        zeige_temperatursumme_diagramm(df_gesamt)

        with st.expander("Rohdaten & Berechnungen anzeigen"):
            st.dataframe(df_anzeige, use_container_width=True)
            st.caption("Quelle: Open-Meteo · Berechnungen: Modell Zizers")

    except Exception as e:
        st.error(f"Fehler beim Laden der Wetterdaten: {e}")

hauptseite()