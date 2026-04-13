from __future__ import annotations

import streamlit as st

from security.permissions import require_permission
from modules.rutas_produccion import render_rutas_produccion as rutas_module


def render_rutas_produccion(usuario: str) -> None:
    if not require_permission("produccion.route", "🚫 No tienes acceso a Rutas de producción."):
        return

    try:
        rutas_module(usuario)
    except Exception as exc:
        st.error("No se pudo cargar el módulo de rutas de producción.")
        st.exception(exc)
