from __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def render_ventas(usuario: str) -> None:
    if not require_permission("ventas.view", "🚫 No tienes acceso al módulo Ventas."):
        return

    # Permisos disponibles dentro del módulo
    st.session_state["perm_ventas_view"] = True
    st.session_state["perm_ventas_create"] = has_permission("ventas.create")
    st.session_state["perm_ventas_edit"] = has_permission("ventas.edit")
    st.session_state["perm_ventas_cancel"] = has_permission("ventas.cancel")
    st.session_state["perm_ventas_approve_discount"] = has_permission("ventas.approve_discount")

    st.session_state["ventas_readonly"] = not any(
        [
            st.session_state["perm_ventas_create"],
            st.session_state["perm_ventas_edit"],
            st.session_state["perm_ventas_cancel"],
            st.session_state["perm_ventas_approve_discount"],
        ]
    )

    try:
        from modules.ventas import render_ventas as ventas_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Ventas.")
        st.exception(exc)
        return

    st.title("💰 Ventas")

    if st.session_state.get("ventas_readonly", False):
        st.info("Modo solo lectura: puedes consultar ventas, pero no registrar, editar ni anular.")

    ventas_module(usuario)
