import streamlit as st
from modules.ventas import render_ventas as ventas_module


def render_ventas(usuario):
    st.title("Ventas")

    ventas_module(usuario)
