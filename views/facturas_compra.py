from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.facturas_compra_service import (
    listar_abonos_factura_compra,
    listar_cuentas_por_pagar,
    listar_facturas_compra,
    listar_lineas_factura,
    registrar_abono_factura_compra,
    registrar_factura_compra,
)
from services.inventario_unificado_service import listar_inventario_unificado
from services.proveedores_select_service import opciones_proveedores_con_manual

TIPOS_LINEA = ["Inventario", "Activo / equipo", "Gasto", "Servicio"]
UNIDADES = ["unidad", "paquete", "caja", "resma", "hoja", "pliego", "rollo", "g", "kg", "mg", "ml", "L", "cm", "m", "cm²", "m²", "cm³", "m³", "otro"]


def _render_abono(usuario: str, cxp: pd.DataFrame) -> None:
    if cxp.empty:
        return
    opciones = {f"#{int(r['id'])} - {r.get('proveedor') or 'Proveedor'} - ${float(r['pendiente_usd'] or 0):,.2f}": r for _, r in cxp.iterrows()}
    seleccion = st.selectbox("Factura pendiente", list(opciones.keys()), key="fc_abono_factura")
    factura = opciones[seleccion]
    pendiente = float(factura["pendiente_usd"] or 0)
    with st.form("form_abono_factura_compra"):
        c1, c2, c3 = st.columns(3)
        fecha_abono = c1.date_input("Fecha", value=date.today())
        monto = c2.number_input("Monto USD", min_value=0.01, max_value=max(pendiente, 0.01), value=min(pendiente, 1.0), format="%.4f")
        metodo = c3.selectbox("Metodo", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
        referencia = st.text_input("Referencia")
        notas = st.text_area("Notas")
        guardar = st.form_submit_button("Registrar abono", use_container_width=True)
    if guardar:
        try:
            registrar_abono_factura_compra(usuario=usuario, factura_id=int(factura["id"]), monto_usd=float(monto), metodo_pago=metodo, referencia=referencia, notas=notas, fecha=fecha_abono.isoformat())
            st.success("Abono registrado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar el abono: {exc}")


def _selector_proveedor_factura() -> str:
    opciones, mapa = opciones_proveedores_con_manual()
    seleccion = st.selectbox("Proveedor", opciones, key="fc_proveedor_select")
    if seleccion == "Escribir manualmente":
        return st.text_input("Proveedor manual", key="fc_proveedor_manual").strip()
    if seleccion == "Sin proveedor":
        st.caption("Registra tus proveedores en el módulo 🏢 Proveedores para seleccionarlos aquí.")
    return mapa.get(seleccion, "")


def render_facturas_compra(usuario: str) -> None:
    st.subheader("Facturas de compra")
    st.caption("Papel, foami, cartulina y otros articulos entran al mismo inventario, aunque se usen como insumo, reventa o ambos.")
    tab_nueva, tab_historial, tab_cxp = st.tabs(["Nueva factura", "Historial", "Cuentas por pagar"])

    with tab_nueva:
        st.session_state.setdefault("facturas_compra_lineas", [])
        inventario = listar_inventario_unificado(activos_only=True)
        tipo_ui = st.selectbox("Tipo de linea", TIPOS_LINEA, key="fc_tipo_linea")
        inventario_id = None
        descripcion_default = ""
        unidad_default = "unidad"

        if tipo_ui == "Inventario":
            if inventario.empty:
                st.warning("No hay articulos. Crea uno en Inventario unificado.")
            else:
                opciones = {
                    f"#{int(r['id'])} - {r['nombre']} - {r['tipo_uso']} - {float(r['stock_actual'] or 0):g} {r['unidad_base']}": r
                    for _, r in inventario.iterrows()
                }
                seleccion = st.selectbox("Articulo", list(opciones.keys()), key="fc_inventario_item")
                item = opciones[seleccion]
                inventario_id = int(item["id"])
                descripcion_default = str(item["nombre"])
                unidad_default = str(item.get("unidad_base") or item.get("unidad") or "unidad")

        c1, c2, c3, c4 = st.columns([3, 1, 1.2, 1])
        descripcion = c1.text_input("Descripcion", value=descripcion_default)
        cantidad = c2.number_input("Cantidad", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
        opciones_unidad = list(UNIDADES)
        if unidad_default not in opciones_unidad:
            opciones_unidad.insert(0, unidad_default)
        unidad_sel = c3.selectbox("Unidad", opciones_unidad, index=opciones_unidad.index(unidad_default))
        unidad = c3.text_input("Unidad personalizada", key="fc_unidad_otro") if unidad_sel == "otro" else unidad_sel
        subtotal_linea = c4.number_input("Subtotal USD", min_value=0.0, step=1.0, format="%.4f")

        if st.button("Agregar linea", use_container_width=True):
            if not descripcion.strip() or subtotal_linea <= 0:
                st.error("Indica descripcion y subtotal.")
            elif tipo_ui == "Inventario" and not inventario_id:
                st.error("Selecciona un articulo.")
            elif not str(unidad).strip():
                st.error("Indica la unidad.")
            else:
                st.session_state["facturas_compra_lineas"].append({
                    "tipo_linea": "Materia prima" if tipo_ui == "Inventario" else tipo_ui,
                    "inventario_id": inventario_id,
                    "mercancia_reventa_id": None,
                    "descripcion": descripcion.strip(),
                    "item": descripcion.strip(),
                    "cantidad": float(cantidad),
                    "unidad": str(unidad).strip(),
                    "subtotal_usd": float(subtotal_linea),
                })
                st.success("Linea agregada.")

        lineas = st.session_state["facturas_compra_lineas"]
        if lineas:
            vista = pd.DataFrame(lineas).copy()
            vista["tipo_linea"] = vista["tipo_linea"].replace({"Materia prima": "Inventario"})
            st.dataframe(vista, use_container_width=True, hide_index=True)
            if st.button("Limpiar lineas", use_container_width=True):
                st.session_state["facturas_compra_lineas"] = []
                st.rerun()
        else:
            st.info("Agrega al menos una linea.")

        subtotal = sum(float(x.get("subtotal_usd") or 0) for x in lineas)
        with st.form("form_nueva_factura_compra"):
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                proveedor = _selector_proveedor_factura()
            numero = f2.text_input("Numero de factura")
            fecha_factura = f3.date_input("Fecha de factura", value=None)
            vencimiento = f4.date_input("Vencimiento", value=None)
            g1, g2, g3, g4, g5 = st.columns(5)
            descuento = g1.number_input("Descuento USD", min_value=0.0, format="%.4f")
            impuestos = g2.number_input("Impuestos %", min_value=0.0, format="%.4f")
            delivery = g3.number_input("Delivery USD", min_value=0.0, format="%.4f")
            comision = g4.number_input("Comision USD", min_value=0.0, format="%.4f")
            otros = g5.number_input("Otros USD", min_value=0.0, format="%.4f")
            p1, p2, p3, p4 = st.columns(4)
            moneda = p1.selectbox("Moneda", ["USD", "Bs", "COP", "EUR"])
            tasa = p2.number_input("Tasa", min_value=0.0001, value=1.0, format="%.4f")
            metodo = p3.selectbox("Metodo de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
            tipo_pago = p4.selectbox("Tipo de pago", ["contado", "credito", "parcial"])
            pagado = st.number_input("Pagado inicial USD", min_value=0.0, format="%.4f")
            observaciones = st.text_area("Observaciones")
            total_preview = max(0.0, subtotal - descuento) + otros
            total_preview += total_preview * impuestos / 100 + delivery + comision
            st.metric("Total estimado", f"${total_preview:,.4f}")
            registrar = st.form_submit_button("Registrar factura", type="primary", use_container_width=True, disabled=not bool(lineas))

        if registrar:
            try:
                resultado = registrar_factura_compra(usuario=usuario, proveedor=proveedor, numero_factura=numero, fecha_factura=fecha_factura.isoformat() if fecha_factura else "", fecha_vencimiento=vencimiento.isoformat() if vencimiento else "", lineas=lineas, descuento_total_usd=float(descuento), impuestos_pct=float(impuestos), delivery_total_usd=float(delivery), comision_total_usd=float(comision), otros_gastos_usd=float(otros), moneda_pago=moneda, tasa_cambio=float(tasa), metodo_pago=metodo, tipo_pago=tipo_pago, monto_pagado_inicial_usd=float(pagado) if pagado > 0 else None, observaciones=observaciones)
                st.session_state["facturas_compra_lineas"] = []
                st.success(f"Factura #{resultado['factura_id']} registrada. Total ${resultado['total_usd']:,.4f}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo registrar: {exc}")

    with tab_historial:
        facturas = listar_facturas_compra(limit=100)
        if facturas.empty:
            st.info("Aun no hay facturas.")
        else:
            st.dataframe(facturas, use_container_width=True, hide_index=True)
            factura_id = st.number_input("Ver lineas de factura ID", min_value=1, value=int(facturas.iloc[0]["id"]), step=1)
            lineas_df = listar_lineas_factura(int(factura_id))
            if not lineas_df.empty:
                st.dataframe(lineas_df, use_container_width=True, hide_index=True)

    with tab_cxp:
        cxp = listar_cuentas_por_pagar(limit=100)
        if cxp.empty:
            st.success("No hay cuentas pendientes.")
        else:
            st.dataframe(cxp, use_container_width=True, hide_index=True)
            _render_abono(usuario, cxp)
        abonos = listar_abonos_factura_compra(limit=100)
        if not abonos.empty:
            st.markdown("Historial de abonos")
            st.dataframe(abonos, use_container_width=True, hide_index=True)
