from __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st


def _load_planificacion_module():
    """Load the production planning module stored with a non-ASCII filename."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "modules"
        / "Planificación_de_producción.py"
    )
    spec = importlib.util.spec_from_file_location(
        "modules.planificacion_de_produccion", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar el módulo desde: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_planificacion_produccion(usuario: str) -> None:
    st.title("🗓️ Planificación de producción")
    st.caption(
        "Organiza, programa y controla tu producción: órdenes, tiempos, costos y ejecución."
    )

    try:
        module = _load_planificacion_module()
        module.render_produccion(usuario)
    except Exception as exc:
        st.error("Error cargando el módulo de planificación de producción")
        st.exception(exc)
