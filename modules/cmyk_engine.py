import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote, normalizar_imagenes
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.history import guardar_historial
from modules.cmyk.page_size import ajustar_consumo_por_tamano


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
    return base_por_tamano.get(tamano_pagina, base_por_tamano["A4"])


def _factor_area_personalizada(ancho_mm: float, alto_mm: float) -> float:
    """Factor relativo usando A4 como referencia para tamaños personalizados."""
    area_a4 = 210.0 * 297.0
    area_custom = max(float(ancho_mm), 1.0) * max(float(alto_mm), 1.0)
    return max(0.20, min(4.0, area_custom / area_a4))


def _obtener_perfiles_driver(marca: str):
    """Perfiles de tipo de papel similares a drivers reales para HP y Epson."""
    perfiles_por_marca = {
        "HP": {
            "Papel normal": 1.00,
            "Papeles fotográficos HP": 1.18,
            "Papel profesional o folleto mate HP": 1.12,
            "Papel de presentación mate HP": 1.10,
            "Papel profesional o folleto brillante HP": 1.16,
            "Otr. papeles fotog. inyec tinta": 1.20,
            "Otr. papeles inyec. tinta mates": 1.08,
            "Otr. pap. inyec tinta brillante": 1.14,
            "Papel normal, ligero/reciclado": 0.94,
        },
        "Epson": {
            "Papel normal": 1.00,
            "Epson Photo Paper Glossy": 1.17,
            "Epson Premium Photo Paper Glossy": 1.22,
            "Epson Ultra Premium Photo Paper Glossy": 1.26,
            "Epson Photo Paper Matte": 1.12,
            "Epson Premium Presentation Paper Matte": 1.10,
            "Epson Premium Presentation Paper Matte Double-sided": 1.11,
            "Epson Brochure & Flyer Paper Matte": 1.13,
            "Sobres": 0.96,
        },
    }
    return perfiles_por_marca.get(marca, perfiles_por_marca["HP"])


def _column_match(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _materiales_papel_disponibles(df_inv: pd.DataFrame) -> pd.DataFrame:
    """Filtra materiales de papel presentes en inventario y con stock positivo."""
    if df_inv.empty:
        return pd.DataFrame()

    df = df_inv.copy()

    col_nombre = _column_match(df, ["nombre", "item", "sku"])
    col_categoria = _column_match(df, ["categoria", "familia", "tipo"])
    col_stock = _column_match(df, ["stock_actual", "stock", "cantidad"])

    if not col_nombre:
        return pd.DataFrame()

    nombres = df[col_nombre].fillna("").astype(str)
    categorias = df[col_categoria].fillna("").astype(str) if col_categoria else ""

    mask_papel_nombre = nombres.str.contains("papel|bond|opalina|couche|glossy|mate|fotograf|cartulina", case=False, na=False)
    if col_categoria:
        mask_papel_categoria = categorias.str.contains("papel|impres|sustrato|material", case=False, na=False)
        mask_papel = mask_papel_nombre | mask_papel_categoria
    else:
        mask_papel = mask_papel_nombre

    df = df[mask_papel].copy()

    if col_stock:
        df["_stock_n"] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0.0)
        df = df[df["_stock_n"] > 0].copy()
    else:
        df["_stock_n"] = 0.0

    col_costo = _column_match(df, ["costo_unitario_usd", "precio_usd", "precio_venta_usd"])
    df["_costo_hoja"] = pd.to_numeric(df[col_costo], errors="coerce").fillna(0.0) if col_costo else 0.0

    col_id = _column_match(df, ["id", "inventario_id"])
    if col_id:
        df["_id"] = df[col_id]
    else:
        df["_id"] = df.index.astype(str)

    df["_material_label"] = df.apply(
        lambda r: f"{str(r[col_nombre]).strip()} | Stock: {float(r['_stock_n']):.2f} | $/hoja: {float(r['_costo_hoja']):.4f}",
        axis=1,
    )

    return df.sort_values(by=["_stock_n", "_costo_hoja"], ascending=[False, True])


# ==========================================================
# RENDER PRINCIPAL
# ==========================================================


def render_cmyk(usuario: str):
    st.title("🎨 Analizador Profesional de Cobertura CMYK")
    st.caption(f"Operador: {usuario}")

    try:
        df_inv, _, df_hist = _load_contexto_cmyk()
    except Exception as e:
        st.error(f"Error cargando datos CMYK: {e}")
        return

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("⚙️ Ajustes de Calibración Automática")

        tamanos_disponibles = ["A5", "A4", "Carta", "Oficio", "A3", "Tabloide", "Personalizado"]
        tamano_pagina = st.selectbox("📄 Tamaño de página", tamanos_disponibles, index=1)

        if tamano_pagina == "Personalizado":
            col_ancho, col_alto = st.columns(2)
            with col_ancho:
                ancho_custom = st.number_input("Ancho (mm)", min_value=50.0, max_value=2000.0, value=210.0, step=1.0)
            with col_alto:
                alto_custom = st.number_input("Alto (mm)", min_value=50.0, max_value=2000.0, value=297.0, step=1.0)

            factor_custom = _factor_area_personalizada(ancho_custom, alto_custom)
            base_a4 = _config_base_imprenta("A4")
            base_imprenta = {
                "costo_desgaste": base_a4["costo_desgaste"] * factor_custom,
                "ml_base": base_a4["ml_base"] * factor_custom,
                "factor_general": base_a4["factor_general"] * factor_custom,
            }
            st.caption(f"Formato personalizado: **{ancho_custom:.0f} x {alto_custom:.0f} mm**")
            st.caption(f"Factor por área aplicado: **{factor_custom:.2f}x**")
        else:
            base_imprenta = _config_base_imprenta(tamano_pagina)

        costo_desgaste = base_imprenta["costo_desgaste"]
        ml_base_pagina = base_imprenta["ml_base"]
        factor_general = base_imprenta["factor_general"]

        st.caption(f"Costo desgaste por página ($): **{costo_desgaste:.3f}**")
        st.caption(f"Consumo base por página (ml): **{ml_base_pagina:.3f}**")
        st.caption(f"Factor general de consumo: **{factor_general:.2f}**")

        perfiles_calidad = {
            "Borrador": PERFILES_CALIDAD["Borrador"]["ink_mult"],
            "Normal": PERFILES_CALIDAD["Normal"]["ink_mult"],
            "Alta": PERFILES_CALIDAD["Alta"]["ink_mult"],
            "Foto": PERFILES_CALIDAD["Foto"]["ink_mult"],
        }
        calidad_impresion = st.selectbox("🖨️ Calidad de impresión", list(perfiles_calidad.keys()), index=1)
        factor_calidad = float(perfiles_calidad[calidad_impresion])

        marca_driver = st.selectbox("🧩 Marca / driver", ["HP", "Epson"], index=0)
        perfiles_driver = _obtener_perfiles_driver(marca_driver)
        tipo_papel_driver = st.selectbox("📄 Tipo de papel (driver)", list(perfiles_driver.keys()), index=0)
        factor_papel = float(perfiles_driver[tipo_papel_driver])

        st.caption(f"Factor calidad aplicado: **{factor_calidad:.2f}**")
        st.caption(f"Factor papel aplicado: **{factor_papel:.2f}**")

        st.markdown("#### 📦 Material / papel desde inventario")
        papeles_inv = _materiales_papel_disponibles(df_inv)
        costo_material_pagina = 0.0
        material_papel = "No seleccionado"

        if papeles_inv.empty:
            st.warning("No hay materiales tipo papel con stock disponible en inventario.")
        else:
            idx_sel = st.selectbox(
                "Selecciona material/papel (solo inventario con stock)",
                options=list(range(len(papeles_inv))),
                format_func=lambda i: papeles_inv.iloc[i]["_material_label"],
                index=0,
            )
            fila_papel = papeles_inv.iloc[int(idx_sel)]
            material_papel = str(fila_papel["_material_label"])
            costo_material_pagina = float(fila_papel["_costo_hoja"])
            st.caption(f"Material activo: **{material_papel}**")

        editar_parametros = st.toggle("Editar parámetros calculados", value=False)
        if editar_parametros:
            costo_desgaste = st.number_input("Costo desgaste por página ($)", min_value=0.0, value=float(costo_desgaste), step=0.001)
            ml_base_pagina = st.number_input("Consumo base por página (ml)", min_value=0.001, value=float(ml_base_pagina), step=0.001)
            factor_general = st.number_input("Factor general de consumo", min_value=0.10, value=float(factor_general), step=0.01)

    with col2:
        archivos = st.file_uploader("Carga tus diseños", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

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
                "refuerzo_negro": 0.06,
            }

            res, tot = analizar_lote(paginas, config)
            for k in totales:
                totales[k] += tot[k]
            resultados.extend(res)

    totales_ajustados = {k: ajustar_consumo_por_tamano(v, tamano_pagina) for k, v in totales.items()}
    total_ml = sum(totales_ajustados.values())
    total_paginas = len(resultados)

    precio_tinta = costo_tinta_ml(df_inv, fallback=0.10)
    costo = calcular_costo_lote(totales_ajustados, precio_tinta, len(resultados), costo_desgaste, 1.15, 0.005, 0.02)
    costo_material_total = costo_material_pagina * float(total_paginas)
    costo_total_con_material = float(costo["costo_total"]) + float(costo_material_total)

    df_resultados = pd.DataFrame(resultados)

    st.subheader("Resumen general")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Consumo total tinta", f"{total_ml:.3f} ml")
    col_b.metric("Precio tinta/ml", f"$ {precio_tinta:.3f}")
    col_c.metric("Costo material", f"$ {costo_material_total:.2f}")
    col_d.metric("Costo total estimado", f"$ {costo_total_con_material:.2f}")
    st.caption(f"Material seleccionado: **{material_papel}**")

    st.subheader("Resultados por página")
    st.dataframe(df_resultados, use_container_width=True, height=360)

    st.markdown("#### Desglose de costos")
    st.dataframe(
        pd.DataFrame(
            [
                {"Concepto": "Tinta", "Monto ($)": round(float(costo["costo_tinta"]), 4)},
                {"Concepto": "Desgaste por páginas", "Monto ($)": round(float(costo["costo_desgaste"]), 4)},
                {"Concepto": "Cabezal", "Monto ($)": round(float(costo["costo_cabezal"]), 4)},
                {"Concepto": "Limpieza", "Monto ($)": 0.02},
                {"Concepto": "Material/Papel", "Monto ($)": round(float(costo_material_total), 4)},
                {"Concepto": "TOTAL", "Monto ($)": round(float(costo_total_con_material), 4)},
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Consumo CMYK")
    st.bar_chart(pd.DataFrame([totales_ajustados], index=["ml"]))

    col_guardar, col_exportar = st.columns([1, 1])
    with col_guardar:
        if st.button("Guardar en historial", use_container_width=True):
            guardar_historial("Impresora", len(resultados), costo_total_con_material, totales_ajustados)
            st.success("Historial guardado correctamente.")
    with col_exportar:
        st.download_button(
            "Descargar detalle CSV",
            data=df_resultados.to_csv(index=False).encode("utf-8"),
            file_name="analisis_cmyk_detalle.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Historial reciente")
    st.dataframe(df_hist, use_container_width=True)
