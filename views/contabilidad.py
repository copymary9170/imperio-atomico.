rom __future__ import annotations

import streamlit as st

from security.permissions import has_permission, require_permission


def render_contabilidad(usuario: str) -> None:
    # 🔐 Protección de acceso
    if not require_permission("contabilidad.view", "🚫 No tienes acceso a Contabilidad."):
        return

    # 🎯 Permisos internos
    st.session_state["perm_contabilidad_view"] = True
    # Compatibilidad: prioriza permisos actuales y mantiene fallback legacy.
    st.session_state["perm_contabilidad_create"] = has_permission("contabilidad.entry") or has_permission(
        "contabilidad.create"
    )
    st.session_state["perm_contabilidad_adjust"] = has_permission("contabilidad.approve") or has_permission(
        "contabilidad.adjust"
    )
    st.session_state["perm_contabilidad_close"] = has_permission("contabilidad.close")
    st.session_state["perm_contabilidad_audit"] = has_permission("auditoria.view") or has_permission(
        "contabilidad.audit"
    )

    st.session_state["contabilidad_readonly"] = not any(
        [
            st.session_state["perm_contabilidad_create"],
            st.session_state["perm_contabilidad_adjust"],
            st.session_state["perm_contabilidad_close"],
        ]
    )

    try:
        from modules.contabilidad import render_contabilidad_dashboard
    except Exception as exc:
        st.error("No se pudo cargar el módulo de Contabilidad.")
        st.exception(exc)
        return

    st.title("📚 Contabilidad")

    # 🚨 Advertencia si es solo lectura
    if st.session_state.get("contabilidad_readonly", False):
        st.warning(
            "Modo solo lectura: puedes consultar información contable, "
            "pero no registrar asientos, hacer ajustes ni cerrar períodos."
        )
