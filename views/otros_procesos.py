import streamlit as st
from modules.procesos import render_otros_procesos as procesos_module


def render_otros_procesos(usuario):

    st.title("🛠️ Otros Procesos")

    procesos_module(usuario)
