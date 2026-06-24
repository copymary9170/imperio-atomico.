from __future__ import annotations

import streamlit as st

from services.inventario_gobernanza_service import (
    anular_factura_compra,
    decidir_ajuste,
    listar_lineas_devolvibles,
    listar_solicitudes_ajuste,
    registrar_devolucion_proveedor,
)
from services.facturas_compra_service import listar_facturas_compra


def render_inventario_gobernanza(usuario: str) -> None:
    st.subheader("🛡️ Gobernanza y autorizaciones")
    st.caption("Aprobaciones, devoluciones y anulaciones con trazabilidad y validación de stock.")

    tabs = st.tabs(["Ajustes pendientes", "Devoluciones al proveedor", "Anular factura"])

    with tabs[0]:
        pendientes = listar_solicitudes_ajuste("pendiente")
        if pendientes.empty:
            st.success("No hay ajustes pendientes de aprobación.")
        else:
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
            ids = [int(x) for x in pendientes["id"].tolist()]
            etiquetas = {
                int(row["id"]): f"#{int(row['id'])} · {row['nombre']} · {row['tipo']} · {float(row['cantidad']):,.4f}"
                for _, row in pendientes.iterrows()
            }
            solicitud_id = st.selectbox("Solicitud", ids, format_func=lambda value: etiquetas[value])
            observacion = st.text_area("Observación de la decisión")
            c1, c2 = st.columns(2)
            if c1.button("Aprobar ajuste", type="primary", use_container_width=True):
                try:
                    decidir_ajuste(solicitud_id, aprobar=True, usuario=usuario, observacion=observacion)
                    st.success("Ajuste aprobado y aplicado al Kardex.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            if c2.button("Rechazar ajuste", use_container_width=True):
                try:
                    decidir_ajuste(solicitud_id, aprobar=False, usuario=usuario, observacion=observacion)
                    st.success("Solicitud rechazada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        historial = listar_solicitudes_ajuste()
        if not historial.empty:
            st.markdown("#### Historial")
            st.dataframe(historial, use_container_width=True, hide_index=True)

    with tabs[1]:
        lineas = listar_lineas_devolvibles()
        lineas = lineas[lineas["disponible_devolver"] > 0] if not lineas.empty else lineas
        if lineas.empty:
            st.info("No hay líneas de inventario disponibles para devolución.")
        else:
            ids = [int(x) for x in lineas["linea_id"].tolist()]
            etiquetas = {
                int(row["linea_id"]): (
                    f"Factura {row['numero_factura'] or row['factura_id']} · {row['nombre']} · "
                    f"disponible {float(row['disponible_devolver']):,.4f}"
                )
                for _, row in lineas.iterrows()
            }
            with st.form("devolucion_proveedor_form"):
                linea_id = st.selectbox("Línea de factura", ids, format_func=lambda value: etiquetas[value])
                fila = lineas[lineas["linea_id"] == linea_id].iloc[0]
                cantidad = st.number_input(
                    "Cantidad a devolver",
                    min_value=0.0001,
                    max_value=float(fila["disponible_devolver"]),
                    value=min(1.0, float(fila["disponible_devolver"])),
                )
                motivo = st.text_area("Motivo *", placeholder="Material defectuoso, faltante, error de compra...")
                nota_credito = st.text_input("Número de nota de crédito o referencia")
                guardar = st.form_submit_button("Registrar devolución", type="primary", use_container_width=True)
            if guardar:
                try:
                    devolucion_id = registrar_devolucion_proveedor(
                        factura_linea_id=linea_id,
                        cantidad=cantidad,
                        motivo=motivo,
                        nota_credito=nota_credito,
                        usuario=usuario,
                    )
                    st.success(f"Devolución #{devolucion_id} registrada y stock descontado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tabs[2]:
        facturas = listar_facturas_compra(200)
        if not facturas.empty:
            facturas = facturas[facturas["estado"].astype(str).str.lower() != "anulada"]
        if facturas.empty:
            st.info("No hay facturas activas para anular.")
        else:
            ids = [int(x) for x in facturas["id"].tolist()]
            etiquetas = {
                int(row["id"]): (
                    f"#{int(row['id'])} · {row['numero_factura'] or 'S/N'} · {row['proveedor'] or 'Proveedor N/D'} · "
                    f"${float(row['total_usd']):,.2f}"
                )
                for _, row in facturas.iterrows()
            }
            factura_id = st.selectbox("Factura", ids, format_func=lambda value: etiquetas[value])
            st.warning(
                "Solo se permite anular una factura sin pagos, sin consumo de lotes y con todo el material todavía disponible."
            )
            motivo = st.text_area("Motivo de anulación *")
            confirmar = st.checkbox("Confirmo que revisé el stock, los lotes y los pagos")
            if st.button("Anular factura", disabled=not confirmar, use_container_width=True):
                try:
                    anular_factura_compra(factura_id, usuario=usuario, motivo=motivo)
                    st.success("Factura anulada y stock revertido.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
