import streamlit as st

from views.legal_enterprise_phase2 import render_legal_enterprise_phase2
from views.legal_hub import render_legal_hub


def render_legal_v2(user: str = "Sistema") -> None:
    st.title("⚖️ Departamento Jurídico")
    st.caption("Operación legal y arquitectura Enterprise visibles desde el mismo módulo.")

    mode = st.radio(
        "Vista",
        ["Operación jurídica", "Enterprise"],
        horizontal=True,
        key="legal_v2_visible_mode",
    )
    st.divider()

    if mode == "Enterprise":
        render_legal_enterprise_phase2(user)
    else:
        render_legal_hub(user)
