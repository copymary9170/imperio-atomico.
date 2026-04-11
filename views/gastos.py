from __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def render_gastos(usuario: str) -> None:
    if not require_permission("gastos.view", "🚫 No tienes acceso al módulo Gastos."):
        return

    st.session_state["perm_gastos_view"] = True
    st.session_state["perm_gastos_create"] = has_permission("gastos.create")
    st.session_state["perm_gastos_edit"] = has_permission("gastos.edit")

    st.session_state["gastos_readonly"] = not any(
        [
            st.session_state["perm_gastos_create"],
            st.session_state["perm_gastos_edit"],
        ]
    )

    try:
        from modules.gastos import render_gastos as gastos_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Gastos.")
        st.exception(exc)
        return

    st.title("💸 Gastos")

    if st.session_state.get("gastos_readonly", False):
        st.info("Modo solo lectura: puedes consultar gastos, pero no registrar ni editar.")

    gastos_module(usuario)
