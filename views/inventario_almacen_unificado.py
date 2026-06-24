from __future__ import annotations

from services.inventario_demo_cleanup import eliminar_articulos_demo
from views.inventario_centro_elite import render_inventario_centro_elite


def render_inventario_almacen_unificado(usuario: str) -> None:
    """Entrada oficial y única del inventario de Copy Mary."""
    eliminar_articulos_demo()
    render_inventario_centro_elite(usuario)
