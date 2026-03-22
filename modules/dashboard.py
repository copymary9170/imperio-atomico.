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



def _safe_pct_change(actual: float, anterior: float) -> float | None:
    """Calcula la variación porcentual evitando divisiones inválidas."""
    if abs(anterior) < 1e-9:
        return None
    return ((actual - anterior) / anterior) * 100



def _fmt_delta(actual: float, anterior: float, prefix: str = "vs. periodo anterior") -> str:
    """Genera un texto compacto de variación para métricas."""
    delta = _safe_pct_change(actual, anterior)
    if delta is None:
        return f"{prefix}: sin base"
    return f"{delta:+.1f}% {prefix}"



def _health_status(ventas_total: float, utilidad: float, stock_bajo: int) -> tuple[str, str]:
    """Resume el estado operativo general del negocio."""
    if ventas_total <= 0:
        return "🔴 Atención", "No hay ventas en el periodo seleccionado."
    if stock_bajo >= 5 or utilidad < 0:
        return "🟡 Riesgo controlado", "Hay presión en rentabilidad o insumos críticos."
    return "🟢 Saludable", "Ventas activas, utilidad positiva y stock bajo control."


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
    now = pd.Timestamp.now()
    hoy = now.normalize()
    if rango != "Todo":
        dias = {"Hoy": 0, "7 días": 7, "30 días": 30}[rango]
        desde = hoy - pd.Timedelta(days=dias)

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

    ini_mes = now.replace(day=1).normalize()
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
    cobertura_stock_dias = 0.0
    if not df_inv_dash.empty:
        capital_inv = float((df_inv_dash["stock_actual"] * df_inv_dash["precio_venta_usd"]).sum())
        stock_bajo = int((df_inv_dash["stock_actual"] <= df_inv_dash["stock_minimo"]).sum())
        cobertura_stock_dias = float(df_inv_dash["stock_actual"].sum()) / max(len(df_inv_dash), 1)

    costos_fijos_hoy = (
        float(dfg[dfg["fecha"].dt.date == hoy.date()]["monto_usd"].sum())
        if (not dfg.empty and "fecha" in dfg.columns)
        else 0.0
    )
    punto_equilibrio_restante = max(0.0, costos_fijos_hoy - ventas_total)

    ventas_previas = 0.0
    gastos_previos = 0.0
    if desde is not None:
        fin_periodo_anterior = desde
        inicio_periodo_anterior = desde - (hoy - desde + pd.Timedelta(days=1))

        if not df_ventas.empty:
            dprev_v = df_ventas.copy()
            dprev_v["fecha"] = pd.to_datetime(dprev_v["fecha"], errors="coerce")
            ventas_previas = float(
                dprev_v[
                    (dprev_v["fecha"] >= inicio_periodo_anterior)
                    & (dprev_v["fecha"] < fin_periodo_anterior)
                ]["total_usd"].sum()
            )
        if not df_gastos.empty:
            dprev_g = df_gastos.copy()
            dprev_g["fecha"] = pd.to_datetime(dprev_g["fecha"], errors="coerce")
            gastos_previos = float(
                dprev_g[
                    (dprev_g["fecha"] >= inicio_periodo_anterior)
                    & (dprev_g["fecha"] < fin_periodo_anterior)
                ]["monto_usd"].sum()
            )

    ticket_promedio = float(dfv["total_usd"].mean()) if not dfv.empty else 0.0
    clientes_activos_periodo = int(dfv["cliente"].nunique()) if not dfv.empty else 0
    margen_operativo = ((utilidad / ventas_total) * 100) if ventas_total else 0.0
    estado_salud, detalle_salud = _health_status(ventas_total, utilidad, stock_bajo)

    # ============================================================
    # RESUMEN EJECUTIVO
    # ============================================================
    hero_a, hero_b = st.columns([2, 1])
    with hero_a:
        st.info(
            f"**Corte del tablero:** {now.strftime('%d/%m/%Y %H:%M')}  \\\n**Estado general:** {estado_salud}  \\\n**Lectura rápida:** {detalle_salud}"
        )
    with hero_b:
        st.metric("Margen operativo", f"{margen_operativo:,.1f}%")
        st.metric("Ticket promedio", f"${ticket_promedio:,.2f}")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("💰 Ventas del periodo", f"${ventas_total:,.2f}", _fmt_delta(ventas_total, ventas_previas))
    kpi2.metric("💸 Gastos del periodo", f"${gastos_total:,.2f}", _fmt_delta(gastos_total, gastos_previos))
    kpi3.metric("📈 Utilidad estimada", f"${utilidad:,.2f}")
    kpi4.metric("👥 Clientes activos", clientes_activos_periodo, f"Total base: {total_clientes}")

    st.divider()

    resumen1, resumen2, resumen3, resumen4 = st.columns(4)
    resumen1.metric("Utilidad neta del mes", f"${utilidad_neta_mes:,.2f}")
    resumen2.metric("Comisiones estimadas", f"${comision_est:,.2f}")
    resumen3.metric("Capital en inventario", f"${capital_inv:,.2f}")
    resumen4.metric("Ítems en mínimo", stock_bajo)

    st.divider()

    dpe1, dpe2, dpe3 = st.columns(3)
    dpe1.metric("Punto de equilibrio pendiente", f"${punto_equilibrio_restante:,.2f}")
    dpe2.metric("Costos cargados hoy", f"${costos_fijos_hoy:,.2f}")
    dpe3.metric("Cobertura promedio stock", f"{cobertura_stock_dias:,.1f} und.")

    if not df_top.empty:
        top3 = df_top.copy()
        top3["costos"] = top3["costos"].fillna(0.0)
        top3["utilidad_neta"] = top3["ventas"] - top3["costos"]
        top3 = top3.sort_values("utilidad_neta", ascending=False).head(5)
        st.subheader("🏆 Ranking de rentabilidad por producto")
        st.dataframe(top3, use_container_width=True, hide_index=True)

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
    else:
        monitor = pd.DataFrame(
            columns=["nombre", "stock_actual", "valor", "estado", "stock_minimo", "nivel"]
        )

    tab1, tab2, tab3 = st.tabs(["📈 Tendencias", "📦 Inventario", "💳 Clientes y pagos"])

    with tab1:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Ventas por día")
            if dfv.empty:
                st.info("No hay ventas registradas en el periodo.")
            else:
                d1 = dfv.copy()
                d1["dia"] = d1["fecha"].dt.date.astype(str)
                resumen_v = d1.groupby("dia", as_index=False)["total_usd"].sum()
                fig_v = px.line(
                    resumen_v,
                    x="dia",
                    y="total_usd",
                    markers=True,
                    title="Evolución de ventas",
                )
                fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_v, use_container_width=True)

        with col_b:
            st.subheader("Gastos por día")
            if dfg.empty:
                st.info("No hay gastos registrados en el periodo.")
            else:
                d2 = dfg.copy()
                d2["dia"] = d2["fecha"].dt.date.astype(str)
                resumen_g = d2.groupby("dia", as_index=False)["monto_usd"].sum()
                fig_g = px.bar(
                    resumen_g,
                    x="dia",
                    y="monto_usd",
                    title="Evolución de gastos",
                )
                fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_g, use_container_width=True)

        st.subheader("Balance del periodo")
        if dfv.empty and dfg.empty:
            st.info("Todavía no hay movimiento suficiente para construir el balance.")
        else:
            ventas_balance = (
                dfv.assign(tipo="Ventas", monto=dfv["total_usd"])[["fecha", "tipo", "monto"]]
                if not dfv.empty
                else pd.DataFrame(columns=["fecha", "tipo", "monto"])
            )
            gastos_balance = (
                dfg.assign(tipo="Gastos", monto=dfg["monto_usd"] * -1)[["fecha", "tipo", "monto"]]
                if not dfg.empty
                else pd.DataFrame(columns=["fecha", "tipo", "monto"])
            )
            flujo = pd.concat([ventas_balance, gastos_balance], ignore_index=True)
            flujo["fecha"] = pd.to_datetime(flujo["fecha"], errors="coerce")
            flujo = flujo.dropna(subset=["fecha"])
            flujo["dia"] = flujo["fecha"].dt.date.astype(str)
            flujo_resumen = flujo.groupby(["dia", "tipo"], as_index=False)["monto"].sum()
            fig_flujo = px.bar(
                flujo_resumen,
                x="dia",
                y="monto",
                color="tipo",
                barmode="relative",
                title="Flujo neto diario",
            )
            fig_flujo.update_layout(xaxis_title="Día", yaxis_title="Monto neto ($)")
            st.plotly_chart(fig_flujo, use_container_width=True)

    with tab2:
        st.subheader("Monitor de insumos")
        if monitor.empty:
            st.info("No hay inventario activo para mostrar.")
        else:
            alertas, cobertura = st.columns([1.2, 1])
            with alertas:
                st.dataframe(
                    monitor[
                        ["nombre", "stock_actual", "valor", "estado", "stock_minimo", "nivel"]
                    ].sort_values(["estado", "stock_actual"], ascending=[True, True]).head(20),
                    use_container_width=True,
                    hide_index=True,
                )
            with cobertura:
                inv_chart = monitor.copy().sort_values("valor", ascending=False).head(10)
                fig_inv = px.bar(
                    inv_chart,
                    x="valor",
                    y="nombre",
                    color="nivel",
                    orientation="h",
                    title="Top inventario por valor",
                )
                fig_inv.update_layout(yaxis_title="", xaxis_title="Valor estimado ($)")
                st.plotly_chart(fig_inv, use_container_width=True)

    with tab3:
        c_a, c_b = st.columns(2)
        with c_a:
            st.subheader("Ventas por método")
            if dfv.empty:
                st.info("Sin datos para métodos de pago.")
            else:
                vm = (
                    dfv.groupby("metodo_pago", as_index=False)["total_usd"]
                    .sum()
                    .sort_values("total_usd", ascending=False)
                )
                fig_m = px.pie(vm, names="metodo_pago", values="total_usd", hole=0.45)
                st.plotly_chart(fig_m, use_container_width=True)

        with c_b:
            st.subheader("Top clientes")
            if dfv.empty or "cliente" not in dfv.columns:
                st.info("Sin datos de clientes en el periodo.")
            else:
                topc = (
                    dfv.groupby("cliente", as_index=False)["total_usd"]
                    .agg(["sum", "count"])
                    .reset_index()
                )
                topc.columns = ["cliente", "ventas_usd", "tickets"]
                topc = topc.sort_values("ventas_usd", ascending=False).head(10)
                st.dataframe(topc, use_container_width=True, hide_index=True)
