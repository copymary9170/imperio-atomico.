import streamlit as st


def render_inventario(usuario: str) -> None:
    """Render wrapper that lazily imports the inventory module.

    Lazy import prevents the whole app from crashing at startup if a dependency
    required only by the inventory module is missing in the execution environment.
    """
    try:
        from modules.inventario import render_inventario as inventario_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Inventario.")
        st.exception(exc)
        return

    inventario_module(usuario)
