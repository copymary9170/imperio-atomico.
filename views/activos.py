from __future__ import annotations

import streamlit as st

from modules.activos import ACTIVOS_UI_VERSION, render_activos as render_activos_modern
from modules.activos_financieros import render_activos_financieros


def render_activos(usuario: str):
    st.caption(f"Vista renovada de activos · {ACTIVOS_UI_VERSION}")
    tab_tecnico, tab_financiero = st.tabs([
        "🧰 Control técnico",
        "💼 Finanzas y patrimonio",
    ])
    with tab_tecnico:
        render_activos_modern(usuario)
    with tab_financiero:
        render_activos_financieros(usuario)
