from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction

ESTADOS_FINALES = {"Entregado", "Devuelto", "Cancelado", "Completado", "Cerrado"}


def _table_exists(conn, table_name: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None
    except Exception:
        return False


def _columns(conn, table_name: str) -> set[str]:
    try:
        if not _table_exists(conn, table_name):
            return set()
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except Exception:
        return set()


def _safe_scalar(sql: str, params: tuple = (), default: float = 0.0) -> float:
    try:
        with db_transaction() as conn:
            row = conn.execute(sql, params).fetchone()
        return float((row[0] if row else default) or 0)
    except Exception:
        return default


def _safe_count(table: str, where: str | None = None, needed: set[str] | None = None) -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0
            if needed and not needed.issubset(_columns(conn, table)):
                return 0
            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def _safe_df(table: str, columns: list[str], where: str | None = None, needed: set[str] | None = None, limit: int = 100) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            existing = _columns(conn, table)
            if needed and not needed.issubset(existing):
                return pd.DataFrame()
            selected = [col for col in columns if col in existing]
            if not selected:
                return pd.DataFrame()
            sql = f"SELECT {', '.join(selected)} FROM {table}"
            if where:
                sql += f" WHERE {where}"
            order_col = "id" if "id" in existing else selected[0]
            sql += f" ORDER BY {order_col} DESC LIMIT {int(limit)}"
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def _today_sales(today: str) -> tuple[float, int]:
    total = _safe_scalar("SELECT SUM(total_usd) FROM ventas WHERE date(fecha)=date(?)", (today,), 0.0)
    count = _safe_count("ventas", "date(fecha)=date('now')", {"fecha"})
    if total == 0:
        total = _safe_scalar("SELECT SUM(total_usd) FROM comprobantes_pos WHERE date(fecha)=date(?)", (today,), 0.0)
        count = max(count, _safe_count("comprobantes_pos", "date(fecha)=date('now')", {"fecha"}))
    return total, count


def _cash_today(today: str) -> dict[str, float]:
    return {
        "efectivo": _safe_scalar("SELECT SUM(monto_usd) FROM movimientos_tesoreria WHERE date(fecha)=date(?) AND tipo='ingreso' AND metodo_pago='efectivo' AND estado='confirmado'", (today,)),
        "transferencia": _safe_scalar("SELECT SUM(monto_usd) FROM movimientos_tesoreria WHERE date(fecha)=date(?) AND tipo='ingreso' AND metodo_pago='transferencia' AND estado='confirmado'", (today,)),
        "zelle": _safe_scalar("SELECT SUM(monto_usd) FROM movimientos_tesoreria WHERE date(fecha)=date(?) AND tipo='ingreso' AND metodo_pago='zelle' AND estado='confirmado'", (today,)),
        "binance": _safe_scalar("SELECT SUM(monto_usd) FROM movimientos_tesoreria WHERE date(fecha)=date(?) AND tipo='ingreso' AND metodo_pago='binance' AND estado='confirmado'", (today,)),
        "egresos": _safe_scalar("SELECT SUM(monto_usd) FROM movimientos_tesoreria WHERE date(fecha)=date(?) AND tipo='egreso' AND estado='confirmado'", (today,)),
    }


def _ot_stage(row: pd.Series) -> str:
    estado = str(row.get("estado") or "")
    if estado in ESTADOS_FINALES:
        return estado
    if int(row.get("bloqueo_entrega") or 0) and estado in {"Listo para despacho", "Despachado"}:
        return "Bloqueada por saldo"
    if int(row.get("bloqueo_produccion") or 0):
        return "Bloqueada por diseño"
    if estado in {"Diseño aprobado", "En producción", "Calidad"}:
        return "Producción"
    if estado in {"Listo para despacho", "Despachado"}:
        return "Entrega"
    return "Activa"


def _global_order_status() -> pd.DataFrame:
    ots = _safe_df(
        "ordenes_trabajo",
        [
            "id", "fecha_creacion", "codigo", "cliente", "tipo_trabajo", "prioridad", "descripcion",
            "estado", "estado_pago", "precio_venta_usd", "anticipo_usd", "saldo_pendiente_usd",
            "bloqueo_produccion", "bloqueo_entrega", "costo_real_usd", "margen_real_usd", "fecha_promesa",
            "responsable", "despacho_id", "diseno_id", "bom_id",
        ],
        None,
        None,
        250,
    )
    if not ots.empty:
        out = ots.copy()
        out["pedido"] = out.get("codigo", pd.Series(dtype=str)).fillna("").astype(str)
        out["fecha"] = out.get("fecha_creacion", "")
        out["etapa"] = out.apply(_ot_stage, axis=1)
        return out[
            [
                "pedido", "fecha", "cliente", "tipo_trabajo", "prioridad", "estado", "etapa",
                "estado_pago", "precio_venta_usd", "anticipo_usd", "saldo_pendiente_usd",
                "costo_real_usd", "margen_real_usd", "fecha_promesa", "responsable",
            ]
        ].head(200)

    tickets = _safe_df("comprobantes_pos", ["id", "fecha", "cliente", "venta_id", "referencia", "total_usd", "estado"], None, None, 200)
    if tickets.empty:
        return pd.DataFrame()
    rows = []
    for _, t in tickets.iterrows():
        rows.append({
            "pedido": f"TICKET-{int(t['id'])}",
            "fecha": t.get("fecha"),
            "cliente": str(t.get("cliente") or "Cliente General"),
            "tipo_trabajo": "POS",
            "prioridad": "Normal",
            "estado": t.get("estado") or "Registrado",
            "etapa": "Vendido / comprobante",
            "estado_pago": "",
            "precio_venta_usd": float(t.get("total_usd") or 0),
            "anticipo_usd": "",
            "saldo_pendiente_usd": "",
            "costo_real_usd": "",
            "margen_real_usd": "",
            "fecha_promesa": "",
            "responsable": "",
        })
    return pd.DataFrame(rows)


def _download_csv(label: str, df: pd.DataFrame, prefix: str) -> None:
    if df.empty:
        return
    st.download_button(label, data=df.to_csv(index=False).encode("utf-8-sig"), file_name=f"{prefix}_{date.today().isoformat()}.csv", mime="text/csv", use_container_width=True)


def render_modo_supervisor(usuario: str = "Sistema") -> None:
    st.title("🧑‍💼 Modo Supervisor")
    st.caption("Vista diaria basada en Órdenes de Trabajo, caja, pendientes y auditoría reciente.")

    today = date.today().isoformat()
    ventas_total, ventas_count = _today_sales(today)
    caja = _cash_today(today)
    neto_caja = caja["efectivo"] + caja["transferencia"] + caja["zelle"] + caja["binance"] - caja["egresos"]

    ot_abiertas = _safe_count("ordenes_trabajo", "estado NOT IN ('Entregado','Cancelado')", {"estado"})
    ot_saldo = _safe_count("ordenes_trabajo", "saldo_pendiente_usd > 0", {"saldo_pendiente_usd"})
    ot_diseno = _safe_count("ordenes_trabajo", "bloqueo_produccion=1", {"bloqueo_produccion"})
    ot_sin_bom = _safe_count("ordenes_trabajo", "COALESCE(bom_id,0)=0 AND tipo_trabajo NOT IN ('Bazar','Copias')", {"bom_id", "tipo_trabajo"})
    disenos_bloqueados = _safe_count("disenos_aprobaciones", "bloqueo_produccion=1", {"bloqueo_produccion"})
    despachos_abiertos = _safe_count("despachos_entregas", "estado NOT IN ('Entregado', 'Devuelto')", {"estado"})
    caja_diferencias = _safe_count("cierres_caja_turnos", "estado='Con diferencia'", {"estado"})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas hoy", f"${ventas_total:,.2f}", delta=f"{ventas_count} registro(s)")
    m2.metric("Caja neta hoy", f"${neto_caja:,.2f}")
    m3.metric("OT abiertas", ot_abiertas, delta=f"Saldo pendiente: {ot_saldo}")
    m4.metric("Bloqueos", ot_diseno + disenos_bloqueados + caja_diferencias, delta=f"Sin BOM: {ot_sin_bom}")

    if ot_saldo or ot_diseno or disenos_bloqueados or caja_diferencias:
        st.error("Hay bloqueos críticos: saldo pendiente, diseño sin aprobar, diferencia de caja o producción bloqueada.")
    elif despachos_abiertos:
        st.warning("Hay despachos abiertos pendientes de seguimiento.")
    else:
        st.success("Operación sin bloqueos críticos detectados.")

    tab_pedidos, tab_caja, tab_pendientes, tab_auditoria = st.tabs(["Estado global OT", "Caja del día", "Pendientes por área", "Auditoría reciente"])

    with tab_pedidos:
        pedidos = _global_order_status()
        if pedidos.empty:
            st.info("No hay órdenes/tickets recientes para construir estado global.")
        else:
            etapa_filter = st.selectbox("Filtrar etapa", ["Todas"] + sorted(pedidos["etapa"].dropna().astype(str).unique().tolist()))
            vista = pedidos if etapa_filter == "Todas" else pedidos[pedidos["etapa"].astype(str).eq(etapa_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            _download_csv("⬇️ Descargar estado global CSV", vista, "estado_global_ot")

    with tab_caja:
        caja_df = pd.DataFrame([
            {"metodo": "efectivo", "monto_usd": caja["efectivo"]},
            {"metodo": "transferencia", "monto_usd": caja["transferencia"]},
            {"metodo": "zelle", "monto_usd": caja["zelle"]},
            {"metodo": "binance", "monto_usd": caja["binance"]},
            {"metodo": "egresos", "monto_usd": -abs(caja["egresos"])},
            {"metodo": "neto", "monto_usd": neto_caja},
        ])
        st.dataframe(caja_df, use_container_width=True, hide_index=True)
        st.bar_chart(caja_df.set_index("metodo")["monto_usd"])
        _download_csv("⬇️ Descargar caja del día CSV", caja_df, "caja_dia")

    with tab_pendientes:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### OT con saldo pendiente")
            df = _safe_df("ordenes_trabajo", ["id", "codigo", "cliente", "estado", "estado_pago", "saldo_pendiente_usd"], "saldo_pendiente_usd > 0", {"saldo_pendiente_usd"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin OT con saldo pendiente.")
            st.markdown("#### OT bloqueadas por diseño")
            df = _safe_df("ordenes_trabajo", ["id", "codigo", "cliente", "estado", "bloqueo_produccion"], "bloqueo_produccion=1", {"bloqueo_produccion"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin OT bloqueadas por diseño.")
        with col2:
            st.markdown("#### Despachos abiertos")
            df = _safe_df("despachos_entregas", ["id", "fecha_creacion", "cliente", "tipo_entrega", "estado", "numero_guia"], "estado NOT IN ('Entregado', 'Devuelto')", {"estado"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin despachos abiertos.")
            st.markdown("#### Cierres con diferencia")
            df = _safe_df("cierres_caja_turnos", ["id", "fecha_operativa", "turno", "cajero", "diferencia_total_usd", "estado"], "estado='Con diferencia'", {"estado"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin cierres con diferencia.")

    with tab_auditoria:
        audit = _safe_df("audit_log", ["id", "fecha", "usuario", "modulo", "accion", "entidad", "entidad_id", "detalle"], None, None, 100)
        if audit.empty:
            st.info("Todavía no hay eventos de auditoría.")
        else:
            st.dataframe(audit, use_container_width=True, hide_index=True)
            _download_csv("⬇️ Descargar auditoría reciente CSV", audit, "auditoria_supervisor")
