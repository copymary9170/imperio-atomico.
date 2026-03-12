from __future__ import annotations

import pandas as pd
import streamlit as st

from services.diagnostics_service import DiagnosticsService, analizar_hoja_diagnostico


def _obtener_capacidad_default(nombre_impresora: str) -> dict[str, float]:
    nombre = (nombre_impresora or "").upper()
    if "L805" in nombre:
        return {"Black": 70.0, "Cyan": 70.0, "Magenta": 70.0, "Yellow": 70.0}
    if "L3250" in nombre:
        return {"Black": 12.4, "Cyan": 14.0, "Magenta": 14.0, "Yellow": 14.0}
    return {"Black": 70.0, "Cyan": 70.0, "Magenta": 70.0, "Yellow": 70.0}


def render_diagnostico(usuario: str) -> None:
    st.caption(f"Usuario activo: {usuario}")

    impresora_sel = st.selectbox(
        "Impresora",
        ["EPSON L805", "EPSON L3250", "Otra"],
        index=0,
    )
    capacidad = _obtener_capacidad_default(impresora_sel)

    st.subheader("Entrada de diagnóstico")
    texto_ocr = st.text_area(
        "Texto OCR detectado",
        placeholder="Pega aquí el texto detectado de la hoja de diagnóstico...",
        height=140,
    )

    cols = st.columns(4)
    porcentajes_foto: dict[str, float] = {}
    for col, color in zip(cols, ["Cyan", "Magenta", "Yellow", "Black"]):
        with col:
            value = st.number_input(
                f"{color} (%)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
            )
            porcentajes_foto[color] = value

    vida_cabezal = st.slider("Vida de cabezal estimada (%)", 0, 100, 100)

    if not st.button("Analizar", type="primary"):
        return

    analisis = analizar_hoja_diagnostico(
        texto_ocr=texto_ocr,
        capacidad=capacidad,
        porcentajes_foto=porcentajes_foto,
        vida_cabezal_detectada=float(vida_cabezal),
    )

    resultados = analisis["resultados"]
    resumen = DiagnosticsService.summarize(
        resultados=resultados,
        vida_cabezal_pct=analisis["vida_cabezal_pct"],
    )

    st.subheader("Resultado final")
    st.dataframe(
        pd.DataFrame(
            [{"Color": c, "Nivel (ml)": v if v is not None else "No detectado"} for c, v in resultados.items()]
        ),
        use_container_width=True,
        hide_index=True,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Vida cabezal", f"{resumen['vida_cabezal_pct']:.2f}%")
    m2.metric("Estado tintas", str(resumen.get("estado_tintas", "N/D")))
    m3.metric("Estado cabezal", str(resumen.get("estado_cabezal", "N/D")))

    contador_imp = int(analisis.get("contador_impresiones", 0))
    if contador_imp > 0:
        st.info(f"📌 Total de páginas impresas detectado: {contador_imp}")
