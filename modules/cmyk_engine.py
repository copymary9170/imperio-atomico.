import streamlit as st
import pandas as pd

from modules.cmyk.analyzer import normalizar_imagenes, analizar_lote
from modules.cmyk.cost_engine import (
    costo_tinta_ml,
    calcular_costo_lote
)
from modules.cmyk.history import (
    guardar_historial
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

        st.subheader("⚙️ Ajustes de Calibración")

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

        # FACTOR GENERAL AUTOMÁTICO
        factor_general = 1.0
        st.caption("Factor de consumo: automático según cobertura de tinta")

        # ------------------------------------------------------
        # CALIDAD DE IMPRESIÓN
        # ------------------------------------------------------

        calidad_map = {
            "Borrador": 0.6,
            "Normal": 1.0,
            "Alta": 1.5,
            "Foto": 2.0
        }

        calidad_sel = st.selectbox(
            "Calidad de impresión",
            list(calidad_map.keys()),
            index=1
        )

        factor_calidad = calidad_map[calidad_sel]

        # ------------------------------------------------------
        # DRIVER DE PAPEL
        # ------------------------------------------------------

        papel_map = {
            "Plain Paper": 0.8,
            "Bond 90g": 1.0,
            "Matte": 1.3,
            "Glossy": 1.6,
            "Photo Premium": 1.9,
            "Cartulina": 1.4
        }

        papel_sel = st.selectbox(
            "Tipo de papel (driver)",
            list(papel_map.keys()),
            index=1
        )

        factor_papel = papel_map[papel_sel]

        st.caption(f"Factor calidad aplicado: **{factor_calidad}**")
        st.caption(f"Factor papel aplicado: **{factor_papel}**")

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
    totales = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}

    with st.spinner("Analizando cobertura CMYK..."):

        for archivo in archivos:

            paginas = normalizar_imagenes(archivo)

            config = {
                "ml_base_pagina": ml_base_pagina,
                "factor_general": factor_general,
                "factor_calidad": factor_calidad,
                "factor_papel": factor_papel,
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

    totales_ajustados = {
        k: ajustar_consumo_por_tamano(v, tamaño_pagina)
        for k, v in totales.items()
    }

    total_ml = sum(totales_ajustados.values())

    # ------------------------------------------------------
    # COSTO
    # ------------------------------------------------------

    precio_tinta = costo_tinta_ml(df_inv, fallback=0.10)

    costo = calcular_costo_lote(
        totales_ajustados,
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

    colA, colB, colC = st.columns(3)

    colA.metric("Consumo total tinta", f"{total_ml:.3f} ml")
    colB.metric("Precio tinta/ml", f"$ {precio_tinta:.3f}")
    colC.metric("Costo total estimado", f"$ {costo['costo_total']:.2f}")

    # ------------------------------------------------------
    # HISTORIAL
    # ------------------------------------------------------

    if st.button("Guardar en historial"):

        guardar_historial(
            "Impresora",
            len(resultados),
            costo["costo_total"],
            totales_ajustados
        )

        st.success("Historial guardado correctamente.")

    st.divider()

    st.subheader("Historial reciente")

    st.dataframe(df_hist, use_container_width=True)
