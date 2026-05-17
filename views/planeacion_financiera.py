from __future__ import annotations

import streamlit as st

from modules.planeacion_financiera import (
    render_planeacion_financiera as render_planeacion_financiera_module,
)
from views.finanzas_control import render_finanzas_control


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💼 Finanzas")

    tab_planeacion, tab_control = st.tabs([
        "Planeación financiera",
        "📊 Control ejecutivo",
    ])

    with tab_planeacion:
        render_planeacion_financiera_module(usuario)

    with tab_control:
        render_finanzas_control(usuario)
