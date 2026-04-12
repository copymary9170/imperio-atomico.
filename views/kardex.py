from __future__ import annotations

import streamlit as st

from security.permissions import require_permission


def render_kardex(usuario: str) -> None:
    """Wrapper del módulo Kardex con control de permisos y carga segura"""

    if not require_permission("kardex.view", "🚫 No tienes acceso al Kardex."):
        return

    try:
        from modules.kardex import render_kardex as kardex_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Kardex.")
        st.exception(exc)
        return

    st.session_state["perm_kardex_view"] = True

    kardex_module(usuario)
