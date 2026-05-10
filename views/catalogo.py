import streamlit as st

from modules.catalogo_visual import render_catalogo_hub


def render_catalogo(usuario):
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_catalogo_hub(usuario)
