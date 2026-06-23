from __future__ import annotations

import streamlit as st

from services.inventario_demo_cleanup import eliminar_articulos_demo
from views.inventario_profesional_integrado import render_inventario_profesional_integrado
from views.facturas_compra import render_facturas_compra
from views.proveedores_compras import render_compras_suministro
from views.almacen_avanzado import render_almacen_avanzado


def render_inventario_almacen_unificado(usuario: str) -> None:
    eliminar_articulos_demo()
    render_inventario_profesional_integrado(usuario)
    with st.expander('Herramientas administrativas adicionales'):
        tabs = st.tabs(['Facturas de compra', 'Compras y proveedores', 'Almacén avanzado'])
        with tabs[0]:
            render_facturas_compra(usuario)
        with tabs[1]:
            render_compras_suministro(usuario)
        with tabs[2]:
            render_almacen_avanzado(usuario)
