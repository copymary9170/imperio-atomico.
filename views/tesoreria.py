from __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def render_tesoreria(usuario: str) -> None:
    if not require_permission("tesoreria.view", "🚫 No tienes acceso al módulo Tesorería."):
        return

    st.session_state["perm_tesoreria_view"] = True
    st.session_state["perm_tesoreria_edit"] = has_permission("tesoreria.edit")

    st.session_state["tesoreria_readonly"] = not st.session_state["perm_tesoreria_edit"]

    try:
        from modules.tesoreria import render_tesoreria as render_tesoreria_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Tesorería.")
        st.exception(exc)
        return

    if st.session_state.get("tesoreria_readonly", False):
        st.info("Modo solo lectura: puedes consultar tesorería, pero no modificar registros.")

    render_tesoreria_module(usuario)
