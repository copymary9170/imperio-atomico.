from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _safe_df(sql: str, table: str, params: tuple = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _safe_count(table: str, where: str = "") -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0
            sql = f"SELECT COUNT(*) AS total FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return 0


def _safe_sum(table: str, column: str, where: str = "") -> float:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0.0
            sql = f"SELECT COALESCE(SUM({column}),0) AS total FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
            return float(row["total"] if row else 0)
    except Exception:
        return 0.0


def _download_button(df: pd.DataFrame, nombre: str) -> None:
    if df.empty:
        return
    st.download_button(
        "⬇️ Descargar CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{nombre}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"download_{nombre}",
    )


def _date_filter(prefix: str) -> tuple[date, date]:
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Desde", value=date.today() - timedelta(days=30), key=f"{prefix}_desde")
    fin = c2.date_input("Hasta", value=date.today(), key=f"{prefix}_hasta")
    return inicio, fin


def _render_caja_punto() -> None:
    st.subheader("💵 Reportes de caja y punto")
    inicio, fin = _date_filter("reportes_caja")
    params = (str(inicio), str(fin))

    movimientos = _safe_df(
        """
        SELECT fecha, tipo, origen, descripcion, monto_usd, metodo_pago, usuario, estado
        FROM movimientos_tesoreria
        WHERE date(fecha) BETWEEN date(?) AND date(?)
        ORDER BY fecha DESC
        """,
        "movimientos_tesoreria",
        params,
    )

    ingresos = 0.0 if movimientos.empty else float(pd.to_numeric(movimientos[movimientos["tipo"].eq("ingreso")]["monto_usd"], errors="coerce").fillna(0).sum())
    egresos = 0.0 if movimientos.empty else float(pd.to_numeric(movimientos[movimientos["tipo"].eq("egreso")]["monto_usd"], errors="coerce").fillna(0).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos", f"$ {ingresos:,.2f}")
    c2.metric("Egresos", f"$ {egresos:,.2f}")
    c3.metric("Saldo", f"$ {ingresos - egresos:,.2f}")
    c4.metric("Movimientos", len(movimientos))

    if not movimientos.empty and "metodo_pago" in movimientos.columns:
        resumen_pago = movimientos.groupby(["metodo_pago", "tipo"], dropna=False)["monto_usd"].sum().reset_index()
        st.markdown("#### Resumen por método de pago")
        st.dataframe(resumen_pago, use_container_width=True, hide_index=True)

    st.markdown("#### Movimientos de caja / punto")
    st.dataframe(movimientos, use_container_width=True, hide_index=True) if not movimientos.empty else st.info("No hay movimientos en el período.")
    _download_button(movimientos, "reporte_caja_punto")


def _render_historico() -> None:
    st.subheader("📚 Reporte histórico")
    inicio, fin = _date_filter("reportes_historico")
    params = (str(inicio), str(fin))

    ventas = _safe_df("SELECT * FROM ventas WHERE date(fecha) BETWEEN date(?) AND date(?) ORDER BY fecha DESC", "ventas", params)
    cotizaciones = _safe_df("SELECT * FROM cotizaciones WHERE date(fecha) BETWEEN date(?) AND date(?) ORDER BY fecha DESC", "cotizaciones", params)
    compras = _safe_df("SELECT * FROM historial_compras WHERE date(fecha) BETWEEN date(?) AND date(?) ORDER BY fecha DESC", "historial_compras", params)

    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas históricas", len(ventas))
    c2.metric("Cotizaciones históricas", len(cotizaciones))
    c3.metric("Compras históricas", len(compras))

    tabs = st.tabs(["Ventas", "Cotizaciones", "Compras"])
    with tabs[0]:
        st.dataframe(ventas, use_container_width=True, hide_index=True) if not ventas.empty else st.info("Sin ventas en el período.")
        _download_button(ventas, "historico_ventas")
    with tabs[1]:
        st.dataframe(cotizaciones, use_container_width=True, hide_index=True) if not cotizaciones.empty else st.info("Sin cotizaciones en el período.")
        _download_button(cotizaciones, "historico_cotizaciones")
    with tabs[2]:
        st.dataframe(compras, use_container_width=True, hide_index=True) if not compras.empty else st.info("Sin compras en el período.")
        _download_button(compras, "historico_compras")


def _render_administrativo() -> None:
    st.subheader("🗂️ Reporte administrativo")
    clientes = _safe_df("SELECT * FROM clientes ORDER BY id DESC LIMIT 1000", "clientes")
    proveedores = _safe_df("SELECT * FROM proveedores ORDER BY id DESC LIMIT 1000", "proveedores")
    inventario = _safe_df("SELECT * FROM inventario ORDER BY id DESC LIMIT 1000", "inventario")
    cxc = _safe_df("SELECT * FROM cuentas_por_cobrar ORDER BY id DESC LIMIT 1000", "cuentas_por_cobrar")
    cxp = _safe_df("SELECT * FROM cuentas_por_pagar_proveedores ORDER BY id DESC LIMIT 1000", "cuentas_por_pagar_proveedores")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes", len(clientes))
    c2.metric("Proveedores", len(proveedores))
    c3.metric("Inventario", len(inventario))
    c4.metric("Cuentas", len(cxc) + len(cxp))

    tabs = st.tabs(["Clientes", "Proveedores", "Inventario", "CxC", "CxP"])
    with tabs[0]: st.dataframe(clientes, use_container_width=True, hide_index=True) if not clientes.empty else st.info("Sin clientes.")
    with tabs[1]: st.dataframe(proveedores, use_container_width=True, hide_index=True) if not proveedores.empty else st.info("Sin proveedores.")
    with tabs[2]: st.dataframe(inventario, use_container_width=True, hide_index=True) if not inventario.empty else st.info("Sin inventario.")
    with tabs[3]: st.dataframe(cxc, use_container_width=True, hide_index=True) if not cxc.empty else st.info("Sin cuentas por cobrar.")
    with tabs[4]: st.dataframe(cxp, use_container_width=True, hide_index=True) if not cxp.empty else st.info("Sin cuentas por pagar.")


def _render_consolidados() -> None:
    st.subheader("📊 Reportes consolidados")
    total_ventas = _safe_sum("movimientos_tesoreria", "monto_usd", "tipo='ingreso' AND estado='confirmado'")
    total_gastos = _safe_sum("movimientos_tesoreria", "monto_usd", "tipo='egreso' AND estado='confirmado'")
    clientes = _safe_count("clientes")
    proveedores = _safe_count("proveedores")
    inventario = _safe_count("inventario")
    cotizaciones = _safe_count("cotizaciones")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas totales", f"$ {total_ventas:,.2f}")
    c2.metric("Gastos totales", f"$ {total_gastos:,.2f}")
    c3.metric("Utilidad bruta", f"$ {total_ventas - total_gastos:,.2f}")
    c4.metric("Cotizaciones", cotizaciones)

    c5, c6, c7 = st.columns(3)
    c5.metric("Clientes", clientes)
    c6.metric("Proveedores", proveedores)
    c7.metric("Items inventario", inventario)

    consolidado = pd.DataFrame([
        {"indicador": "Ventas totales", "valor": total_ventas},
        {"indicador": "Gastos totales", "valor": total_gastos},
        {"indicador": "Utilidad bruta", "valor": total_ventas - total_gastos},
        {"indicador": "Clientes", "valor": clientes},
        {"indicador": "Proveedores", "valor": proveedores},
        {"indicador": "Inventario", "valor": inventario},
        {"indicador": "Cotizaciones", "valor": cotizaciones},
    ])
    st.dataframe(consolidado, use_container_width=True, hide_index=True)
    _download_button(consolidado, "reporte_consolidado")


def render_reportes(usuario: str = "Sistema") -> None:
    st.title("📊 Reportes")
    st.caption("Reportes de caja, punto de venta, histórico, administración y consolidados.")

    tab_caja, tab_hist, tab_admin, tab_cons = st.tabs([
        "💵 Caja y punto",
        "📚 Histórico",
        "🗂️ Administrativo",
        "📊 Consolidados",
    ])

    with tab_caja:
        _render_caja_punto()
    with tab_hist:
        _render_historico()
    with tab_admin:
        _render_administrativo()
    with tab_cons:
        _render_consolidados()
