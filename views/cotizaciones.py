import streamlit as st
from modules.configuracion import render_configuracion as configuracion_module


def render_configuracion(usuario):

    st.title("⚙️ Configuración")

    configuracion_module(usuario)
