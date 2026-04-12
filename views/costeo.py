from __future__ import annotations

import streamlit as st

from security.permissions import require_permission


def render_costeo(usuario: str) -> None:
    """Wrapper del módulo Costeo con control de permisos y carga segura"""

    # 🔐 Permiso de acceso (temporal: usa inventario.view)
    if not require_permission("inventario.view", "🚫 No tienes acceso al módulo Costeo."):
        return

    try:
        from modules.costeo import render_costeo as costeo_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Costeo.")
        st.exception(exc)
        return

    # 🧠 Contexto para futuro control fino
    st.session_state["perm_costeo_view"] = True

    # 🚀 Render real
    costeo_module(usuario)
