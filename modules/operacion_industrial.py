from __future__ import annotations

from modules.operacion_industrial_ui.dashboard import render_operacion_industrial_dashboard
from services.operacion_industrial_service import OperacionIndustrialService


def render_operacion_industrial(usuario: str) -> None:
    """Renderiza el dashboard unificado de operación industrial."""
    service = OperacionIndustrialService()
    render_operacion_industrial_dashboard(usuario, service)
