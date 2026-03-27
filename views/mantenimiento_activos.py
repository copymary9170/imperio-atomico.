from __future__ import annotations

from modules.operacion_industrial import render_operacion_industrial


def render_mantenimiento_activos(usuario: str) -> None:
    render_operacion_industrial(usuario)
