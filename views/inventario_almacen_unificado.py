from __future__ import annotations

import streamlit as st

from services.inventario_demo_cleanup import eliminar_articulos_demo
from views.almacen_avanzado import render_almacen_avanzado
from views.facturas_compra import render_facturas_compra
from views.inventario_calidad_elite import render_inventario_calidad_elite
from views.inventario_profesional_integrado import render_inventario_profesional_integrado
from views.inventario_tipo_panaderia import render_inventario_tipo_panaderia
from views.proveedores_compras import render_compras_suministro


def render_inventario_almacen_unificado(usuario: str) -> None:
    """Punto único de entrada para inventario, producción, compras y almacén."""
    eliminar_articulos_demo()

    st.title("📦 Inventario / Almacén")
    st.caption(
        "Centro corporativo de existencias, abastecimiento, producción, trazabilidad, "
        "costos, lotes, vencimientos, reservas, kardex y control de calidad de datos."
    )

    st.info(
        "La primera pestaña audita la calidad del inventario y muestra exactamente qué "
        "datos faltan. La existencia oficial se controla únicamente desde este módulo."
    )

    tab_elite, tab_operacion, tab_panaderia, tab_facturas, tab_compras, tab_historicos = st.tabs(
        [
            "🏆 Panel elite",
            "📊 Operación y existencias",
            "🥖 Producción y lotes",
            "🧾 Facturas de compra",
            "🛒 Compras y proveedores",
            "🗄️ Históricos / plantillas",
        ]
    )

    with tab_elite:
        render_inventario_calidad_elite(usuario)

    with tab_operacion:
        render_inventario_profesional_integrado(usuario)

    with tab_panaderia:
        render_inventario_tipo_panaderia(usuario)

    with tab_facturas:
        st.subheader("Facturas y recepción documental")
        st.caption(
            "Registra el soporte de cada compra y distribuye sus costos reales entre los artículos recibidos."
        )
        render_facturas_compra(usuario)

    with tab_compras:
        st.subheader("Abastecimiento y proveedores")
        st.caption(
            "Gestiona solicitudes, proveedores y reposición sin crear un stock paralelo al inventario principal."
        )
        render_compras_suministro(usuario)

    with tab_historicos:
        st.warning(
            "Esta sección no modifica la existencia oficial. Se conserva únicamente para "
            "consultar, descargar o migrar archivos antiguos."
        )
        render_almacen_avanzado(usuario)
