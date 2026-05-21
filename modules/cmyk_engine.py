from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.docx_support import normalizar_archivo_impresion
from modules.cmyk.history import guardar_historial
from modules.cmyk.inventory_engine import descontar_inventario, filtrar_tintas, mapear_consumo_ids, validar_stock
from modules.cmyk.page_size import ajustar_consumo_por_tamano
from modules.integration_hub import render_send_buttons


TAMANOS = {
    "A5": {"costo_desgaste": 0.012, "ml_base": 0.09, "factor_general": 0.90},
    "A4": {"costo_desgaste": 0.020, "ml_base": 0.15, "factor_general": 1.00},
    "Carta": {"costo_desgaste": 0.021, "ml_base": 0.16, "factor_general": 1.02},
    "Oficio": {"costo_desgaste": 0.025, "ml_base": 0.18, "factor_general": 1.08},
    "A3": {"costo_desgaste": 0.034, "ml_base": 0.25, "factor_general": 1.22},
    "Tabloide": {"costo_desgaste": 0.036, "ml_base": 0.27, "factor_general": 1.30},
}

PERFILES_DRIVER = {
    "HP": {
        "Papel normal": 1.00,
        "Papeles fotográficos HP": 1.18,
        "Papel profesional o folleto mate HP": 1.12,
        "Papel profesional o folleto brillante HP": 1.16,
        "Otro papel fotográfico inyección tinta": 1.20,
        "Papel normal ligero/reciclado": 0.94,
    },
    "Epson": {
        "Papel normal": 1.00,
        "Epson Photo Paper Glossy": 1.17,
        "Epson Premium Photo Paper Glossy": 1.22,
        "Epson Ultra Premium Photo Paper Glossy": 1.26,
        "Epson Photo Paper Matte": 1.12,
        "Epson Premium Presentation Paper Matte": 1.10,
    },
}

IMPRESORA_GENERICA = {
    "id": None,
    "nombre": "Impresora genérica CMYK",
    "label": "Impresora genérica CMYK",
    "modelo": "Genérica",
    "unidad": "Impresión",
    "categoria": "Impresora",
}


def _column_match(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _factor_area_personalizada(ancho_mm: float, alto_mm: float) -> float:
    area_a4 = 210.0 * 297.0
    area_custom = max(float(ancho_mm), 1.0) * max(float(alto_mm), 1.0)
    return max(0.20, min(4.0, area_custom / area_a4))


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
    opciones = []
    for _, row in df[mask].iterrows():
        nombre = str(row.get(col_equipo, "")).strip()
        modelo = str(row.get(col_modelo, "")).strip() if col_modelo else ""
        label = f"{nombre} ({modelo})" if modelo and modelo.lower() != "nan" else nombre
        opciones.append({
            "id": int(row[col_id]) if col_id and pd.notna(row[col_id]) else None,
            "nombre": nombre,
            "label": label,
            "modelo": modelo,
            "unidad": str(row.get(col_unidad, "")).strip() if col_unidad else "",
            "categoria": str(row.get(col_categoria, "")).strip() if col_categoria else "",
        })
    unicas, vistos = [], set()
    for op in opciones:
        key = op["label"].lower()
        if key not in vistos:
            vistos.add(key)
            unicas.append(op)
    return unicas


def _detectar_marca(impresora: dict) -> str:
    texto = " ".join([str(impresora.get("nombre", "")), str(impresora.get("modelo", "")), str(impresora.get("label", ""))]).lower()
    return "Epson" if "epson" in texto else "HP"


def _sistema_tinta(impresora: dict) -> str:
    texto = " ".join([str(impresora.get("nombre", "")), str(impresora.get("modelo", "")), str(impresora.get("unidad", ""))]).lower()
    return "Tanque CMYK (4 tintas)" if any(k in texto for k in ["tank", "ecotank", "tanque", "l3", "l5", "l8"]) else "Cartucho (Color + Negro)"


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
    mask = nombres.str.contains("papel|bond|opalina|couche|glossy|mate|fotograf|cartulina", case=False, na=False)
    if col_categoria:
        mask = mask | categorias.str.contains("papel|impres|sustrato|material", case=False, na=False)
    df = df[mask].copy()
    if col_stock:
        df["_stock_n"] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0.0)
        df = df[df["_stock_n"] > 0].copy()
    else:
        df["_stock_n"] = 0.0
    col_costo = _column_match(df, ["costo_unitario_usd", "precio_usd", "precio_venta_usd"])
    df["_costo_hoja"] = pd.to_numeric(df[col_costo], errors="coerce").fillna(0.0) if col_costo else 0.0
    df["_material_label"] = df.apply(lambda r: f"{str(r[col_nombre]).strip()} | Stock: {float(r['_stock_n']):.2f} | $/hoja: {float(r['_costo_hoja']):.4f}", axis=1)
    return df.sort_values(by=["_stock_n", "_costo_hoja"], ascending=[False, True])


def _precio_sugerido(costo_total: float, paginas: int, margen: float, comision: float, impuesto: float, redondeo: float) -> dict:
    if paginas <= 0:
        return {"base": 0.0, "subtotal": 0.0, "comision": 0.0, "impuesto": 0.0, "precio_final": 0.0, "precio_unitario": 0.0}
    base = float(costo_total)
    subtotal = base * (1 + margen / 100)
    monto_comision = subtotal * (comision / 100)
    monto_impuesto = (subtotal + monto_comision) * (impuesto / 100)
    precio = subtotal + monto_comision + monto_impuesto
    if redondeo > 0:
        precio = round(precio / redondeo) * redondeo
    return {"base": base, "subtotal": subtotal, "comision": monto_comision, "impuesto": monto_impuesto, "precio_final": precio, "precio_unitario": precio / paginas}


def _detalle_por_pagina(resultados: list[dict], precio_tinta_ml: float, costo_material: float, costo_desgaste_pagina: float, desperdicio_factor: float, precio_unitario: float) -> pd.DataFrame:
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
    cols = ["archivo", "Tipo diseño", "Densidad total", "Factor consumo auto", "C (ml)", "M (ml)", "Y (ml)", "K (ml)", "K extra auto (ml)", "Tinta total página (ml)", "Costo tinta página", "Costo papel página", "Costo desgaste página", "Costo total página", "Precio sugerido página", "Utilidad estimada página"]
    return df[[c for c in cols if c in df.columns]]


def render_cmyk(usuario):
    st.title("🖨️ Impresiones / Motor CMYK")
    st.caption("Analiza PDF, Word DOCX, JPG/JPEG y PNG página por página: CMYK, tinta, papel, desgaste, costo y precio sugerido.")

    df_inv, df_act, df_hist = _load_contexto_cmyk()
    opciones_imp = _impresoras_disponibles(df_act)
    if not opciones_imp:
        st.info("No hay impresoras registradas en Activos. Se usará una impresora genérica para que puedas analizar archivos ahora mismo.")
        opciones_imp = [IMPRESORA_GENERICA]

    c1, c2, c3 = st.columns(3)
    impresora = c1.selectbox("Impresora", opciones_imp, format_func=lambda x: x["label"], key="cmyk_impresora")
    marca_default = _detectar_marca(impresora)
    marca = c2.selectbox("Marca / Driver", ["HP", "Epson"], index=0 if marca_default == "HP" else 1, key="cmyk_marca")
    calidad = c3.selectbox("Calidad", list(PERFILES_CALIDAD.keys()), index=1, key="cmyk_calidad")
    st.caption(f"Activo seleccionado: ID #{impresora.get('id') or 'N/A'} | Categoría: {impresora.get('categoria') or 'N/D'} | Unidad: {impresora.get('unidad') or 'N/D'}")

    perfiles = PERFILES_DRIVER.get(marca, PERFILES_DRIVER["HP"])
    a, b, c = st.columns(3)
    tipo_papel_driver = a.selectbox("Perfil de papel (driver)", list(perfiles.keys()), key="cmyk_papel_driver")
    tamano = b.selectbox("Tamaño", ["A5", "A4", "Carta", "Oficio", "A3", "Tabloide", "Personalizado"], index=1, key="cmyk_tamano")
    sistema_tinta = c.selectbox("Sistema de tinta", ["Tanque CMYK (4 tintas)", "Cartucho (Color + Negro)"], index=0 if _sistema_tinta(impresora).startswith("Tanque") else 1, key="cmyk_sistema_tinta")

    with st.expander("⚙️ Modo Pro CMYK", expanded=True):
        p1, p2, p3 = st.columns(3)
        refuerzo_negro = p1.slider("Refuerzo de negro (K)", 0.0, 0.40, 0.12, 0.01, key="cmyk_refuerzo_k")
        desperdicio_factor = p2.slider("Factor de desperdicio", 1.0, 1.4, 1.0, 0.01, key="cmyk_desperdicio")
        redondeo = p3.number_input("Redondeo precio sugerido", min_value=0.0, value=0.05, step=0.05, key="cmyk_redondeo")
        q1, q2, q3 = st.columns(3)
        margen = q1.slider("Margen de utilidad (%)", 5, 200, 55, 1, key="cmyk_margen")
        comision = q2.slider("Comisión cobro (%)", 0.0, 12.0, 0.0, 0.1, key="cmyk_comision")
        impuesto = q3.slider("Impuesto (%)", 0.0, 20.0, 0.0, 0.1, key="cmyk_impuesto")

    factor_area = 1.0
    if tamano == "Personalizado":
        x1, x2 = st.columns(2)
        ancho = x1.number_input("Ancho (mm)", min_value=50.0, value=210.0, step=1.0, key="cmyk_ancho")
        alto = x2.number_input("Alto (mm)", min_value=50.0, value=297.0, step=1.0, key="cmyk_alto")
        factor_area = _factor_area_personalizada(ancho, alto)

    materiales = _materiales_papel_disponibles(df_inv)
    costo_material = 0.0
    material_papel = "Sin material de inventario"
    if not materiales.empty:
        idx = st.selectbox("Material de papel (inventario)", range(len(materiales)), format_func=lambda i: materiales.iloc[i]["_material_label"], key="cmyk_material")
        material = materiales.iloc[idx]
        costo_material = float(material["_costo_hoja"])
        material_papel = str(material.get("nombre", material.get("item", "Papel")))
    else:
        st.info("No hay papel detectado en Inventario. El análisis seguirá con costo de papel $0. Puedes registrar papel luego para mejorar el costo.")

    st.subheader("📤 Analizar archivo")
    st.info("Formatos soportados: PDF, Word .docx, JPG/JPEG y PNG. Los .doc antiguos deben guardarse como .docx o PDF.")
    archivos = st.file_uploader("Sube archivos para analizar página por página", type=["pdf", "docx", "png", "jpg", "jpeg"], accept_multiple_files=True, key="cmyk_archivos")
    ejecutar = st.button("🔍 Analizar PDF / Word / JPG / PNG", type="primary", use_container_width=True, key="cmyk_analizar_lote")
    resultado_key = "cmyk_resultado_actual"

    if ejecutar:
        if not archivos:
            st.error("Carga al menos un archivo para analizar.")
            return
        paginas, nombres_archivos = [], []
        for archivo in archivos:
            nombres_archivos.append(getattr(archivo, "name", ""))
            try:
                paginas.extend(normalizar_archivo_impresion(archivo))
            except Exception as exc:
                st.warning(f"No se pudo procesar {archivo.name}: {exc}")
        if not paginas:
            st.error("No se pudieron procesar páginas válidas.")
            return

        base = TAMANOS.get("A4" if tamano == "Personalizado" else tamano, TAMANOS["A4"])
        factor_calidad = float(PERFILES_CALIDAD[calidad]["ink_mult"])
        factor_driver = float(perfiles.get(tipo_papel_driver, 1.0))
        ml_base = float(base["ml_base"]) * factor_area
        if tamano != "Personalizado":
            ml_base = ajustar_consumo_por_tamano(ml_base, tamano)

        resultados, totales = analizar_lote(paginas, {"ml_base_pagina": ml_base, "factor_general": float(base["factor_general"]), "factor_calidad": factor_calidad, "factor_papel": factor_driver, "factor_k": 1.0, "auto_negro_inteligente": True, "refuerzo_negro": float(refuerzo_negro)})
        total_paginas = len(resultados)
        precio_tinta = costo_tinta_ml(filtrar_tintas(df_inv), fallback=0.035)
        costos = calcular_costo_lote(totales_cmyk=totales, precio_tinta_ml=precio_tinta, paginas=total_paginas, costo_desgaste_pagina=float(base["costo_desgaste"]), desperdicio_factor=float(desperdicio_factor), desgaste_head_ml=0.005, costo_limpieza=0.0)
        costo_papel_total = total_paginas * costo_material
        costo_total = float(costos["costo_total"]) + float(costo_papel_total)
        precio = _precio_sugerido(costo_total, total_paginas, float(margen), float(comision), float(impuesto), float(redondeo))
        detalle = _detalle_por_pagina(resultados, precio_tinta, costo_material, float(base["costo_desgaste"]), float(desperdicio_factor), float(precio["precio_unitario"]))
        consumos_ids = mapear_consumo_ids(filtrar_tintas(df_inv), totales, sistema_tinta=sistema_tinta, impresora=impresora["nombre"])
        alertas = validar_stock(df_inv, consumos_ids)
        st.session_state[resultado_key] = {"impresora_label": impresora["label"], "impresora_nombre": impresora["nombre"], "nombres_archivos": nombres_archivos, "total_paginas": total_paginas, "resultados": resultados, "detalle_paginas": detalle, "totales": totales, "costos": costos, "costo_total": costo_total, "costo_papel_total": costo_papel_total, "precio_tinta_ml": float(precio_tinta), "precio": precio, "consumos_ids": consumos_ids, "alertas": alertas, "margen": float(margen), "comision": float(comision), "impuesto": float(impuesto), "material_papel": material_papel, "costo_material": float(costo_material)}

    analisis = st.session_state.get(resultado_key)
    if not analisis:
        st.subheader("Historial reciente")
        st.dataframe(df_hist, use_container_width=True)
        return

    total_paginas = int(analisis["total_paginas"])
    totales = analisis["totales"]
    costo_total = float(analisis["costo_total"])
    precio = analisis["precio"]
    detalle = analisis.get("detalle_paginas", pd.DataFrame())
    alertas = analisis["alertas"]
    consumos_ids = analisis["consumos_ids"]

    st.success(f"Análisis completado para {total_paginas} páginas.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("C (ml)", f"{totales['C']:.2f}")
    m2.metric("M (ml)", f"{totales['M']:.2f}")
    m3.metric("Y (ml)", f"{totales['Y']:.2f}")
    m4.metric("K (ml)", f"{totales['K']:.2f}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costo total", f"$ {costo_total:.2f}")
    c2.metric("Costo / página", f"$ {(costo_total / max(total_paginas, 1)):.4f}")
    c3.metric("Precio sugerido", f"$ {precio['precio_final']:.2f}")
    c4.metric("Precio / página", f"$ {precio['precio_unitario']:.4f}")
    st.caption(f"Material usado: {analisis['material_papel']} | $/hoja: {float(analisis['costo_material']):.4f} | $ tinta/ml: {float(analisis.get('precio_tinta_ml', 0.0)):.4f}")

    tabs = st.tabs(["📄 Análisis por página", "💹 Desglose precio", "🧪 Consumo total", "📜 Historial / Acciones"])
    with tabs[0]:
        st.markdown("#### CMYK, tinta y costo de cada página")
        st.dataframe(detalle if isinstance(detalle, pd.DataFrame) and not detalle.empty else pd.DataFrame(analisis["resultados"]), use_container_width=True, hide_index=True)
        if isinstance(detalle, pd.DataFrame) and not detalle.empty:
            st.download_button("⬇️ Descargar análisis por página CSV", data=detalle.to_csv(index=False).encode("utf-8-sig"), file_name="analisis_cmyk_por_pagina.csv", mime="text/csv", use_container_width=True, key="cmyk_descargar_paginas")
    with tabs[1]:
        st.dataframe(pd.DataFrame([{"Concepto": "Costo base", "Monto": precio["base"]}, {"Concepto": f"Subtotal con margen ({analisis['margen']}%)", "Monto": precio["subtotal"]}, {"Concepto": f"Comisión ({analisis['comision']}%)", "Monto": precio["comision"]}, {"Concepto": f"Impuesto ({analisis['impuesto']}%)", "Monto": precio["impuesto"]}, {"Concepto": "Precio final", "Monto": precio["precio_final"]}]), hide_index=True, use_container_width=True)
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
            st.success(msg) if ok else st.error(msg)
        if st.button("Limpiar análisis actual", use_container_width=True, key="cmyk_limpiar"):
            st.session_state.pop(resultado_key, None)
            st.info("Análisis limpiado. Puedes cargar nuevos archivos.")

    st.markdown("### 🔗 Enviar a otros módulos")

    def _build_cmyk_to_corte():
        return ("analisis_cmyk", {"archivo": ", ".join(analisis.get("nombres_archivos", [])), "trabajo": f"Impresión {total_paginas} páginas", "cantidad": total_paginas, "costo_base": round(float(costo_total), 2), "material": analisis.get("material_papel", ""), "observaciones": f"Impresora: {analisis.get('impresora_nombre', 'N/D')}", "referencia": f"CMYK-{analisis.get('impresora_nombre', 'N/D')}"})

    def _build_cmyk_to_cotizaciones():
        return ("cotizacion_preliminar", {"costo_base": round(float(costo_total), 2), "tiempo_estimado": round(float(total_paginas) * 0.15, 2), "tipo_produccion": "cmyk", "archivo": ", ".join(analisis.get("nombres_archivos", [])), "referencia": f"CMYK-{analisis.get('impresora_nombre', 'N/D')}"})

    render_send_buttons(source_module="cmyk", payload_builders={"corte industrial": _build_cmyk_to_corte, "cotizaciones": _build_cmyk_to_cotizaciones})
