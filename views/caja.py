import streamlit as st
from modules.caja import render_caja as caja_module


def render_caja(usuario):

    st.title("🏁 Cierre de Caja")

    user_role = st.session_state.get("rol", "Admin")

    caja_module(usuario, user_role)
