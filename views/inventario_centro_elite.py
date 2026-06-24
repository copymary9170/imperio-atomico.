from __future__ import annotations

import streamlit as st

from modules.mermas import render_mermas
from services.inventario_centro_elite_service import (
    alertas_operativas,
    conciliacion_stock_lotes,
    resumen_centro,
    ultimos_movimientos,
)
from views.facturas_compra import render_facturas_compra
from views.inventario_calidad_elite import render_inventario_calidad_elite
from views.inventario_control_contable import render_inventario_control_contable
from views.inventario_costeo_elite import render_inventario_costeo_elite
from views.inventario_operativo_copy_mary import render_inventario_operativo_copy_mary
from views.inventario_profesional_integrado import render_inventario_profesional_integrado
from views.inventario_tipo_panaderia import render_inventario_tipo_panaderia
from views.kardex import render_kardex
from views.proveedores_compras import render_compras_suministro


SECCIONES = [
    "🏢 Resumen ejecutivo",
    "🗂️ Maestro y parámetros",
    "🧾 Comprar y recibir",
    "🏭 Producir y transformar",
    "🔄 Movimientos y reservas",
    "📐 Costeo y rendimiento",
    "🔍 Control, Kardex y auditoría",
]


def _render_resumen(usuario: str) -> None:
    resumen = resumen_centro()
    a, b, c, d = st.columns(4)
    a.metric("Artículos activos", int(resumen["articulos"]))
    b.metric("Valor del inventario", f"${resumen['valor_inventario']:,.2f}")
    c.metric("Stock crítico", int(resumen["criticos"]))
    d.metric("Cuentas por pagar", f"${resumen['cuentas_por_pagar']:,.2f}")

    e, f, g = st.columns(3)
    e.metric("Cantidad reservada", f"{resumen['reservados']:,.2f}")
    f.metric("Lotes por vencer", int(resumen["lotes_por_vencer"]))
    g.metric("Recetas activas", int(resumen["recetas_activas"]))

    st.markdown("### Alertas operativas")
    alertas = alertas_operativas()
    urgentes = alertas[alertas["estado"] != "NORMAL"] if not alertas.empty else alertas
    if urgentes.empty:
        st.success("No hay artículos agotados, críticos o en punto de reorden.")
    else:
        st.dataframe(urgentes, use_container_width=True, hide_index=True)

    st.markdown("### Conciliación entre existencia y lotes")
    diferencias = conciliacion_stock_lotes()
    if diferencias.empty:
        st.success("El stock general coincide con la suma de lotes registrados.")
    else:
        st.warning(
            "Hay artículos cuya existencia general no coincide con la suma de sus lotes. "
            "Revisa entradas antiguas o realiza un conteo físico antes de producir o vender."
        )
        st.dataframe(diferencias, use_container_width=True, hide_index=True)

    st.markdown("### Últimos movimientos")
    movimientos = ultimos_movimientos(30)
    if movimientos.empty:
        st.info("Todavía no hay movimientos registrados.")
    else:
        st.dataframe(movimientos, use_container_width=True, hide_index=True)


def _render_compras(usuario: str) -> None:
    st.subheader("🧾 Compra, factura y recepción")
    st.info(
        "Flujo oficial: registra la factura una sola vez, distribuye delivery, impuestos y "
        "comisiones, aumenta el stock y luego vincula el lote para conservar trazabilidad."
    )
    opcion = st.radio(
        "Etapa",
        ["Registrar factura y recepción", "Planificar compra y proveedores"],
        horizontal=True,
        key="inventario_compra_etapa",
    )
    if opcion == "Registrar factura y recepción":
        render_facturas_compra(usuario)
    else:
        render_compras_suministro(usuario)


def _render_control(usuario: str) -> None:
    st.subheader("🔍 Control y auditoría")
    opcion = st.radio(
        "Herramienta",
        ["Kardex", "Auditoría contable y cierres", "Calidad de datos", "Mermas y desperdicio"],
        horizontal=True,
        key="inventario_control_herramienta",
    )
    if opcion == "Kardex":
        render_kardex(usuario)
    elif opcion == "Auditoría contable y cierres":
        render_inventario_control_contable(usuario)
    elif opcion == "Calidad de datos":
        render_inventario_calidad_elite(usuario)
    else:
        render_mermas(usuario)


def render_inventario_centro_elite(usuario: str) -> None:
    st.title("📦 Centro de Inventario Elite")
    st.caption(
        "Una sola fuente de verdad para compras, existencias, lotes, producción, costos, "
        "reservas, mermas, conteos y trazabilidad de Copy Mary."
    )

    seccion = st.radio(
        "Proceso de inventario",
        SECCIONES,
        horizontal=True,
        key="inventario_centro_seccion",
    )
    st.divider()

    if seccion == "🏢 Resumen ejecutivo":
        _render_resumen(usuario)
    elif seccion == "🗂️ Maestro y parámetros":
        render_inventario_profesional_integrado(usuario)
    elif seccion == "🧾 Comprar y recibir":
        _render_compras(usuario)
    elif seccion == "🏭 Producir y transformar":
        render_inventario_tipo_panaderia(usuario)
    elif seccion == "🔄 Movimientos y reservas":
        render_inventario_operativo_copy_mary(usuario)
    elif seccion == "📐 Costeo y rendimiento":
        render_inventario_costeo_elite(usuario)
    else:
        _render_control(usuario)
