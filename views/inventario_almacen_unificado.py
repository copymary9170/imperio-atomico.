from __future__ import annotations

import streamlit as st

from services.inventario_demo_cleanup import eliminar_articulos_demo
from views.almacen_avanzado import render_almacen_avanzado
from views.facturas_compra import render_facturas_compra
from views.inventario_profesional_integrado import render_inventario_profesional_integrado
from views.proveedores_compras import render_compras_suministro


def render_inventario_almacen_unificado(usuario: str) -> None:
    """Punto único de entrada para inventario, compras y almacén.

    La operación vigente vive en SQLite mediante el inventario profesional.
    Los archivos CSV del almacén se conservan únicamente como históricos y
    plantillas de migración, para evitar dos fuentes de stock simultáneas.
    """
    eliminar_articulos_demo()

    st.title("📦 Inventario / Almacén")
    st.caption(
        "Control central de existencias, reservas, compras, consumo, kardex, "
        "conteos físicos, mermas y reposición de Copy Mary."
    )

    st.info(
        "La existencia oficial se controla desde Operación. Las compras y los "
        "movimientos actualizan el mismo inventario; los CSV se mantienen solo "
        "como respaldo histórico."
    )

    tab_operacion, tab_facturas, tab_compras, tab_historicos = st.tabs(
        [
            "📊 Operación y existencias",
            "🧾 Facturas de compra",
            "🛒 Compras y proveedores",
            "🗄️ Históricos / plantillas",
        ]
    )

    with tab_operacion:
        render_inventario_profesional_integrado(usuario)

    with tab_facturas:
        st.subheader("Facturas y recepción documental")
        st.caption(
            "Registra el soporte de la compra. La entrada física del material "
            "debe reflejarse también en el inventario operativo."
        )
        render_facturas_compra(usuario)

    with tab_compras:
        st.subheader("Abastecimiento y proveedores")
        st.caption(
            "Gestiona solicitudes, proveedores y reposición sin crear un stock "
            "paralelo al inventario principal."
        )
        render_compras_suministro(usuario)

    with tab_historicos:
        st.warning(
            "Esta sección no modifica la existencia oficial. Se conserva para "
            "consultar o descargar archivos antiguos y facilitar su migración."
        )
        render_almacen_avanzado(usuario)
