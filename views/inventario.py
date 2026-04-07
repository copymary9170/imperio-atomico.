import streamlit as st


def render_inventario(usuario: str) -> None:
    """Render wrapper that lazily imports the inventory module.

    Lazy import prevents the whole app from crashing at startup if a dependency
    required only by the inventory module is missing in the execution environment.
    """
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

    tasa_bcv = float(config.get("tasa_bcv", st.session_state.get("tasa_bcv", tasa_bcv_default)) or tasa_bcv_default)
    tasa_binance = float(
        config.get("tasa_binance", st.session_state.get("tasa_binance", tasa_binance_default)) or tasa_binance_default
    )

    inventario_module(usuario, tasa_bcv=tasa_bcv, tasa_binance=tasa_binance)
