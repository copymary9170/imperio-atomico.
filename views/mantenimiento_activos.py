from __future__ import annotations

import streamlit as st

from modules.activos import ACTIVOS_UI_VERSION, render_activos


def render_mantenimiento_activos(usuario: str) -> None:
    st.title("🛠️ Mantenimiento de activos")
    st.caption(
        "Vista operativa de mantenimiento con priorización automática de backlog, "
        f"diagnóstico visual y trazabilidad de componentes · {ACTIVOS_UI_VERSION}."
    )
    render_activos(usuario)
