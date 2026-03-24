import streamlit as st

from modules.costeo import render_costeo as costeo_module


def render_costeo(usuario):
    st.title("🧮 Costeo")
    costeo_module(usuario)
