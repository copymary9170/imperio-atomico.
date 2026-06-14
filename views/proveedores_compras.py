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
        conn.execute(
            f"INSERT INTO proveedores ({','.join(keys)}) VALUES ({placeholders})",
            [payload[k] for k in keys],
        )


def _safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


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
        SELECT
            id,
            proveedor,
            numero_factura,
            fecha_factura,
            fecha_vencimiento,
            total_usd,
            pagado_usd,
            pendiente_usd,
            estado,
            metodo_pago,
            tipo_pago
        FROM facturas_compra
        WHERE pendiente_usd > 0.0001 OR estado IN ('pendiente', 'parcial')
        ORDER BY proveedor, date(fecha_vencimiento), id DESC
        """
    )


def _abonos_facturas_compra() -> pd.DataFrame:
    return _read_query(
        """
        SELECT
            a.id,
            a.fecha,
            f.proveedor,
            f.numero_factura,
            a.factura_id,
            a.monto_usd,
            a.metodo_pago,
            a.referencia,
            a.notas,
            a.movimiento_tesoreria_id
        FROM abonos_facturas_compra a
        LEFT JOIN facturas_compra f ON f.id = a.factura_id
        ORDER BY a.id DESC
        LIMIT 500
        """
    )


def _resumen_cxp_por_proveedor(cxp: pd.DataFrame) -> pd.DataFrame:
    if cxp.empty:
        return pd.DataFrame()
    df = cxp.copy()
    df["proveedor"] = df["proveedor"].fillna("Proveedor N/D").astype(str)
    df["fecha_vencimiento_dt"] = pd.to_datetime(df["fecha_vencimiento"], errors="coerce")
    hoy = pd.Timestamp.today().normalize()
    df["vencida"] = df["fecha_vencimiento_dt"].notna() & (df["fecha_vencimiento_dt"] < hoy)
    df["vence_pronto"] = df["fecha_vencimiento_dt"].notna() & df["fecha_vencimiento_dt"].between(hoy, hoy + pd.Timedelta(days=7), inclusive="both")
    resumen = df.groupby("proveedor", as_index=False).agg(
        facturas_pendientes=("id", "count"),
        total_pendiente_usd=("pendiente_usd", "sum"),
        total_facturado_usd=("total_usd", "sum"),
        facturas_vencidas=("vencida", "sum"),
        vencen_7_dias=("vence_pronto", "sum"),
    )
    return resumen.sort_values("total_pendiente_usd", ascending=False)


def render_proveedores(usuario: str = "Sistema") -> None:
    st.subheader("👥 Proveedores")
    st.caption("Ficha maestra, relación proveedor-producto, documentos, evaluación y pagos relacionados.")

    proveedores = _read_table("proveedores", "id DESC", 1000)
    compras = _read_table("historial_compras", "id DESC", 1000)
    docs = _read_table("proveedor_documentos", "id DESC", 500)
    evaluaciones = _read_table("evaluaciones_proveedor", "id DESC", 500)
    cxp_legacy = _read_table("cuentas_por_pagar_proveedores", "id DESC", 500)
    cxp_nueva = _facturas_compra_cxp()
    abonos_nuevos = _abonos_facturas_compra()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proveedores", len(proveedores))
    c2.metric("Activos", int(proveedores.get("activo", pd.Series(dtype=int)).fillna(1).astype(int).sum()) if not proveedores.empty and "activo" in proveedores.columns else len(proveedores))
    c3.metric("Compras históricas", f"${_safe_sum(compras, 'costo_total_usd'):,.2f}")
    c4.metric("CxP nueva", f"${_safe_sum(cxp_nueva, 'pendiente_usd'):,.2f}")

    tabs = st.tabs([
        "Listado",
        "Nuevo rápido",
        "Maestro avanzado",
        "Proveedor-Producto",
        "Historial de compras",
        "Documentos",
        "Evaluaciones",
        "CxP facturas",
        "Abonos facturas",
        "CxP anterior",
        "Pagos",
    ])

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
                _insert_provider({
                    "nombre": nombre.strip(),
                    "rif": rif.strip(),
                    "telefono": telefono.strip(),
                    "email": email.strip(),
                    "contacto": contacto.strip(),
                    "tipo_proveedor": tipo,
                    "direccion": direccion.strip(),
                    "dias_credito_default": int(dias_credito),
                    "moneda_default": moneda,
                    "lead_time_dias": int(lead_time),
                    "banco": banco.strip(),
                    "datos_bancarios": banco.strip(),
                    "observaciones": observaciones.strip(),
                    "activo": 1,
                })
                st.success("Proveedor guardado.")
                st.rerun()

    with tabs[2]:
        _render_internal("Maestro avanzado de proveedores", "_render_proveedores")

    with tabs[3]:
        _render_internal("Proveedor-Producto", "_render_catalogo_proveedor_producto")

    with tabs[4]:
        if compras.empty:
            st.info("No hay historial de compras.")
        else:
            st.dataframe(compras, use_container_width=True, hide_index=True)
        st.caption("La gestión avanzada del historial vive en 🛒 Compras → Historial compras para evitar formularios duplicados.")

    with tabs[5]:
        if docs.empty:
            st.info("No hay documentos de proveedor registrados.")
        else:
            st.dataframe(docs, use_container_width=True, hide_index=True)
        with st.expander("Gestión avanzada de documentos"):
            _render_internal("Documentos de proveedor", "_render_documentos_proveedor")

    with tabs[6]:
        if evaluaciones.empty:
            st.info("No hay evaluaciones de proveedor registradas.")
        else:
            st.dataframe(evaluaciones, use_container_width=True, hide_index=True)
        with st.expander("Evaluación avanzada"):
            _render_internal("Evaluación de proveedores", "_render_evaluacion_proveedores", usuario)

    with tabs[7]:
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
            st.download_button(
                "⬇️ Descargar CxP facturas CSV",
                data=detalle.to_csv(index=False).encode("utf-8-sig"),
                file_name="cxp_facturas_por_proveedor.csv",
                mime="text/csv",
                use_container_width=True,
            )
        st.caption("Esta pestaña usa la CxP nueva creada desde Facturas de compra.")

    with tabs[8]:
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
            st.download_button(
                "⬇️ Descargar abonos CSV",
                data=vista_abonos.to_csv(index=False).encode("utf-8-sig"),
                file_name="abonos_facturas_por_proveedor.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tabs[9]:
        st.markdown("##### CxP anterior / legado")
        if cxp_legacy.empty:
            st.info("No hay cuentas por pagar anteriores de proveedores.")
        else:
            st.dataframe(cxp_legacy, use_container_width=True, hide_index=True)
        st.caption("Este bloque queda como referencia histórica. La CxP nueva vive en 'CxP facturas'.")

    with tabs[10]:
        _render_internal("Pagos a proveedores", "_render_pagos_proveedores", usuario)


def render_compras_suministro(usuario: str = "Sistema") -> None:
    st.subheader("🛒 Compras / Órdenes de suministro")
    st.caption("Compras, recibo inteligente, órdenes de compra, recepciones, costos promedio, historial y obligaciones con proveedores.")

    ordenes = _read_table("ordenes_compra", "id DESC", 500)
    detalle = _read_table("ordenes_compra_detalle", "id DESC", 1000)
    recepciones = _read_table("recepciones_orden_compra", "id DESC", 500)
    historial = _read_table("historial_compras", "id DESC", 1000)
    cxp_legacy = _read_table("cuentas_por_pagar_proveedores", "id DESC", 500)
    cxp_nueva = _facturas_compra_cxp()
    tasa_bcv, tasa_binance = _get_rates()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes", len(ordenes))
    c2.metric("Recepciones", len(recepciones))
    c3.metric("Compras históricas", f"${_safe_sum(historial, 'costo_total_usd'):,.2f}")
    c4.metric("CxP facturas", f"${_safe_sum(cxp_nueva, 'pendiente_usd'):,.2f}")

    tabs = st.tabs([
        "Registrar compra",
        "Recibo inteligente",
        "Órdenes",
        "Detalle OC",
        "Recepciones",
        "Historial compras",
        "Resumen abastecimiento",
        "CxP facturas",
        "CxP anterior",
        "Alertas",
    ])

    with tabs[0]:
        _render_internal("Registrar compra", "_render_compras", usuario, tasa_bcv, tasa_binance)

    with tabs[1]:
        _render_internal("Recibo inteligente", "_render_recibo_inteligente", usuario, tasa_bcv, tasa_binance)

    with tabs[2]:
        if ordenes.empty:
            st.info("No hay órdenes de compra registradas.")
        else:
            st.dataframe(ordenes, use_container_width=True, hide_index=True)
        with st.expander("Gestión avanzada de órdenes de compra"):
            _render_internal("Órdenes de compra", "_render_ordenes_compra", usuario)

    with tabs[3]:
        if detalle.empty:
            st.info("No hay detalle de órdenes.")
        else:
            st.dataframe(detalle, use_container_width=True, hide_index=True)

    with tabs[4]:
        if recepciones.empty:
            st.info("No hay recepciones registradas.")
        else:
            st.dataframe(recepciones, use_container_width=True, hide_index=True)

    with tabs[5]:
        if historial.empty:
            st.info("No hay historial de compras.")
        else:
            st.dataframe(historial, use_container_width=True, hide_index=True)
        with st.expander("Historial avanzado"):
            _render_internal("Historial de compras", "_render_historial_compras")

    with tabs[6]:
        _render_internal("Resumen de abastecimiento", "_render_resumen_abastecimiento")

    with tabs[7]:
        st.markdown("##### Cuentas por pagar desde facturas de compra")
        if cxp_nueva.empty:
            st.success("No hay facturas pendientes por pagar.")
        else:
            resumen = _resumen_cxp_por_proveedor(cxp_nueva)
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            st.dataframe(cxp_nueva, use_container_width=True, hide_index=True)

    with tabs[8]:
        st.markdown("##### CxP anterior / legado")
        if cxp_legacy.empty:
            st.info("No hay cuentas por pagar anteriores de proveedores.")
        else:
            st.dataframe(cxp_legacy, use_container_width=True, hide_index=True)
        with st.expander("CxP avanzada anterior"):
            _render_internal("Cuentas por pagar de proveedores", "_render_cuentas_por_pagar")

    with tabs[9]:
        alertas = []
        if not ordenes.empty and "estado" in ordenes.columns:
            abiertas = ordenes[ordenes["estado"].fillna("").astype(str).str.lower().isin(["borrador", "aprobada", "enviada", "parcial"])]
            if not abiertas.empty:
                alertas.append({"nivel": "Media", "alerta": f"Hay {len(abiertas)} orden(es) abiertas o parciales.", "accion": "Revisar recepción o cierre."})
        if not cxp_nueva.empty:
            cxp_tmp = cxp_nueva.copy()
            cxp_tmp["fecha_vencimiento_dt"] = pd.to_datetime(cxp_tmp["fecha_vencimiento"], errors="coerce")
            vencidas = cxp_tmp[cxp_tmp["fecha_vencimiento_dt"].notna() & (cxp_tmp["fecha_vencimiento_dt"] < pd.Timestamp.today().normalize())]
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": f"Hay {len(vencidas)} factura(s) de compra vencidas por pagar.", "accion": "Revisar CxP facturas y registrar abono."})
        if alertas:
            st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
        else:
            st.success("Sin alertas críticas de compras/proveedores con la información disponible.")
