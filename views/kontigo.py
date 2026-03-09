import streamlit as st
from modules.kontigo import render_kontigo as kontigo_module


def render_kontigo(usuario):

    st.title("💳 Kontigo")

    kontigo_module(usuario)
