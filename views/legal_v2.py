import streamlit as st

from legal_v4.ui import render_legal_v4
from security.permissions import has_permission
from views.legal_hub import render_legal_hub

LEGAL_RELEASE = "2026.06.28 - Legal V4.1 Enterprise"


def render_legal_v2(user: str = "Sistema") -> None:
    if not has_permission("legal.view"):
        st.error("No tienes permiso para acceder al Departamento Juridico.")
        return

    st.success(f"Version activa: {LEGAL_RELEASE}")

    available_modes = ["Legal V4.1 Enterprise", "Operacion juridica legacy"]
    mode = st.radio("Vista", available_modes, horizontal=True, key="legal_visible_mode")
    st.divider()

    if mode == "Legal V4.1 Enterprise":
        render_legal_v4(user)
    else:
        render_legal_hub(user)
