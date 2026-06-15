from __future__ import annotations

import streamlit as st

from views.almacen_avanzado import render_almacen_avanzado
from views.catalogo import render_catalogo
from views.facturas_compra import render_facturas_compra
from views.inventario import render_inventario
from views.kardex import render_kardex
from views.materia_prima import render_materia_prima
from views.mercancia_reventa import render_mercancia_reventa
from views.productos_terminados import render_productos_terminados
from views.proveedores_compras import render_compras_suministro, render_proveedores
from views.stock_minimo import render_stock_minimo
from views.unidades_fraccionadas import render_unidades_fraccionadas


def render_inventario_almacen_unificado(usuario: str) -> None:
    st.title("📦 Inventario / Almacén")
    tabs = st.tabs([
        "🧾 Facturas de compra",
        "📦 Materia prima",
        "🛍️ Mercancía reventa",
        "🧩 Productos terminados",
        "⚙️ Inventario operativo",
        "🧪 Recetas / consumo",
        "📋 Conteo físico",
        "💰 Rentabilidad",
        "📉 Stock mínimo",
        "📏 Unidades",
        "🧾 Kardex",
        "🛒 Compras",
        "👥 Proveedores",
        "🏬 Almacén",
        "🛍️ Catálogo",
    ])
    with tabs[0]:
        render_facturas_compra(usuario)
    with tabs[1]:
        render_materia_prima(usuario)
    with tabs[2]:
        render_mercancia_reventa(usuario)
    with tabs[3]:
        render_productos_terminados(usuario)
    with tabs[4]:
        render_inventario(usuario)
    with tabs[5]:
        render_stock_minimo(usuario)
    with tabs[6]:
        render_unidades_fraccionadas(usuario)
    with tabs[7]:
        render_kardex(usuario)
    with tabs[8]:
        render_compras_suministro(usuario)
    with tabs[9]:
        render_proveedores(usuario)
    with tabs[10]:
        render_almacen_avanzado(usuario)
    with tabs[11]:
        render_catalogo(usuario)
