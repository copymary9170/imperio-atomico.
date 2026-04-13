from __future__ import annotations

import streamlit as st

from security.permissions import require_any_permission
from modules.rutas_produccion import render_rutas_produccion as rutas_module


def render_rutas_produccion(usuario: str) -> None:
    if not require_any_permission(
        ["produccion.route", "produccion.execute"],
        "🚫 No tienes acceso a Rutas de producción.",
    ):
        return

    st.title("🧭 Rutas de producción")
    rutas_module(usuario)

