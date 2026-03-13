import importlib.util

import streamlit as st


def _missing_diagnostics_dependencies() -> list[str]:
    required = ["cv2", "numpy", "pytesseract", "pdf2image"]
    return [name for name in required if importlib.util.find_spec(name) is None]


def render_diagnostico(usuario):
    st.title("🧠 Diagnóstico IA")

    missing = _missing_diagnostics_dependencies()
    if missing:
        st.error(
            "El módulo de diagnóstico no está disponible en este entorno. "
            f"Faltan dependencias: {', '.join(missing)}."
        )
        st.info("Instala las dependencias faltantes para habilitar esta vista.")
        return

    from modules.diagnostico import render_diagnostico as diagnostico_module

    diagnostico_module(usuario)
