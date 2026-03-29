from __future__ import annotations

from modules.planeacion_financiera import (
    render_planeacion_financiera as render_planeacion_financiera_module,
)


def render_planeacion_financiera(usuario: str) -> None:
    render_planeacion_financiera_module(usuario)
