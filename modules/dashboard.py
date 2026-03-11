from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from utils.calculations import calculate_daily_profit


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================


def _scalar(conn, query: str, params: tuple = ()) -> float:
    """
    Ejecuta una consulta SQL que devuelve un único valor numérico.
    """
    row = conn.execute(query, params).fetchone()

    if not row:
        return 0.0

    try:
        return float(row[0] or 0.0)
    except Exception:
        return 0.0


def _read_df(conn, query: str, default_columns: list[str]) -> pd.DataFrame:
    """
    Ejecuta una consulta SQL y retorna un DataFrame seguro.
    """
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame(columns=default_columns)


def _config_pct(conn, key: str, fallback: float) -> float:
    """
    Lee porcentaje de configuración y devuelve fallback si no existe.
    """
    row = conn.execute(
        "SELECT valor FROM configuracion WHERE parametro = ? LIMIT 1",
        (key,),
    ).fetchone()

    if not row:
        return fallback

    try:
        return float(row[0])
    except Exception:
        return fallback


# ============================================================
# DASHBOARD FINANCIERO
# ============================================================


def render_dashboard() -> None:
    st.subheader("📊 Dashboard Ejecutivo")
    st.caption(
        "Resumen general del negocio: ventas, gastos, comisiones, clientes e inventario."
    )

    try:
        with db_transaction() as conn:
            df_ventas = _read_df(
                conn,
                """
                SELECT
                    v.fecha,
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    v.metodo_pago,
                    v.total_usd
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                WHERE v.estado='registrada'
                """,
                ["fecha", "cliente", "metodo_pago", "total_usd"],
            )

            df_gastos = _read_df(
                conn,
                """
                SELECT fecha, monto_usd, categoria
                FROM gastos
                WHERE estado='activo'
                """,
                ["fecha", "monto_usd", "categoria"],
            )

            total_clientes = int(
                _scalar(
                    conn,
                    "SELECT COUNT(*) FROM clientes WHERE estado='activo'",
                )
            )

            df_inv_dash = _read_df(
                conn,
                """
                SELECT
                    nombre,
                    stock_actual,
                    precio_venta_usd,
                    stock_minimo
                FROM inventario
                WHERE estado='activo'
                """,
                ["nombre", "stock_actual", "precio_venta_usd", "stock_minimo"],
            )

            df_top = _read_df(
                conn,
                """
                SELECT
                    vd.descripcion,
                    SUM(vd.subtotal_usd) AS ventas,
                    SUM(vd.costo_unitario_usd * vd.cantidad) AS costos
                FROM ventas_detalle vd
                WHERE vd.estado='activo'
                GROUP BY vd.descripcion
                """,
                ["descripcion", "ventas", "costos"],
            )

            banco_perc = _config_pct(conn, "banco_perc", 0.5)
            kontigo_perc = _config_pct(conn, "kontigo_perc", 5.0)

    except Exception as e:
        st.error("Error cargando dashboard")
        st.exception(e)
        return

    # ------------------------------
    # Filtro temporal
    # ------------------------------
    rango = st.selectbox("Periodo", ["Hoy", "7 días", "30 días", "Todo"], index=2)
    desde = None
    if rango != "Todo":
        dias = {"Hoy": 0, "7 días": 7, "30 días": 30}[rango]
        desde = pd.Timestamp.now().normalize() - pd.Timedelta(days=dias)

    dfv = df_ventas.copy()
    dfg = df_gastos.copy()

    if not dfv.empty:
        dfv["fecha"] = pd.to_datetime(dfv["fecha"], errors="coerce")
        dfv = dfv.dropna(subset=["fecha"])
        if desde is not None:
            dfv = dfv[dfv["fecha"] >= desde]

    if not dfg.empty:
        dfg["fecha"] = pd.to_datetime(dfg["fecha"], errors="coerce")
        dfg = dfg.dropna(subset=["fecha"])
        if desde is not None:
            dfg = dfg[dfg["fecha"] >= desde]

    ventas_total = float(dfv["total_usd"].sum()) if not dfv.empty else 0.0
    gastos_total = float(dfg["monto_usd"].sum()) if not dfg.empty else 0.0

    comision_est = 0.0
    if not dfv.empty:
        ventas_bancarias = dfv[
            dfv["metodo_pago"].str.contains(
                "transferencia|pago móvil|zelle|binance",
                case=False,
                na=False,
            )
        ]
        ventas_kontigo = dfv[dfv["metodo_pago"].str.contains("kontigo", case=False, na=False)]
        if not ventas_bancarias.empty:
            comision_est += float(ventas_bancarias["total_usd"].sum() * (banco_perc / 100))
        if not ventas_kontigo.empty:
            comision_est += float(ventas_kontigo["total_usd"].sum() * (kontigo_perc / 100))

    utilidad = calculate_daily_profit(ventas_total, gastos_total, comision_est)

    ini_mes = pd.Timestamp.now().replace(day=1).normalize()
    ventas_mes = 0.0
    gastos_mes = 0.0
    if not df_ventas.empty:
        dvm = df_ventas.copy()
        dvm["fecha"] = pd.to_datetime(dvm["fecha"], errors="coerce")
        ventas_mes = float(dvm[dvm["fecha"] >= ini_mes]["total_usd"].sum())
    if not df_gastos.empty:
        dgm = df_gastos.copy()
        dgm["fecha"] = pd.to_datetime(dgm["fecha"], errors="coerce")
        gastos_mes = float(dgm[dgm["fecha"] >= ini_mes]["monto_usd"].sum())

    utilidad_neta_mes = ventas_mes - gastos_mes

    capital_inv = 0.0
    stock_bajo = 0
    if not df_inv_dash.empty:
        capital_inv = float((df_inv_dash["stock_actual"] * df_inv_dash["precio_venta_usd"]).sum())
        stock_bajo = int((df_inv_dash["stock_actual"] <= df_inv_dash["stock_minimo"]).sum())

    costos_fijos_hoy = (
        float(dfg[dfg["fecha"].dt.date == pd.Timestamp.now().date()]["monto_usd"].sum())
        if (not dfg.empty and "fecha" in dfg.columns)
        else 0.0
    )
    punto_equilibrio_restante = max(0.0, costos_fijos_hoy - ventas_total)

    # ============================================================
    # MÉTRICAS PRINCIPALES
    # ============================================================
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Utilidad Neta del Mes", f"$ {utilidad_neta_mes:,.2f}")
    kpi2.metric("Eficiencia Producción (comisiones)", f"$ {comision_est:,.2f}")
    kpi3.metric("Alerta Insumos Críticos", stock_bajo)
    st.divider()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 Ventas", f"${ventas_total:,.2f}")
    c2.metric("💸 Gastos", f"${gastos_total:,.2f}")
    c3.metric("🏦 Comisiones", f"${comision_est:,.2f}")
    c4.metric("📈 Utilidad", f"${utilidad:,.2f}")
    c5.metric("👥 Clientes", total_clientes)
    c6.metric("🚨 Ítems Mínimo", stock_bajo)

    st.divider()

    dpe1, dpe2 = st.columns(2)
    dpe1.metric("Punto de Equilibrio (faltante hoy)", f"$ {punto_equilibrio_restante:,.2f}")
    dpe2.metric("Costos fijos hoy", f"$ {costos_fijos_hoy:,.2f}")

    if not df_top.empty:
        top3 = df_top.copy()
        top3["costos"] = top3["costos"].fillna(0.0)
        top3["utilidad_neta"] = top3["ventas"] - top3["costos"]
        top3 = top3.sort_values("utilidad_neta", ascending=False).head(3)
        st.subheader("🏆 Ranking de Rentabilidad Neta por producto")
        st.dataframe(top3, use_container_width=True, hide_index=True)

    st.subheader("🚦 Monitor de Insumos")
    if not df_inv_dash.empty:
        monitor = df_inv_dash.copy()
        monitor["nivel"] = np.where(
            monitor["stock_actual"] <= monitor["stock_minimo"],
            "🔴 Crítico",
            np.where(
                monitor["stock_actual"] <= (monitor["stock_minimo"] * 1.5),
                "🟡 Bajo",
                "🟢 OK",
            ),
        )
        monitor["valor"] = (
            pd.to_numeric(monitor["stock_actual"], errors="coerce").fillna(0.0)
            * pd.to_numeric(monitor["precio_venta_usd"], errors="coerce").fillna(0.0)
        )
        monitor["estado"] = np.where(
            monitor["stock_actual"] <= monitor["stock_minimo"],
            "Crítico",
            "Operativo",
        )
        st.dataframe(
            monitor[
                ["nombre", "stock_actual", "valor", "estado", "stock_minimo", "nivel"]
            ].head(20),
            use_container_width=True,
            hide_index=True,
        )

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("📆 Ventas por día")
        if dfv.empty:
            st.info("No hay ventas registradas en el periodo.")
        else:
            d1 = dfv.copy()
            d1["dia"] = d1["fecha"].dt.date.astype(str)
            resumen_v = d1.groupby("dia", as_index=False)["total_usd"].sum()
            fig_v = px.line(resumen_v, x="dia", y="total_usd", markers=True)
            fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
            st.plotly_chart(fig_v, use_container_width=True)

    with col_b:
        st.subheader("📉 Gastos por día")
        if dfg.empty:
            st.info("No hay gastos registrados en el periodo.")
        else:
            d2 = dfg.copy()
            d2["dia"] = d2["fecha"].dt.date.astype(str)
            resumen_g = d2.groupby("dia", as_index=False)["monto_usd"].sum()
            fig_g = px.bar(resumen_g, x="dia", y="monto_usd")
            fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
            st.plotly_chart(fig_g, use_container_width=True)

    c_a, c_b = st.columns(2)
    with c_a:
        st.subheader("💳 Ventas por método")
        if dfv.empty:
            st.info("Sin datos para métodos de pago.")
        else:
            vm = (
                dfv.groupby("metodo_pago", as_index=False)["total_usd"]
                .sum()
                .sort_values("total_usd", ascending=False)
            )
            fig_m = px.pie(vm, names="metodo_pago", values="total_usd")
            st.plotly_chart(fig_m, use_container_width=True)

    with c_b:
        st.subheader("🏆 Top clientes")
        if dfv.empty or "cliente" not in dfv.columns:
            st.info("Sin datos de clientes en el periodo.")
        else:
            topc = (
                dfv.groupby("cliente", as_index=False)["total_usd"]
                .sum()
                .sort_values("total_usd", ascending=False)
                .head(10)
            )
            st.dataframe(topc, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📦 Estado del Inventario")
    st.metric("💼 Capital inmovilizado en inventario", f"${capital_inv:,.2f}")
