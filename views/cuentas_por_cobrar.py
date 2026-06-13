from __future__ import annotations

import pandas as pd
import streamlit as st

from services.cuentas_por_cobrar_service import (
    crear_cuenta_por_cobrar,
    listar_abonos_cxc,
    listar_cuentas_por_cobrar,
    registrar_abono_cxc,
)


def render_cuentas_por_cobrar(usuario: str) -> None:
    st.subheader("💰 Cuentas por cobrar")
    st.caption("Controla clientes que dejaron pagos pendientes, abonos y saldos por cobrar.")

    tab_lista, tab_nueva, tab_abono = st.tabs(["Pendientes / historial", "Nueva cuenta", "Registrar abono"])

    with tab_lista:
        df = listar_cuentas_por_cobrar(limit=200)
        if df.empty:
            st.success("No hay cuentas por cobrar registradas.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            cuenta_id = st.number_input("Ver abonos de cuenta ID", min_value=1, value=int(df.iloc[0]["id"]), step=1)
            abonos = listar_abonos_cxc(int(cuenta_id))
            if abonos.empty:
                st.caption("Sin abonos para esa cuenta.")
            else:
                st.dataframe(abonos, use_container_width=True, hide_index=True)

    with tab_nueva:
        with st.form("form_nueva_cxc"):
            c1, c2, c3 = st.columns(3)
            cliente = c1.text_input("Cliente")
            concepto = c2.text_input("Concepto / trabajo")
            referencia = c3.text_input("Referencia")
            c4, c5, c6 = st.columns(3)
            total = c4.number_input("Total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            pagado = c5.number_input("Pagado inicial USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            fecha_compromiso = c6.date_input("Fecha compromiso", value=None)
            metodo_pago = st.selectbox("Método de pago inicial", ["", "efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
            notas = st.text_area("Notas")
            submitted = st.form_submit_button("Crear cuenta por cobrar", use_container_width=True)
        if submitted:
            try:
                cuenta_id = crear_cuenta_por_cobrar(usuario=usuario, cliente=cliente, concepto=concepto, total_usd=float(total), pagado_usd=float(pagado), fecha_compromiso=fecha_compromiso.isoformat() if fecha_compromiso else "", metodo_pago=metodo_pago, referencia=referencia, notas=notas)
                st.success(f"Cuenta por cobrar creada: #{cuenta_id}")
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_abono:
        df = listar_cuentas_por_cobrar(limit=200)
        pendientes = df[df["pendiente_usd"] > 0] if not df.empty else pd.DataFrame()
        if pendientes.empty:
            st.success("No hay saldos pendientes por cobrar.")
        else:
            opciones = {f"#{int(row['id'])} · {row['cliente']} · {row['concepto']} · pendiente ${float(row['pendiente_usd']):,.2f}": int(row["id"]) for _, row in pendientes.iterrows()}
            with st.form("form_abono_cxc"):
                label = st.selectbox("Cuenta", list(opciones.keys()))
                c1, c2, c3 = st.columns(3)
                monto = c1.number_input("Monto abono USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                metodo = c2.selectbox("Método", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
                referencia = c3.text_input("Referencia")
                notas = st.text_area("Notas del abono")
                submitted = st.form_submit_button("Registrar abono", use_container_width=True)
            if submitted:
                try:
                    res = registrar_abono_cxc(usuario=usuario, cuenta_id=opciones[label], monto_usd=float(monto), metodo_pago=metodo, referencia=referencia, notas=notas)
                    st.success(f"Abono registrado. Pendiente: ${res['pendiente_usd']:,.4f}. Estado: {res['estado']}.")
                except Exception as exc:
                    st.error(f"No se pudo registrar abono: {exc}")

    st.caption(f"Usuario: {usuario}")
