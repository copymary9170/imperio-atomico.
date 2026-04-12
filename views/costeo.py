from __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def render_costeo(usuario: str) -> None:
    """Wrapper del módulo Costeo con control de permisos y carga segura"""

    if not require_permission("costeo.view", "🚫 No tienes acceso al módulo Costeo."):
        return

    try:
        from modules.costeo import render_costeo as costeo_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Costeo.")
        st.exception(exc)
        return

    st.session_state["perm_costeo_view"] = True
    st.session_state["perm_costeo_edit"] = has_permission("costeo.edit")
    st.session_state["costeo_readonly"] = not st.session_state["perm_costeo_edit"]

    if st.session_state["costeo_readonly"]:
        st.info("Modo solo lectura: puedes consultar costeo, pero no modificarlo.")

    costeo_module(usuario)
