from __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def _get_rates() -> tuple[float, float]:
    try:
        from modules.configuracion import DEFAULT_CONFIG, get_current_config
    except Exception:
        return 36.5, 38.0

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

    return tasa_bcv, tasa_binance


def _load_inventory_module():
    try:
        from modules import inventario as inv_module
        inv_module._ensure_inventory_support_tables()
        inv_module._ensure_config_defaults()
        return inv_module
    except Exception as exc:
        st.error("No se pudo cargar el módulo interno de Inventario.")
        st.exception(exc)
        return None


def _render_safe(section_name: str, callback, *args, **kwargs) -> None:
    try:
        callback(*args, **kwargs)
    except Exception as exc:
        st.error(f"No se pudo cargar la sección {section_name}.")
        st.exception(exc)


def render_inventario(usuario: str) -> None:
    """Inventario operativo rescatado y organizado sin selector duplicado.

    Aquí solo quedan las secciones propias del inventario. Compras, proveedores,
    catálogo, kardex y documentos viven como pestañas principales del hub
    📦 Inventario / Almacén.
    """
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

    inv_module = _load_inventory_module()
    if inv_module is None:
        return

    st.caption("Inventario operativo: existencias, productos, variantes, movimientos, reposición básica, ajustes y reportes.")
    df = inv_module._load_inventory_df()

    tabs = st.tabs([
        "Resumen",
        "Existencias",
        "Productos",
        "Variantes",
        "Movimientos",
        "Reposición básica",
        "Ajustes",
        "Reportes",
        "Recetas",
        "Conteo físico",
        "Rentabilidad",
        "Integración",
    ])

    with tabs[0]:
        _render_safe("Resumen", inv_module._render_inventario_dashboard, df)
    with tabs[1]:
        _render_safe("Existencias", inv_module._render_existencias, df)
    with tabs[2]:
        _render_safe("Productos", inv_module._render_productos, usuario)
    with tabs[3]:
        _render_safe("Variantes", inv_module._render_variantes)
    with tabs[4]:
        _render_safe("Movimientos", inv_module._render_movimientos)
    with tabs[5]:
        _render_safe("Reposición básica", inv_module._render_reposicion, df)
    with tabs[6]:
        _render_safe("Ajustes", inv_module._render_ajustes, usuario)
    with tabs[7]:
        _render_safe("Reportes", inv_module._render_reportes, df)
    with tabs[8]:
        _render_safe("Recetas", inv_module._render_recetas_consumo, usuario)
    with tabs[9]:
        _render_safe("Conteo físico", inv_module._render_conteo_fisico, usuario)
    with tabs[10]:
        _render_safe("Rentabilidad", inv_module._render_rentabilidad_inventario, df)
    with tabs[11]:
        _render_safe("Integración", inv_module._render_integridad_e_integraciones)
