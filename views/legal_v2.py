import streamlit as st

from security.permissions import has_permission
from views.legal_enterprise_phase2 import render_legal_enterprise_phase2
from views.legal_hub import render_legal_hub


def render_legal_v2(user: str = "Sistema") -> None:
    if not has_permission("legal.view"):
        st.error("🚫 No tienes permiso para acceder al Departamento Jurídico.")
        st.caption("Solicita el permiso legal.view a un administrador del sistema.")
        return

    st.title("⚖️ Departamento Jurídico")
    st.caption("Operación legal y arquitectura Enterprise visibles desde el mismo módulo.")

    available_modes = ["Operación jurídica"]
    if has_permission("legal.admin") or has_permission("legal.audit.view"):
        available_modes.append("Enterprise")

    mode = st.radio(
        "Vista",
        available_modes,
        horizontal=True,
        key="legal_v2_visible_mode",
    )
    st.divider()

    if mode == "Enterprise":
        render_legal_enterprise_phase2(user)
    else:
        render_legal_hub(user)
