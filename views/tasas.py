import streamlit as st
from modules.tasas import render_tasas as tasas_module


def render_tasas(usuario):

    st.title("👀 Tasas activas")

    tasas_module(usuario)
