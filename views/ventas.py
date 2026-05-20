from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission
from views.pos_rapido import render_pos_rapido
from views.cola_impresion import render_cola_impresion
from views.ticket_pos import render_ticket_pos


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _safe_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _load_unified_history() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    ventas = _safe_df(
        """
        SELECT id, fecha, 'Venta profesional' AS origen, COALESCE(c.nombre,'Sin cliente') AS cliente,
               COALESCE(v.metodo_pago,'') AS metodo_pago, COALESCE(v.total_usd,0) AS total_usd,
               COALESCE(v.estado,'registrado') AS estado, ('VENTA-' || v.id) AS referencia
        FROM ventas v
        LEFT JOIN clientes c ON c.id = v.cliente_id
        ORDER BY v.id DESC
        LIMIT 500
        """
    )
    if not ventas.empty:
        rows.append(ventas)

    pos = _safe_df(
        """
        SELECT id, fecha, 'POS rápido' AS origen, COALESCE(cliente,'Cliente General') AS cliente,
               COALESCE(metodo_pago,'') AS metodo_pago, COALESCE(total_usd,0) AS total_usd,
               COALESCE(estado,'pagada') AS estado, ('POS-' || id) AS referencia
        FROM pos_ventas
        ORDER BY id DESC
        LIMIT 500
        """
    )
    if not pos.empty:
        rows.append(pos)

    comps = _safe_df(
        """
        SELECT id, fecha, 'Comprobante' AS origen, COALESCE(cliente,'Cliente General') AS cliente,
               COALESCE(metodo_pago,'') AS metodo_pago, COALESCE(total_usd,0) AS total_usd,
               COALESCE(estado,'Emitido') AS estado, COALESCE(referencia, 'COMP-' || id) AS referencia
        FROM comprobantes_pos
        ORDER BY id DESC
        LIMIT 500
        """
    )
    if not comps.empty:
        rows.append(comps)

    if not rows:
        return pd.DataFrame(columns=["id", "fecha", "origen", "cliente", "metodo_pago", "total_usd", "estado", "referencia"])
    df = pd.concat(rows, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["total_usd"] = pd.to_numeric(df["total_usd"], errors="coerce").fillna(0.0)
    return df.sort_values("fecha", ascending=False, na_position="last")


def _render_historial_unificado() -> None:
    st.subheader("📜 Historial unificado")
    st.caption("Vista consolidada de ventas profesionales, ventas POS y comprobantes emitidos.")
    df = _load_unified_history()
    if df.empty:
        st.info("No hay ventas, POS ni comprobantes para mostrar.")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    origen = c1.selectbox("Origen", ["Todos"] + sorted(df["origen"].dropna().unique().tolist()))
    metodo = c2.selectbox("Método", ["Todos"] + sorted(df["metodo_pago"].dropna().astype(str).unique().tolist()))
    buscar = c3.text_input("Buscar cliente / referencia")

    vista = df.copy()
    if origen != "Todos":
        vista = vista[vista["origen"].eq(origen)]
    if metodo != "Todos":
        vista = vista[vista["metodo_pago"].astype(str).eq(metodo)]
    if buscar.strip():
        txt = buscar.strip()
        vista = vista[vista["cliente"].astype(str).str.contains(txt, case=False, na=False) | vista["referencia"].astype(str).str.contains(txt, case=False, na=False)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Registros", len(vista))
    m2.metric("Total USD", f"${float(vista['total_usd'].sum()):,.2f}")
    m3.metric("Ticket promedio", f"${float(vista['total_usd'].sum()) / max(len(vista), 1):,.2f}")
    st.dataframe(vista, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Descargar historial unificado CSV", data=vista.to_csv(index=False).encode("utf-8-sig"), file_name="historial_unificado_ventas.csv", mime="text/csv", use_container_width=True)


def _render_alertas_ventas() -> None:
    st.subheader("🚨 Alertas de ventas")
    st.caption("Detecta descuadres entre ventas, POS, comprobantes, crédito, cola de impresión y descuentos.")

    pos = _safe_df("SELECT id, fecha, cliente, total_usd, estado FROM pos_ventas ORDER BY id DESC LIMIT 1000")
    comps = _safe_df("SELECT id, fecha, venta_id, referencia, cliente, total_usd, estado FROM comprobantes_pos ORDER BY id DESC LIMIT 1000")
    cxc = _safe_df("SELECT id, venta_id, cliente_id, saldo_usd, estado, dias_vencimiento, notas FROM cuentas_por_cobrar ORDER BY id DESC LIMIT 1000")
    cola = _safe_df("SELECT id, venta_pos_id, cliente, estado, total_paginas, archivo_nombre FROM cola_impresion ORDER BY id DESC LIMIT 1000")
    ventas_detalle = _safe_df(
        """
        SELECT vd.venta_id, vd.descripcion, vd.cantidad, vd.precio_unitario_usd, vd.costo_unitario_usd,
               vd.subtotal_usd, v.total_usd
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        ORDER BY vd.venta_id DESC
        LIMIT 1000
        """
    )

    pos_con_comp = set()
    if not comps.empty and "referencia" in comps.columns:
        refs = comps["referencia"].fillna("").astype(str)
        pos_con_comp = {int(x.replace("POS-", "")) for x in refs[refs.str.startswith("POS-")] if x.replace("POS-", "").isdigit()}
    pos_sin_comp = pos[~pos["id"].astype(int).isin(pos_con_comp)] if not pos.empty else pd.DataFrame()

    comps_sin_venta = pd.DataFrame()
    if not comps.empty:
        venta_id = pd.to_numeric(comps.get("venta_id", pd.Series(dtype=float)), errors="coerce").fillna(0)
        refs = comps.get("referencia", pd.Series(dtype=str)).fillna("").astype(str)
        comps_sin_venta = comps[(venta_id <= 0) & ~refs.str.startswith("POS-")]

    cxc_vencida = pd.DataFrame()
    if not cxc.empty:
        dias = pd.to_numeric(cxc.get("dias_vencimiento", pd.Series(dtype=float)), errors="coerce").fillna(0)
        cxc_vencida = cxc[cxc["estado"].fillna("").astype(str).str.lower().isin(["vencida", "pendiente"]) & (dias > 0)]

    cola_sin_venta = pd.DataFrame()
    impresos_no_entregados = pd.DataFrame()
    if not cola.empty:
        venta_pos = pd.to_numeric(cola.get("venta_pos_id", pd.Series(dtype=float)), errors="coerce").fillna(0)
        cola_sin_venta = cola[venta_pos <= 0]
        impresos_no_entregados = cola[cola["estado"].fillna("").astype(str).isin(["Impreso", "Error / Reimprimir"])]

    margen_negativo = pd.DataFrame()
    if not ventas_detalle.empty:
        subtotal = pd.to_numeric(ventas_detalle["subtotal_usd"], errors="coerce").fillna(0)
        costo = pd.to_numeric(ventas_detalle["cantidad"], errors="coerce").fillna(0) * pd.to_numeric(ventas_detalle["costo_unitario_usd"], errors="coerce").fillna(0)
        margen_negativo = ventas_detalle[(subtotal - costo) < 0]

    alertas = []
    if not pos_sin_comp.empty:
        alertas.append({"nivel": "Media", "alerta": "Ventas POS sin comprobante asociado", "cantidad": len(pos_sin_comp), "accion": "Emitir o validar comprobante automático POS."})
    if not comps_sin_venta.empty:
        alertas.append({"nivel": "Media", "alerta": "Comprobantes sin venta/POS asociado", "cantidad": len(comps_sin_venta), "accion": "Vincular comprobante a venta, POS u OT."})
    if not cxc_vencida.empty:
        alertas.append({"nivel": "Alta", "alerta": "Cuentas por cobrar vencidas", "cantidad": len(cxc_vencida), "accion": "Gestionar cobranza por documento."})
    if not cola_sin_venta.empty:
        alertas.append({"nivel": "Media", "alerta": "Cola de impresión sin venta POS asociada", "cantidad": len(cola_sin_venta), "accion": "Asociar venta/cobro o validar trabajo gratuito."})
    if not impresos_no_entregados.empty:
        alertas.append({"nivel": "Media", "alerta": "Trabajos impresos no entregados o con reimpresión", "cantidad": len(impresos_no_entregados), "accion": "Revisar entrega o reimpresión."})
    if not margen_negativo.empty:
        alertas.append({"nivel": "Alta", "alerta": "Líneas de venta con margen negativo", "cantidad": len(margen_negativo), "accion": "Revisar precio/costo/descuento."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("POS sin comprobante", len(pos_sin_comp))
    c2.metric("CxC vencidas", len(cxc_vencida))
    c3.metric("Cola sin venta", len(cola_sin_venta))
    c4.metric("Margen negativo", len(margen_negativo))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas críticas de ventas con la información disponible.")

    tabs = st.tabs(["POS sin comprobante", "Comprobantes sueltos", "CxC vencidas", "Cola impresión", "Margen negativo"])
    with tabs[0]:
        st.dataframe(pos_sin_comp, use_container_width=True, hide_index=True) if not pos_sin_comp.empty else st.success("Sin POS pendientes de comprobante.")
    with tabs[1]:
        st.dataframe(comps_sin_venta, use_container_width=True, hide_index=True) if not comps_sin_venta.empty else st.success("Sin comprobantes sueltos.")
    with tabs[2]:
        st.dataframe(cxc_vencida, use_container_width=True, hide_index=True) if not cxc_vencida.empty else st.success("Sin CxC vencidas detectadas.")
    with tabs[3]:
        if not cola_sin_venta.empty:
            st.markdown("#### Cola sin venta asociada")
            st.dataframe(cola_sin_venta, use_container_width=True, hide_index=True)
        if not impresos_no_entregados.empty:
            st.markdown("#### Impresos no entregados / reimpresión")
            st.dataframe(impresos_no_entregados, use_container_width=True, hide_index=True)
        if cola_sin_venta.empty and impresos_no_entregados.empty:
            st.success("Sin alertas de cola de impresión.")
    with tabs[4]:
        st.dataframe(margen_negativo, use_container_width=True, hide_index=True) if not margen_negativo.empty else st.success("Sin líneas con margen negativo.")


def render_ventas(usuario: str) -> None:
    if not require_permission("ventas.view", "🚫 No tienes acceso al módulo Ventas."):
        return

    st.session_state["perm_ventas_view"] = True
    st.session_state["perm_ventas_create"] = has_permission("ventas.create")
    st.session_state["perm_ventas_edit"] = has_permission("ventas.edit")
    st.session_state["perm_ventas_cancel"] = has_permission("ventas.cancel")
    st.session_state["perm_ventas_approve_discount"] = has_permission("ventas.approve_discount")

    st.session_state["ventas_readonly"] = not any([
        st.session_state["perm_ventas_create"],
        st.session_state["perm_ventas_edit"],
        st.session_state["perm_ventas_cancel"],
        st.session_state["perm_ventas_approve_discount"],
    ])

    try:
        from modules import ventas as ventas_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Ventas.")
        st.exception(exc)
        return

    st.title("💰 Ventas")
    st.caption("Mostrador, venta profesional, impresión, comprobantes, crédito, historial, resumen y alertas.")

    if st.session_state.get("ventas_readonly", False):
        st.info("Modo solo lectura: puedes consultar ventas, pero no registrar, editar ni anular.")

    tabs = st.tabs([
        "🖥️ POS rápido / Mostrador",
        "📝 Venta profesional",
        "🗂️ Cola de impresión",
        "🧾 Comprobantes / Tickets",
        "💳 Crédito / CxC por venta",
        "📜 Historial unificado",
        "📊 Resumen comercial",
        "🚨 Alertas de ventas",
    ])

    with tabs[0]:
        render_pos_rapido(usuario)
    with tabs[1]:
        ventas_module._render_tab_registro(usuario)
    with tabs[2]:
        render_cola_impresion(usuario)
    with tabs[3]:
        render_ticket_pos(usuario)
    with tabs[4]:
        ventas_module._render_tab_cuentas_por_cobrar(usuario)
    with tabs[5]:
        _render_historial_unificado()
        with st.expander("Historial profesional detallado"):
            ventas_module._render_tab_historial()
    with tabs[6]:
        ventas_module._render_tab_resumen()
    with tabs[7]:
        _render_alertas_ventas()
