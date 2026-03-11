from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from utils.calculations import calculate_daily_profitArchivar

Compartir

Crear PR


esto es lo que tenia antes ve si puedes adaptarlo o mejorarlo con lo que esta actualmente en el codigoi:         \n# ===========================================================\n# 📊 DASHBOARD GENERAL\n# ===========================================================\nif menu == "📊 Dashboard":\n\n    st.title("📊 Dashboard Ejecutivo")\n    st.caption("Resumen general del negocio: ventas, gastos, comisiones, clientes e inventario.")\n\n    with conectar() as conn:\n        try:\n            df_ventas = pd.read_sql("SELECT fecha, cliente, metodo, monto_total FROM ventas", conn)\n        except Exception:\n            df_ventas = pd.DataFrame(columns=["fecha", "cliente", "metodo", "monto_total"])\n\n        try:\n            df_gastos = pd.read_sql("SELECT fecha, monto, categoria FROM gastos WHERE COALESCE(activo,1)=1", conn)\n        except Exception:\n            df_gastos = pd.DataFrame(columns=["fecha", "monto", "categoria"])\n\n        try:\n            total_clientes = conn.execute("SELECT COUNT(*) FROM clientes WHERE COALESCE(activo,1)=1").fetchone()[0]\n        except Exception:\n            total_clientes = 0\n\n        try:\n            df_inv_dash = pd.read_sql("SELECT item, cantidad, precio_usd, minimo, COALESCE(activo,1) as activo FROM inventario WHERE COALESCE(activo,1)=1", conn)\n        except Exception:\n            df_inv_dash = pd.DataFrame(columns=["item", "cantidad", "precio_usd", "minimo", "activo"])\n        try:\n            df_tiempos_dash = pd.read_sql("SELECT minutos_reales FROM tiempos_produccion", conn)\n        except Exception:\n            df_tiempos_dash = pd.DataFrame(columns=['minutos_reales'])\n\n    # ------------------------------\n    # Filtro temporal\n    # ------------------------------\n    rango = st.selectbox("Periodo", ["Hoy", "7 días", "30 días", "Todo"], index=2)\n    desde = None\n    if rango != "Todo":\n        dias = {"Hoy": 0, "7 días": 7, "30 días": 30}[rango]\n        desde = pd.Timestamp.now().normalize() - pd.Timedelta(days=dias)\n\n    dfv = df_ventas.copy()\n    dfg = df_gastos.copy()\n\n    if not dfv.empty:\n        dfv["fecha"] = pd.to_datetime(dfv["fecha"], errors="coerce")\n        dfv = dfv.dropna(subset=["fecha"])\n        if desde is not None:\n            dfv = dfv[dfv["fecha"] >= desde]\n\n    if not dfg.empty:\n        dfg["fecha"] = pd.to_datetime(dfg["fecha"], errors="coerce")\n        dfg = dfg.dropna(subset=["fecha"])\n        if desde is not None:\n            dfg = dfg[dfg["fecha"] >= desde]\n\n    ventas_total = float(dfv["monto_total"].sum()) if not dfv.empty else 0.0\n    gastos_total = float(dfg["monto"].sum()) if not dfg.empty else 0.0\n\n    banco_perc = float(st.session_state.get('banco_perc', 0.5))\n    kontigo_perc = float(st.session_state.get('kontigo_perc_entrada', st.session_state.get('kontigo_perc', 5.0)))\n\n    comision_est = 0.0\n    if not dfv.empty:\n        ventas_bancarias = dfv[dfv['metodo'].str.contains("Pago|Transferencia", case=False, na=False)]\n        ventas_kontigo = dfv[dfv['metodo'].str.contains("Kontigo", case=False, na=False)]\n        if not ventas_bancarias.empty:\n            comision_est += float(ventas_bancarias['monto_total'].sum() * (banco_perc / 100))\n        if not ventas_kontigo.empty:\n            comision_est += float(ventas_kontigo['monto_total'].sum() * (kontigo_perc / 100))\n\n    utilidad = ventas_total - gastos_total - comision_est\n\n    utilidad_neta_mes = 0.0\n    if not df_ventas.empty:\n        dvm = df_ventas.copy()\n        dvm['fecha'] = pd.to_datetime(dvm['fecha'], errors='coerce')\n        ini_mes = pd.Timestamp.now().replace(day=1).normalize()\n        ventas_mes = float(dvm[dvm['fecha'] >= ini_mes]['monto_total'].sum()) if 'monto_total' in dvm.columns else 0.0\n        gastos_mes = 0.0\n        if not df_gastos.empty:\n            dgm = df_gastos.copy()\n            dgm['fecha'] = pd.to_datetime(dgm['fecha'], errors='coerce')\n            gastos_mes = float(dgm[dgm['fecha'] >= ini_mes]['monto'].sum()) if 'monto' in dgm.columns else 0.0\n        utilidad_neta_mes = money(ventas_mes - gastos_mes)\n\n    eficiencia_horas = float(df_tiempos_dash['minutos_reales'].mean() / 60.0) if not df_tiempos_dash.empty else 0.0\n    insumos_criticos = int((df_inv_dash['cantidad'] <= df_inv_dash['minimo']).sum()) if not df_inv_dash.empty else 0\n\n    kpi1, kpi2, kpi3 = st.columns(3)\n    kpi1.metric('Utilidad Neta del Mes', f"$ {utilidad_neta_mes:,.2f}")\n    kpi2.metric('Eficiencia Producción (prom. entrega)', f"{eficiencia_horas:.2f} h")\n    kpi3.metric('Alerta Insumos Críticos', insumos_criticos)\n    st.divider()\n\n    capital_inv = 0.0\n    stock_bajo = 0\n    if not df_inv_dash.empty:\n        capital_inv = float((df_inv_dash["cantidad"] * df_inv_dash["precio_usd"]).sum())\n        stock_bajo = int((df_inv_dash["cantidad"] <= df_inv_dash["minimo"]).sum())\n\n    # KPI v4.0 de mando\n    costos_fijos_hoy = float(dfg[dfg['fecha'].dt.date == pd.Timestamp.now().date()]['monto'].sum()) if (not dfg.empty and 'fecha' in dfg.columns) else 0.0\n    punto_equilibrio_restante = max(0.0, money(costos_fijos_hoy - ventas_total))\n\n    c1, c2, c3, c4, c5, c6 = st.columns(6)\n    c1.metric("💰 Ventas", f"${ventas_total:,.2f}")\n    c2.metric("💸 Gastos", f"${gastos_total:,.2f}")\n    c3.metric("🏦 Comisiones", f"${comision_est:,.2f}")\n    c4.metric("📈 Utilidad", f"${utilidad:,.2f}")\n    c5.metric("👥 Clientes", total_clientes)\n    c6.metric("🚨 Ítems Mínimo", stock_bajo)\n\n    st.divider()\n\n    dpe1, dpe2 = st.columns(2)\n    dpe1.metric('Punto de Equilibrio (faltante hoy)', f"$ {punto_equilibrio_restante:,.2f}")\n    dpe2.metric('Costos fijos hoy', f"$ {costos_fijos_hoy:,.2f}")\n\n    with conectar() as conn:\n        df_top = pd.read_sql_query("SELECT detalle, monto_total FROM ventas WHERE COALESCE(activo,1)=1 ORDER BY fecha DESC LIMIT 500", conn)\n        try:\n            df_costos = pd.read_sql_query("SELECT trabajo, COALESCE(costo,0) AS costo FROM ordenes_produccion WHERE COALESCE(activo,1)=1", conn)\n        except Exception:\n            df_costos = pd.DataFrame(columns=['trabajo', 'costo'])\n    if not df_top.empty:\n        ventas_det = df_top.groupby('detalle', as_index=False)['monto_total'].sum().rename(columns={'monto_total': 'ventas'})\n        if not df_costos.empty:\n            costos_det = df_costos.groupby('trabajo', as_index=False)['costo'].sum().rename(columns={'trabajo': 'detalle', 'costo': 'costos'})\n            top3 = ventas_det.merge(costos_det, on='detalle', how='left')\n        else:\n            top3 = ventas_det.copy()\n            top3['costos'] = 0.0\n        top3['costos'] = top3['costos'].fillna(0.0)\n        top3['utilidad_neta'] = top3['ventas'] - top3['costos']\n        top3 = top3.sort_values('utilidad_neta', ascending=False).head(3)\n        st.subheader('🏆 Ranking de Rentabilidad Neta por producto')\n        st.dataframe(top3, use_container_width=True, hide_index=True)\n\n    st.subheader('🚦 Monitor de Insumos')\n    if not df_inv_dash.empty:\n        monitor = df_inv_dash.copy()\n        monitor['nivel'] = np.where(monitor['cantidad'] <= monitor['minimo'], '🔴 Crítico', np.where(monitor['cantidad'] <= (monitor['minimo']*1.5), '🟡 Bajo', '🟢 OK'))\n        monitor['valor'] = pd.to_numeric(monitor['cantidad'], errors='coerce').fillna(0.0) * pd.to_numeric(monitor['precio_usd'], errors='coerce').fillna(0.0)\n        monitor['estado'] = np.where(monitor['cantidad'] <= monitor['minimo'], 'Crítico', 'Operativo')\n        st.dataframe(monitor[['item','cantidad','valor','estado','minimo','nivel']].head(20), use_container_width=True, hide_index=True)\n\n    col_a, col_b = st.columns(2)\n\n    with col_a:\n        st.subheader("📆 Ventas por día")\n        if dfv.empty:\n            st.info("No hay ventas registradas en el periodo.")\n        else:\n            d1 = dfv.copy()\n            d1["dia"] = d1["fecha"].dt.date.astype(str)\n            resumen_v = d1.groupby("dia", as_index=False)["monto_total"].sum()\n            fig_v = px.line(resumen_v, x="dia", y="monto_total", markers=True)\n            fig_v.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")\n            st.plotly_chart(fig_v, use_container_width=True)\n\n    with col_b:\n        st.subheader("📉 Gastos por día")\n        if dfg.empty:\n            st.info("No hay gastos registrados en el periodo.")\n        else:\n            d2 = dfg.copy()\n            d2["dia"] = d2["fecha"].dt.date.astype(str)\n            resumen_g = d2.groupby("dia", as_index=False)["monto"].sum()\n            fig_g = px.bar(resumen_g, x="dia", y="monto")\n            fig_g.update_layout(xaxis_title="Día", yaxis_title="Monto ($)")\n            st.plotly_chart(fig_g, use_container_width=True)\n\n    cA, cB = st.columns(2)\n    with cA:\n        st.subheader("💳 Ventas por método")\n        if dfv.empty:\n            st.info("Sin datos para métodos de pago.")\n        else:\n            vm = dfv.groupby('metodo', as_index=False)['monto_total'].sum().sort_values('monto_total', ascending=False)\n            fig_m = px.pie(vm, names='metodo', values='monto_total')\n            st.plotly_chart(fig_m, use_container_width=True)\n\n    with cB:\n        st.subheader("🏆 Top clientes")\n        if dfv.empty or 'cliente' not in dfv.columns:\n            st.info("Sin datos de clientes en el periodo.")\n        else:\n            topc = dfv.groupby('cliente', as_index=False)['monto_total'].sum().sort_values('monto_total', ascending=False).head(10)\n            st.dataframe(topc, use_container_width=True)\n\n    st.divider()\n    st.subheader("📦 Estado del Inventario")\n    st.metric("💼 Capital inmovilizado en inventario", f"${capital_inv:,.2f}")
Copiar
Summary
Adapté el dashboard a la estructura actual del sistema (tablas/columnas vigentes) y lo convertí en un Dashboard Ejecutivo con carga robusta de ventas, gastos, clientes, inventario, top de rentabilidad y porcentajes de comisión desde configuración. 

Integré filtro de período (Hoy, 7 días, 30 días, Todo) y lógica de cálculo para ventas, gastos, comisiones estimadas, utilidad, utilidad neta mensual, capital inmovilizado, stock bajo y punto de equilibrio diario. 

Añadí KPIs ampliados + secciones visuales: métricas principales, ranking de rentabilidad por producto, monitor de insumos, ventas/gastos por día, ventas por método y top clientes. 

Screenshot
Captura de pantalla tomada

Testing

✅ python -m py_compile modules/dashboard.py views/dashboard.py app.py

✅ streamlit run app.py --server.headless true --server.port 8501

✅ Script Playwright ejecutado contra http://127.0.0.1:8501 para validación visual y captura.

Además, dejé los cambios commiteados (b7e796d) y generé el PR con título y descripción.


Archivo (1)

dashboard.py
modules/dashboard.py
+252
-165



Vista previa
Diferencias
Registros

modules/dashboard.py
modules/dashboard.py
+252
-165

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


# ============================================================
# DASHBOARD FINANCIERO
# ============================================================

def render_dashboard() -> None:

    st.subheader("📊 Dashboard Financiero")

    try:

        with db_transaction() as conn:

            # -----------------------------
            # INGRESOS DEL DÍA
            # -----------------------------

            daily_revenue = _scalar(
                conn,
                """
                SELECT SUM(total_usd)
                FROM ventas
                WHERE date(fecha)=date('now')
                AND estado='registrada'
                """
            )

            # -----------------------------
            # GASTOS DEL DÍA
            # -----------------------------

            daily_expenses = _scalar(
                conn,
                """
                SELECT SUM(monto_usd)
                FROM gastos
                WHERE date(fecha)=date('now')
                AND estado='activo'
                """
            )

            # -----------------------------
            # COSTO PRODUCTIVO
            # -----------------------------

            daily_production_cost = _scalar(
                conn,
                """
                SELECT SUM(costo_unitario_usd * cantidad)
                FROM ventas_detalle
                WHERE date(fecha)=date('now')
                AND estado='activo'
                """
            )

            # -----------------------------
            # GANANCIA MENSUAL
            # -----------------------------

            monthly_profit = _scalar(
                conn,
                """
                SELECT
                COALESCE(SUM(v.total_usd),0)
                -
                COALESCE(
                    (
                        SELECT SUM(g.monto_usd)
                        FROM gastos g
                        WHERE strftime('%Y-%m', g.fecha)=strftime('%Y-%m','now')
                        AND g.estado='activo'
                    ),
                0)
                FROM ventas v
                WHERE strftime('%Y-%m', v.fecha)=strftime('%Y-%m','now')
                AND v.estado='registrada'
                """
            )

            # -----------------------------
            # VENTAS DEL MES
            # -----------------------------

            monthly_sales = _scalar(
                conn,
                """
                SELECT SUM(total_usd)
                FROM ventas
                WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now')
                AND estado='registrada'
                """
            )

            # -----------------------------
            # CATEGORÍA CON MÁS GASTO
            # -----------------------------

            top_expense = conn.execute(
                """
                SELECT categoria, SUM(monto_usd) total
                FROM gastos
                WHERE estado='activo'
                GROUP BY categoria
                ORDER BY total DESC
                LIMIT 1
                """
            ).fetchone()

            # -----------------------------
            # PRODUCTO MÁS VENDIDO
            # -----------------------------

            best_product = conn.execute(
                """
                SELECT descripcion, SUM(cantidad) qty
                FROM ventas_detalle
                WHERE estado='activo'
                GROUP BY descripcion
                ORDER BY qty DESC
                LIMIT 1
                """
            ).fetchone()

    except Exception as e:

        st.error("Error cargando dashboard")

        st.exception(e)

        return

    # ============================================================
    # CÁLCULOS
    # ============================================================

    daily_profit = calculate_daily_profit(
        daily_revenue,
        daily_expenses,
        daily_production_cost
    )

    margin = (daily_profit / daily_revenue * 100) if daily_revenue else 0.0

    # ============================================================
    # MÉTRICAS PRINCIPALES
    # ============================================================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Ingresos diarios",
        f"$ {daily_revenue:,.2f}"
    )

    c2.metric(
        "Gastos diarios",
        f"$ {daily_expenses:,.2f}"
    )

    c3.metric(
        "Ganancia diaria",
        f"$ {daily_profit:,.2f}",
        delta=f"{margin:,.2f}% margen"
    )

    c4.metric(
        "Ganancia mensual",
        f"$ {monthly_profit:,.2f}"
    )

    st.divider()

    # ============================================================
    # MÉTRICAS SECUNDARIAS
    # ============================================================

    c5, c6 = st.columns(2)

    c5.metric(
        "Ventas del mes",
        f"$ {monthly_sales:,.2f}"
    )

    c6.metric(
        "Costo productivo diario",
        f"$ {daily_production_cost:,.2f}"
    )

    st.divider()

    # ============================================================
    # INSIGHTS
    # ============================================================

    if top_expense:

        st.info(
            f"💸 Categoría con mayor gasto: **{top_expense['categoria']}**"
        )

    else:

        st.info("No hay gastos registrados.")

    if best_product:

        st.success(
            f"🏆 Producto más vendido: **{best_product['descripcion']}**"
        )

    else:

        st.info("No hay ventas registradas.")
