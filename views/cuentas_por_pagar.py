import streamlit as st

from modules.cuentas_por_pagar import render_cuentas_por_pagar as render_cuentas_por_pagar_module


def render_cuentas_por_pagar(usuario):
    st.title("💸 Cuentas por pagar")
    render_cuentas_por_pagar_module(usuario)
