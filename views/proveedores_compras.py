from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _read_table(table: str, order: str = "id DESC", limit: int = 500) -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return pd.DataFrame()
        try:
            return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY {order} LIMIT {int(limit)}", conn)
        except Exception:
            return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {int(limit)}", conn)


def _read_query(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _insert_provider(data: dict[str, Any]) -> None:
    with db_transaction() as conn:
        cols = _columns(conn, "proveedores")
        if not cols:
            st.error("No existe la tabla proveedores.")
            return
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        placeholders = ",".join(["?"] * len(keys))
        conn.execute(f"INSERT INTO proveedores ({','.join(keys)}) VALUES ({placeholders})", [payload[k] for k in keys])


def _safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _provider_key(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    return " ".join(text.strip().lower().split())


def _filter_provider(df: pd.DataFrame, proveedor: str, column: str = "proveedor") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    return df[df[column].apply(_provider_key).eq(_provider_key(proveedor))].copy()


def _add_vencimiento_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "fecha_vencimiento" not in df.columns:
        return df.copy()
    out = df.copy()
    hoy = pd.Timestamp.today().normalize()
    vencimiento = pd.to_datetime(out["fecha_vencimiento"], errors="coerce")
    out["dias_para_vencer"] = (vencimiento - hoy).dt.days
    out["estado_vencimiento"] = "Sin vencimiento"
    out.loc[vencimiento.notna() & (out["dias_para_vencer"] < 0), "estado_vencimiento"] = "Vencida"
    out.loc[vencimiento.notna() & out["dias_para_vencer"].between(0, 7, inclusive="both"), "estado_vencimiento"] = "Vence en 7 días"
    out.loc[vencimiento.notna() & (out["dias_para_vencer"] > 7), "estado_vencimiento"] = "Vigente"
    out["dias_para_vencer"] = out["dias_para_vencer"].astype("Int64")
    return out


def _get_rates() -> tuple[float, float]:
    try:
        from modules.configuracion import DEFAULT_CONFIG, get_current_config
        config = get_current_config()
        tasa_bcv_default = float(DEFAULT_CONFIG.get("tasa_bcv", 36.5))
        tasa_binance_default = float(DEFAULT_CONFIG.get("tasa_binance", 38.0))
        tasa_bcv = float(config.get("tasa_bcv", st.session_state.get("tasa_bcv", tasa_bcv_default)) or tasa_bcv_default)
        tasa_binance = float(config.get("tasa_binance", st.session_state.get("tasa_binance", tasa_binance_default)) or tasa_binance_default)
        return tasa_bcv, tasa_binance
    except Exception:
        return 36.5, 38.0


def _inventory_module():
    try:
        from modules import inventario as inv_module
        inv_module._ensure_inventory_support_tables()
        inv_module._ensure_config_defaults()
        return inv_module
    except Exception as exc:
        st.error("No se pudo cargar la función avanzada del inventario.")
        st.exception(exc)
        return None


def _render_internal(section: str, callback_name: str, *args) -> None:
    inv_module = _inventory_module()
    if inv_module is None:
        return
    callback = getattr(inv_module, callback_name, None)
    if callback is None:
        st.warning(f"La sección {section} no está disponible en el módulo interno.")
        return
    try:
        callback(*args)
    except Exception as exc:
        st.error(f"No se pudo cargar {section}.")
        st.exception(exc)


def _facturas_compra_cxp() -> pd.DataFrame:
    return _read_query(
        """
        SELECT id, proveedor, numero_factura, fecha_factura, fecha_vencimiento,
               total_usd, pagado_usd, pendiente_usd, estado, metodo_pago, tipo_pago
        FROM facturas_compra
        WHERE pendiente_usd > 0.0001 OR estado IN ('pendiente', 'parcial')
        ORDER BY proveedor, date(fecha_vencimiento), id DESC
        """
    )


def _abonos_facturas_compra() -> pd.DataFrame:
    return _read_query(
        """
        SELECT a.id, a.fecha, f.proveedor, f.numero_factura, a.factura_id,
               a.monto_usd, a.metodo_pago, a.referencia, a.notas, a.movimiento_tesoreria_id
        FROM abonos_facturas_compra a
        LEFT JOIN facturas_compra f ON f.id = a.factura_id
        ORDER BY a.id DESC
        LIMIT 500
        """
    )


def _resumen_cxp_por_proveedor(cxp: pd.DataFrame) -> pd.DataFrame:
    if cxp.empty:
        return pd.DataFrame()
    df = _add_vencimiento_columns(cxp)
    df["proveedor"] = df["proveedor"].fillna("Proveedor N/D").astype(str)
    resumen = df.groupby("proveedor", as_index=False).agg(
        facturas_pendientes=("id", "count"),
        total_pendiente_usd=("pendiente_usd", "sum"),
        total_facturado_usd=("total_usd", "sum"),
        facturas_vencidas=("estado_vencimiento", lambda s: int((s == "Vencida").sum())),
        vencen_7_dias=("estado_vencimiento", lambda s: int((s == "Vence en 7 días").sum())),
    )
    return resumen.sort_values("total_pendiente_usd", ascending=False)


def _provider_options(proveedores: pd.DataFrame, compras: pd.DataFrame, cxp: pd.DataFrame, abonos: pd.DataFrame) -> list[str]:
    nombres: list[str] = []
    for df, col in [(proveedores, "nombre"), (compras, "proveedor"), (cxp, "proveedor"), (abonos, "proveedor")]:
        if not df.empty and col in df.columns:
            nombres.extend(df[col].dropna().astype(str).tolist())
    return sorted({x.strip() for x in nombres if x and x.strip()}, key=str.lower)


def _render_perfil_proveedor(proveedores: pd.DataFrame, compras: pd.DataFrame, cxp_nueva: pd.DataFrame, abonos_nuevos: pd.DataFrame) -> None:
    st.markdown("##### Perfil financiero del proveedor")
    opciones = _provider_options(proveedores, compras, cxp_nueva, abonos_nuevos)
    if not opciones:
        st.info("No hay proveedores, compras, facturas o abonos para construir un perfil.")
        return

    proveedor_sel = st.selectbox("Proveedor", opciones, key="perfil_proveedor_select")
    proveedor_info = _filter_provider(proveedores, proveedor_sel, "nombre") if "nombre" in proveedores.columns else pd.DataFrame()
    compras_p = _filter_provider(compras, proveedor_sel, "proveedor")
    cxp_p = _add_vencimiento_columns(_filter_provider(cxp_nueva, proveedor_sel, "proveedor"))
    abonos_p = _filter_provider(abonos_nuevos, proveedor_sel, "proveedor")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deuda pendiente", f"${_safe_sum(cxp_p, 'pendiente_usd'):,.2f}")
    c2.metric("Compras históricas", f"${_safe_sum(compras_p, 'costo_total_usd'):,.2f}")
    c3.metric("Abonos registrados", f"${_safe_sum(abonos_p, 'monto_usd'):,.2f}")
    c4.metric("Facturas pendientes", len(cxp_p))

    vencidas = cxp_p[cxp_p.get("estado_vencimiento", pd.Series(dtype=str)).eq("Vencida")] if not cxp_p.empty else pd.DataFrame()
    vence_7 = cxp_p[cxp_p.get("estado_vencimiento", pd.Series(dtype=str)).eq("Vence en 7 días")] if not cxp_p.empty else pd.DataFrame()
    sin_venc = cxp_p[cxp_p.get("estado_vencimiento", pd.Series(dtype=str)).eq("Sin vencimiento")] if not cxp_p.empty else pd.DataFrame()
    a1, a2, a3 = st.columns(3)
    a1.metric("Vencidas", len(vencidas), f"${_safe_sum(vencidas, 'pendiente_usd'):,.2f}")
    a2.metric("Vencen en 7 días", len(vence_7), f"${_safe_sum(vence_7, 'pendiente_usd'):,.2f}")
    a3.metric("Sin vencimiento", len(sin_venc), f"${_safe_sum(sin_venc, 'pendiente_usd'):,.2f}")

    if not proveedor_info.empty:
        st.markdown("###### Datos del proveedor")
        st.dataframe(proveedor_info.head(1), use_container_width=True, hide_index=True)

    st.markdown("###### Facturas pendientes y vencimientos")
    if cxp_p.empty:
        st.success("Este proveedor no tiene facturas pendientes en la CxP nueva.")
    else:
        cols = [c for c in ["id", "numero_factura", "fecha_factura", "fecha_vencimiento", "estado_vencimiento", "dias_para_vencer", "total_usd", "pagado_usd", "pendiente_usd", "estado", "tipo_pago", "metodo_pago"] if c in cxp_p.columns]
        st.dataframe(cxp_p[cols], use_container_width=True, hide_index=True)

    col_abonos, col_compras = st.columns(2)
    with col_abonos:
        st.markdown("###### Abonos")
        if abonos_p.empty:
            st.info("Sin abonos registrados para este proveedor.")
        else:
            st.dataframe(abonos_p, use_container_width=True, hide_index=True)
    with col_compras:
        st.markdown("###### Compras históricas")
        if compras_p.empty:
            st.info("Sin compras históricas registradas para este proveedor.")
        else:
            st.dataframe(compras_p, use_container_width=True, hide_index=True)

    partes = []
    for nombre_bloque, df_bloque in {"facturas_pendientes": cxp_p, "abonos": abonos_p, "compras": compras_p}.items():
        if not df_bloque.empty:
            partes.append(f"\n## {nombre_bloque}\n" + df_bloque.to_csv(index=False))
    if partes:
        st.download_button(
            "⬇️ Descargar perfil CSV",
            data=("".join(partes)).encode("utf-8-sig"),
            file_name=f"perfil_proveedor_{proveedor_sel.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


def render_proveedores(usuario: str = "Sistema") -> None:
    st.subheader("👥 Proveedores")
    st.caption("Ficha maestra, relación proveedor-producto, documentos, evaluación y pagos relacionados.")

    proveedores = _read_table("proveedores", "id DESC", 1000)
    compras = _read_table("historial_compras", "id DESC", 1000)
    docs = _read_table("proveedor_documentos", "id DESC", 500)
    evaluaciones = _read_table("evaluaciones_proveedor", "id DESC", 500)
    cxp_legacy = _read_table("cuentas_por_pagar_proveedores", "id DESC", 500)
    cxp_nueva = _add_vencimiento_columns(_facturas_compra_cxp())
    abonos_nuevos = _abonos_facturas_compra()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proveedores", len(proveedores))
    c2.metric("Activos", int(proveedores.get("activo", pd.Series(dtype=int)).fillna(1).astype(int).sum()) if not proveedores.empty and "activo" in proveedores.columns else len(proveedores))
    c3.metric("Compras históricas", f"${_safe_sum(compras, 'costo_total_usd'):,.2f}")
    c4.metric("CxP nueva", f"${_safe_sum(cxp_nueva, 'pendiente_usd'):,.2f}")

    tabs = st.tabs(["Listado", "Perfil proveedor", "Nuevo rápido", "Maestro avanzado", "Proveedor-Producto", "Historial de compras", "Documentos", "Evaluaciones", "CxP facturas", "Abonos facturas", "CxP anterior", "Pagos"])

    with tabs[0]:
        if proveedores.empty:
            st.info("No hay proveedores registrados.")
        else:
            filtro = st.text_input("Buscar proveedor", key="buscar_proveedor")
            vista = proveedores.copy()
            if filtro.strip():
                mask = vista.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False)).any(axis=1)
                vista = vista[mask]
            st.dataframe(vista, use_container_width=True, hide_index=True)

    with tabs[1]:
        _render_perfil_proveedor(proveedores, compras, cxp_nueva, abonos_nuevos)

    with tabs[2]:
        with st.form("form_nuevo_proveedor"):
            col_a, col_b = st.columns(2)
            nombre = col_a.text_input("Nombre / Razón social")
            rif = col_b.text_input("RIF / Identificación fiscal")
            telefono = col_a.text_input("Teléfono")
            email = col_b.text_input("Email")
            contacto = col_a.text_input("Contacto / vendedor")
            tipo = col_b.selectbox("Tipo proveedor", ["Insumos", "Servicios", "Maquinaria", "Papelería", "Transporte", "Otro"])
            direccion = st.text_area("Dirección")
            col_c, col_d, col_e = st.columns(3)
            dias_credito = col_c.number_input("Días de crédito", min_value=0, value=0, step=1)
            moneda = col_d.selectbox("Moneda default", ["USD", "VES", "COP", "EUR"])
            lead_time = col_e.number_input("Lead time días", min_value=0, value=0, step=1)
            banco = st.text_input("Banco / Datos bancarios")
            observaciones = st.text_area("Observaciones")
            guardar = st.form_submit_button("Guardar proveedor")
        if guardar:
            if not nombre.strip():
                st.error("El nombre del proveedor es obligatorio.")
            else:
                _insert_provider({"nombre": nombre.strip(), "rif": rif.strip(), "telefono": telefono.strip(), "email": email.strip(), "contacto": contacto.strip(), "tipo_proveedor": tipo, "direccion": direccion.strip(), "dias_credito_default": int(dias_credito), "moneda_default": moneda, "lead_time_dias": int(lead_time), "banco": banco.strip(), "datos_bancarios": banco.strip(), "observaciones": observaciones.strip(), "activo": 1})
                st.success("Proveedor guardado.")
                st.rerun()

    with tabs[3]:
        _render_internal("Maestro avanzado de proveedores", "_render_proveedores")
    with tabs[4]:
        _render_internal("Proveedor-Producto", "_render_catalogo_proveedor_producto")
    with tabs[5]:
        st.dataframe(compras, use_container_width=True, hide_index=True) if not compras.empty else st.info("No hay historial de compras.")
        st.caption("La gestión avanzada del historial vive en 🛒 Compras → Historial compras para evitar formularios duplicados.")
    with tabs[6]:
        st.dataframe(docs, use_container_width=True, hide_index=True) if not docs.empty else st.info("No hay documentos de proveedor registrados.")
        with st.expander("Gestión avanzada de documentos"):
            _render_internal("Documentos de proveedor", "_render_documentos_proveedor")
    with tabs[7]:
        st.dataframe(evaluaciones, use_container_width=True, hide_index=True) if not evaluaciones.empty else st.info("No hay evaluaciones de proveedor registradas.")
        with st.expander("Evaluación avanzada"):
            _render_internal("Evaluación de proveedores", "_render_evaluacion_proveedores", usuario)
    with tabs[8]:
        st.markdown("##### CxP nueva desde facturas de compra")
        resumen = _resumen_cxp_por_proveedor(cxp_nueva)
        if cxp_nueva.empty:
            st.success("No hay facturas de compra pendientes por proveedor.")
        else:
            r1, r2, r3 = st.columns(3)
            r1.metric("Total pendiente", f"${_safe_sum(cxp_nueva, 'pendiente_usd'):,.2f}")
            r2.metric("Facturas pendientes", len(cxp_nueva))
            r3.metric("Proveedores con deuda", len(resumen))
            st.markdown("###### Resumen por proveedor")
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            st.markdown("###### Facturas pendientes")
            filtro_proveedor = st.selectbox("Filtrar proveedor", ["Todos"] + sorted(cxp_nueva["proveedor"].fillna("Proveedor N/D").astype(str).unique().tolist()), key="proveedores_cxp_nueva_filtro")
            detalle = cxp_nueva.copy()
            if filtro_proveedor != "Todos":
                detalle = detalle[detalle["proveedor"].fillna("Proveedor N/D").astype(str).eq(filtro_proveedor)]
            st.dataframe(detalle, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar CxP facturas CSV", data=detalle.to_csv(index=False).encode("utf-8-sig"), file_name="cxp_facturas_por_proveedor.csv", mime="text/csv", use_container_width=True)
        st.caption("Esta pestaña usa la CxP nueva creada desde Facturas de compra.")
    with tabs[9]:
        st.markdown("##### Abonos registrados desde facturas de compra")
        if abonos_nuevos.empty:
            st.info("Aún no hay abonos registrados en la CxP nueva.")
        else:
            filtro = st.text_input("Buscar proveedor / factura / referencia", key="proveedores_abonos_buscar")
            vista_abonos = abonos_nuevos.copy()
            if filtro.strip():
                mask = vista_abonos.astype(str).apply(lambda col: col.str.contains(filtro.strip(), case=False, na=False)).any(axis=1)
                vista_abonos = vista_abonos[mask]
            st.dataframe(vista_abonos, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar abonos CSV", data=vista_abonos.to_csv(index=False).encode("utf-8-sig"), file_name="abonos_facturas_por_proveedor.csv", mime="text/csv", use_container_width=True)
    with tabs[10]:
        st.markdown("##### CxP anterior / legado")
        st.dataframe(cxp_legacy, use_container_width=True, hide_index=True) if not cxp_legacy.empty else st.info("No hay cuentas por pagar anteriores de proveedores.")
        st.caption("Este bloque queda como referencia histórica. La CxP nueva vive en 'CxP facturas'.")
    with tabs[11]:
        _render_internal("Pagos a proveedores", "_render_pagos_proveedores", usuario)


def render_compras_suministro(usuario: str = "Sistema") -> None:
    st.subheader("🛒 Compras / Órdenes de suministro")
    st.caption("Compras, recibo inteligente, órdenes de compra, recepciones, costos promedio, historial y obligaciones con proveedores.")

    ordenes = _read_table("ordenes_compra", "id DESC", 500)
    detalle = _read_table("ordenes_compra_detalle", "id DESC", 1000)
    recepciones = _read_table("recepciones_orden_compra", "id DESC", 500)
    historial = _read_table("historial_compras", "id DESC", 1000)
    cxp_legacy = _read_table("cuentas_por_pagar_proveedores", "id DESC", 500)
    cxp_nueva = _add_vencimiento_columns(_facturas_compra_cxp())
    tasa_bcv, tasa_binance = _get_rates()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes", len(ordenes))
    c2.metric("Recepciones", len(recepciones))
    c3.metric("Compras históricas", f"${_safe_sum(historial, 'costo_total_usd'):,.2f}")
    c4.metric("CxP facturas", f"${_safe_sum(cxp_nueva, 'pendiente_usd'):,.2f}")

    tabs = st.tabs(["Registrar compra", "Recibo inteligente", "Órdenes", "Detalle OC", "Recepciones", "Historial compras", "Resumen abastecimiento", "CxP facturas", "CxP anterior", "Alertas"])
    with tabs[0]:
        _render_internal("Registrar compra", "_render_compras", usuario, tasa_bcv, tasa_binance)
    with tabs[1]:
        _render_internal("Recibo inteligente", "_render_recibo_inteligente", usuario, tasa_bcv, tasa_binance)
    with tabs[2]:
        st.dataframe(ordenes, use_container_width=True, hide_index=True) if not ordenes.empty else st.info("No hay órdenes de compra registradas.")
        with st.expander("Gestión avanzada de órdenes de compra"):
            _render_internal("Órdenes de compra", "_render_ordenes_compra", usuario)
    with tabs[3]:
        st.dataframe(detalle, use_container_width=True, hide_index=True) if not detalle.empty else st.info("No hay detalle de órdenes.")
    with tabs[4]:
        st.dataframe(recepciones, use_container_width=True, hide_index=True) if not recepciones.empty else st.info("No hay recepciones registradas.")
    with tabs[5]:
        st.dataframe(historial, use_container_width=True, hide_index=True) if not historial.empty else st.info("No hay historial de compras.")
        with st.expander("Historial avanzado"):
            _render_internal("Historial de compras", "_render_historial_compras")
    with tabs[6]:
        _render_internal("Resumen de abastecimiento", "_render_resumen_abastecimiento")
    with tabs[7]:
        st.markdown("##### Cuentas por pagar desde facturas de compra")
        if cxp_nueva.empty:
            st.success("No hay facturas pendientes por pagar.")
        else:
            st.dataframe(_resumen_cxp_por_proveedor(cxp_nueva), use_container_width=True, hide_index=True)
            st.dataframe(cxp_nueva, use_container_width=True, hide_index=True)
    with tabs[8]:
        st.markdown("##### CxP anterior / legado")
        st.dataframe(cxp_legacy, use_container_width=True, hide_index=True) if not cxp_legacy.empty else st.info("No hay cuentas por pagar anteriores de proveedores.")
        with st.expander("CxP avanzada anterior"):
            _render_internal("Cuentas por pagar de proveedores", "_render_cuentas_por_pagar")
    with tabs[9]:
        alertas = []
        if not ordenes.empty and "estado" in ordenes.columns:
            abiertas = ordenes[ordenes["estado"].fillna("").astype(str).str.lower().isin(["borrador", "aprobada", "enviada", "parcial"])]
            if not abiertas.empty:
                alertas.append({"nivel": "Media", "alerta": f"Hay {len(abiertas)} orden(es) abiertas o parciales.", "accion": "Revisar recepción o cierre."})
        if not cxp_nueva.empty:
            vencidas = cxp_nueva[cxp_nueva["estado_vencimiento"].eq("Vencida")]
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": f"Hay {len(vencidas)} factura(s) de compra vencidas por pagar.", "accion": "Revisar CxP facturas y registrar abono."})
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True) if alertas else st.success("Sin alertas críticas de compras/proveedores con la información disponible.")