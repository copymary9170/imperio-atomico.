from __future__ import annotations

import streamlit as st

from modules.activos import ACTIVOS_UI_VERSION, render_activos as render_activos_modern


def render_activos(usuario: str):
    st.caption(f"Vista renovada de activos · {ACTIVOS_UI_VERSION}")
    render_activos_modern(usuario)


