import streamlit as st
import pandas as pd

from modules.cmyk.analyzer import normalizar_imagenes, analizar_lote
from modules.cmyk.cost_engine import (
    costo_tinta_ml,
    calcular_costo_lote,
    PERFILES_CALIDAD,
)
from modules.cmyk.history import (
    guardar_historial
)
from modules.cmyk.page_size import ajustar_consumo_por_tamano
from modules.cmyk.context import _load_contexto_cmyk


# ==========================================================
# BASE AUTOMÁTICA DE IMPRENTA
# ==========================================================


def _config_base_imprenta(tamano_pagina: str):
    """Devuelve parámetros base típicos de una imprenta digital."""

    base_por_tamano = {
        "A5": {"costo_desgaste": 0.012, "ml_base": 0.09, "factor_general": 0.90},
        "A4": {"costo_desgaste": 0.020, "ml_base": 0.15, "factor_general": 1.00},
        "Carta": {"costo_desgaste": 0.021, "ml_base": 0.16, "factor_general": 1.02},
        "Oficio": {"costo_desgaste": 0.025, "ml_base": 0.18, "factor_general": 1.08},
        "A3": {"costo_desgaste": 0.034, "ml_base": 0.25, "factor_general": 1.22},
        "Tabloide": {"costo_desgaste": 0.036, "ml_base": 0.27, "factor_general": 1.30},
    }

@@ -35,73 +36,152 @@ def _config_base_imprenta(tamano_pagina: str):
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

        st.subheader("⚙️ Ajustes de Calibración Automática")

        tamaños_disponibles = ["A5", "A4", "Carta", "Oficio", "A3", "Tabloide"]
        tamaño_pagina = st.selectbox("📄 Tamaño de página", tamaños_disponibles, index=1)

        base_imprenta = _config_base_imprenta(tamaño_pagina)

        costo_desgaste = base_imprenta["costo_desgaste"]
        ml_base_pagina = base_imprenta["ml_base"]
        factor_general = base_imprenta["factor_general"]

        st.caption(f"Costo desgaste por página ($): **{costo_desgaste:.3f}**")
        st.caption(f"Consumo base por página (ml): **{ml_base_pagina:.3f}**")
        st.caption(f"Factor General de Consumo: **{factor_general:.2f}**")
        st.caption("Base automática por tamaño de página (referencia de imprenta digital).")

        # ------------------------------------------------------
        # MODO AUTOMÁTICO DE IMPRENTA
        # ------------------------------------------------------

        # ------------------------------------------------------
        # PAPEL DE INVENTARIO (SE MANTIENE POR SESSION STATE)
        # ------------------------------------------------------

        posibles_cols_nombre = ["nombre", "item", "sku"]
        col_nombre = next((c for c in posibles_cols_nombre if c in df_inv.columns), None)

        df_papeles = pd.DataFrame()
        if col_nombre and not df_inv.empty:
            serie_nombre = df_inv[col_nombre].fillna("").astype(str)
            filtro_categoria = (
                df_inv["categoria"].fillna("").astype(str).str.contains("papel", case=False, na=False)
                if "categoria" in df_inv.columns
                else False
            )
            filtro_nombre = serie_nombre.str.contains(
                "papel|bond|fotograf|cartulina|opalina|sulfato|couche",
                case=False,
                na=False,
            )

            if isinstance(filtro_categoria, pd.Series):
                df_papeles = df_inv[filtro_categoria | filtro_nombre].copy()
            else:
                df_papeles = df_inv[filtro_nombre].copy()

        if not df_papeles.empty and "id" in df_papeles.columns:
            opciones_papel = {
                f"{str(row.get(col_nombre, 'Papel')).strip()} (ID {int(row['id'])})": int(row["id"])
                for _, row in df_papeles.iterrows()
            }
            ids_papel = list(opciones_papel.values())

            key_papel_inv = "cmyk_papel_inventario_id"
            if key_papel_inv not in st.session_state or st.session_state[key_papel_inv] not in ids_papel:
                st.session_state[key_papel_inv] = ids_papel[0]

            id_actual = int(st.session_state[key_papel_inv])
            idx_actual = ids_papel.index(id_actual) if id_actual in ids_papel else 0

            etiqueta_papel = st.selectbox(
                "📦 Papel desde inventario",
                list(opciones_papel.keys()),
                index=idx_actual,
                key="cmyk_papel_inventario_label",
            )
            st.session_state[key_papel_inv] = opciones_papel[etiqueta_papel]
            st.caption(f"Papel inventario seleccionado: **{etiqueta_papel}**")
        else:
            st.warning("No se detectaron papeles en inventario; se usará solo el perfil del driver.")

        # ------------------------------------------------------
        # CALIDAD Y PAPEL DE DRIVER
        # ------------------------------------------------------

        perfiles_calidad = {
            "Borrador": PERFILES_CALIDAD["Borrador"]["ink_mult"],
            "Normal": PERFILES_CALIDAD["Normal"]["ink_mult"],
            "Alta": PERFILES_CALIDAD["Alta"]["ink_mult"],
            "Foto": PERFILES_CALIDAD["Foto"]["ink_mult"],
        }
        calidad_impresion = st.selectbox(
            "🖨️ Calidad de impresión",
            list(perfiles_calidad.keys()),
            index=1,
        )
        factor_calidad = float(perfiles_calidad[calidad_impresion])

        perfiles_driver = {
            "Bond 75g": 0.92,
            "Bond 90g": 1.00,
            "Papel Mate": 1.10,
            "Papel Fotográfico": 1.18,
            "Cartulina": 1.14,
        }
        tipo_papel_driver = st.selectbox(
            "📄 Tipo de papel (driver)",
            list(perfiles_driver.keys()),
            index=1,
        )
        factor_papel = float(perfiles_driver[tipo_papel_driver])

        st.caption(f"Calidad de impresión: **{calidad_impresion}**")
        st.caption(f"Tipo de papel (driver): **{tipo_papel_driver}**")
        st.caption(f"Factor calidad aplicado: **{factor_calidad:.2f}**")
        st.caption(f"Factor papel aplicado: **{factor_papel:.2f}**")

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
