from __future__ import annotations

import streamlit as st

from database.schema import init_schema
from modules.caja import render_caja
from modules.clientes import render_clientes
from modules.dashboard import render_dashboard
from modules.gastos import render_gastos
from modules.inventario import render_inventario
from modules.ventas import render_ventas


st.set_page_config(page_title="Imperio Atómico ERP", layout="wide")


def _bootstrap_session() -> None:
    if "usuario" not in st.session_state:
        st.session_state.usuario = "admin"
    if "rol" not in st.session_state:
        st.session_state.rol = "Admin"


def render_sidebar() -> str:
    st.sidebar.title("Imperio Atómico ERP")
    st.sidebar.caption("Gestión profesional para imprenta y papelería creativa")
    return st.sidebar.radio(
        "Módulos",
        [
            "Dashboard",
            "Ventas",
            "Gastos",
            "Inventario",
            "Clientes",
            "Caja",
        ],
    )


def main() -> None:
    init_schema()
    _bootstrap_session()
    module = render_sidebar()

    st.title("Sistema de Gestión Empresarial")
    st.caption(
        "Monedas soportadas: USD, Bolívares (BCV), Binance USDT y Kontigo. "
        "Incluye contabilidad operativa, control de caja e indicadores financieros."
    )

    user = st.session_state.usuario
    role = st.session_state.rol

    if module == "Dashboard":
        render_dashboard()
    elif module == "Ventas":
        render_ventas(user)
    elif module == "Gastos":
        render_gastos(user)
    elif module == "Inventario":
        render_inventario(user)
    elif module == "Clientes":
        render_clientes(user)
    elif module == "Caja":
        render_caja(user, role)


if __name__ == "__main__":
    main()
