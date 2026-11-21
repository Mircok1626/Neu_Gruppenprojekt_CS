"""Seite Wetter: Warum warnt die App?

Zeigt Temperatur, Regen, Gradstunden bei Blattnässe und ob die Sporen keimbereit sind.
Bis «heute» (Datum links in der Seitenleiste) kommen die Werte gemessen von Agrometeo,
seit dem 1.1. und mit echter Blattnässe. Danach folgt die Prognose von Open-Meteo,
dort sagt das Modell (gemeinsam.py) die Infektionen voraus.
"""

import altair as alt
import pandas as pd
import streamlit as st

import gemeinsam as g   # gemeinsame Daten und Funktionen (Datum, Agrometeo, Modell, Saison)

WEINROT = "#7B1E3A"
BLAU = "#5B8DBE"
GRAU_PUNKT = "#8A8A8A"
PROGNOSE_FLAECHE = "#F1E8E0"


def zeige_titel(jahr):
    """Zeigt Titel und Untertitel, gleich wie auf den anderen Seiten."""
    st.title("Weather – why does the app warn?")
    st.caption(f"Zizers Halde · Season {jahr}: temperature, precipitation, leaf wetness and infections at a glance.")


def legende(eintraege):
    """Zeigt eine Legende als Zeile mit kleinen Symbolen (eintraege: Liste von (Symbol-HTML, Text))."""
    teile = [f"<span style='margin-left:16px; white-space:nowrap;'>{symbol} {text}</span>"
             for symbol, text in eintraege]
    st.markdown("<div style='text-align:right; font-size:13px; margin-bottom:4px;'>"
                + "".join(teile) + "</div>", unsafe_allow_html=True)


def symbol_linie(farbe):
    return f"<span style='display:inline-block; width:18px; height:3px; background:{farbe}; vertical-align:middle;'></span>"


def symbol_kasten(farbe, rand="none"):
    return (f"<span style='display:inline-block; width:12px; height:12px; background:{farbe}; "
            f"border:{rand}; border-radius:2px; vertical-align:middle;'></span>")


def symbol_punkt(farbe):
    return (f"<span style='display:inline-block; width:11px; height:11px; background:{farbe}; "
            f"border-radius:50%; vertical-align:middle;'></span>")


def prognose_flaeche(df, heute):
    """Hellbraune Fläche über der Prognose (alles nach heute)."""
    bereich = pd.DataFrame({"von": [heute], "bis": [df["datum"].max() + pd.Timedelta(days=1)]})
    return alt.Chart(bereich).mark_rect(color=PROGNOSE_FLAECHE).encode(x="von:T", x2="bis:T")


def heute_linie(heute):
    """Gestrichelte senkrechte Linie bei heute."""
    return alt.Chart(pd.DataFrame({"heute": [heute]})).mark_rule(
        color="#333333", strokeDash=[4, 4]).encode(x="heute:T")


def zoom_waagrecht():
    """Erlaubt Reinzoomen (Mausrad) und Verschieben (ziehen), aber nur entlang der Zeitachse.

    encodings=["x"]: Nur die Datumsachse bewegt sich. Die Achsen für Temperatur, Regen
    und Gradstunden bleiben fest, darum kann nichts ins Minus rutschen.
    Doppelklick ins Diagramm setzt den Zoom wieder zurück.
    """
    return alt.selection_interval(bind="scales", encodings=["x"])


def zeige_kombi_diagramm(df, heute):
    """Diagramm 1: Temperatur (Linie), Regen (Balken) und Infektionen (Punkte)."""
    with st.container(border=True):
        st.subheader("Temperature, rain and infections")
        legende([
            (symbol_linie(WEINROT), "Daily mean °C"),
            (symbol_kasten(BLAU), "Rain mm"),
            (symbol_punkt(WEINROT), "Infection"),
            (symbol_punkt(GRAU_PUNKT), "Infection weather, but spores not yet ready to germinate"),
            (symbol_kasten(PROGNOSE_FLAECHE, "1px solid #D8C8B8"), "Forecast"),
        ])

        achse = alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m."))
        basis = alt.Chart(df).encode(x=achse)
        info = [alt.Tooltip("datum:T", title="Date", format="%d.%m.%Y"),
                alt.Tooltip("temp_mittel:Q", title="Daily mean °C", format=".1f"),
                alt.Tooltip("niederschlag_mm:Q", title="Rain mm", format=".1f"),
                alt.Tooltip("quelle:N", title="Source")]

        regen = basis.mark_bar(color=BLAU, opacity=0.8).encode(
            y=alt.Y("niederschlag_mm:Q", title="Rain (mm)", axis=alt.Axis(orient="right")), tooltip=info)
        temperatur = basis.mark_line(color=WEINROT, strokeWidth=2.5).encode(
            y=alt.Y("temp_mittel:Q", title="Temperature (°C)", axis=alt.Axis(orient="left")), tooltip=info
        ).add_params(zoom_waagrecht())   # Zoom gilt für alle Teile, weil sie dieselbe Datumsachse teilen

        # Punkte oben im Diagramm: Infektion (weinrot) oder Infektionswetter vor der Keimbereitschaft (grau)
        punkte_daten = df[df["infektion"] | df["vor_keimbereit"]].copy()
        punkte_daten["art"] = punkte_daten["infektion"].map({True: "Infection", False: "not yet ready to germinate"})
        punkte = alt.Chart(punkte_daten).mark_circle(size=120, opacity=1).encode(
            x=achse, y=alt.value(12),
            color=alt.Color("art:N", scale=alt.Scale(domain=["Infection", "not yet ready to germinate"],
                                                     range=[WEINROT, GRAU_PUNKT]), legend=None),
            tooltip=[alt.Tooltip("datum:T", title="Date", format="%d.%m.%Y"),
                     alt.Tooltip("art:N", title="Type"), alt.Tooltip("quelle:N", title="Source")])

        diagramm = alt.layer(prognose_flaeche(df, heute), regen, temperatur, heute_linie(heute), punkte
                             ).resolve_scale(y="independent").properties(height=280)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Measured by Agrometeo up to today, then forecast from Open-Meteo. "
                   "Infections in the forecast are predicted by the model (as in the calendar). "
                   "Zoom: mouse wheel in the chart, pan: drag, reset: double-click.")


def zeige_gradstunden_diagramm(df, heute):
    """Diagramm 2: Gradstunden bei Blattnässe, daraus entstehen die Infektionen."""
    gemessen = df[df["quelle"] == "measured"].copy()
    with st.container(border=True):
        st.subheader("Infections: When was the leaf wet and warm for long enough?")
        st.caption(f"Degree hours = temperature of all hours with a wet leaf added up. "
                   f"From {g.GRADSTUNDEN_INFEKTION} degree hours there is an infection, "
                   f"but only once the spores are ready to germinate. Measured by Agrometeo.")
        if gemessen.empty:
            st.info("There are no measured values from Agrometeo for this period.")
            return
        legende([(symbol_kasten(WEINROT), "Infection"),
                 (symbol_kasten("#C9A3B0"), "no infection"),
                 (symbol_linie(WEINROT), f"Threshold {g.GRADSTUNDEN_INFEKTION} degree hours")])

        gemessen["ergebnis"] = gemessen["infektion"].map({True: "Infection", False: "no infection"})
        balken = alt.Chart(gemessen).mark_bar().encode(
            x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m."),
                    scale=alt.Scale(domain=[df["datum"].min(), df["datum"].max()])),
            y=alt.Y("gradstunden_bn:Q", title="Degree hours with leaf wetness"),
            color=alt.Color("ergebnis:N", scale=alt.Scale(domain=["Infection", "no infection"],
                                                          range=[WEINROT, "#C9A3B0"]), legend=None),
            tooltip=[alt.Tooltip("datum:T", title="Date", format="%d.%m.%Y"),
                     alt.Tooltip("blattnaesse_std:Q", title="Leaf wet (hours)", format=".1f"),
                     alt.Tooltip("gradstunden_bn:Q", title="Degree hours", format=".0f"),
                     alt.Tooltip("blattzahl:Q", title="Leaves per shoot", format=".0f"),
                     alt.Tooltip("ergebnis:N", title="Result")])
        grenze = alt.Chart(pd.DataFrame({"y": [g.GRADSTUNDEN_INFEKTION]})).mark_rule(
            color=WEINROT, strokeDash=[4, 4]).encode(y="y:Q")
        diagramm = alt.layer(balken.add_params(zoom_waagrecht()), grenze, heute_linie(heute)).properties(height=250)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Not every day above the threshold is an infection: Agrometeo also checks whether the vine "
                   "already has enough leaves that the fungus can attack (e.g. at the end of April often only 2 small leaves).")


def zeige_keimbereitschaft(df, heute, keimbereit):
    """Infobanner: Ist die Temperatursumme von 140 erreicht (Sporen keimbereit, Spritzsaison beginnt)?"""
    # Temperatursumme am heutigen Tag (seit 1.1., nur der Teil über 8 °C)
    bis_heute = df[df["datum"] <= heute]
    summe = bis_heute["temperatursumme"].iloc[-1] if len(bis_heute) > 0 else 0

    if keimbereit is not None and keimbereit <= heute:
        st.success(f"The temperature sum of {g.KEIMBEREIT_AB} was reached on {keimbereit:%d.%m.%Y}: "
                   "The spores are ready to germinate, the spray season has begun.",
                   icon=":material/check_circle:")
    else:
        st.info(f"The spores are not yet ready to germinate: temperature sum {summe:.0f} of {g.KEIMBEREIT_AB}. "
                "The spray season only begins after that.", icon=":material/info:")


def hauptseite():
    """Baut die komplette Wetter-Seite auf."""
    heute = pd.Timestamp(g.heute())   # Datum aus der Seitenleiste
    zeige_titel(heute.year)

    zeitraum = st.radio(
        "Period",
        ["Since 1 Jan", "3 weeks + forecast"],
        index=1,
        horizontal=True,
        label_visibility="collapsed"
    )

    try:
        with st.spinner("Loading weather data..."):
            df_gesamt = g.wetter_seit_neujahr(heute.date())
    except Exception as e:
        st.error(f"Error loading the weather data: {e}")
        return

    keimbereit = g.keimbereitschaft(df_gesamt)
    # Grauer Punkt: Gradstunden für eine Infektion erreicht, aber die Sporen sind noch nicht keimbereit
    df_gesamt["vor_keimbereit"] = ((df_gesamt["gradstunden_bn"].fillna(0) >= g.GRADSTUNDEN_INFEKTION)
                                   & ~df_gesamt["keimbereit"])

    if zeitraum == "3 weeks + forecast":
        df_anzeige = df_gesamt[df_gesamt["datum"] >= heute - pd.Timedelta(days=21)]
    else:
        df_anzeige = df_gesamt

    zeige_kombi_diagramm(df_anzeige, heute)
    zeige_gradstunden_diagramm(df_anzeige, heute)
    zeige_keimbereitschaft(df_gesamt, heute, keimbereit)

    with st.expander("Show raw data & calculations"):
        spalten = ["datum", "quelle", "temp_mittel", "niederschlag_mm", "blattnaesse_std",
                   "gradstunden_bn", "temperatursumme", "keimbereit", "infektion"]
        st.dataframe(df_anzeige[[s for s in spalten if s in df_anzeige]], width="stretch", hide_index=True)
        st.caption("Source: Agrometeo (measured) and Open-Meteo (forecast) · Zizers station")


hauptseite()
