import streamlit as st

from views.dashboard import render_dashboard
from views.ventas import render_ventas
from views.inventario import render_inventario
from views.gastos import render_gastos
from views.clientes import render_clientes
from views.produccion import render_produccion
from views.activos import render_activos
from views.corte import render_corte
from views.sublimacion import render_sublimacion
from views.diagnostico import render_diagnostico


st.set_page_config(
    page_title="Imperio Atómico ERP",
    layout="wide"
)

menu = st.sidebar.selectbox(
    "Menú",
    [
        "Dashboard",
        "Ventas",
        "Inventario",
        "Gastos",
        "Clientes",
        "Producción",
        "Activos",
        "Corte",
        "Sublimación",
        "Diagnóstico"
    ]
)

usuario = st.session_state.get("usuario", "Sistema")

if menu == "Dashboard":
    render_dashboard()

elif menu == "Ventas":
    render_ventas(usuario)

elif menu == "Inventario":
    render_inventario(usuario)

elif menu == "Gastos":
    render_gastos(usuario)

elif menu == "Clientes":
    render_clientes(usuario)

elif menu == "Producción":
    render_produccion(usuario)

elif menu == "Activos":
    render_activos(usuario)

elif menu == "Corte":
    render_corte(usuario)

elif menu == "Sublimación":
    render_sublimacion(usuario)

elif menu == "Diagnóstico":
    render_diagnostico(usuario)
