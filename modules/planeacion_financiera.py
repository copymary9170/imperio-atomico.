from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.planeacion_financiera_service import (
    calcular_flujo_caja_proyectado,
    generar_alertas_gerenciales,
    guardar_presupuesto_operativo,
    listar_presupuesto_operativo,
    resumen_presupuesto_operativo,
)

# NUEVO: puedes conectar luego a servicios reales
# (por ahora placeholders seguros)
def _placeholder_df(columns):
    return pd.DataFrame(columns=columns)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _salud_financiera_score(resumen: dict[str, float | str], flujo: pd.DataFrame) -> tuple[int, str, str]:
    ingresos = _safe_float(resumen.get("ingresos_ejecutados_usd"))
    egresos = _safe_float(resumen.get("egresos_ejecutados_usd"))
    desviacion_egresos = _safe_float(resumen.get("desviacion_egresos_usd"))

    if flujo.empty:
        saldo_proyectado_min = 0.0
    else:
        saldo_proyectado_min = _safe_float(flujo["saldo_proyectado_usd"].min())

    score = 100
    if ingresos > 0:
        margen = (ingresos - egresos) / ingresos
        if margen < 0:
            score -= 35
        elif margen < 0.1:
            score -= 15
    elif egresos > 0:
        score -= 25

    if desviacion_egresos > 0:
        score -= 15

    if saldo_proyectado_min < 0:
        score -= 35
    elif saldo_proyectado_min < 1000:
        score -= 10

    score = max(0, min(100, int(round(score))))

    if score >= 80:
        return score, "Saludable", "✅ Flujo y ejecución bajo control."
    if score >= 60:
        return score, "Atención", "⚠️ Hay señales tempranas de presión en caja o margen."
    return score, "Crítico", "🚨 Prioriza caja, cobranza y ajuste de costos de inmediato."


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💰 Planeación Financiera")
    st.caption("Módulo operativo: presupuesto, flujo de caja, ingresos, costos y control financiero.")

    periodo_default = date.today().strftime("%Y-%m")
    periodo = st.text_input("Período (YYYY-MM)", value=periodo_default)

    # =========================
    # DATA BASE
    # =========================
    with db_transaction() as conn:
        resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
        flujo = calcular_flujo_caja_proyectado(conn)
        alertas = generar_alertas_gerenciales(conn, periodo=periodo)
        presupuesto = listar_presupuesto_operativo(conn, periodo=periodo)

    # =========================
    # DASHBOARD
    # =========================
    st.subheader("📊 Dashboard financiero")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Saldo actual", f"$ {float(flujo.iloc[0]['saldo_actual_usd']) if not flujo.empty else 0:,.2f}")
    c2.metric("Flujo 30d", f"$ {float(flujo.iloc[-1]['flujo_proyectado_usd']) if not flujo.empty else 0:,.2f}")
    c3.metric("Pagos 30d", f"$ {float(flujo.iloc[-1]['pagos_proximos_usd']) if not flujo.empty else 0:,.2f}")
    c4.metric("Cobros 30d", f"$ {float(flujo.iloc[-1]['cobros_esperados_usd']) if not flujo.empty else 0:,.2f}")
    c5.metric("Desviación egresos", f"$ {_safe_float(resumen.get('desviacion_egresos_usd')):,.2f}")

    score, estado_salud, recomendacion_salud = _salud_financiera_score(resumen, flujo)
    st.progress(score / 100)
    st.caption(f"**Score financiero:** {score}/100 · **Estado:** {estado_salud}. {recomendacion_salud}")

    # =========================
    # NAVEGACIÓN
    # =========================
    tabs = st.tabs([
        "Flujo de Caja",
        "Presupuesto",
        "Ingresos",
        "Costos",
        "KPIs",
        "Escenarios",
        "Alertas"
    ])

    # =========================
    # FLUJO DE CAJA
    # =========================
    with tabs[0]:
        st.subheader("💸 Flujo de caja proyectado")
        st.dataframe(flujo, use_container_width=True, hide_index=True)

        if not flujo.empty:
            col_fecha = "fecha" if "fecha" in flujo.columns else "fecha_corte" if "fecha_corte" in flujo.columns else None
            if col_fecha:
                st.line_chart(flujo.set_index(col_fecha)[["flujo_proyectado_usd"]])
            else:
                st.line_chart(flujo[["flujo_proyectado_usd"]])

        st.download_button(
            "Exportar CSV",
            flujo.to_csv(index=False).encode(),
            f"flujo_{periodo}.csv",
        )

    # =========================
    # PRESUPUESTO
    # =========================
    with tabs[1]:
        st.subheader("📅 Presupuesto operativo")

        st.dataframe(presupuesto, use_container_width=True, hide_index=True)

        with st.form("form_presupuesto", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoría")
            tipo = c2.selectbox("Tipo", ["ingreso", "egreso"])
            monto = c3.number_input("Monto", 0.0)

            c4, c5 = st.columns(2)
            meta_kpi = c4.number_input("Meta KPI", 0.0)
            notas = c5.text_input("Notas")

            submit = st.form_submit_button("Guardar")

        if submit:
            with db_transaction() as conn:
                guardar_presupuesto_operativo(
                    conn,
                    periodo=periodo,
                    categoria=categoria,
                    tipo=tipo,
                    monto_presupuestado_usd=float(monto),
                    meta_kpi_usd=float(meta_kpi),
                    usuario=usuario,
                    notas=notas,
                )
            st.success("Guardado")
            st.rerun()

        st.subheader("Resumen")
        st.json(resumen)

    # =========================
    # INGRESOS (NUEVO)
    # =========================
    with tabs[2]:
        st.subheader("📈 Proyección de ingresos")

        ingresos_df = _placeholder_df(["linea", "cantidad", "precio", "total"])

        with st.form("form_ingresos"):
            c1, c2, c3 = st.columns(3)
            linea = c1.text_input("Línea negocio")
            cantidad = c2.number_input("Cantidad", 0)
            precio = c3.number_input("Precio", 0.0)

            if st.form_submit_button("Agregar"):
                total = cantidad * precio
                st.success(f"Ingreso estimado: ${total:,.2f}")

        st.dataframe(ingresos_df, use_container_width=True)

    # =========================
    # COSTOS
    # =========================
    with tabs[3]:
        st.subheader("💸 Costos y gastos")

        costos_df = _placeholder_df(["categoria", "tipo", "monto"])

        with st.form("form_costos"):
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoría")
            tipo = c2.selectbox("Tipo", ["fijo", "variable"])
            monto = c3.number_input("Monto", 0.0)

            if st.form_submit_button("Agregar costo"):
                st.success("Costo registrado")

        st.dataframe(costos_df, use_container_width=True)

    # =========================
    # KPIs
    # =========================
    with tabs[4]:
        st.subheader("📊 Indicadores financieros")

        ingresos = float(resumen.get("ingresos_totales_usd", 0))
        egresos = float(resumen.get("egresos_totales_usd", 0))
        utilidad = ingresos - egresos

        k1, k2, k3 = st.columns(3)
        k1.metric("Ingresos", f"$ {ingresos:,.2f}")
        k2.metric("Egresos", f"$ {egresos:,.2f}")
        k3.metric("Utilidad", f"$ {utilidad:,.2f}")

        if ingresos > 0:
            margen = (utilidad / ingresos) * 100
            st.metric("Margen (%)", f"{margen:.2f}%")

    # =========================
    # ALERTAS
    # =========================
    with tabs[5]:
        st.subheader("🧪 Simulador de escenarios")
        st.caption("Proyecta impacto en caja antes de tomar decisiones de crecimiento, recorte o inversión.")

        escenario_nombre = st.text_input("Nombre del escenario", value="Escenario Base")

        e1, e2, e3 = st.columns(3)
        var_ingresos = e1.slider("Variación ingresos (%)", min_value=-50, max_value=100, value=10, step=5)
        var_egresos = e2.slider("Variación egresos (%)", min_value=-50, max_value=100, value=5, step=5)
        var_cobranza = e3.slider("Mejora cobranza CxC (%)", min_value=0, max_value=100, value=15, step=5)

        ingresos_base = _safe_float(resumen.get("ingresos_ejecutados_usd"))
        egresos_base = _safe_float(resumen.get("egresos_ejecutados_usd"))
        cobros_base = _safe_float(flujo.iloc[-1]["cobros_esperados_usd"]) if not flujo.empty else 0.0
        pagos_base = _safe_float(flujo.iloc[-1]["pagos_proximos_usd"]) if not flujo.empty else 0.0
        saldo_actual = _safe_float(flujo.iloc[0]["saldo_actual_usd"]) if not flujo.empty else 0.0

        ingresos_esc = ingresos_base * (1 + var_ingresos / 100)
        egresos_esc = egresos_base * (1 + var_egresos / 100)
        cobros_esc = cobros_base * (1 + var_cobranza / 100)
        flujo_esc = cobros_esc + ingresos_esc - pagos_base - egresos_esc
        saldo_esc = saldo_actual + flujo_esc

        s1, s2, s3 = st.columns(3)
        s1.metric("Flujo estimado escenario", f"$ {flujo_esc:,.2f}")
        s2.metric("Saldo proyectado escenario", f"$ {saldo_esc:,.2f}")
        s3.metric("Variación vs base", f"$ {saldo_esc - (saldo_actual + (cobros_base + ingresos_base - pagos_base - egresos_base)):,.2f}")

        st.info(
            f"{escenario_nombre}: con estos supuestos, tu caja proyectada a 30 días sería de $ {saldo_esc:,.2f}."
        )

    with tabs[6]:
        st.subheader("🚨 Alertas financieras")

        st.dataframe(alertas, use_container_width=True, hide_index=True)

        st.download_button(
            "Exportar alertas",
            alertas.to_csv(index=False).encode(),
            f"alertas_{periodo}.csv",
        )
