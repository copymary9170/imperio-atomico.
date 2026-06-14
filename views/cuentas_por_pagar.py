from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.facturas_compra_service import (
    listar_abonos_factura_compra,
    listar_cuentas_por_pagar,
    registrar_abono_factura_compra,
)


def _render_abono(usuario: str, cxp: pd.DataFrame) -> int | None:
    if cxp.empty:
        st.info("No hay facturas pendientes para abonar.")
        return None

    opciones = {
        f"#{int(row['id'])} · {row.get('proveedor') or 'Proveedor N/D'} · Pendiente ${float(row['pendiente_usd'] or 0):,.2f}": row
        for _, row in cxp.iterrows()
    }
    seleccion = st.selectbox("Factura pendiente", list(opciones.keys()), key="cxp_standalone_factura")
    factura = opciones[seleccion]
    factura_id = int(factura["id"])
    pendiente = float(factura["pendiente_usd"] or 0.0)

    with st.form("form_cxp_standalone_abono"):
        c1, c2, c3 = st.columns(3)
        fecha_abono = c1.date_input("Fecha", value=date.today(), key="cxp_standalone_fecha")
        monto = c2.number_input("Monto USD", min_value=0.0, max_value=max(pendiente, 0.01), value=min(pendiente, 1.0), step=1.0, format="%.4f", key="cxp_standalone_monto")
        metodo = c3.selectbox("Método", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"], key="cxp_standalone_metodo")
        referencia = st.text_input("Referencia / comprobante", key="cxp_standalone_referencia")
        notas = st.text_area("Notas", key="cxp_standalone_notas")
        submit = st.form_submit_button("💸 Registrar abono", use_container_width=True)

    if submit:
        try:
            result = registrar_abono_factura_compra(
                usuario=usuario,
                factura_id=factura_id,
                monto_usd=float(monto),
                metodo_pago=metodo,
                referencia=referencia,
                notas=notas,
                fecha=fecha_abono.isoformat(),
            )
            st.success(f"✅ Abono registrado. Pendiente actual: ${result['pendiente_actual_usd']:,.4f}. Estado: {result['estado']}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar el abono: {exc}")

    return factura_id


def render_cuentas_por_pagar(usuario: str) -> None:
    st.title("💸 Cuentas por pagar")
    st.caption("Control de facturas de compra pendientes y abonos parciales a proveedores.")

    cxp = listar_cuentas_por_pagar(limit=300)
    abonos = listar_abonos_factura_compra(limit=300)

    total_pendiente = 0.0 if cxp.empty else float(pd.to_numeric(cxp["pendiente_usd"], errors="coerce").fillna(0).sum())
    total_abonado = 0.0 if abonos.empty else float(pd.to_numeric(abonos["monto_usd"], errors="coerce").fillna(0).sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Facturas pendientes", 0 if cxp.empty else len(cxp))
    c2.metric("Total por pagar", f"${total_pendiente:,.2f}")
    c3.metric("Abonos registrados", f"${total_abonado:,.2f}")

    tab_pendientes, tab_abono, tab_historial = st.tabs(["📌 Pendientes", "💸 Registrar abono", "📜 Historial de abonos"])

    with tab_pendientes:
        if cxp.empty:
            st.success("No hay cuentas por pagar pendientes.")
        else:
            buscar = st.text_input("Buscar proveedor / factura", key="cxp_standalone_buscar")
            vista = cxp.copy()
            if buscar.strip():
                txt = buscar.strip()
                vista = vista[
                    vista["proveedor"].astype(str).str.contains(txt, case=False, na=False)
                    | vista["numero_factura"].astype(str).str.contains(txt, case=False, na=False)
                ]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar CxP CSV",
                data=vista.to_csv(index=False).encode("utf-8-sig"),
                file_name="cuentas_por_pagar.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab_abono:
        factura_id = _render_abono(usuario, cxp)
        if factura_id:
            st.markdown("##### Abonos de la factura seleccionada")
            abonos_factura = listar_abonos_factura_compra(factura_id, limit=100)
            if abonos_factura.empty:
                st.info("Esta factura aún no tiene abonos registrados.")
            else:
                st.dataframe(abonos_factura, use_container_width=True, hide_index=True)

    with tab_historial:
        if abonos.empty:
            st.info("Aún no hay abonos registrados.")
        else:
            st.dataframe(abonos, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Descargar historial de abonos CSV",
                data=abonos.to_csv(index=False).encode("utf-8-sig"),
                file_name="historial_abonos_proveedores.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.caption(f"Usuario: {usuario}")
