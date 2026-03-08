import streamlit as st
from modules.corte import render_corte as corte_module


def render_corte(usuario):
    st.title("Corte Industrial")

    corte_module(usuario)
