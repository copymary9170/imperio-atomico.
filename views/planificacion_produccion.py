rom __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st

from security.permissions import require_any_permission


def _load_planificacion_module():
    """Carga el módulo de planificación almacenado con nombre no ASCII."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "modules"
        / "Planificación_de_producción.py"
    )

    if not module_path.exists():
        raise FileNotFoundError(f"No existe el archivo del módulo: {module_path}")

    spec = importlib.util.spec_from_file_location(
        "modules.planificacion_de_produccion",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el módulo desde: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_planificacion_produccion(usuario: str) -> None:
    if not require_any_permission(
        ["produccion.plan", "produccion.execute"],
        "🚫 No tienes acceso a Planificación de producción.",
    ):
        return

    try:
        module = _load_planificacion_module()

        if hasattr(module, "render_planificacion_produccion"):
            module.render_planificacion_produccion(usuario)
        elif hasattr(module, "render_produccion"):
            module.render_produccion(usuario)
        else:
            raise AttributeError(
                "El módulo no expone ni 'render_planificacion_produccion(usuario)' "
                "ni 'render_produccion(usuario)'."
            )

    except Exception as exc:
        st.error("No se pudo cargar el módulo de planificación de producción.")
        st.exception(exc)
