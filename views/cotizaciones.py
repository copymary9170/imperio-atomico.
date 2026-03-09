import streamlit as st
from modules.gastos import render_gastos as gastos_module


def render_gastos(usuario):

    st.title("📉 Gastos")

    gastos_module(usuario)
