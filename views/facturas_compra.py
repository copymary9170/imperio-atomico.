from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.facturas_compra_service import (
    TIPOS_LINEA_FACTURA,
    listar_abonos_factura_compra,
    listar_cuentas_por_pagar,
    listar_facturas_compra,
    listar_lineas_factura,
    registrar_abono_factura_compra,
    registrar_factura_compra,
)
from services.materia_prima_service import listar_materia_prima
from services.reventa_service import listar_mercancia_reventa


def _label_materia_prima(row: pd.Series) -> str:
    return f"#{int(row['id'])} · {row['nombre']} · stock {float(row['stock_actual'] or 0):g} {row['unidad']}"


def _label_reventa(row: pd.Series) -> str:
    return f"#{int(row['id'])} · {row['nombre']} · stock {float(row['stock_actual'] or 0):g} {row['unidad']}"


def _render_registrar_abono_cxp(usuario: str, cxp: pd.DataFrame) -> None:
    st.markdown("##### Registrar abono a proveedor")
    if cxp.empty:
        st.caption("No hay facturas pendientes para abonar.")
        return

    opciones = {
        f"#{int(row['id'])} · {row.get('proveedor') or 'Proveedor N/D'} · Pendiente ${float(row['pendiente_usd'] or 0):,.2f}": row
        for _, row in cxp.iterrows()
    }
    seleccion = st.selectbox("Factura pendiente", list(opciones.keys()), key="cxp_factura_abono")
    factura = opciones[seleccion]
    pendiente = float(factura["pendiente_usd"] or 0.0)

    with st.form("form_abono_factura_compra"):
        c1, c2, c3 = st.columns(3)
        fecha_abono = c1.date_input("Fecha del abono", value=date.today())
        monto_abono = c2.number_input("Monto abono USD", min_value=0.0, max_value=max(pendiente, 0.01), value=min(pendiente, 1.0), step=1.0, format="%.4f")
        metodo_pago = c3.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"], key="cxp_metodo_abono")
        referencia = st.text_input("Referencia / comprobante", placeholder="Opcional")
        notas = st.text_area("Notas", placeholder="Opcional")
        submit_abono = st.form_submit_button("💸 Registrar abono", use_container_width=True)

    if submit_abono:
        try:
            result = registrar_abono_factura_compra(
                usuario=usuario,
                factura_id=int(factura["id"]),
                monto_usd=float(monto_abono),
                metodo_pago=metodo_pago,
                referencia=referencia,
                notas=notas,
                fecha=fecha_abono.isoformat(),
            )
            st.success(
                f"✅ Abono #{result['abono_id']} registrado. Pendiente actual: ${result['pendiente_actual_usd']:,.4f}. Estado: {result['estado']}"
            )
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar el abono: {exc}")


def render_facturas_compra(usuario: str) -> None:
    st.subheader("🧾 Facturas de compra")
    st.caption(
        "Registra una factura completa con varias líneas. Materia prima y mercancía para reventa actualizan stock automáticamente; "
        "activos, gastos y servicios quedan registrados para control de factura y cuentas por pagar."
    )

    tab_nueva, tab_historial, tab_cxp = st.tabs(["Nueva factura", "Historial", "Cuentas por pagar"])

    with tab_nueva:
        if "facturas_compra_lineas" not in st.session_state:
            st.session_state["facturas_compra_lineas"] = []

        st.markdown("##### Líneas de la factura")
        materia_prima = listar_materia_prima()
        reventa = listar_mercancia_reventa()
        tipo_linea = st.selectbox("Tipo de línea", TIPOS_LINEA_FACTURA, key="fc_tipo_linea")

        descripcion_default = ""
        inventario_id = None
        mercancia_reventa_id = None
        unidad_default = "unidad"

        if tipo_linea == "Materia prima":
            if not materia_prima.empty:
                opciones_mp = {_label_materia_prima(row): row for _, row in materia_prima.iterrows()}
                item_label = st.selectbox("Materia prima", list(opciones_mp.keys()), key="fc_materia_prima")
                item_row = opciones_mp[item_label]
                descripcion_default = str(item_row["nombre"])
                inventario_id = int(item_row["id"])
                unidad_default = str(item_row.get("unidad") or "unidad")
            else:
                st.warning("No hay materia prima creada. Puedes usar otro tipo de línea o crear la materia prima primero.")
        elif tipo_linea == "Mercancia para reventa":
            if not reventa.empty:
                opciones_reventa = {_label_reventa(row): row for _, row in reventa.iterrows()}
                item_label = st.selectbox("Mercancía reventa", list(opciones_reventa.keys()), key="fc_reventa")
                item_row = opciones_reventa[item_label]
                descripcion_default = str(item_row["nombre"])
                mercancia_reventa_id = int(item_row["id"])
                unidad_default = str(item_row.get("unidad") or "unidad")
            else:
                st.warning("No hay mercancía para reventa creada. Créala primero en Inventario / Almacén → Mercancía reventa.")

        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        descripcion = c1.text_input("Descripción", value=descripcion_default, placeholder="Ej: lápices, foami, papel bond, impresora HP 580")
        cantidad = c2.number_input("Cantidad", min_value=0.0001, value=1.0, step=1.0, format="%.4f", key="fc_cantidad")
        unidad = c3.text_input("Unidad", value=unidad_default)
        subtotal_linea = c4.number_input("Subtotal USD", min_value=0.0, value=0.0, step=1.0, format="%.4f", key="fc_subtotal_linea")

        if st.button("➕ Agregar línea", use_container_width=True):
            if not descripcion.strip() or subtotal_linea <= 0:
                st.error("La línea necesita descripción y subtotal mayor a cero.")
            elif tipo_linea == "Materia prima" and not inventario_id:
                st.error("Selecciona una materia prima válida.")
            elif tipo_linea == "Mercancia para reventa" and not mercancia_reventa_id:
                st.error("Selecciona una mercancía para reventa válida.")
            else:
                st.session_state["facturas_compra_lineas"].append(
                    {
                        "tipo_linea": tipo_linea,
                        "inventario_id": inventario_id,
                        "mercancia_reventa_id": mercancia_reventa_id,
                        "descripcion": descripcion,
                        "item": descripcion,
                        "cantidad": float(cantidad),
                        "unidad": unidad,
                        "subtotal_usd": float(subtotal_linea),
                    }
                )
                st.success("Línea agregada a la factura.")

        lineas = st.session_state.get("facturas_compra_lineas", [])
        if lineas:
            st.dataframe(pd.DataFrame(lineas), use_container_width=True, hide_index=True)
            if st.button("🧹 Limpiar líneas", use_container_width=True):
                st.session_state["facturas_compra_lineas"] = []
                st.rerun()
        else:
            st.info("Agrega al menos una línea a la factura.")

        subtotal = sum(float(x.get("subtotal_usd") or 0.0) for x in lineas)
        st.markdown("##### Encabezado y costos globales")
        with st.form("form_nueva_factura_compra"):
            f1, f2, f3, f4 = st.columns(4)
            proveedor = f1.text_input("Proveedor")
            numero_factura = f2.text_input("Número de factura")
            fecha_factura = f3.date_input("Fecha de factura", value=None)
            fecha_vencimiento = f4.date_input("Fecha de vencimiento", value=None)

            g1, g2, g3, g4, g5 = st.columns(5)
            descuento = g1.number_input("Descuento / promo USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            impuestos_pct = g2.number_input("Impuestos %", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            delivery = g3.number_input("Delivery total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            comision = g4.number_input("Comisión total USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
            otros = g5.number_input("Otros gastos USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")

            p1, p2, p3, p4 = st.columns(4)
            moneda = p1.selectbox("Moneda", ["USD", "Bs", "COP", "EUR"])
            tasa = p2.number_input("Tasa", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
            metodo_pago = p3.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
            tipo_pago = p4.selectbox("Tipo de pago", ["contado", "credito", "parcial"])

            monto_pagado = st.number_input("Monto pagado inicial USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            observaciones = st.text_area("Observaciones")

            base_desc = max(0.0, subtotal - float(descuento)) + float(otros)
            impuesto_total = base_desc * (float(impuestos_pct) / 100.0)
            total = base_desc + impuesto_total + float(delivery) + float(comision)
            pagado_preview = total if monto_pagado <= 0 and tipo_pago == "contado" else float(monto_pagado)
            pendiente_preview = max(0.0, total - pagado_preview)

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Subtotal líneas", f"${subtotal:,.4f}")
            m2.metric("Base neta", f"${base_desc:,.4f}")
            m3.metric("Impuesto", f"${impuesto_total:,.4f}")
            m4.metric("Total", f"${total:,.4f}")
            m5.metric("Pendiente", f"${pendiente_preview:,.4f}")

            submitted = st.form_submit_button("💾 Registrar factura", use_container_width=True, disabled=not bool(lineas))

        if submitted:
            try:
                resultado = registrar_factura_compra(
                    usuario=usuario,
                    proveedor=proveedor,
                    numero_factura=numero_factura,
                    fecha_factura=fecha_factura.isoformat() if fecha_factura else "",
                    fecha_vencimiento=fecha_vencimiento.isoformat() if fecha_vencimiento else "",
                    lineas=lineas,
                    descuento_total_usd=float(descuento),
                    impuestos_pct=float(impuestos_pct),
                    delivery_total_usd=float(delivery),
                    comision_total_usd=float(comision),
                    otros_gastos_usd=float(otros),
                    moneda_pago=moneda,
                    tasa_cambio=float(tasa),
                    metodo_pago=metodo_pago,
                    tipo_pago=tipo_pago,
                    monto_pagado_inicial_usd=float(monto_pagado) if float(monto_pagado) > 0 else None,
                    observaciones=observaciones,
                )
                st.session_state["facturas_compra_lineas"] = []
                st.success(f"Factura #{resultado['factura_id']} registrada. Total: ${resultado['total_usd']:,.4f}. Estado: {resultado['estado']}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo registrar la factura: {exc}")

    with tab_historial:
        st.markdown("##### Historial de facturas")
        facturas = listar_facturas_compra(limit=100)
        if facturas.empty:
            st.info("Aún no hay facturas registradas.")
        else:
            st.dataframe(facturas, use_container_width=True, hide_index=True)
            factura_id = st.number_input("Ver líneas de factura ID", min_value=1, value=int(facturas.iloc[0]["id"]), step=1)
            lineas_df = listar_lineas_factura(int(factura_id))
            if lineas_df.empty:
                st.caption("Sin líneas para esa factura.")
            else:
                st.dataframe(lineas_df, use_container_width=True, hide_index=True)
            abonos_df = listar_abonos_factura_compra(int(factura_id))
            st.caption("Abonos de esta factura")
            if abonos_df.empty:
                st.info("Esta factura no tiene abonos registrados.")
            else:
                st.dataframe(abonos_df, use_container_width=True, hide_index=True)

    with tab_cxp:
        st.markdown("##### Cuentas por pagar")
        cxp = listar_cuentas_por_pagar(limit=100)
        if cxp.empty:
            st.success("No hay cuentas por pagar pendientes.")
        else:
            total_pendiente = float(pd.to_numeric(cxp["pendiente_usd"], errors="coerce").fillna(0).sum())
            c1, c2 = st.columns(2)
            c1.metric("Facturas pendientes", len(cxp))
            c2.metric("Total por pagar", f"${total_pendiente:,.2f}")
            st.dataframe(cxp, use_container_width=True, hide_index=True)
            _render_registrar_abono_cxp(usuario, cxp)

    st.caption(f"Usuario: {usuario}")
