import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote, normalizar_imagenes
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.history import guardar_historial, obtener_historial
from modules.cmyk.inventory_engine import (
    descontar_inventario,
    filtrar_tintas,
    mapear_consumo_ids,
    validar_stock,
)
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

def _impresoras_disponibles(df_act: pd.DataFrame) -> list[dict]:
    """Lista impresoras activas detectadas en tabla activos."""
    if df_act is None or df_act.empty:
        return []

    df = df_act.copy()
    nombre_col = _column_match(df, ["equipo", "nombre", "modelo"])
    if not nombre_col:
        return []

    categoria_col = _column_match(df, ["categoria", "unidad", "tipo"])
    id_col = _column_match(df, ["id", "activo_id"])

    if categoria_col:
        mask_imp = df[categoria_col].fillna("").astype(str).str.contains("impres|cmyk|inkjet", case=False, na=False)
        if mask_imp.any():
            df = df[mask_imp].copy()

    if df.empty:
        return []

    if not id_col:
        df["_id"] = df.index.astype(int)
        id_col = "_id"

    return [
        {
            "id": int(row[id_col]),
            "nombre": str(row.get("equipo") or row.get("nombre") or row.get("modelo") or "Impresora"),
            "modelo": str(row.get("modelo") or "").strip(),
            "unidad": str(row.get("unidad") or "").strip(),
            "categoria": str(row.get("categoria") or "").strip(),
            "label": (
                f"{str(row.get('equipo') or row.get('nombre') or row.get('modelo') or 'Impresora')}"
                f"{(' · ' + str(row.get('modelo'))) if str(row.get('modelo') or '').strip() else ''}"
                f" (ID {int(row[id_col])})"
            ),
        }
        for _, row in df.iterrows()
    ]


def _descontar_material_papel(material_id: int, cantidad_hojas: float) -> tuple[bool, str]:
    from database.connection import db_transaction

    if cantidad_hojas <= 0:
        return True, "No se descontó papel (cantidad 0)."

    try:
        with db_transaction() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}
            col_stock = "stock_actual" if "stock_actual" in cols else ("cantidad" if "cantidad" in cols else None)
            if not col_stock:
                return False, "No existe columna de stock en inventario."

            row = conn.execute(
                f"SELECT {col_stock}, COALESCE(nombre, item, sku, 'Material') FROM inventario WHERE id=?",
                (int(material_id),),
            ).fetchone()

            if not row:
                return False, "Material no encontrado."

            stock_actual = float(row[0] or 0.0)
            nombre = str(row[1])
            if stock_actual < cantidad_hojas:
                return False, f"Stock insuficiente de {nombre}. Disponible: {stock_actual:.2f}."

            conn.execute(
                f"UPDATE inventario SET {col_stock}=COALESCE({col_stock},0)-? WHERE id=?",
                (float(cantidad_hojas), int(material_id)),
            )
            return True, f"Papel descontado: {cantidad_hojas:.2f} hojas de {nombre}."
    except Exception as exc:
        return False, f"Error descontando material: {exc}"


def _registrar_desgaste_impresora(impresora_id: int, costo_desgaste_total: float, vidas_cabezales: int = 2) -> tuple[bool, str]:
    from database.connection import db_transaction

    if costo_desgaste_total <= 0:
        return True, "Sin desgaste para registrar."

    try:
        with db_transaction() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()}
            if "vida_cabezal_pct" in cols:
                dec_pct = min(100.0, float(costo_desgaste_total) * 0.02 * max(1, int(vidas_cabezales)))
                conn.execute(
                    "UPDATE activos SET vida_cabezal_pct=MAX(0, COALESCE(vida_cabezal_pct,100)-?) WHERE id=?",
                    (float(dec_pct), int(impresora_id)),
                )
            if "desgaste" in cols:
                conn.execute(
                    "UPDATE activos SET desgaste=COALESCE(desgaste,0)+? WHERE id=?",
                    (float(costo_desgaste_total), int(impresora_id)),
                )
                return True, f"Desgaste de impresora actualizado (+{costo_desgaste_total:.4f}). Cabezales: {int(vidas_cabezales)}"
            if "desgaste_por_uso" in cols:
                conn.execute(
                    "UPDATE activos SET desgaste_por_uso=COALESCE(desgaste_por_uso,0)+? WHERE id=?",
                    (float(costo_desgaste_total), int(impresora_id)),
                )
                return True, f"Vida útil/uso registrada (+{costo_desgaste_total:.4f}). Cabezales: {int(vidas_cabezales)}"
            return False, "No se encontró columna de desgaste en activos."
    except Exception as exc:
        return False, f"Error registrando desgaste: {exc}"


def _payload_base_cmyk(
    usuario: str,
    impresora: str,
    total_paginas: int,
    total_ml: float,
    costo_total: float,
    material: str,
    totales_ajustados: dict,
) -> dict:
    return {
        "origen": "cmyk",
        "usuario": str(usuario),
        "impresora": str(impresora),
        "trabajo": f"Impresión CMYK ({total_paginas} pág)",
        "cantidad": int(total_paginas),
        "unidades": int(total_paginas),
        "material": str(material),
        "costo_estimado": float(costo_total),
        "costo_base": float(costo_total),
        "total_ml": float(total_ml),
@@ -328,55 +341,72 @@ def render_cmyk(usuario: str):
            )
            fila_papel = papeles_inv.iloc[int(idx_sel)]
            material_papel = str(fila_papel["_material_label"])
            material_papel_id = int(fila_papel["_id"])
            costo_material_pagina = float(fila_papel["_costo_hoja"])
            st.caption(f"Material activo: **{material_papel}**")

        editar_parametros = st.toggle("Editar parámetros calculados", value=False)
        if editar_parametros:
            costo_desgaste = st.number_input("Costo desgaste por página ($)", min_value=0.0, value=float(costo_desgaste), step=0.001)
            ml_base_pagina = st.number_input("Consumo base por página (ml)", min_value=0.001, value=float(ml_base_pagina), step=0.001)
            factor_general = st.number_input("Factor general de consumo", min_value=0.10, value=float(factor_general), step=0.01)

        st.markdown("#### 🖨️ Impresora y control de inventario")
        impresoras = _impresoras_disponibles(df_act)
        if impresoras:
            idx_imp = st.selectbox(
                "Impresora para este análisis",
                options=list(range(len(impresoras))),
                format_func=lambda i: impresoras[i]["label"],
                index=0,
            )
            impresora_data = impresoras[int(idx_imp)]
            impresora = str(impresora_data["nombre"])
            impresora_id = int(impresora_data["id"])
            pista_impresora = " ".join(
                [
                    str(impresora_data.get("nombre") or ""),
                    str(impresora_data.get("modelo") or ""),
                    str(impresora_data.get("categoria") or ""),
                    str(impresora_data.get("unidad") or ""),
                ]
            ).strip()
        else:
            impresora = "Impresora"
            impresora_id = None
            pista_impresora = ""
            st.info("No se detectaron impresoras activas en Activos. Se guardará como 'Impresora'.")

        sistema_tinta = st.selectbox(
            "Sistema de tinta",
            ["Tanque CMYK (4 tintas)", "Cartucho (negro + color/tricolor)"],
            index=0,
            help="Tanque descuenta C/M/Y/K por separado. Cartucho descuenta negro y cartucho de color (C+M+Y).",
        )
        st.caption("Cabezales considerados para desgaste de vida útil: **2**")

        descontar_stock = st.toggle("Descontar tintas del inventario al guardar", value=True)
        descontar_papel = st.toggle("Descontar papel/material del inventario", value=True)
        registrar_desgaste = st.toggle("Registrar consumo de vida útil/desgaste del activo", value=True)

    with col2:
        archivos = st.file_uploader("Carga tus diseños", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

    if not archivos:
        st.info("Sube archivos para iniciar el análisis.")
        return

    resultados = []
    totales = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}
    with st.spinner("Analizando cobertura CMYK..."):
        for archivo in archivos:
            try:
                paginas = normalizar_imagenes(archivo)
            except ValueError as exc:
                st.warning(str(exc))
                continue

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

    df_tintas = filtrar_tintas(df_inv)
    consumos_ids = mapear_consumo_ids(
        df_tintas,
        totales_ajustados,
        sistema_tinta=sistema_tinta,
        impresora=f"{impresora} {pista_impresora}",
    )
    alertas_stock = validar_stock(df_tintas, consumos_ids)

    if alertas_stock:
        st.markdown("#### ⚠️ Validación de stock de tintas")
        for alerta in alertas_stock:
            st.warning(alerta)

    col_guardar, col_exportar = st.columns([1, 1])
    with col_guardar:
        if st.button("Guardar en historial", use_container_width=True):
            guardar_historial(impresora, len(resultados), costo_total_con_material, totales_ajustados)
            mensajes = ["Historial guardado correctamente."]

            if descontar_stock:
                ok_stock, msg_stock = descontar_inventario(consumos_ids)
                mensajes.append(msg_stock)
                if not ok_stock:
                    st.warning(f"Stock tintas: {msg_stock}")

            if descontar_papel and material_papel_id is not None:
                ok_papel, msg_papel = _descontar_material_papel(int(material_papel_id), float(total_paginas))
                mensajes.append(msg_papel)
                if not ok_papel:
                    st.warning(f"Material: {msg_papel}")

            if registrar_desgaste and impresora_id is not None:
                ok_desg, msg_desg = _registrar_desgaste_impresora(
                    int(impresora_id),
                    float(costo["costo_desgaste"]),
                    vidas_cabezales=2,
                )
                mensajes.append(msg_desg)
                if not ok_desg:
                    st.warning(f"Activos: {msg_desg}")

            st.success(" | ".join(mensajes))
            df_hist = obtener_historial(limit=100)
    with col_exportar:
        st.download_button(
            "Descargar detalle CSV",
            data=df_resultados.to_csv(index=False).encode("utf-8"),
            file_name="analisis_cmyk_detalle.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("#### 🚚 Enviar trabajo CMYK a otros módulos")
    payload_base = _payload_base_cmyk(
        usuario=usuario,
        impresora=impresora,
        total_paginas=total_paginas,
        total_ml=total_ml,
        costo_total=costo_total_con_material,
        material=material_papel,
        totales_ajustados=totales_ajustados,
    )

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("🔥 Enviar a Sublimación", use_container_width=True):
        cola = st.session_state.get("cola_sublimacion", [])
        payload_sub = {
            **payload_base,
            "tipo_produccion": "sublimacion",
            "descripcion": f"Transfer CMYK ({total_paginas} páginas)",
            "costo_transfer_total": float(costo_total_con_material),
            "cantidad": int(total_paginas),
        }
        cola.append(payload_sub)
        st.session_state["cola_sublimacion"] = cola
        st.success("Trabajo enviado a la cola de Sublimación.")

    if b2.button("🛠️ Enviar a Otros Procesos", use_container_width=True):
        st.session_state["datos_proceso_desde_cmyk"] = {
            **payload_base,
            "tipo_produccion": "otros_procesos",
            "observacion": f"Costo base CMYK: $ {costo_total_con_material:.2f} | Material: {material_papel}",
        }
        st.success("Trabajo enviado a Otros Procesos.")

    if b3.button("✂️ Enviar a Corte", use_container_width=True):
        st.session_state["datos_corte_desde_cmyk"] = {
            **payload_base,
            "tipo_produccion": "corte",
            "archivo": "Lote CMYK",
            "costo_base": float(costo_total_con_material),
        }
        st.success("Trabajo enviado a Corte como pre-orden.")

    if b4.button("📝 Enviar a Cotización", use_container_width=True):
        st.session_state["datos_pre_cotizacion"] = {
            **payload_base,
            "descripcion": f"Impresión CMYK {total_paginas} pág | {material_papel}",
            "tipo_produccion": "cmyk",
        }
        st.success("Trabajo enviado a Cotizaciones.")

    st.divider()
    st.subheader("Historial reciente")
    st.dataframe(df_hist, use_container_width=True)
