from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.audit_service import log_audit_event


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
        if not row:
            return default
        value = row[0]
        return float(value or 0)
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
    total = _safe_scalar(
        "SELECT SUM(total_usd) FROM ventas WHERE date(fecha)=date(?)",
        (today,),
        0.0,
    )
    count = _safe_count("ventas", "date(fecha)=date('now')", {"fecha"})
    if total == 0:
        total = _safe_scalar(
            "SELECT SUM(total_usd) FROM comprobantes_pos WHERE date(fecha)=date(?)",
            (today,),
            0.0,
        )
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


def _stage_label(row: dict[str, object]) -> str:
    if str(row.get("despacho_estado") or "") in {"Entregado", "Devuelto"}:
        return "Entrega finalizada"
    if row.get("despacho_estado"):
        return "En despacho"
    if str(row.get("diseno_estado") or "") in {"Aprobado por cliente", "Listo para imprimir", "Listo para sublimar", "Listo para cortar"}:
        return "Diseño aprobado / producción"
    if row.get("diseno_estado"):
        return "Diseño pendiente"
    if row.get("cola_estado"):
        return "Cola impresión"
    if row.get("ticket_id"):
        return "Vendido / comprobante"
    return "Registrado"


def _global_order_status() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    tickets = _safe_df("comprobantes_pos", ["id", "fecha", "cliente", "telefono", "venta_id", "referencia", "total_usd", "estado"], None, None, 250)
    ventas = _safe_df("ventas", ["id", "fecha", "cliente", "cliente_nombre", "total_usd", "estado"], None, None, 250)
    disenos = _safe_df("disenos_aprobaciones", ["id", "fecha_creacion", "cliente", "venta_id", "referencia", "nombre_diseno", "estado", "bloqueo_produccion"], None, None, 250)
    despachos = _safe_df("despachos_entregas", ["id", "fecha_creacion", "cliente", "venta_id", "referencia", "tipo_entrega", "estado", "numero_guia"], None, None, 250)
    cola = _safe_df("cola_impresion", ["id", "fecha_creacion", "cliente", "venta_id", "referencia", "archivo_nombre", "estado"], None, None, 250)

    if not tickets.empty:
        for _, t in tickets.iterrows():
            venta_id = t.get("venta_id")
            referencia = str(t.get("referencia") or "")
            cliente = str(t.get("cliente") or "Cliente General")
            related_diseno = pd.DataFrame()
            related_despacho = pd.DataFrame()
            related_cola = pd.DataFrame()
            if not disenos.empty:
                mask = disenos.get("cliente", pd.Series(dtype=str)).astype(str).eq(cliente)
                if venta_id and "venta_id" in disenos.columns:
                    mask = mask | disenos["venta_id"].fillna(0).astype(int).eq(int(venta_id))
                if referencia and "referencia" in disenos.columns:
                    mask = mask | disenos["referencia"].astype(str).eq(referencia)
                related_diseno = disenos[mask]
            if not despachos.empty:
                mask = despachos.get("cliente", pd.Series(dtype=str)).astype(str).eq(cliente)
                if venta_id and "venta_id" in despachos.columns:
                    mask = mask | despachos["venta_id"].fillna(0).astype(int).eq(int(venta_id))
                if referencia and "referencia" in despachos.columns:
                    mask = mask | despachos["referencia"].astype(str).eq(referencia)
                related_despacho = despachos[mask]
            if not cola.empty:
                mask = cola.get("cliente", pd.Series(dtype=str)).astype(str).eq(cliente)
                if venta_id and "venta_id" in cola.columns:
                    mask = mask | cola["venta_id"].fillna(0).astype(int).eq(int(venta_id))
                if referencia and "referencia" in cola.columns:
                    mask = mask | cola["referencia"].astype(str).eq(referencia)
                related_cola = cola[mask]

            row = {
                "pedido": f"TICKET-{int(t['id'])}",
                "fecha": t.get("fecha"),
                "cliente": cliente,
                "total_usd": float(t.get("total_usd") or 0),
                "ticket_id": int(t["id"]),
                "venta_id": venta_id,
                "cola_estado": related_cola.iloc[0].get("estado") if not related_cola.empty else "",
                "diseno_estado": related_diseno.iloc[0].get("estado") if not related_diseno.empty else "",
                "bloqueo_diseno": int(related_diseno.iloc[0].get("bloqueo_produccion") or 0) if not related_diseno.empty else 0,
                "despacho_estado": related_despacho.iloc[0].get("estado") if not related_despacho.empty else "",
                "guia": related_despacho.iloc[0].get("numero_guia") if not related_despacho.empty else "",
            }
            row["etapa"] = _stage_label(row)
            rows.append(row)

    if not rows and not ventas.empty:
        for _, v in ventas.iterrows():
            cliente = str(v.get("cliente_nombre") or v.get("cliente") or "Cliente")
            row = {
                "pedido": f"VENTA-{int(v['id'])}",
                "fecha": v.get("fecha"),
                "cliente": cliente,
                "total_usd": float(v.get("total_usd") or 0),
                "ticket_id": "",
                "venta_id": int(v["id"]),
                "cola_estado": "",
                "diseno_estado": "",
                "bloqueo_diseno": 0,
                "despacho_estado": "",
                "guia": "",
                "etapa": "Vendido",
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.head(200)


def _download_csv(label: str, df: pd.DataFrame, prefix: str) -> None:
    if df.empty:
        return
    st.download_button(
        label,
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{prefix}_{date.today().isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_modo_supervisor(usuario: str = "Sistema") -> None:
    st.title("🧑‍💼 Modo Supervisor")
    st.caption("Vista ejecutiva diaria: ventas, caja, producción, alertas, pedidos y auditoría reciente.")

    today = date.today().isoformat()
    ventas_total, ventas_count = _today_sales(today)
    caja = _cash_today(today)
    neto_caja = caja["efectivo"] + caja["transferencia"] + caja["zelle"] + caja["binance"] - caja["egresos"]

    disenos_bloqueados = _safe_count("disenos_aprobaciones", "bloqueo_produccion=1", {"bloqueo_produccion"})
    despachos_abiertos = _safe_count("despachos_entregas", "estado NOT IN ('Entregado', 'Devuelto')", {"estado"})
    cola_pendiente = _safe_count("cola_impresion", "estado NOT IN ('Completado', 'Cancelado', 'Entregado')", {"estado"})
    caja_diferencias = _safe_count("cierres_caja_turnos", "estado='Con diferencia'", {"estado"})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas hoy", f"${ventas_total:,.2f}", delta=f"{ventas_count} registro(s)")
    m2.metric("Caja neta hoy", f"${neto_caja:,.2f}")
    m3.metric("Producción pendiente", cola_pendiente + disenos_bloqueados, delta=f"Diseños bloqueados: {disenos_bloqueados}")
    m4.metric("Despachos abiertos", despachos_abiertos, delta=f"Cierres con diferencia: {caja_diferencias}")

    if disenos_bloqueados or caja_diferencias:
        st.error("Hay bloqueos críticos: revisa diseños sin aprobación o cierres con diferencia.")
    elif cola_pendiente or despachos_abiertos:
        st.warning("Hay pendientes operativos por atender hoy.")
    else:
        st.success("Operación sin bloqueos críticos detectados.")

    tab_pedidos, tab_caja, tab_pendientes, tab_auditoria = st.tabs([
        "Estado global de pedidos",
        "Caja del día",
        "Pendientes por área",
        "Auditoría reciente",
    ])

    with tab_pedidos:
        pedidos = _global_order_status()
        if pedidos.empty:
            st.info("No hay pedidos/ventas recientes para construir estado global.")
        else:
            etapa_filter = st.selectbox("Filtrar etapa", ["Todas"] + sorted(pedidos["etapa"].dropna().astype(str).unique().tolist()))
            vista = pedidos if etapa_filter == "Todas" else pedidos[pedidos["etapa"].astype(str).eq(etapa_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            _download_csv("⬇️ Descargar estado global CSV", vista, "estado_global_pedidos")

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
            st.markdown("#### Diseños bloqueados")
            df = _safe_df("disenos_aprobaciones", ["id", "fecha_creacion", "cliente", "nombre_diseno", "estado", "bloqueo_produccion"], "bloqueo_produccion=1", {"bloqueo_produccion"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin diseños bloqueados.")
            st.markdown("#### Cola impresión")
            df = _safe_df("cola_impresion", ["id", "fecha_creacion", "cliente", "archivo_nombre", "estado"], "estado NOT IN ('Completado', 'Cancelado', 'Entregado')", {"estado"}, 100)
            st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin cola pendiente.")
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

    log_audit_event(usuario=usuario, modulo="Supervisor", accion="ver_modo_supervisor", entidad="dashboard", detalle="Modo Supervisor consultado")
