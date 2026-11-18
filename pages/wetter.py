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
    st.title("Wetter – warum warnt die App?")
    st.caption(f"Zizers Halde · Saison {jahr}: Temperatur, Niederschlag, Blattnässe und Infektionen auf einen Blick.")


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
        st.subheader("Temperatur, Regen und Infektionen")
        legende([
            (symbol_linie(WEINROT), "Tagesmittel °C"),
            (symbol_kasten(BLAU), "Regen mm"),
            (symbol_punkt(WEINROT), "Infektion"),
            (symbol_punkt(GRAU_PUNKT), "Infektionswetter, aber noch nicht keimbereit"),
            (symbol_kasten(PROGNOSE_FLAECHE, "1px solid #D8C8B8"), "Prognose"),
        ])

        achse = alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m."))
        basis = alt.Chart(df).encode(x=achse)
        info = [alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                alt.Tooltip("temp_mittel:Q", title="Tagesmittel °C", format=".1f"),
                alt.Tooltip("niederschlag_mm:Q", title="Regen mm", format=".1f"),
                alt.Tooltip("quelle:N", title="Quelle")]

        regen = basis.mark_bar(color=BLAU, opacity=0.8).encode(
            y=alt.Y("niederschlag_mm:Q", title="Regen (mm)", axis=alt.Axis(orient="right")), tooltip=info)
        temperatur = basis.mark_line(color=WEINROT, strokeWidth=2.5).encode(
            y=alt.Y("temp_mittel:Q", title="Temperatur (°C)", axis=alt.Axis(orient="left")), tooltip=info
        ).add_params(zoom_waagrecht())   # Zoom gilt für alle Teile, weil sie dieselbe Datumsachse teilen

        # Punkte oben im Diagramm: Infektion (weinrot) oder Infektionswetter vor der Keimbereitschaft (grau)
        punkte_daten = df[df["infektion"] | df["vor_keimbereit"]].copy()
        punkte_daten["art"] = punkte_daten["infektion"].map({True: "Infektion", False: "noch nicht keimbereit"})
        punkte = alt.Chart(punkte_daten).mark_circle(size=120, opacity=1).encode(
            x=achse, y=alt.value(12),
            color=alt.Color("art:N", scale=alt.Scale(domain=["Infektion", "noch nicht keimbereit"],
                                                     range=[WEINROT, GRAU_PUNKT]), legend=None),
            tooltip=[alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                     alt.Tooltip("art:N", title="Art"), alt.Tooltip("quelle:N", title="Quelle")])

        diagramm = alt.layer(prognose_flaeche(df, heute), regen, temperatur, heute_linie(heute), punkte
                             ).resolve_scale(y="independent").properties(height=280)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Bis heute gemessen von Agrometeo, danach Prognose von Open-Meteo. "
                   "Infektionen in der Prognose sagt das Modell voraus (wie im Kalender). "
                   "Zoomen: Mausrad im Diagramm, verschieben: ziehen, zurücksetzen: Doppelklick.")


def zeige_gradstunden_diagramm(df, heute):
    """Diagramm 2: Gradstunden bei Blattnässe, daraus entstehen die Infektionen."""
    gemessen = df[df["quelle"] == "gemessen"].copy()
    with st.container(border=True):
        st.subheader("Infektionen: Wann war das Blatt lange genug nass und warm?")
        st.caption(f"Gradstunden = Temperatur aller Stunden mit nassem Blatt zusammengezählt. "
                   f"Ab {g.GRADSTUNDEN_INFEKTION} Gradstunden gibt es eine Infektion, "
                   f"aber erst, wenn die Sporen keimbereit sind. Gemessen von Agrometeo.")
        if gemessen.empty:
            st.info("Für diesen Zeitraum gibt es keine gemessenen Werte von Agrometeo.")
            return
        legende([(symbol_kasten(WEINROT), "Infektion"),
                 (symbol_kasten("#C9A3B0"), "keine Infektion"),
                 (symbol_linie(WEINROT), f"Grenze {g.GRADSTUNDEN_INFEKTION} Gradstunden")])

        gemessen["ergebnis"] = gemessen["infektion"].map({True: "Infektion", False: "keine Infektion"})
        balken = alt.Chart(gemessen).mark_bar().encode(
            x=alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m."),
                    scale=alt.Scale(domain=[df["datum"].min(), df["datum"].max()])),
            y=alt.Y("gradstunden_bn:Q", title="Gradstunden bei Blattnässe"),
            color=alt.Color("ergebnis:N", scale=alt.Scale(domain=["Infektion", "keine Infektion"],
                                                          range=[WEINROT, "#C9A3B0"]), legend=None),
            tooltip=[alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                     alt.Tooltip("blattnaesse_std:Q", title="Blatt nass (Stunden)", format=".1f"),
                     alt.Tooltip("gradstunden_bn:Q", title="Gradstunden", format=".0f"),
                     alt.Tooltip("blattzahl:Q", title="Blätter pro Trieb", format=".0f"),
                     alt.Tooltip("ergebnis:N", title="Ergebnis")])
        grenze = alt.Chart(pd.DataFrame({"y": [g.GRADSTUNDEN_INFEKTION]})).mark_rule(
            color=WEINROT, strokeDash=[4, 4]).encode(y="y:Q")
        diagramm = alt.layer(balken.add_params(zoom_waagrecht()), grenze, heute_linie(heute)).properties(height=250)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Nicht jeder Tag über der Grenze ist eine Infektion: Agrometeo prüft zusätzlich, ob die Rebe "
                   "schon genug Blätter hat, die der Pilz befallen kann (z. B. Ende April oft erst 2 kleine Blätter).")


def zeige_keimbereitschaft(df, heute, keimbereit):
    """Infobanner: Ist die Temperatursumme von 140 erreicht (Sporen keimbereit, Spritzsaison beginnt)?"""
    # Temperatursumme am heutigen Tag (seit 1.1., nur der Teil über 8 °C)
    bis_heute = df[df["datum"] <= heute]
    summe = bis_heute["temperatursumme"].iloc[-1] if len(bis_heute) > 0 else 0

    if keimbereit is not None and keimbereit <= heute:
        st.success(f"Die Temperatursumme von {g.KEIMBEREIT_AB} wurde am {keimbereit:%d.%m.%Y} erreicht: "
                   "Die Sporen sind keimbereit, die Spritzsaison hat begonnen.",
                   icon=":material/check_circle:")
    else:
        st.info(f"Die Sporen sind noch nicht keimbereit: Temperatursumme {summe:.0f} von {g.KEIMBEREIT_AB}. "
                "Erst danach beginnt die Spritzsaison.", icon=":material/info:")


def hauptseite():
    """Baut die komplette Wetter-Seite auf."""
    heute = pd.Timestamp(g.heute())   # Datum aus der Seitenleiste
    zeige_titel(heute.year)

    zeitraum = st.radio(
        "Zeitraum",
        ["Seit 1.1.", "3 Wochen + Prognose"],
        index=1,
        horizontal=True,
        label_visibility="collapsed"
    )

    try:
        with st.spinner("Lade Wetterdaten..."):
            df_gesamt = g.wetter_seit_neujahr(heute.date())
    except Exception as e:
        st.error(f"Fehler beim Laden der Wetterdaten: {e}")
        return

    keimbereit = g.keimbereitschaft(df_gesamt)
    # Grauer Punkt: Gradstunden für eine Infektion erreicht, aber die Sporen sind noch nicht keimbereit
    df_gesamt["vor_keimbereit"] = ((df_gesamt["gradstunden_bn"].fillna(0) >= g.GRADSTUNDEN_INFEKTION)
                                   & ~df_gesamt["keimbereit"])

    if zeitraum == "3 Wochen + Prognose":
        df_anzeige = df_gesamt[df_gesamt["datum"] >= heute - pd.Timedelta(days=21)]
    else:
        df_anzeige = df_gesamt

    zeige_kombi_diagramm(df_anzeige, heute)
    zeige_gradstunden_diagramm(df_anzeige, heute)
    zeige_keimbereitschaft(df_gesamt, heute, keimbereit)

    with st.expander("Rohdaten & Berechnungen anzeigen"):
        spalten = ["datum", "quelle", "temp_mittel", "niederschlag_mm", "blattnaesse_std",
                   "gradstunden_bn", "temperatursumme", "keimbereit", "infektion"]
        st.dataframe(df_anzeige[[s for s in spalten if s in df_anzeige]], width="stretch", hide_index=True)
        st.caption("Quelle: Agrometeo (gemessen) und Open-Meteo (Prognose) · Station Zizers")


hauptseite()