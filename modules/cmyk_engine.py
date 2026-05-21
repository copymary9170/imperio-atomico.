import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote, normalizar_imagenes
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.history import guardar_historial
from modules.cmyk.inventory_engine import descontar_inventario, filtrar_tintas, mapear_consumo_ids, validar_stock
from modules.cmyk.page_size import ajustar_consumo_por_tamano
from modules.integration_hub import render_send_buttons


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
    texto = " ".join([str(impresora.get("nombre", "")), str(impresora.get("modelo", "")), str(impresora.get("label", ""))]).lower()
    if "epson" in texto:
        return "Epson"
    return "HP"


def _sistema_tinta_recomendado(impresora: dict) -> str:
    texto = " ".join([str(impresora.get("nombre", "")), str(impresora.get("modelo", "")), str(impresora.get("unidad", ""))]).lower()
    if any(k in texto for k in ["tank", "ecotank", "tanque", "l3", "l5", "l8"]):
        return "Tanque CMYK (4 tintas)"
    return "Cartucho (Color + Negro)"


def _precio_sugerido(costo_total: float, paginas: int, margen_utilidad: float, comision_pasarela: float, impuesto_venta: float, redondeo: float) -> dict:
    if paginas <= 0:
        return {"base": 0.0, "subtotal": 0.0, "comision": 0.0, "impuesto": 0.0, "precio_final": 0.0, "precio_unitario": 0.0}
    base = float(costo_total)
    subtotal = base * (1.0 + (margen_utilidad / 100.0))
    comision = subtotal * (comision_pasarela / 100.0)
    impuesto = (subtotal + comision) * (impuesto_venta / 100.0)
    precio = subtotal + comision + impuesto
    if redondeo > 0:
        precio = round(precio / redondeo) * redondeo
    return {"base": base, "subtotal": subtotal, "comision": comision, "impuesto": impuesto, "precio_final": precio, "precio_unitario": precio / paginas}


def _enriquecer_resultados_por_pagina(resultados: list[dict], precio_tinta_ml: float, costo_material: float, costo_desgaste_pagina: float, desperdicio_factor: float, precio_unitario: float) -> pd.DataFrame:
    df = pd.DataFrame(resultados)
    if df.empty:
        return df
    for col in ["C (ml)", "M (ml)", "Y (ml)", "K (ml)", "K extra auto (ml)"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["Tinta total página (ml)"] = df[["C (ml)", "M (ml)", "Y (ml)", "K (ml)"]].sum(axis=1)
    df["Costo tinta página"] = df["Tinta total página (ml)"] * float(precio_tinta_ml) * float(desperdicio_factor)
    df["Costo papel página"] = float(costo_material)
    df["Costo desgaste página"] = float(costo_desgaste_pagina)
    df["Costo total página"] = df["Costo tinta página"] + df["Costo papel página"] + df["Costo desgaste página"]
    df["Precio sugerido página"] = float(precio_unitario)
    df["Utilidad estimada página"] = df["Precio sugerido página"] - df["Costo total página"]
    orden = [
        "archivo",
        "Tipo diseño",
        "Densidad total",
        "Factor consumo auto",
        "C (ml)",
        "M (ml)",
        "Y (ml)",
        "K (ml)",
        "K extra auto (ml)",
        "Tinta total página (ml)",
        "Costo tinta página",
        "Costo papel página",
        "Costo desgaste página",
        "Costo total página",
        "Precio sugerido página",
        "Utilidad estimada página",
    ]
    return df[[c for c in orden if c in df.columns]]


def render_cmyk(usuario):
    st.title("🖨️ Impresiones / Motor CMYK")
    st.caption("Analiza PDF, PNG o JPG página por página: consumo CMYK, tinta, papel, desgaste, costo por página, precio sugerido e inventario.")

    df_inv, df_act, df_hist = _load_contexto_cmyk()
    opciones_imp = _impresoras_disponibles(df_act)

    if not opciones_imp:
        st.warning("No hay impresoras registradas en Activos. Registra al menos una para continuar.")
        return

    c1, c2, c3 = st.columns(3)
    impresora_op = c1.selectbox("Impresora (desde Activos)", opciones_imp, format_func=lambda x: x["label"], key="cmyk_impresora")
    marca_default = _detectar_marca_impresora(impresora_op)
    marca = c2.selectbox("Marca / Driver", ["HP", "Epson"], index=0 if marca_default == "HP" else 1, key="cmyk_marca")
    calidad = c3.selectbox("Calidad", list(PERFILES_CALIDAD.keys()), index=1, key="cmyk_calidad")

    st.caption(f"Activo seleccionado: ID #{impresora_op.get('id') or 'N/A'} | Categoría: {impresora_op.get('categoria') or 'N/D'} | Unidad: {impresora_op.get('unidad') or 'N/D'}")

    perfiles_driver = _obtener_perfiles_driver(marca)
    c4, c5, c6 = st.columns(3)
    tipo_papel_driver = c4.selectbox("Perfil de papel (driver)", list(perfiles_driver.keys()), key="cmyk_papel_driver")
    tamano = c5.selectbox("Tamaño", ["A5", "A4", "Carta", "Oficio", "A3", "Tabloide", "Personalizado"], index=1, key="cmyk_tamano")
    sistema_default = _sistema_tinta_recomendado(impresora_op)
    sistema_tinta = c6.selectbox("Sistema de tinta", ["Tanque CMYK (4 tintas)", "Cartucho (Color + Negro)"], index=0 if sistema_default.startswith("Tanque") else 1, key="cmyk_sistema_tinta")

    with st.expander("⚙️ Modo Pro CMYK", expanded=True):
        p1, p2, p3 = st.columns(3)
        refuerzo_negro = p1.slider("Refuerzo de negro (K)", min_value=0.0, max_value=0.40, value=0.12, step=0.01, key="cmyk_refuerzo_k")
        desperdicio_factor = p2.slider("Factor de desperdicio", min_value=1.0, max_value=1.4, value=1.0, step=0.01, key="cmyk_desperdicio")
        redondeo_precio = p3.number_input("Redondeo precio sugerido", min_value=0.0, value=0.05, step=0.05, key="cmyk_redondeo")
        pr1, pr2, pr3 = st.columns(3)
        margen_utilidad = pr1.slider("Margen de utilidad (%)", min_value=5, max_value=200, value=55, step=1, key="cmyk_margen")
        comision_pasarela = pr2.slider("Comisión cobro (%)", min_value=0.0, max_value=12.0, value=0.0, step=0.1, key="cmyk_comision")
        impuesto_venta = pr3.slider("Impuesto (%)", min_value=0.0, max_value=20.0, value=0.0, step=0.1, key="cmyk_impuesto")

    factor_area = 1.0
    if tamano == "Personalizado":
        a1, a2 = st.columns(2)
        ancho = a1.number_input("Ancho (mm)", min_value=50.0, value=210.0, step=1.0, key="cmyk_ancho")
        alto = a2.number_input("Alto (mm)", min_value=50.0, value=297.0, step=1.0, key="cmyk_alto")
        factor_area = _factor_area_personalizada(ancho, alto)

    materiales = _materiales_papel_disponibles(df_inv)
    costo_material = 0.0
    material_papel = "Sin material"
    if not materiales.empty:
        idx = st.selectbox("Material de papel (inventario)", range(len(materiales)), format_func=lambda i: materiales.iloc[i]["_material_label"], key="cmyk_material")
        material = materiales.iloc[idx]
        costo_material = float(material["_costo_hoja"])
        material_papel = str(material.get("nombre", material.get("item", "Papel")))

    archivos = st.file_uploader("Archivos para analizar página por página (PDF/PNG/JPG)", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="cmyk_archivos")
    ejecutar = st.button("🔍 Analizar CMYK y costo por página", type="primary", use_container_width=True, key="cmyk_analizar_lote")
    resultado_key = "cmyk_resultado_actual"

    if ejecutar:
        if not archivos:
            st.error("Carga al menos un archivo para analizar.")
            return
        paginas = []
        nombres_archivos = []
        for archivo in archivos:
            nombres_archivos.append(getattr(archivo, "name", ""))
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

        resultados, totales = analizar_lote(paginas, {"ml_base_pagina": ml_base, "factor_general": float(base["factor_general"]), "factor_calidad": factor_calidad, "factor_papel": factor_driver, "factor_k": 1.0, "auto_negro_inteligente": True, "refuerzo_negro": float(refuerzo_negro)})
        total_paginas = len(resultados)
        precio_tinta = costo_tinta_ml(filtrar_tintas(df_inv), fallback=0.035)
        costos = calcular_costo_lote(totales_cmyk=totales, precio_tinta_ml=precio_tinta, paginas=total_paginas, costo_desgaste_pagina=float(base["costo_desgaste"]), desperdicio_factor=float(desperdicio_factor), desgaste_head_ml=0.005, costo_limpieza=0.0)
        costo_papel_total = total_paginas * costo_material
        costo_total = float(costos["costo_total"]) + float(costo_papel_total)
        precio = _precio_sugerido(costo_total=costo_total, paginas=total_paginas, margen_utilidad=float(margen_utilidad), comision_pasarela=float(comision_pasarela), impuesto_venta=float(impuesto_venta), redondeo=float(redondeo_precio))
        detalle_paginas = _enriquecer_resultados_por_pagina(resultados, precio_tinta_ml=precio_tinta, costo_material=costo_material, costo_desgaste_pagina=float(base["costo_desgaste"]), desperdicio_factor=float(desperdicio_factor), precio_unitario=float(precio["precio_unitario"]))
        consumos_ids = mapear_consumo_ids(filtrar_tintas(df_inv), totales, sistema_tinta=sistema_tinta, impresora=impresora_op["nombre"])
        alertas = validar_stock(df_inv, consumos_ids)

        st.session_state[resultado_key] = {"impresora_label": impresora_op["label"], "impresora_nombre": impresora_op["nombre"], "nombres_archivos": nombres_archivos, "total_paginas": total_paginas, "resultados": resultados, "detalle_paginas": detalle_paginas, "totales": totales, "costos": costos, "costo_total": costo_total, "costo_papel_total": costo_papel_total, "precio_tinta_ml": float(precio_tinta), "precio": precio, "consumos_ids": consumos_ids, "alertas": alertas, "margen_utilidad": float(margen_utilidad), "comision_pasarela": float(comision_pasarela), "impuesto_venta": float(impuesto_venta), "material_papel": material_papel, "costo_material": float(costo_material)}

    analisis = st.session_state.get(resultado_key)
    if not analisis:
        st.subheader("Historial reciente")
        st.dataframe(df_hist, use_container_width=True)
        return

    total_paginas = int(analisis["total_paginas"])
    totales = analisis["totales"]
    costos = analisis["costos"]
    costo_total = float(analisis["costo_total"])
    costo_papel_total = float(analisis["costo_papel_total"])
    precio = analisis["precio"]
    alertas = analisis["alertas"]
    consumos_ids = analisis["consumos_ids"]
    detalle_paginas = analisis.get("detalle_paginas", pd.DataFrame())

    st.success(f"Análisis completado para {total_paginas} páginas.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("C (ml)", f"{totales['C']:.2f}")
    m2.metric("M (ml)", f"{totales['M']:.2f}")
    m3.metric("Y (ml)", f"{totales['Y']:.2f}")
    m4.metric("K (ml)", f"{totales['K']:.2f}")

    st.subheader("💵 Costos y precio")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costo total", f"$ {costo_total:.2f}")
    c2.metric("Costo / página", f"$ {(costo_total / max(total_paginas, 1)):.4f}")
    c3.metric("Precio sugerido", f"$ {precio['precio_final']:.2f}")
    c4.metric("Precio / página", f"$ {precio['precio_unitario']:.4f}")

    utilidad_estimada = max(0.0, precio["precio_final"] - costo_total)
    p1, p2, p3 = st.columns(3)
    p1.metric("Utilidad bruta estimada", f"$ {utilidad_estimada:.2f}")
    p2.metric("Costo tinta", f"$ {float(costos['costo_tinta']):.2f}")
    p3.metric("Costo papel", f"$ {float(costo_papel_total):.2f}")

    st.caption(f"Material usado: {analisis['material_papel']} | $ / hoja: {float(analisis['costo_material']):.4f} | $ tinta/ml: {float(analisis.get('precio_tinta_ml', 0.0)):.4f}")

    tabs = st.tabs(["📄 Análisis por página", "💹 Desglose precio", "🧪 Consumo total", "📜 Historial / Acciones"])
    with tabs[0]:
        st.markdown("#### CMYK, tinta y costo de cada página")
        if isinstance(detalle_paginas, pd.DataFrame) and not detalle_paginas.empty:
            st.dataframe(detalle_paginas, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar análisis por página CSV", data=detalle_paginas.to_csv(index=False).encode("utf-8-sig"), file_name="analisis_cmyk_por_pagina.csv", mime="text/csv", use_container_width=True, key="cmyk_descargar_paginas")
        else:
            st.dataframe(pd.DataFrame(analisis["resultados"]), use_container_width=True)
    with tabs[1]:
        st.dataframe(pd.DataFrame([{"Concepto": "Costo base", "Monto": precio["base"]}, {"Concepto": f"Subtotal con margen ({analisis['margen_utilidad']}%)", "Monto": precio["subtotal"]}, {"Concepto": f"Comisión ({analisis['comision_pasarela']}%)", "Monto": precio["comision"]}, {"Concepto": f"Impuesto ({analisis['impuesto_venta']}%)", "Monto": precio["impuesto"]}, {"Concepto": "Precio final", "Monto": precio["precio_final"]}]), hide_index=True, use_container_width=True)
    with tabs[2]:
        st.dataframe(pd.DataFrame([{"Color": "C", "ml": totales["C"]}, {"Color": "M", "ml": totales["M"]}, {"Color": "Y", "ml": totales["Y"]}, {"Color": "K", "ml": totales["K"]}]), hide_index=True, use_container_width=True)
        for alerta in alertas:
            st.warning(alerta)
    with tabs[3]:
        if st.button("Guardar historial", use_container_width=True, key="cmyk_guardar_historial"):
            guardar_historial(impresora=analisis["impresora_label"], paginas=total_paginas, costo=costo_total, consumos=totales)
            st.success("Historial guardado.")
        if not alertas and st.button("Descontar inventario", use_container_width=True, key="cmyk_descontar_inventario"):
            ok, msg = descontar_inventario(consumos_ids)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        if st.button("Limpiar análisis actual", use_container_width=True, key="cmyk_limpiar"):
            st.session_state.pop(resultado_key, None)
            st.info("Análisis limpiado. Puedes cargar nuevos archivos.")

    st.markdown("### 🔗 Enviar a otros módulos")

    def _build_cmyk_to_corte():
        return ("analisis_cmyk", {"archivo": ", ".join(analisis.get("nombres_archivos", [])), "trabajo": f"Impresión {total_paginas} páginas", "cantidad": total_paginas, "costo_base": round(float(costo_total), 2), "material": analisis.get("material_papel", ""), "observaciones": f"Impresora: {analisis.get('impresora_nombre', 'N/D')}", "referencia": f"CMYK-{analisis.get('impresora_nombre', 'N/D')}"})

    def _build_cmyk_to_cotizaciones():
        return ("cotizacion_preliminar", {"costo_base": round(float(costo_total), 2), "tiempo_estimado": round(float(total_paginas) * 0.15, 2), "tipo_produccion": "cmyk", "archivo": ", ".join(analisis.get("nombres_archivos", [])), "referencia": f"CMYK-{analisis.get('impresora_nombre', 'N/D')}"})

    render_send_buttons(source_module="cmyk", payload_builders={"corte industrial": _build_cmyk_to_corte, "cotizaciones": _build_cmyk_to_cotizaciones})
