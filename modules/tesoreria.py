from __future__ import annotations

from datetime import date, timedelta
import streamlit as st

from database.connection import db_transaction
from services.tesoreria_service import (
    ORIGENES_TESORERIA,
    registrar_movimiento_tesoreria,
    listar_movimientos_tesoreria,
    listar_vencimientos,
    obtener_resumen_tesoreria,
)


def _render_metricas(resumen: dict[str, float]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Saldo neto período", f"$ {resumen['saldo_neto_periodo_usd']:,.2f}")
    c2.metric("Ingresos", f"$ {resumen['total_ingresos_usd']:,.2f}")
    c3.metric("Egresos", f"$ {resumen['total_egresos_usd']:,.2f}")
    c4.metric("Flujo neto", f"$ {resumen['flujo_neto_usd']:,.2f}")
    c5.metric("CXP próximas", f"$ {resumen['cxp_proximas_usd']:,.2f}")
    c6.metric("CXC pendientes", f"$ {resumen['cxc_pendientes_usd']:,.2f}")


def _render_form_ajuste_manual(usuario: str) -> None:
    st.write("### Registrar ajuste manual")
    with st.form("tesoreria_ajuste_manual", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tipo = c1.selectbox("Tipo", ["ingreso", "egreso"])
        monto_usd = c2.number_input("Monto USD", min_value=0.01, value=0.01, format="%.2f")
        fecha_mov = c3.date_input("Fecha", value=date.today())

        c4, c5, c6 = st.columns(3)
        moneda = c4.selectbox("Moneda", ["USD", "BS", "USDT", "KONTIGO"])
        tasa = c5.number_input("Tasa", min_value=0.0001, value=1.0, format="%.4f")
        metodo_pago = c6.selectbox("Método", ["efectivo", "transferencia", "zelle", "binance", "pago móvil", "kontigo"])

        descripcion = st.text_input("Descripción", placeholder="Ajuste de caja, aporte de socios, retiro, etc.")
        referencia_id = st.number_input("Referencia opcional", min_value=0, value=0, step=1)
        submit = st.form_submit_button("Guardar ajuste")

    if not submit:
        return

    with db_transaction() as conn:
        registrar_movimiento_tesoreria(
            conn,
            tipo=tipo,
            origen="ajuste_manual",
            referencia_id=int(referencia_id) if referencia_id else None,
            descripcion=descripcion,
            monto_usd=float(monto_usd),
            moneda=moneda,
            monto_moneda=float(monto_usd if moneda == "USD" else monto_usd * tasa),
            tasa_cambio=float(tasa),
            metodo_pago=metodo_pago,
            usuario=usuario,
            allow_duplicate=referencia_id == 0,
        )
    st.success("Ajuste manual registrado correctamente.")
    st.rerun()


def render_tesoreria(usuario: str) -> None:
    st.title("🏦 Tesorería / Flujo de caja")
    st.caption("Libro operativo de caja para movimientos reales, trazabilidad por origen y vencimientos.")

    filtro1, filtro2, filtro3, filtro4 = st.columns(4)
    fecha_desde = filtro1.date_input("Desde", value=date.today() - timedelta(days=30))
    fecha_hasta = filtro2.date_input("Hasta", value=date.today())
    tipo = filtro3.selectbox("Tipo", ["Todos", "ingreso", "egreso"])
    origen = filtro4.selectbox("Origen", ["Todos"] + list(ORIGENES_TESORERIA))

    filtro5, _ = st.columns([1, 3])
    metodo_pago = filtro5.selectbox(
        "Método de pago",
        ["Todos", "efectivo", "transferencia", "zelle", "binance", "pago móvil", "kontigo", "usd", "bs", "usdt"],
    )

    with db_transaction() as conn:
        resumen = obtener_resumen_tesoreria(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
        )
        movimientos = listar_movimientos_tesoreria(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
            tipo=None if tipo == "Todos" else tipo,
            origen=None if origen == "Todos" else origen,
            metodo_pago=None if metodo_pago == "Todos" else metodo_pago,
        )
        vencimientos = listar_vencimientos(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
        )

    _render_metricas(resumen)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Movimientos", "Vencimientos", "Resumen por origen", "Ajustes manuales"]
    )

    with tab1:
        st.write("### Movimientos de tesorería")
        if movimientos.empty:
            st.info("No hay movimientos registrados para el filtro seleccionado.")
        else:
            st.dataframe(movimientos, use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar CSV",
                data=movimientos.to_csv(index=False).encode("utf-8"),
                file_name="tesoreria_movimientos.csv",
                mime="text/csv",
            )

            st.write("### Ver detalle de referencia")
            opciones = {
                f"#{int(row.id)} · {row.tipo} · {row.origen} · ${float(row.monto_usd):,.2f}": int(row.id)
                for row in movimientos.itertuples()
            }
            seleccionado = st.selectbox("Movimiento", list(opciones.keys()))
            detalle = movimientos[movimientos["id"] == opciones[seleccionado]].iloc[0].to_dict()
            st.json(detalle)

    with tab2:
        st.write("### Próximos vencimientos")
        cxp = vencimientos["cxp_proximas"]
        cxc = vencimientos["cxc_pendientes"]
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Cuentas por pagar próximas a vencer")
            if cxp.empty:
                st.info("Sin cuentas por pagar en el rango.")
            else:
                st.dataframe(cxp, use_container_width=True, hide_index=True)
        with c2:
            st.caption("Cuentas por cobrar pendientes")
            if cxc.empty:
                st.info("Sin cuentas por cobrar pendientes.")
            else:
                st.dataframe(cxc, use_container_width=True, hide_index=True)

    with tab3:
        st.write("### Resumen por origen")
        if movimientos.empty:
            st.info("Sin datos para resumir.")
        else:
            resumen_origen = (
                movimientos.groupby(["origen", "tipo"], as_index=False)["monto_usd"]
                .sum()
                .sort_values(["tipo", "monto_usd"], ascending=[True, False])
            )
            pivot = resumen_origen.pivot_table(
                index="origen",
                columns="tipo",
                values="monto_usd",
                aggfunc="sum",
                fill_value=0.0,
            ).reset_index()
            if "ingreso" not in pivot.columns:
                pivot["ingreso"] = 0.0
            if "egreso" not in pivot.columns:
                pivot["egreso"] = 0.0
            pivot["flujo_neto"] = pivot["ingreso"] - pivot["egreso"]
            st.dataframe(pivot, use_container_width=True, hide_index=True)
            st.bar_chart(resumen_origen.set_index(["origen", "tipo"])["monto_usd"])

    with tab4:
        _render_form_ajuste_manual(usuario)
