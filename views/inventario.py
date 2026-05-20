from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import streamlit as st

from security.permissions import has_permission, require_permission


@contextmanager
def _clean_inventory_inner_navigation():
    """Oculta textos heredados del módulo interno cuando vive dentro del hub de Inventario / Almacén."""
    original_title = st.title
    original_selectbox = st.selectbox

    def patched_title(body: Any, *args: Any, **kwargs: Any):
        if str(body).strip() == "📦 Centro de Control de Inventario":
            return st.caption("Inventario operativo: productos, existencias, compras, movimientos y reportes.")
        return original_title(body, *args, **kwargs)

    def patched_selectbox(label: str, options, *args: Any, **kwargs: Any):
        if str(label).strip() == "Navegación del módulo de inventario":
            label = "Sección de inventario operativo"
        return original_selectbox(label, options, *args, **kwargs)

    st.title = patched_title
    st.selectbox = patched_selectbox
    try:
        yield
    finally:
        st.title = original_title
        st.selectbox = original_selectbox


def _render_inventario_original(usuario: str) -> None:
    try:
        from modules.configuracion import DEFAULT_CONFIG, get_current_config
        from modules.inventario import render_inventario as inventario_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Inventario.")
        st.exception(exc)
        return

    tasa_bcv_default = float(DEFAULT_CONFIG.get("tasa_bcv", 36.5))
    tasa_binance_default = float(DEFAULT_CONFIG.get("tasa_binance", 38.0))

    try:
        config = get_current_config()
    except Exception:
        config = {}

    try:
        tasa_bcv = float(config.get("tasa_bcv", st.session_state.get("tasa_bcv", tasa_bcv_default)) or tasa_bcv_default)
    except Exception:
        tasa_bcv = tasa_bcv_default

    try:
        tasa_binance = float(config.get("tasa_binance", st.session_state.get("tasa_binance", tasa_binance_default)) or tasa_binance_default)
    except Exception:
        tasa_binance = tasa_binance_default

    with _clean_inventory_inner_navigation():
        inventario_module(usuario, tasa_bcv=tasa_bcv, tasa_binance=tasa_binance)


def render_inventario(usuario: str) -> None:
    """Inventario operativo puro, sin pestañas anidadas duplicadas."""
    if not require_permission("inventario.view", "🚫 No tienes acceso al módulo Inventario."):
        return

    st.session_state["perm_inventario_view"] = True
    st.session_state["perm_inventario_create"] = has_permission("inventario.create")
    st.session_state["perm_inventario_edit"] = has_permission("inventario.edit")
    st.session_state["perm_inventario_move"] = has_permission("inventario.move")
    st.session_state["perm_inventario_adjust"] = has_permission("inventario.adjust")
    st.session_state["inventario_readonly"] = not any([
        st.session_state["perm_inventario_create"],
        st.session_state["perm_inventario_edit"],
        st.session_state["perm_inventario_move"],
        st.session_state["perm_inventario_adjust"],
    ])

    if st.session_state.get("inventario_readonly", False):
        st.info("Modo solo lectura: puedes consultar inventario, pero no crear, editar, mover ni ajustar.")

    _render_inventario_original(usuario)
