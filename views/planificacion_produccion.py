from __future__ import annotations

import streamlit as st

from modules import planificacion_produccion as planificacion_module
from security.permissions import require_any_permission


def render_planificacion_produccion(usuario: str) -> None:
    if not require_any_permission(
        ["produccion.plan", "produccion.execute"],
        "🚫 No tienes acceso a Planificación de producción.",
    ):
        return

    try:
        if hasattr(planificacion_module, "render_planificacion_produccion"):
            planificacion_module.render_planificacion_produccion(usuario)
        elif hasattr(planificacion_module, "render_produccion"):
            planificacion_module.render_produccion(usuario)
        else:
            raise AttributeError(
                "El módulo no expone ni 'render_planificacion_produccion(usuario)' "
                "ni 'render_produccion(usuario)'."
            )

    except Exception as exc:
        st.error("No se pudo cargar el módulo de planificación de producción.")
        st.exception(exc)
