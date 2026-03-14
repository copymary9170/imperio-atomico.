import streamlit as st
import pandas as pd
from datetime import datetime

from modules.cmyk.analyzer import normalizar_imagenes, analizar_lote
from modules.cmyk.cost_engine import (
    costo_tinta_ml,
    calcular_costo_lote,
    simular_papel_calidad
)
from modules.cmyk.inventory_engine import (
    filtrar_tintas,
    mapear_consumo_ids,
    validar_stock,
    descontar_inventario
)
from modules.cmyk.history import (
    guardar_historial,
    obtener_historial
)
from modules.cmyk.page_size import ajustar_consumo_por_tamano
from modules.cmyk.context import _load_contexto_cmyk


# ==========================================================
# RENDER PRINCIPAL
# ==========================================================

def render_cmyk(usuario: str):

    st.title("🎨 Analizador Profesional de Cobertura CMYK")
    st.caption(f"Operador: {usuario}")

    try:
        df_inv, df_act, df_hist = _load_contexto_cmyk()
    except Exception as e:
        st.error(f"Error cargando datos CMYK: {e}")
        return

    # ------------------------------------------------------
    # CONFIGURACIÓN
    # ------------------------------------------------------

    col1, col2 = st.columns([1, 2])

    with col1:

        tamaño_pagina = st.selectbox(
            "📄 Tamaño de página",
            ["A5", "A4", "A3", "Carta", "Oficio", "Tabloide"],
            index=1
        )

        costo_desgaste = st.number_input(
            "Costo desgaste por página ($)",
            min_value=0.0,
            value=0.02,
            step=0.005
        )

        ml_base_pagina = st.number_input(
            "Consumo base por página (ml)",
            min_value=0.01,
            value=0.15
        )

        factor_general = st.slider(
            "Factor general de consumo",
            1.0, 3.0, 1.5
        )

    with col2:

        archivos = st.file_uploader(
            "Carga tus diseños",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True
        )

    # ------------------------------------------------------
    # ANÁLISIS
    # ------------------------------------------------------

    if not archivos:
        st.info("Sube archivos para iniciar el análisis.")
        return

    resultados = []
    totales = {"C": 0, "M": 0, "Y": 0, "K": 0}

    with st.spinner("Analizando cobertura CMYK..."):

        for archivo in archivos:

            paginas = normalizar_imagenes(archivo)

            config = {
                "ml_base_pagina": ml_base_pagina,
                "factor_general": factor_general,
                "factor_calidad": 1.0,
                "factor_papel": 1.0,
                "factor_k": 0.8,
                "auto_negro_inteligente": True,
                "refuerzo_negro": 0.06
            }

            res, tot = analizar_lote(paginas, config)

            for k in totales:
                totales[k] += tot[k]

            resultados.extend(res)

    # ------------------------------------------------------
    # AJUSTAR POR TAMAÑO DE PÁGINA
    # ------------------------------------------------------

    total_ml = sum(totales.values())

    total_ml = ajustar_consumo_por_tamano(
        total_ml,
        tamaño_pagina
    )

    # ------------------------------------------------------
    # COSTO
    # ------------------------------------------------------

    precio_tinta = costo_tinta_ml(df_inv, fallback=0.10)

    costo = calcular_costo_lote(
        totales,
        precio_tinta,
        len(resultados),
        costo_desgaste,
        1.15,
        0.005,
        0.02
    )

    # ------------------------------------------------------
    # RESULTADOS
    # ------------------------------------------------------

    df_resultados = pd.DataFrame(resultados)

    st.subheader("Resultados por página")

    st.dataframe(df_resultados, use_container_width=True)

    st.metric(
        "Costo total estimado",
        f"$ {costo['costo_total']:.2f}"
    )

    # ------------------------------------------------------
    # HISTORIAL
    # ------------------------------------------------------

    if st.button("Guardar en historial"):

        guardar_historial(
            "Impresora",
            len(resultados),
            costo["costo_total"],
            totales
        )

        st.success("Historial guardado.")

    st.divider()

    st.subheader("Historial reciente")

    st.dataframe(df_hist, use_container_width=True)
