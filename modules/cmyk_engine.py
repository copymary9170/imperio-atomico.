import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote, normalizar_imagenes
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.history import guardar_historial
from modules.cmyk.inventory_engine import descontar_inventario, filtrar_tintas, mapear_consumo_ids, validar_stock
from modules.cmyk.page_size import ajustar_consumo_por_tamano


def _config_base_imprenta(tamano_pagina: str):
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
    area_a4 = 210.0 * 297.0
    area_custom = max(float(ancho_mm), 1.0) * max(float(alto_mm), 1.0)
    return max(0.20, min(4.0, area_custom / area_a4))


def _obtener_perfiles_driver(marca: str):
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
    mask_papel = nombres.str.contains("papel|bond|opalina|couche|glossy|mate|fotograf|cartulina", case=False, na=False)
    if col_categoria:
        mask_papel = mask_papel | categorias.str.contains("papel|impres|sustrato|material", case=False, na=False)

    df = df[mask_papel].copy()
    if col_stock:
        df["_stock_n"] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0.0)
        df = df[df["_stock_n"] > 0].copy()
    else:
        df["_stock_n"] = 0.0

    col_costo = _column_match(df, ["costo_unitario_usd", "precio_usd", "precio_venta_usd"])
    df["_costo_hoja"] = pd.to_numeric(df[col_costo], errors="coerce").fillna(0.0) if col_costo else 0.0

    df["_material_label"] = df.apply(
        lambda r: f"{str(r[col_nombre]).strip()} | Stock: {float(r['_stock_n']):.2f} | $/hoja: {float(r['_costo_hoja']):.4f}",
        axis=1,
    )
    return df.sort_values(by=["_stock_n", "_costo_hoja"], ascending=[False, True])


def _impresoras_disponibles(df_act: pd.DataFrame) -> list[dict]:
    if df_act is None or df_act.empty:
        return []

    df = df_act.copy()
    col_equipo = _column_match(df, ["equipo", "nombre"])
    col_categoria = _column_match(df, ["categoria", "tipo"])
    col_modelo = _column_match(df, ["modelo", "unidad"])
    col_unidad = _column_match(df, ["unidad", "tipo"])
    col_id = _column_match(df, ["id"])

    if not col_equipo:
        return []

    equipos = df[col_equipo].fillna("").astype(str)
    categorias = df[col_categoria].fillna("").astype(str) if col_categoria else ""
    mask = equipos.str.contains("impres|printer|plotter|epson|hp|canon|brother", case=False, na=False)
    if col_categoria:
        mask = mask | categorias.str.contains("impres", case=False, na=False)

    df = df[mask].copy()
    if df.empty:
        return []

    opciones = []
    for _, row in df.iterrows():
        nombre = str(row.get(col_equipo, "")).strip()
        modelo = str(row.get(col_modelo, "")).strip() if col_modelo else ""
        label = f"{nombre} ({modelo})" if modelo and modelo.lower() != "nan" else nombre
        opciones.append(
            {
                "id": int(row[col_id]) if col_id and pd.notna(row[col_id]) else None,
                "nombre": nombre,
                "label": label,
                "modelo": modelo,
                "unidad": str(row.get(col_unidad, "")).strip() if col_unidad else "",
                "categoria": str(row.get(col_categoria, "")).strip() if col_categoria else "",
            }
        )

    vistos = set()
    unicas = []
    for op in opciones:
        k = op["label"].lower()
        if k not in vistos:
            vistos.add(k)
            unicas.append(op)
    return unicas


def _detectar_marca_impresora(impresora: dict) -> str:
    texto = " ".join(
        [
            str(impresora.get("nombre", "")),
            str(impresora.get("modelo", "")),
            str(impresora.get("label", "")),
        ]
    ).lower()
    if "epson" in texto:
        return "Epson"
    return "HP"


def _sistema_tinta_recomendado(impresora: dict) -> str:
    texto = " ".join(
        [
            str(impresora.get("nombre", "")),
            str(impresora.get("modelo", "")),
            str(impresora.get("unidad", "")),
        ]
    ).lower()
    if any(k in texto for k in ["tank", "ecotank", "tanque", "l3", "l5", "l8"]):
        return "Tanque CMYK (4 tintas)"
    return "Cartucho (Color + Negro)"


def _precio_sugerido(
    costo_total: float,
    paginas: int,
    margen_utilidad: float,
    comision_pasarela: float,
    impuesto_venta: float,
    redondeo: float,
) -> dict:
    if paginas <= 0:
        return {
            "base": 0.0,
            "subtotal": 0.0,
            "comision": 0.0,
            "impuesto": 0.0,
            "precio_final": 0.0,
            "precio_unitario": 0.0,
        }

    base = float(costo_total)
    subtotal = base * (1.0 + (margen_utilidad / 100.0))
    comision = subtotal * (comision_pasarela / 100.0)
    impuesto = (subtotal + comision) * (impuesto_venta / 100.0)
    precio = subtotal + comision + impuesto

    if redondeo > 0:
        precio = round(precio / redondeo) * redondeo

    return {
        "base": base,
        "subtotal": subtotal,
        "comision": comision,
        "impuesto": impuesto,
        "precio_final": precio,
        "precio_unitario": precio / paginas,
    }


def render_cmyk(usuario):
    st.title("🖨️ Motor CMYK")
    st.caption("Analiza consumo de tinta y costo por lote usando inventario/activos.")

    df_inv, df_act, df_hist = _load_contexto_cmyk()
    opciones_imp = _impresoras_disponibles(df_act)

    if not opciones_imp:
        st.warning("No hay impresoras registradas en Activos. Registra al menos una para continuar.")
        return

    c1, c2, c3 = st.columns(3)
    impresora_op = c1.selectbox("Impresora (desde Activos)", opciones_imp, format_func=lambda x: x["label"])
    marca_default = _detectar_marca_impresora(impresora_op)
    marca = c2.selectbox("Marca / Driver", ["HP", "Epson"], index=0 if marca_default == "HP" else 1)
    calidad = c3.selectbox("Calidad", list(PERFILES_CALIDAD.keys()), index=1)

    st.caption(
        f"Activo seleccionado: ID #{impresora_op.get('id') or 'N/A'} | "
        f"Categoría: {impresora_op.get('categoria') or 'N/D'} | "
        f"Unidad: {impresora_op.get('unidad') or 'N/D'}"
    )

    perfiles_driver = _obtener_perfiles_driver(marca)
    c4, c5, c6 = st.columns(3)
    tipo_papel_driver = c4.selectbox("Perfil de papel (driver)", list(perfiles_driver.keys()))
    tamano = c5.selectbox("Tamaño", ["A5", "A4", "Carta", "Oficio", "A3", "Tabloide", "Personalizado"], index=1)
    sistema_default = _sistema_tinta_recomendado(impresora_op)
    sistema_tinta = c6.selectbox(
        "Sistema de tinta",
        ["Tanque CMYK (4 tintas)", "Cartucho (Color + Negro)"],
        index=0 if sistema_default.startswith("Tanque") else 1,
    )

    with st.expander("⚙️ Modo Pro CMYK", expanded=False):
        p1, p2, p3 = st.columns(3)
        refuerzo_negro = p1.slider("Refuerzo de negro (K)", min_value=0.0, max_value=0.40, value=0.12, step=0.01)
        desperdicio_factor = p2.slider("Factor de desperdicio", min_value=1.0, max_value=1.4, value=1.0, step=0.01)
        redondeo_precio = p3.number_input("Redondeo precio sugerido", min_value=0.0, value=0.05, step=0.05)

        pr1, pr2, pr3 = st.columns(3)
        margen_utilidad = pr1.slider("Margen de utilidad (%)", min_value=5, max_value=200, value=55, step=1)
        comision_pasarela = pr2.slider("Comisión cobro (%)", min_value=0.0, max_value=12.0, value=0.0, step=0.1)
        impuesto_venta = pr3.slider("Impuesto (%)", min_value=0.0, max_value=20.0, value=0.0, step=0.1)

    factor_area = 1.0
    if tamano == "Personalizado":
        a1, a2 = st.columns(2)
        ancho = a1.number_input("Ancho (mm)", min_value=50.0, value=210.0, step=1.0)
        alto = a2.number_input("Alto (mm)", min_value=50.0, value=297.0, step=1.0)
        factor_area = _factor_area_personalizada(ancho, alto)

    materiales = _materiales_papel_disponibles(df_inv)
    costo_material = 0.0
    material_papel = "Sin material"
    if not materiales.empty:
        idx = st.selectbox("Material de papel (inventario)", range(len(materiales)), format_func=lambda i: materiales.iloc[i]["_material_label"])
        material = materiales.iloc[idx]
        costo_material = float(material["_costo_hoja"])
        material_papel = str(material.get("nombre", material.get("item", "Papel")))

    archivos = st.file_uploader("Archivos (PDF/PNG/JPG)", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)
    ejecutar = st.button("Analizar lote", type="primary", use_container_width=True)

    if not ejecutar:
        st.subheader("Historial reciente")
        st.dataframe(df_hist, use_container_width=True)
        return


    if not archivos:
        st.error("Carga al menos un archivo para analizar.")
        return

    paginas = []
    for archivo in archivos:
        try:
            paginas.extend(normalizar_imagenes(archivo))
        except Exception as exc:
            st.warning(f"No se pudo procesar {archivo.name}: {exc}")

    if not paginas:
        st.error("No se pudieron procesar páginas válidas.")
        return

    base = _config_base_imprenta("A4" if tamano == "Personalizado" else tamano)
    factor_driver = float(perfiles_driver.get(tipo_papel_driver, 1.0))
    factor_calidad = float(PERFILES_CALIDAD[calidad]["ink_mult"])
    ml_base = float(base["ml_base"]) * factor_area
    if tamano != "Personalizado":
        ml_base = ajustar_consumo_por_tamano(ml_base, tamano)

    resultados, totales = analizar_lote(
        paginas,
        {
            "ml_base_pagina": ml_base,
            "factor_general": float(base["factor_general"]),
            "factor_calidad": factor_calidad,
            "factor_papel": factor_driver,
            "factor_k": 1.0,
            "auto_negro_inteligente": True,
            "refuerzo_negro": float(refuerzo_negro),
        },
    )

    total_paginas = len(resultados)
    precio_tinta = costo_tinta_ml(filtrar_tintas(df_inv), fallback=0.035)
    costos = calcular_costo_lote(
        totales_cmyk=totales,
        precio_tinta_ml=precio_tinta,
        paginas=total_paginas,
        costo_desgaste_pagina=float(base["costo_desgaste"]),
        desperdicio_factor=float(desperdicio_factor),
        desgaste_head_ml=0.005,
        costo_limpieza=0.0,
    )

    costo_papel_total = total_paginas * costo_material
    costo_total = float(costos["costo_total"]) + float(costo_papel_total)

    st.success(f"Análisis completado para {total_paginas} páginas.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("C (ml)", f"{totales['C']:.2f}")
    m2.metric("M (ml)", f"{totales['M']:.2f}")
    m3.metric("Y (ml)", f"{totales['Y']:.2f}")
    m4.metric("K (ml)", f"{totales['K']:.2f}")

    st.metric("Costo total estimado", f"$ {costo_total:.2f}")

    precio = _precio_sugerido(
        costo_total=costo_total,
        paginas=total_paginas,
        margen_utilidad=float(margen_utilidad),
        comision_pasarela=float(comision_pasarela),
        impuesto_venta=float(impuesto_venta),
        redondeo=float(redondeo_precio),
    )

    st.subheader("💹 Precio sugerido")
    p1, p2, p3 = st.columns(3)
    p1.metric("Precio final recomendado", f"$ {precio['precio_final']:.2f}")
    p2.metric("Precio recomendado / página", f"$ {precio['precio_unitario']:.4f}")
    utilidad_estimada = max(0.0, precio["precio_final"] - costo_total)
    p3.metric("Utilidad bruta estimada", f"$ {utilidad_estimada:.2f}")

    st.dataframe(
        pd.DataFrame(
            [
                {"Concepto": "Costo base", "Monto": precio["base"]},
                {"Concepto": f"Subtotal con margen ({margen_utilidad}%)", "Monto": precio["subtotal"]},
                {"Concepto": f"Comisión ({comision_pasarela}%)", "Monto": precio["comision"]},
                {"Concepto": f"Impuesto ({impuesto_venta}%)", "Monto": precio["impuesto"]},
                {"Concepto": "Precio final", "Monto": precio["precio_final"]},
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    b1, b2, b3 = st.columns(3)
    b1.metric("Costo tinta", f"$ {float(costos['costo_tinta']):.2f}")
    b2.metric("Costo desgaste", f"$ {float(costos['costo_desgaste']):.2f}")
    b3.metric("Costo papel", f"$ {float(costo_papel_total):.2f}")

    if total_paginas > 0:
        st.caption(f"Costo unitario aproximado: $ {(costo_total / total_paginas):.4f} por página")
    st.dataframe(pd.DataFrame(resultados), use_container_width=True)

    consumos_ids = mapear_consumo_ids(
        filtrar_tintas(df_inv),
        totales,
        sistema_tinta=sistema_tinta,
        impresora=impresora_op["nombre"],
    )
    alertas = validar_stock(df_inv, consumos_ids)
    for alerta in alertas:
        st.warning(alerta)

    if st.button("Guardar historial", use_container_width=True):
        guardar_historial(impresora=impresora_op["label"], paginas=total_paginas, costo=costo_total, consumos=totales)
        st.success("Historial guardado.")

    if not alertas and st.button("Descontar inventario", use_container_width=True):
        ok, msg = descontar_inventario(consumos_ids)
        if ok:
            st.success(msg)
        else:
            st.error(msg)
