from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from services.planeacion_financiera_service import (
    calcular_flujo_caja_proyectado,
    generar_alertas_gerenciales,
    resumen_presupuesto_operativo,
)
from utils.calculations import calculate_daily_profit


# ============================================================
# AUXILIARES
# ============================================================


def _scalar(conn, query: str, params: tuple = ()) -> float:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0.0
    try:
        return float(row[0] or 0.0)
    except Exception:
        return 0.0


def _read_df(conn, query: str, default_columns: list[str]) -> pd.DataFrame:
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame(columns=default_columns)


def _config_pct(conn, key: str, fallback: float) -> float:
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
    if abs(anterior) < 1e-9:
        return None
    return ((actual - anterior) / anterior) * 100


def _fmt_delta(actual: float, anterior: float, prefix: str = "vs periodo anterior") -> str:
    delta = _safe_pct_change(actual, anterior)
    if delta is None:
        return f"{prefix}: sin base"
    return f"{delta:+.1f}% {prefix}"


def _health_status(
    ventas_total: float,
    utilidad: float,
    stock_bajo: int,
    flujo_30d: float = 0.0,
) -> tuple[str, str]:
    if ventas_total <= 0:
        return "🔴 Atención", "No hay ventas en el periodo seleccionado."
    if utilidad < 0 or flujo_30d < 0:
        return "🔴 Riesgo", "La utilidad o el flujo proyectado muestran presión financiera."
    if stock_bajo >= 5:
        return "🟡 Riesgo controlado", "Hay presión por inventario crítico."
    return "🟢 Saludable", "Ventas activas, utilidad positiva y flujo bajo control."


def _build_executive_alerts(
    margen_operativo: float,
    punto_equilibrio_restante: float,
    stock_bajo: int,
    utilidad: float,
    ventas_total: float,
    flujo_30d: float,
    desviacion_egresos: float,
) -> list[tuple[str, str]]:
    alerts: list[tuple[str, str]] = []

    if ventas_total <= 0:
        alerts.append(("error", "No hay ventas en el periodo seleccionado."))
    elif utilidad < 0:
        alerts.append(("error", "La utilidad del periodo es negativa. Revisa gastos, costos y precios."))
    elif margen_operativo < 12:
        alerts.append(("warning", "El margen operativo está bajo. Revisa mix de productos y gastos."))
    else:
        alerts.append(("success", "El margen operativo se mantiene en una zona saludable."))

    if flujo_30d < 0:
        alerts.append(("error", "El flujo proyectado a 30 días es negativo."))
    else:
        alerts.append(("success", "El flujo proyectado a 30 días se mantiene positivo."))

    if desviacion_egresos > 0:
        alerts.append(("warning", f"Los egresos superan el presupuesto en ${desviacion_egresos:,.2f}."))
    else:
        alerts.append(("success", "Los egresos están dentro del presupuesto."))

    if punto_equilibrio_restante > 0:
        alerts.append(("warning", f"Aún faltan ${punto_equilibrio_restante:,.2f} para cubrir costos del día."))
    else:
        alerts.append(("success", "El punto de equilibrio diario está cubierto."))

    if stock_bajo >= 5:
        alerts.append(("error", f"Hay {stock_bajo} productos/insumos en nivel crítico o mínimo."))
    elif stock_bajo > 0:
        alerts.append(("warning", f"Hay {stock_bajo} productos/insumos con riesgo de reposición."))
    else:
        alerts.append(("success", "No hay alertas críticas de inventario."))

    return alerts


def _normalize_dates(df: pd.DataFrame, col: str = "fecha") -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce")
    out = out.dropna(subset=[col])
    return out


def _period_bounds(rango: str, now: pd.Timestamp) -> pd.Timestamp | None:
    hoy = now.normalize()
    if rango == "Todo":
        return None
    dias = {"Hoy": 0, "7 días": 7, "30 días": 30, "90 días": 90}.get(rango, 30)
    return hoy - pd.Timedelta(days=dias)


# ============================================================
# DASHBOARD EJECUTIVO + FINANCIERO
# ============================================================


def render_dashboard() -> None:
    st.subheader("📊 Dashboard Ejecutivo")
    st.caption("Vista ejecutiva del negocio: ventas, gastos, utilidad, presupuesto, flujo, clientes y stock.")

    now = pd.Timestamp.now()
    periodo_default = now.strftime("%Y-%m")

    col_ctrl1, col_ctrl2 = st.columns([1, 1])
    with col_ctrl1:
        rango = st.selectbox("Periodo", ["Hoy", "7 días", "30 días", "90 días", "Todo"], index=2)
    with col_ctrl2:
        periodo = st.text_input("Periodo financiero (YYYY-MM)", value=periodo_default)

    try:
        with db_transaction() as conn:
            df_ventas = _read_df(
                conn,
                """
                SELECT
                    v.fecha,
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    COALESCE(v.metodo_pago, 'Sin método') AS metodo_pago,
                    COALESCE(v.total_usd, 0) AS total_usd
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                WHERE v.estado = 'registrada'
                """,
                ["fecha", "cliente", "metodo_pago", "total_usd"],
            )

            df_gastos = _read_df(
                conn,
                """
                SELECT
                    fecha,
                    COALESCE(monto_usd, 0) AS monto_usd,
                    COALESCE(categoria, 'Sin categoría') AS categoria
                FROM gastos
                WHERE estado = 'activo'
                """,
                ["fecha", "monto_usd", "categoria"],
            )

            total_clientes = int(_scalar(conn, "SELECT COUNT(*) FROM clientes WHERE estado='activo'"))

            df_inv_dash = _read_df(
                conn,
                """
                SELECT
                    nombre,
                    COALESCE(stock_actual, 0) AS stock_actual,
                    COALESCE(precio_venta_usd, 0) AS precio_venta_usd,
                    COALESCE(stock_minimo, 0) AS stock_minimo
                FROM inventario
                WHERE estado = 'activo'
                """,
                ["nombre", "stock_actual", "precio_venta_usd", "stock_minimo"],
            )

            df_top = _read_df(
                conn,
                """
                SELECT
                    COALESCE(vd.descripcion, 'Sin descripción') AS descripcion,
                    SUM(COALESCE(vd.subtotal_usd, 0)) AS ventas,
                    SUM(COALESCE(vd.costo_unitario_usd, 0) * COALESCE(vd.cantidad, 0)) AS costos
                FROM ventas_detalle vd
                WHERE vd.estado = 'activo'
                GROUP BY vd.descripcion
                """,
                ["descripcion", "ventas", "costos"],
            )

            banco_perc = _config_pct(conn, "banco_perc", 0.5)
            kontigo_perc = _config_pct(conn, "kontigo_perc", 5.0)

            resumen_presupuesto = resumen_presupuesto_operativo(conn, periodo=periodo)
            flujo_proyectado = calcular_flujo_caja_proyectado(conn)
            alertas_fin = generar_alertas_gerenciales(conn, periodo=periodo)

    except Exception as e:
        st.error("Error cargando dashboard.")
        st.exception(e)
        return

    desde = _period_bounds(rango, now)
    hoy = now.normalize()

    dfv = _normalize_dates(df_ventas, "fecha")
    dfg = _normalize_dates(df_gastos, "fecha")

    if desde is not None:
        if not dfv.empty:
            dfv = dfv[dfv["fecha"] >= desde]
        if not dfg.empty:
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
        dvm = _normalize_dates(df_ventas, "fecha")
        ventas_mes = float(dvm[dvm["fecha"] >= ini_mes]["total_usd"].sum()) if not dvm.empty else 0.0

    if not df_gastos.empty:
        dgm = _normalize_dates(df_gastos, "fecha")
        gastos_mes = float(dgm[dgm["fecha"] >= ini_mes]["monto_usd"].sum()) if not dgm.empty else 0.0

    utilidad_neta_mes = ventas_mes - gastos_mes

    capital_inv = 0.0
    stock_bajo = 0
    cobertura_stock_unidades = 0.0
    if not df_inv_dash.empty:
        capital_inv = float((df_inv_dash["stock_actual"] * df_inv_dash["precio_venta_usd"]).sum())
        stock_bajo = int((df_inv_dash["stock_actual"] <= df_inv_dash["stock_minimo"]).sum())
        cobertura_stock_unidades = float(df_inv_dash["stock_actual"].sum()) / max(len(df_inv_dash), 1)

    costos_hoy = (
        float(dfg[dfg["fecha"].dt.date == hoy.date()]["monto_usd"].sum())
        if not dfg.empty
        else 0.0
    )
    punto_equilibrio_restante = max(0.0, costos_hoy - ventas_total)

    ventas_previas = 0.0
    gastos_previos = 0.0
    if desde is not None:
        fin_periodo_anterior = desde
        inicio_periodo_anterior = desde - (hoy - desde + pd.Timedelta(days=1))

        if not df_ventas.empty:
            dprev_v = _normalize_dates(df_ventas, "fecha")
            ventas_previas = float(
                dprev_v[
                    (dprev_v["fecha"] >= inicio_periodo_anterior)
                    & (dprev_v["fecha"] < fin_periodo_anterior)
                ]["total_usd"].sum()
            )

        if not df_gastos.empty:
            dprev_g = _normalize_dates(df_gastos, "fecha")
            gastos_previos = float(
                dprev_g[
                    (dprev_g["fecha"] >= inicio_periodo_anterior)
                    & (dprev_g["fecha"] < fin_periodo_anterior)
                ]["monto_usd"].sum()
            )

    ticket_promedio = float(dfv["total_usd"].mean()) if not dfv.empty else 0.0
    clientes_activos_periodo = int(dfv["cliente"].nunique()) if not dfv.empty else 0

    margen_operativo = ((utilidad / ventas_total) * 100) if ventas_total else 0.0

    flujo_7d = 0.0
    flujo_15d = 0.0
    flujo_30d = 0.0
    saldo_actual = 0.0
    cobros_30d = 0.0
    pagos_30d = 0.0

    if not flujo_proyectado.empty:
        saldo_actual = float(flujo_proyectado.iloc[0].get("saldo_actual_usd", 0.0))

        f7 = flujo_proyectado[flujo_proyectado["horizonte_dias"] == 7] if "horizonte_dias" in flujo_proyectado.columns else pd.DataFrame()
        f15 = flujo_proyectado[flujo_proyectado["horizonte_dias"] == 15] if "horizonte_dias" in flujo_proyectado.columns else pd.DataFrame()
        f30 = flujo_proyectado[flujo_proyectado["horizonte_dias"] == 30] if "horizonte_dias" in flujo_proyectado.columns else pd.DataFrame()

        if not f7.empty:
            flujo_7d = float(f7.iloc[-1].get("flujo_proyectado_usd", 0.0))
        if not f15.empty:
            flujo_15d = float(f15.iloc[-1].get("flujo_proyectado_usd", 0.0))
        if not f30.empty:
            flujo_30d = float(f30.iloc[-1].get("flujo_proyectado_usd", 0.0))
            cobros_30d = float(f30.iloc[-1].get("cobros_esperados_usd", 0.0))
            pagos_30d = float(f30.iloc[-1].get("pagos_proximos_usd", 0.0))
        else:
            flujo_30d = float(flujo_proyectado.iloc[-1].get("flujo_proyectado_usd", 0.0))
            cobros_30d = float(flujo_proyectado.iloc[-1].get("cobros_esperados_usd", 0.0))
            pagos_30d = float(flujo_proyectado.iloc[-1].get("pagos_proximos_usd", 0.0))

    ingresos_presupuestados = float(resumen_presupuesto.get("ingresos_presupuestados_usd", 0.0))
    egresos_presupuestados = float(resumen_presupuesto.get("egresos_presupuestados_usd", 0.0))
    ingresos_reales = float(resumen_presupuesto.get("ingresos_reales_usd", 0.0))
    egresos_reales = float(resumen_presupuesto.get("egresos_reales_usd", 0.0))
    desviacion_ingresos = float(resumen_presupuesto.get("desviacion_ingresos_usd", 0.0))
    desviacion_egresos = float(resumen_presupuesto.get("desviacion_egresos_usd", 0.0))

    estado_salud, detalle_salud = _health_status(
        ventas_total,
        utilidad,
        stock_bajo,
        flujo_30d,
    )

    dias_periodo = max((hoy - desde).days + 1, 1) if desde is not None else 30
    run_rate_ventas = (ventas_total / dias_periodo) * 30 if dias_periodo else 0.0
    run_rate_utilidad = (utilidad / dias_periodo) * 30 if dias_periodo else 0.0

    alertas_ejecutivas = _build_executive_alerts(
        margen_operativo=margen_operativo,
        punto_equilibrio_restante=punto_equilibrio_restante,
        stock_bajo=stock_bajo,
        utilidad=utilidad,
        ventas_total=ventas_total,
        flujo_30d=flujo_30d,
        desviacion_egresos=desviacion_egresos,
    )

    ingresos_vs_gastos = pd.DataFrame(
        {
            "concepto": ["Ventas", "Gastos", "Comisiones", "Utilidad"],
            "monto_usd": [ventas_total, gastos_total, comision_est, utilidad],
        }
    )

    presupuesto_vs_real = pd.DataFrame(
        {
            "concepto": ["Ingresos", "Egresos"],
            "presupuestado_usd": [ingresos_presupuestados, egresos_presupuestados],
            "real_usd": [ingresos_reales, egresos_reales],
            "desviacion_usd": [desviacion_ingresos, desviacion_egresos],
        }
    )

    hero_a, hero_b = st.columns([2, 1])

    with hero_a:
        st.info(
            f"**Corte:** {now.strftime('%d/%m/%Y %H:%M')}  \n"
            f"**Estado general:** {estado_salud}  \n"
            f"**Lectura rápida:** {detalle_salud}"
        )

    with hero_b:
        st.metric("Margen operativo", f"{margen_operativo:,.1f}%")
        st.metric("Ticket promedio", f"${ticket_promedio:,.2f}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💰 Ventas del periodo", f"${ventas_total:,.2f}", _fmt_delta(ventas_total, ventas_previas))
    k2.metric("💸 Gastos del periodo", f"${gastos_total:,.2f}", _fmt_delta(gastos_total, gastos_previos))
    k3.metric("📈 Utilidad estimada", f"${utilidad:,.2f}")
    k4.metric("👥 Clientes del periodo", clientes_activos_periodo, f"Base activa: {total_clientes}")

    st.divider()

    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("Saldo actual", f"${saldo_actual:,.2f}")
    f2.metric("Flujo 7 días", f"${flujo_7d:,.2f}")
    f3.metric("Flujo 15 días", f"${flujo_15d:,.2f}")
    f4.metric("Flujo 30 días", f"${flujo_30d:,.2f}")
    f5.metric("Desv. egresos", f"${desviacion_egresos:,.2f}")

    st.divider()

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Utilidad neta del mes", f"${utilidad_neta_mes:,.2f}")
    r2.metric("Comisiones estimadas", f"${comision_est:,.2f}")
    r3.metric("Capital en inventario", f"${capital_inv:,.2f}")
    r4.metric("Ítems en mínimo", stock_bajo)

    st.divider()

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Punto equilibrio pendiente", f"${punto_equilibrio_restante:,.2f}")
    p2.metric("Costos cargados hoy", f"${costos_hoy:,.2f}")
    p3.metric("Cobros 30 días", f"${cobros_30d:,.2f}")
    p4.metric("Pagos 30 días", f"${pagos_30d:,.2f}")

    rr1, rr2, rr3 = st.columns(3)
    rr1.metric("Run-rate ventas (30 días)", f"${run_rate_ventas:,.2f}")
    rr2.metric("Run-rate utilidad (30 días)", f"${run_rate_utilidad:,.2f}")
    rr3.metric("Cobertura promedio stock", f"{cobertura_stock_unidades:,.1f} und.")

    with st.expander("🚨 Alertas ejecutivas", expanded=True):
        for nivel, mensaje in alertas_ejecutivas:
            if nivel == "error":
                st.error(mensaje)
            elif nivel == "warning":
                st.warning(mensaje)
            else:
                st.success(mensaje)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 Tendencias", "💵 Finanzas", "🧾 Presupuesto vs Real", "📦 Inventario", "💳 Clientes y pagos"]
    )

    with tab1:
        c_a, c_b = st.columns(2)

        with c_a:
            st.subheader("Ventas por día")
            if dfv.empty:
                st.info("No hay ventas registradas en el periodo.")
            else:
                ventas_dia = dfv.copy()
                ventas_dia["dia"] = ventas_dia["fecha"].dt.date.astype(str)
                resumen_v = ventas_dia.groupby("dia", as_index=False)["total_usd"].sum()
                fig_v = px.line(
                    resumen_v,
                    x="dia",
                    y="total_usd",
                    markers=True,
                    title="Evolución de ventas",
                )
                fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_v, use_container_width=True)

        with c_b:
            st.subheader("Gastos por día")
            if dfg.empty:
                st.info("No hay gastos registrados en el periodo.")
            else:
                gastos_dia = dfg.copy()
                gastos_dia["dia"] = gastos_dia["fecha"].dt.date.astype(str)
                resumen_g = gastos_dia.groupby("dia", as_index=False)["monto_usd"].sum()
                fig_g = px.bar(
                    resumen_g,
                    x="dia",
                    y="monto_usd",
                    title="Evolución de gastos",
                )
                fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")
                st.plotly_chart(fig_g, use_container_width=True)

    with tab2:
        fa, fb = st.columns(2)

        with fa:
            st.subheader("Resumen financiero")
            st.dataframe(ingresos_vs_gastos, use_container_width=True, hide_index=True)

            fig_fin = px.bar(
                ingresos_vs_gastos,
                x="concepto",
                y="monto_usd",
                color="concepto",
                title="Ventas vs gastos vs utilidad",
            )
            fig_fin.update_layout(xaxis_title="", yaxis_title="Monto ($)")
            st.plotly_chart(fig_fin, use_container_width=True)

        with fb:
            st.subheader("Gastos por categoría")
            if dfg.empty:
                st.info("No hay gastos para clasificar.")
            else:
                gastos_categoria = (
                    dfg.groupby("categoria", as_index=False)["monto_usd"]
                    .sum()
                    .sort_values("monto_usd", ascending=False)
                )
                fig_gc = px.pie(
                    gastos_categoria,
                    names="categoria",
                    values="monto_usd",
                    hole=0.45,
                    title="Composición de gastos",
                )
                st.plotly_chart(fig_gc, use_container_width=True)
                st.dataframe(gastos_categoria, use_container_width=True, hide_index=True)

        if not flujo_proyectado.empty:
            st.subheader("Flujo proyectado")
            st.dataframe(flujo_proyectado, use_container_width=True, hide_index=True)

            if "horizonte_dias" in flujo_proyectado.columns and "flujo_proyectado_usd" in flujo_proyectado.columns:
                fig_fp = px.line(
                    flujo_proyectado,
                    x="horizonte_dias",
                    y="flujo_proyectado_usd",
                    markers=True,
                    title="Proyección de flujo de caja",
                )
                fig_fp.update_layout(xaxis_title="Horizonte (días)", yaxis_title="Flujo proyectado ($)")
                st.plotly_chart(fig_fp, use_container_width=True)

    with tab3:
        st.subheader("Presupuesto vs real")
        st.dataframe(presupuesto_vs_real, use_container_width=True, hide_index=True)

        fig_pr = px.bar(
            presupuesto_vs_real.melt(
                id_vars="concepto",
                value_vars=["presupuestado_usd", "real_usd"],
                var_name="tipo",
                value_name="monto_usd",
            ),
            x="concepto",
            y="monto_usd",
            color="tipo",
            barmode="group",
            title="Presupuesto vs real",
        )
        fig_pr.update_layout(xaxis_title="", yaxis_title="Monto ($)")
        st.plotly_chart(fig_pr, use_container_width=True)

        st.subheader("Resumen de presupuesto")
        st.json(resumen_presupuesto)

        st.subheader("Alertas financieras")
        st.dataframe(alertas_fin, use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("Monitor de inventario")
        if df_inv_dash.empty:
            st.info("No hay inventario activo para mostrar.")
        else:
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

            mostrar_solo_riesgo = st.toggle("Mostrar solo ítems en riesgo", value=False)
            monitor_view = monitor.copy()
            if mostrar_solo_riesgo:
                monitor_view = monitor_view[monitor_view["nivel"] != "🟢 OK"]

            ia, ib = st.columns([1.2, 1])

            with ia:
                st.dataframe(
                    monitor_view[
                        ["nombre", "stock_actual", "stock_minimo", "precio_venta_usd", "valor", "nivel"]
                    ].sort_values(["nivel", "stock_actual"], ascending=[True, True]),
                    use_container_width=True,
                    hide_index=True,
                )

            with ib:
                inv_chart = monitor_view.copy().sort_values("valor", ascending=False).head(10)
                if inv_chart.empty:
                    st.info("No hay ítems para graficar.")
                else:
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

    with tab5:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Ventas por método de pago")
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
                vm["participacion_%"] = (
                    (vm["total_usd"] / max(float(vm["total_usd"].sum()), 1e-9)) * 100
                ).round(2)
                st.dataframe(vm, use_container_width=True, hide_index=True)

        with c2:
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
                topc["ticket_promedio"] = np.where(
                    topc["tickets"] > 0,
                    topc["ventas_usd"] / topc["tickets"],
                    0.0,
                )
                topc = topc.sort_values("ventas_usd", ascending=False).head(10)
                st.dataframe(topc, use_container_width=True, hide_index=True)


def render_planeacion_financiera(_usuario: str | None = None) -> None:
    """Compatibilidad con la vista legacy que espera este entrypoint."""
    render_dashboard()
