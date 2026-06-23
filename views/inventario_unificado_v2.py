from __future__ import annotations

import views.inventario_unificado as base
from views.inventario_unificado_form_v2 import normalizar_pegado, render_form


def render_inventario_unificado(usuario: str) -> None:
    base._render_form_crear = render_form
    base._data_para_crear = normalizar_pegado
    base.render_inventario_unificado(usuario)
