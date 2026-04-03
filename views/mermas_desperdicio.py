import streamlit as st
from modules.mermas import render_mermas as mermas_module


def render_mermas(usuario):
    st.title("♻️ Mermas y desperdicio")
    mermas_module(usuario)


