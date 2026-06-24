from __future__ import annotations

from modules.configuracion import render_configuracion


def render_configuracion_sistema(usuario: str) -> None:
    """Muestra la configuración general usando el módulo central existente."""
    render_configuracion(usuario)
