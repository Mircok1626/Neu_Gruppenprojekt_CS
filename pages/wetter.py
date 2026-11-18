"""Seite Wetter: Warum warnt die App?

Zeigt Temperatur, Regen, Gradstunden bei Blattnässe und die Temperatursumme.
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


def zeige_banner(jahr):
    """Zeigt den weinroten Banner oben auf der Wetter-Seite."""
    st.markdown(f"""
    <div style="
        background-color: #7B1E3A;
        color: white;
        padding: 32px 40px;
        border-radius: 20px;
        margin-bottom: 24px;
    ">
        <p style="margin: 0 0 6px 0; font-size: 14px; color: #F8E8EC; letter-spacing: 0.5px;">
            Zizers Halde · Saison {jahr}
        </p>
        <h1 style="margin: 0; font-size: 36px; color: white;">
            Wetter – warum warnt die App?
        </h1>
        <p style="margin: 8px 0 0 0; font-size: 18px; color: #F8E8EC;">
            Temperatur, Niederschlag, Blattnässe und Infektionen auf einen Blick.
        </p>
    </div>
    """, unsafe_allow_html=True)


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
            y=alt.Y("temp_mittel:Q", title="Temperatur (°C)", axis=alt.Axis(orient="left")), tooltip=info)

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
                   "Infektionen in der Prognose sagt das Modell voraus (wie im Kalender).")


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
        diagramm = alt.layer(balken, grenze, heute_linie(heute)).properties(height=250)
        st.altair_chart(diagramm, width="stretch")
        st.caption("Nicht jeder Tag über der Grenze ist eine Infektion: Agrometeo prüft zusätzlich, ob die Rebe "
                   "schon genug Blätter hat, die der Pilz befallen kann (z. B. Ende April oft erst 2 kleine Blätter).")


def zeige_temperatursumme_diagramm(df, heute, keimbereit):
    """Diagramm 3: Temperatursumme seit 1.1. mit 140-Linie. Ab 140 beginnt die Spritzsaison."""
    with st.container(border=True):
        st.subheader("Temperatursumme seit 1.1. – wann beginnt die Spritzsaison?")
        st.caption(f"Jeder Tag zählt mit, so viel er über 8 °C warm ist. Ab {g.KEIMBEREIT_AB} sind die "
                   "Wintersporen keimbereit. Ab dann warnt der Kalender vor Infektionen.")

        achse = alt.X("datum:T", title=None, axis=alt.Axis(format="%d.%m."))
        kurve = alt.Chart(df).mark_line(color=WEINROT, strokeWidth=2.5).encode(
            x=achse, y=alt.Y("temperatursumme:Q", title="Temperatursumme (°C)"),
            tooltip=[alt.Tooltip("datum:T", title="Datum", format="%d.%m.%Y"),
                     alt.Tooltip("temperatursumme:Q", title="Temperatursumme", format=".0f")])
        linie = alt.Chart(pd.DataFrame({"y": [g.KEIMBEREIT_AB], "text": [f"{g.KEIMBEREIT_AB} = keimbereit"]}))
        linie_140 = linie.mark_rule(color="#2E6B3E", strokeDash=[5, 5], strokeWidth=2).encode(y="y:Q")
        text_140 = linie.mark_text(align="left", dx=4, dy=-8, color="#2E6B3E").encode(
            x=alt.value(0), y="y:Q", text="text:N")
        ebenen = [prognose_flaeche(df, heute), kurve, linie_140, text_140, heute_linie(heute)]

        # Punkt am Tag der Keimbereitschaft mit dem Datum
        if keimbereit is not None:
            punkt_daten = pd.DataFrame({"datum": [keimbereit], "y": [g.KEIMBEREIT_AB],
                                        "text": [keimbereit.strftime("%d.%m.")]})
            punkt = alt.Chart(punkt_daten).mark_circle(color="#2E6B3E", size=110, opacity=1).encode(
                x="datum:T", y="y:Q")
            punkt_text = alt.Chart(punkt_daten).mark_text(dy=14, color="#2E6B3E", fontWeight="bold").encode(
                x="datum:T", y="y:Q", text="text:N")
            ebenen += [punkt, punkt_text]

        st.altair_chart(alt.layer(*ebenen).properties(height=250), width="stretch")
        if keimbereit is None:
            st.caption("Die Sporen sind noch nicht keimbereit. Die Spritzsaison hat noch nicht begonnen.")
        else:
            st.caption(f"Keimbereit seit {keimbereit:%d.%m.%Y}: Ab diesem Tag beginnt im Kalender die Spritzsaison.")


def hauptseite():
    """Baut die komplette Wetter-Seite auf."""
    heute = pd.Timestamp(g.heute())   # Datum aus der Seitenleiste
    zeige_banner(heute.year)

    zeitraum = st.radio(
        "Zeitraum",
        ["Seit 1.1.", "3 Wochen + Prognose", "14 Tage voraus"],
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
    elif zeitraum == "14 Tage voraus":
        df_anzeige = df_gesamt[df_gesamt["datum"] >= heute]
    else:
        df_anzeige = df_gesamt

    zeige_kombi_diagramm(df_anzeige, heute)
    zeige_gradstunden_diagramm(df_anzeige, heute)
    zeige_temperatursumme_diagramm(df_gesamt, heute, keimbereit)   # immer ab 1.1.

    with st.expander("Rohdaten & Berechnungen anzeigen"):
        spalten = ["datum", "quelle", "temp_mittel", "niederschlag_mm", "blattnaesse_std",
                   "gradstunden_bn", "temperatursumme", "keimbereit", "infektion"]
        st.dataframe(df_anzeige[[s for s in spalten if s in df_anzeige]], width="stretch", hide_index=True)
        st.caption("Quelle: Agrometeo (gemessen) und Open-Meteo (Prognose) · Station Zizers")


hauptseite()