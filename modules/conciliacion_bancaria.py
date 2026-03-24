from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from database.connection import db_transaction
from services.conciliacion_service import (
    cerrar_periodo,
    conciliar_movimientos,
    listar_cierres_periodo,
    listar_movimientos_bancarios,
    listar_movimientos_tesoreria_pendientes,
    obtener_reporte_fiscal_simple,
    obtener_resumen_cierre_periodo,
    obtener_resumen_conciliacion,
    periodo_desde_fecha,
    registrar_movimiento_bancario,
    sugerir_cruces,
)


def _render_resumen(fecha_desde: str, fecha_hasta: str) -> None:
    with db_transaction() as conn:
        resumen = obtener_resumen_conciliacion(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Mov. banco", int(resumen["total_banco"]))
    c2.metric("Pendientes", int(resumen["pendientes"]))
    c3.metric("Conciliados", int(resumen["conciliados"]))
    c4.metric("Con diferencia", int(resumen["con_diferencia"]))
    c5.metric("Dif. acumulada", f"$ {float(resumen['diferencia_total_usd']):,.2f}")


def _render_importacion_manual(usuario: str) -> None:
    st.subheader("➕ Registrar movimiento bancario (manual)")
    with st.form("conciliacion_form_banco", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=date.today()).isoformat()
        tipo = c2.selectbox("Tipo", ["ingreso", "egreso"], index=0)
        cuenta = c3.text_input("Cuenta bancaria", value="Banco principal")

        descripcion = st.text_input("Descripción", placeholder="Transferencia cliente / pago proveedor / comisión...")
        c4, c5, c6 = st.columns(3)
        monto = c4.number_input("Monto", min_value=0.01, step=0.01, format="%.2f")
        referencia = c5.text_input("Referencia banco", placeholder="Nro operación")
        moneda = c6.selectbox("Moneda", ["USD", "VES", "EUR"], index=0)
        saldo_reportado = st.number_input("Saldo reportado (opcional)", min_value=0.0, step=0.01, format="%.2f")

        submit = st.form_submit_button("💾 Guardar movimiento bancario", use_container_width=True)

    if submit:
        try:
            with db_transaction() as conn:
                registrar_movimiento_bancario(
                    conn,
                    fecha=fecha,
                    descripcion=descripcion,
                    monto=float(monto),
                    tipo=tipo,
                    cuenta_bancaria=cuenta,
                    referencia_banco=referencia,
                    usuario=usuario,
                    moneda=moneda,
                    saldo_reportado=float(saldo_reportado) if saldo_reportado > 0 else None,
                )
            st.success("Movimiento bancario registrado.")
        except Exception as exc:
            st.error("No se pudo registrar el movimiento bancario.")
            st.exception(exc)


def _render_conciliacion_manual(usuario: str, fecha_desde: str, fecha_hasta: str) -> None:
    st.subheader("🔄 Conciliación manual")
    with db_transaction() as conn:
        banco_pendiente = listar_movimientos_bancarios(
            conn,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado_conciliacion="pendiente",
        )
        tes_pendiente = listar_movimientos_tesoreria_pendientes(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        sugeridos = sugerir_cruces(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    if banco_pendiente.empty:
        st.success("No hay movimientos bancarios pendientes en el rango.")
        return
    if tes_pendiente.empty:
        st.warning("No hay movimientos de tesorería pendientes para cruzar.")
        return

    if not sugeridos.empty:
        st.caption("Sugerencias automáticas por monto/tipo/fecha.")
        st.dataframe(sugeridos.head(20), use_container_width=True, hide_index=True)

    banco_options = [
        f"#{int(row.id)} | {row.fecha} | {row.tipo} | $ {float(row.monto):,.2f} | {row.descripcion}"
        for row in banco_pendiente.itertuples(index=False)
    ]
    tes_options = [
        f"#{int(row.id)} | {row.fecha} | {row.tipo} | $ {float(row.monto_usd):,.2f} | {row.origen}"
        for row in tes_pendiente.itertuples(index=False)
    ]

    c1, c2 = st.columns(2)
    banco_sel = c1.selectbox("Movimiento bancario", banco_options)
    tes_sel = c2.selectbox("Movimiento tesorería", tes_options)
    notas = st.text_area("Notas de conciliación", placeholder="Comentario opcional de soporte.")

    if st.button("✅ Conciliar selección", use_container_width=True):
        banco_id = int(banco_sel.split("|", 1)[0].replace("#", "").strip())
        tes_id = int(tes_sel.split("|", 1)[0].replace("#", "").strip())
        try:
            with db_transaction() as conn:
                conciliar_movimientos(
                    conn,
                    banco_movimiento_id=banco_id,
                    tesoreria_movimiento_id=tes_id,
                    usuario=usuario,
                    notas=notas,
                )
            st.success("Conciliación registrada.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo completar la conciliación.")
            st.exception(exc)


def _render_diferencias_y_exportacion(fecha_desde: str, fecha_hasta: str) -> None:
    st.subheader("📤 Resultados, diferencias y exportación")
    with db_transaction() as conn:
        resultados = listar_movimientos_bancarios(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    if resultados.empty:
        st.info("Sin movimientos bancarios para mostrar.")
        return

    diferencias = resultados[resultados["estado_conciliacion"] == "con_diferencia"]
    pend = resultados[resultados["estado_conciliacion"] == "pendiente"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Movimientos con diferencia**")
        if diferencias.empty:
            st.caption("Sin diferencias detectadas.")
        else:
            st.dataframe(diferencias, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Pendientes de conciliación**")
        if pend.empty:
            st.caption("Sin pendientes.")
        else:
            st.dataframe(pend, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Exportar conciliación (CSV)",
        data=resultados.to_csv(index=False).encode("utf-8"),
        file_name=f"conciliacion_bancaria_{fecha_desde}_{fecha_hasta}.csv",
        mime="text/csv",
    )


def _render_cierre_periodo(usuario: str) -> None:
    st.subheader("🔒 Cierre de período (diario / mensual)")
    c1, c2, c3 = st.columns(3)
    tipo_cierre = c1.selectbox("Tipo de cierre", ["mensual", "diario"], index=0)
    hoy = date.today()
    inicio_default = hoy.replace(day=1) if tipo_cierre == "mensual" else hoy
    fecha_desde = c2.date_input("Desde", value=inicio_default, key=f"cierre_desde_{tipo_cierre}").isoformat()
    fecha_hasta = c3.date_input("Hasta", value=hoy, key=f"cierre_hasta_{tipo_cierre}").isoformat()
    periodo_default = periodo_desde_fecha(hoy if tipo_cierre == "diario" else date.fromisoformat(fecha_hasta), tipo_cierre=tipo_cierre)
    periodo = st.text_input("Código período", value=periodo_default)

    with db_transaction() as conn:
        resumen = obtener_resumen_cierre_periodo(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Ingresos", f"$ {float(resumen['total_ingresos_usd']):,.2f}")
    k2.metric("Egresos", f"$ {float(resumen['total_egresos_usd']):,.2f}")
    k3.metric("Saldo neto", f"$ {float(resumen['saldo_neto_usd']):,.2f}")
    k4.metric("Banco sin conciliar", int(resumen["movimientos_bancarios_pendientes"]))
    k5.metric("Tesorería sin conciliar", int(resumen["movimientos_tesoreria_pendientes"]))

    notas = st.text_area("Notas del cierre", placeholder="Observaciones de control interno / aprobaciones.")
    if st.button("🧷 Ejecutar cierre", use_container_width=True):
        try:
            with db_transaction() as conn:
                cerrar_periodo(
                    conn,
                    periodo=periodo,
                    tipo_cierre=tipo_cierre,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    usuario=usuario,
                    notas=notas,
                )
            st.success("Cierre registrado y período marcado como cerrado.")
        except Exception as exc:
            st.error("No se pudo ejecutar el cierre.")
            st.exception(exc)

    with db_transaction() as conn:
        cierres = listar_cierres_periodo(conn)
        fiscal = obtener_reporte_fiscal_simple(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    st.markdown("**Historial de cierres**")
    if cierres.empty:
        st.caption("Aún sin cierres registrados.")
    else:
        st.dataframe(cierres, use_container_width=True, hide_index=True)

    st.markdown("**Base para reporte fiscal simple del período**")
    st.dataframe(fiscal, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Exportar base fiscal (CSV)",
        data=fiscal.to_csv(index=False).encode("utf-8"),
        file_name=f"base_fiscal_{fecha_desde}_{fecha_hasta}.csv",
        mime="text/csv",
    )


def render_conciliacion_bancaria(usuario: str) -> None:
    st.title("🏛️ Conciliación bancaria y cierre de período")
    st.caption("Cruce incremental entre banco y tesorería con trazabilidad para cierres diarios/mensuales.")

    c1, c2 = st.columns(2)
    hoy = date.today()
    fecha_desde = c1.date_input("Desde", value=hoy - timedelta(days=30), key="conc_desde").isoformat()
    fecha_hasta = c2.date_input("Hasta", value=hoy, key="conc_hasta").isoformat()

    _render_resumen(fecha_desde, fecha_hasta)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["➕ Banco manual", "🔄 Conciliar", "📤 Diferencias y export", "🔒 Cierre de período"]
    )
    with tab1:
        _render_importacion_manual(usuario)
    with tab2:
        _render_conciliacion_manual(usuario, fecha_desde, fecha_hasta)
    with tab3:
        _render_diferencias_y_exportacion(fecha_desde, fecha_hasta)
    with tab4:
        _render_cierre_periodo(usuario)
