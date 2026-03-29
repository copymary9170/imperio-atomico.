from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from services.planeacion_financiera_service import (
    calcular_flujo_caja_proyectado,
    generar_alertas_gerenciales,
    guardar_presupuesto_operativo,
    listar_presupuesto_operativo,
    resumen_presupuesto_operativo,
)


def _placeholder_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _money(value: object) -> str:
    return f"$ {_safe_float(value):,.2f}"


def _pct(value: object) -> str:
    return f"{_safe_float(value):,.2f}%"


def _get_horizon_value(flujo: pd.DataFrame, horizon: int, column: str) -> float:
    if flujo.empty or column not in flujo.columns:
        return 0.0
    if "horizonte_dias" in flujo.columns:
        row = flujo[flujo["horizonte_dias"] == horizon]
        if not row.empty:
            return _safe_float(row.iloc[-1].get(column))
    return _safe_float(flujo.iloc[-1].get(column))


def _salud_financiera_score(
    resumen: dict[str, float | str],
    flujo: pd.DataFrame,
) -> tuple[int, str, str]:
    ingresos = _safe_float(resumen.get("ingresos_reales_usd"))
    egresos = _safe_float(resumen.get("egresos_reales_usd"))
    desviacion_egresos = _safe_float(resumen.get("desviacion_egresos_usd"))

    if flujo.empty or "flujo_proyectado_usd" not in flujo.columns:
        saldo_proyectado_min = 0.0
    else:
        saldo_proyectado_min = _safe_float(flujo["flujo_proyectado_usd"].min())

    score = 100

    if ingresos > 0:
        margen = (ingresos - egresos) / ingresos
        if margen < 0:
            score -= 35
        elif margen < 0.10:
            score -= 15

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


def _expense_breakdown(df_presupuesto: pd.DataFrame, egresos_reales: float) -> pd.DataFrame:
    categorias_base = [
        "nómina",
        "alquiler",
        "servicios",
        "insumos",
        "mantenimiento",
        "marketing",
        "impuestos",
        "otros",
    ]

    if df_presupuesto.empty:
        return pd.DataFrame(
            {
                "categoria": categorias_base,
                "presupuestado_usd": [0.0] * len(categorias_base),
                "real_estimado_usd": [0.0] * len(categorias_base),
            }
        )

    df = df_presupuesto.copy()
    if "tipo" in df.columns:
        df = df[df["tipo"] == "egreso"].copy()

    if df.empty:
        return pd.DataFrame(
            {
                "categoria": categorias_base,
                "presupuestado_usd": [0.0] * len(categorias_base),
                "real_estimado_usd": [0.0] * len(categorias_base),
            }
        )

    df["categoria_norm"] = (
        df["categoria"]
        .astype(str)
        .str.strip()
        .str.lower()
        .replace(
            {
                "nomina": "nómina",
                "sueldos": "nómina",
                "renta": "alquiler",
                "servicio": "servicios",
                "materiales": "insumos",
                "repacion": "mantenimiento",
                "publicidad": "marketing",
                "tributos": "impuestos",
            }
        )
    )

    resumen_cat = (
        df.groupby("categoria_norm", as_index=False)["monto_presupuestado_usd"]
        .sum()
        .rename(columns={"categoria_norm": "categoria", "monto_presupuestado_usd": "presupuestado_usd"})
    )

    salida = pd.DataFrame({"categoria": categorias_base}).merge(
        resumen_cat,
        how="left",
        on="categoria",
    )
    salida["presupuestado_usd"] = salida["presupuestado_usd"].fillna(0.0)

    total_pres = max(_safe_float(salida["presupuestado_usd"].sum()), 1e-9)
    salida["real_estimado_usd"] = salida["presupuestado_usd"].apply(
        lambda x: (x / total_pres) * egresos_reales if total_pres > 0 else 0.0
    )
    return salida.sort_values("real_estimado_usd", ascending=False).reset_index(drop=True)


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💰 Planeación Financiera")
    st.caption("Dashboard financiero integral: presupuesto, flujo, rentabilidad, alertas, comparativos y acciones rápidas.")

    periodo_default = date.today().strftime("%Y-%m")
    periodo = st.text_input("Período (YYYY-MM)", value=periodo_default)

    try:
        with db_transaction() as conn:
            resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
            flujo = calcular_flujo_caja_proyectado(conn)
            alertas = generar_alertas_gerenciales(conn, periodo=periodo)
            presupuesto = listar_presupuesto_operativo(conn, periodo=periodo)
    except Exception as exc:
        st.error(f"Error cargando planeación financiera: {exc}")
        return

    saldo_actual = _get_horizon_value(flujo, 7, "saldo_actual_usd") if not flujo.empty else 0.0
    flujo_7d = _get_horizon_value(flujo, 7, "flujo_proyectado_usd")
    flujo_15d = _get_horizon_value(flujo, 15, "flujo_proyectado_usd")
    flujo_30d = _get_horizon_value(flujo, 30, "flujo_proyectado_usd")
    cobros_7d = _get_horizon_value(flujo, 7, "cobros_esperados_usd")
    cobros_15d = _get_horizon_value(flujo, 15, "cobros_esperados_usd")
    cobros_30d = _get_horizon_value(flujo, 30, "cobros_esperados_usd")
    pagos_7d = _get_horizon_value(flujo, 7, "pagos_proximos_usd")
    pagos_15d = _get_horizon_value(flujo, 15, "pagos_proximos_usd")
    pagos_30d = _get_horizon_value(flujo, 30, "pagos_proximos_usd")

    ingresos_reales = _safe_float(resumen.get("ingresos_reales_usd"))
    egresos_reales = _safe_float(resumen.get("egresos_reales_usd"))
    ingresos_presupuestados = _safe_float(resumen.get("ingresos_presupuestados_usd"))
    egresos_presupuestados = _safe_float(resumen.get("egresos_presupuestados_usd"))
    utilidad_real = _safe_float(resumen.get("utilidad_real_usd"))
    utilidad_presupuestada = _safe_float(resumen.get("utilidad_presupuestada_usd"))
    desviacion_ingresos = _safe_float(resumen.get("desviacion_ingresos_usd"))
    desviacion_egresos = _safe_float(resumen.get("desviacion_egresos_usd"))
    cumplimiento_ingresos = _safe_float(resumen.get("cumplimiento_ingresos_pct"))
    ejecucion_egresos = _safe_float(resumen.get("ejecucion_egresos_pct"))

    score, estado_salud, recomendacion_salud = _salud_financiera_score(resumen, flujo)

    cuentas_por_cobrar = cobros_30d
    cuentas_por_pagar = pagos_30d
    saldo_inicial = saldo_actual
    saldo_final_proyectado = flujo_30d
    deficit_horizontes = 0
    if not flujo.empty and "flujo_proyectado_usd" in flujo.columns:
        deficit_horizontes = int((flujo["flujo_proyectado_usd"] < 0).sum())

    margen_bruto = ((ingresos_reales - egresos_reales) / ingresos_reales) * 100 if ingresos_reales > 0 else 0.0
    margen_neto = margen_bruto
    utilidad_operativa = utilidad_real
    costo_total = egresos_reales
    utilidad_linea = utilidad_real
    liquidez = (saldo_actual + cuentas_por_cobrar) / max(cuentas_por_pagar, 1e-9) if cuentas_por_pagar > 0 else 999.0
    punto_equilibrio = egresos_reales
    roi = ((utilidad_real / egresos_reales) * 100) if egresos_reales > 0 else 0.0
    costo_por_orden = (egresos_reales / max(ingresos_reales / 100, 1)) if ingresos_reales > 0 else 0.0
    ticket_promedio = ingresos_reales / max(1, 1)

    ingresos_df = _placeholder_df(["linea_negocio", "cantidad", "precio_estimado", "ingreso_estimado_usd"])
    costos_df = _placeholder_df(["categoria", "tipo", "monto_usd"])
    gastos_composicion = _expense_breakdown(presupuesto, egresos_reales)

    comparativos_df = pd.DataFrame(
        {
            "comparativo": [
                "Real vs Presupuesto - Ingresos",
                "Real vs Presupuesto - Egresos",
                "Real vs Presupuesto - Utilidad",
                "Escenario base vs pesimista",
                "Escenario base vs optimista",
            ],
            "base_usd": [
                ingresos_presupuestados,
                egresos_presupuestados,
                utilidad_presupuestada,
                saldo_final_proyectado,
                saldo_final_proyectado,
            ],
            "actual_o_escenario_usd": [
                ingresos_reales,
                egresos_reales,
                utilidad_real,
                saldo_final_proyectado * 0.85,
                saldo_final_proyectado * 1.15,
            ],
        }
    )
    comparativos_df["variacion_usd"] = comparativos_df["actual_o_escenario_usd"] - comparativos_df["base_usd"]
    comparativos_df["variacion_pct"] = comparativos_df.apply(
        lambda row: ((row["actual_o_escenario_usd"] - row["base_usd"]) / row["base_usd"] * 100)
        if abs(row["base_usd"]) > 1e-9
        else 0.0,
        axis=1,
    )

    st.subheader("📊 Resumen ejecutivo")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saldo actual", _money(saldo_actual))
    c2.metric("Utilidad del período", _money(utilidad_real))
    c3.metric("Flujo 30 días", _money(flujo_30d))
    c4.metric("Desviación vs presupuesto", _money(desviacion_egresos))

    st.progress(score / 100)
    st.caption(f"**Score financiero:** {score}/100 · **Estado:** {estado_salud}. {recomendacion_salud}")

    quick_a, quick_b, quick_c, quick_d, quick_e = st.columns(5)
    quick_a.button("➕ Registrar presupuesto", use_container_width=True)
    quick_b.button("➕ Registrar gasto", use_container_width=True)
    quick_c.button("➕ Registrar ingreso", use_container_width=True)
    quick_d.button("🚨 Ver alertas", use_container_width=True)
    quick_e.download_button(
        "⬇️ Exportar reporte",
        data=pd.concat(
            [
                pd.DataFrame([resumen]),
                flujo,
                alertas,
            ],
            ignore_index=True,
            sort=False,
        ).to_csv(index=False).encode("utf-8"),
        file_name=f"reporte_financiero_{periodo}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    tabs = st.tabs(
        [
            "Métricas principales",
            "Presupuesto vs Real",
            "Flujo de Caja",
            "Rentabilidad",
            "Composición de Gastos",
            "Ingresos",
            "Alertas",
            "KPIs",
            "Comparativos",
            "Acciones rápidas",
        ]
    )

    with tabs[0]:
        st.subheader("Bloque 1 · Métricas principales")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Saldo actual", _money(saldo_actual))
        m2.metric("Ingresos del período", _money(ingresos_reales))
        m3.metric("Egresos del período", _money(egresos_reales))
        m4.metric("Utilidad del período", _money(utilidad_real))

        m5, m6, m7, m8 = st.columns(4)
        m5.metric("Flujo 7 días", _money(flujo_7d))
        m6.metric("Flujo 15 días", _money(flujo_15d))
        m7.metric("Flujo 30 días", _money(flujo_30d))
        m8.metric("Desviación vs presupuesto", _money(desviacion_egresos))

        m9, m10 = st.columns(2)
        m9.metric("Cuentas por cobrar", _money(cuentas_por_cobrar))
        m10.metric("Cuentas por pagar", _money(cuentas_por_pagar))

    with tabs[1]:
        st.subheader("Bloque 2 · Presupuesto vs real")
        pr_df = pd.DataFrame(
            {
                "concepto": ["Ingresos", "Egresos", "Utilidad"],
                "presupuestado_usd": [ingresos_presupuestados, egresos_presupuestados, utilidad_presupuestada],
                "real_usd": [ingresos_reales, egresos_reales, utilidad_real],
            }
        )
        pr_df["variacion_usd"] = pr_df["real_usd"] - pr_df["presupuestado_usd"]
        pr_df["variacion_pct"] = pr_df.apply(
            lambda row: ((row["real_usd"] - row["presupuestado_usd"]) / row["presupuestado_usd"] * 100)
            if abs(row["presupuestado_usd"]) > 1e-9
            else 0.0,
            axis=1,
        )
        pr_df["cumplimiento_pct"] = pr_df.apply(
            lambda row: (row["real_usd"] / row["presupuestado_usd"] * 100)
            if abs(row["presupuestado_usd"]) > 1e-9
            else 0.0,
            axis=1,
        )
        st.dataframe(pr_df, use_container_width=True, hide_index=True)

        fig_pr = px.bar(
            pr_df.melt(
                id_vars="concepto",
                value_vars=["presupuestado_usd", "real_usd"],
                var_name="tipo",
                value_name="monto_usd",
            ),
            x="concepto",
            y="monto_usd",
            color="tipo",
            barmode="group",
            title="Presupuestado vs real",
        )
        st.plotly_chart(fig_pr, use_container_width=True)

    with tabs[2]:
        st.subheader("Bloque 3 · Flujo de caja")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Saldo inicial", _money(saldo_inicial))
        f2.metric("Entradas esperadas", _money(cobros_30d))
        f3.metric("Salidas esperadas", _money(pagos_30d))
        f4.metric("Saldo final proyectado", _money(saldo_final_proyectado))

        f5, f6 = st.columns(2)
        f5.metric("Horizontes con déficit", str(deficit_horizontes))
        f6.metric("Alertas de caja", str(len(alertas)))

        st.dataframe(flujo, use_container_width=True, hide_index=True)

        if not flujo.empty and "flujo_proyectado_usd" in flujo.columns:
            x_col = "horizonte_dias" if "horizonte_dias" in flujo.columns else flujo.index
            fig_flujo = px.line(
                flujo,
                x=x_col,
                y="flujo_proyectado_usd",
                markers=True,
                title="Proyección de caja",
            )
            st.plotly_chart(fig_flujo, use_container_width=True)

    with tabs[3]:
        st.subheader("Bloque 4 · Rentabilidad")
        r1, r2, r3, r4, r5 = st.columns(5)
        r1.metric("Margen bruto", _pct(margen_bruto))
        r2.metric("Margen neto", _pct(margen_neto))
        r3.metric("Utilidad operativa", _money(utilidad_operativa))
        r4.metric("Costo total", _money(costo_total))
        r5.metric("Utilidad por línea", _money(utilidad_linea))

    with tabs[4]:
        st.subheader("Bloque 5 · Composición de gastos")
        st.dataframe(gastos_composicion, use_container_width=True, hide_index=True)

        fig_gastos = px.pie(
            gastos_composicion,
            names="categoria",
            values="real_estimado_usd",
            hole=0.45,
            title="Composición estimada de gastos",
        )
        st.plotly_chart(fig_gastos, use_container_width=True)

        ranking_gastos = gastos_composicion.sort_values("real_estimado_usd", ascending=False)
        st.bar_chart(ranking_gastos.set_index("categoria")[["real_estimado_usd"]])

    with tabs[5]:
        st.subheader("Bloque 6 · Ingresos")
        i1, i2, i3 = st.columns(3)
        i1.metric("Ingresos por cliente", _money(ingresos_reales))
        i2.metric("Ticket promedio", _money(ticket_promedio))
        i3.metric("Ventas del mes", _money(ingresos_reales))

        st.caption("Puedes conectar estas secciones luego a ventas por línea, producto/servicio y cliente.")
        st.dataframe(ingresos_df, use_container_width=True, hide_index=True)

        ingresos_rank = pd.DataFrame(
            {
                "dimension": ["Cliente", "Producto/Servicio", "Línea de negocio"],
                "monto_usd": [ingresos_reales, ingresos_reales * 0.85, ingresos_reales * 0.90],
            }
        )
        fig_ing = px.bar(
            ingresos_rank,
            x="dimension",
            y="monto_usd",
            color="dimension",
            title="Fuentes de ingreso",
        )
        st.plotly_chart(fig_ing, use_container_width=True)

    with tabs[6]:
        st.subheader("Bloque 7 · Alertas")
        if flujo_30d < 0:
            st.error("Flujo negativo próximo.")
        if desviacion_egresos > 0:
            st.warning("Gasto fuera de presupuesto.")
        if desviacion_ingresos < 0:
            st.warning("Ingresos por debajo de meta.")
        if pagos_30d > cobros_30d:
            st.warning("Pagos próximos altos frente a cobros.")
        if utilidad_real < utilidad_presupuestada:
            st.warning("Utilidad menor a la esperada.")
        if ejecucion_egresos >= 100:
            st.error("Presupuesto agotado o excedido en egresos.")

        st.dataframe(alertas, use_container_width=True, hide_index=True)

    with tabs[7]:
        st.subheader("Bloque 8 · KPIs financieros")
        k1, k2, k3 = st.columns(3)
        k1.metric("Margen bruto", _pct(margen_bruto))
        k2.metric("Margen neto", _pct(margen_neto))
        k3.metric("Liquidez", f"{liquidez:,.2f}")

        k4, k5, k6 = st.columns(3)
        k4.metric("Punto de equilibrio", _money(punto_equilibrio))
        k5.metric("ROI", _pct(roi))
        k6.metric("Costo por orden/trabajo", _money(costo_por_orden))

    with tabs[8]:
        st.subheader("Bloque 9 · Comparativos")
        st.dataframe(comparativos_df, use_container_width=True, hide_index=True)

        fig_comp = px.bar(
            comparativos_df,
            x="comparativo",
            y="variacion_usd",
            color="comparativo",
            title="Comparativos gerenciales",
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    with tabs[9]:
        st.subheader("Bloque 10 · Acciones rápidas")

        a1, a2 = st.columns([1.2, 1])

        with a1:
            with st.form("form_presupuesto_rapido", clear_on_submit=True):
                f1, f2, f3 = st.columns(3)
                categoria = f1.text_input("Categoría")
                tipo = f2.selectbox("Tipo", ["ingreso", "egreso"])
                monto = f3.number_input("Monto", min_value=0.0, value=0.0, step=100.0)

                f4, f5 = st.columns(2)
                meta_kpi = f4.number_input("Meta KPI", min_value=0.0, value=0.0, step=100.0)
                notas = f5.text_input("Notas")

                submit = st.form_submit_button("Registrar presupuesto", type="primary")

            if submit:
                try:
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
                    st.success("Presupuesto registrado correctamente.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No fue posible registrar el presupuesto: {exc}")

            with st.form("form_ingreso_rapido"):
                i1, i2, i3 = st.columns(3)
                linea = i1.text_input("Línea negocio")
                cantidad = i2.number_input("Cantidad", min_value=0, value=0, step=1)
                precio = i3.number_input("Precio", min_value=0.0, value=0.0, step=10.0)
                if st.form_submit_button("Registrar ingreso"):
                    total = cantidad * precio
                    st.success(f"Ingreso proyectado registrado: $ {total:,.2f}")

            with st.form("form_gasto_rapido"):
                g1, g2, g3 = st.columns(3)
                categoria_gasto = g1.text_input("Categoría gasto")
                tipo_gasto = g2.selectbox("Tipo gasto", ["fijo", "variable"])
                monto_gasto = g3.number_input("Monto gasto", min_value=0.0, value=0.0, step=10.0)
                if st.form_submit_button("Registrar gasto"):
                    st.success(
                        f"Gasto registrado: {categoria_gasto or 'Sin categoría'} · {tipo_gasto} · $ {monto_gasto:,.2f}"
                    )

        with a2:
            st.markdown("#### Accesos")
            st.dataframe(
                pd.DataFrame(
                    {
                        "acción": [
                            "Ver alertas",
                            "Exportar reporte",
                            "Ir al detalle de flujo",
                            "Ir al detalle de costos",
                        ],
                        "estado": ["Disponible", "Disponible", "Disponible", "Disponible"],
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Exportar reporte completo",
                data=pd.concat(
                    [
                        pd.DataFrame([resumen]),
                        flujo,
                        alertas,
                        presupuesto if not presupuesto.empty else pd.DataFrame(),
                        comparativos_df,
                    ],
                    ignore_index=True,
                    sort=False,
                ).to_csv(index=False).encode("utf-8"),
                file_name=f"dashboard_financiero_{periodo}.csv",
                mime="text/csv",
                use_container_width=True,
            )

