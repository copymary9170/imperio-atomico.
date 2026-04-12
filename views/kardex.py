from __future__ import annotations

import streamlit as st

from security.permissions import require_permission


def render_kardex(usuario: str) -> None:
    """Wrapper del módulo Kardex con control de permisos y carga segura"""

    # 🔐 Permiso de acceso
    if not require_permission("inventario.view", "🚫 No tienes acceso al Kardex."):
        return

    try:
        from modules.kardex import render_kardex as kardex_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Kardex.")
        st.exception(exc)
        return

    # 🧠 Contexto opcional futuro (puedes expandir luego)
    st.session_state["perm_kardex_view"] = True

    # 🚀 Render del módulo real
    kardex_module(usuario)
