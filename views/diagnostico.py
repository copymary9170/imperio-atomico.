import importlib
import importlib.util

import streamlit as st

from views.diagnostico_tecnico import render_diagnostico_tecnico


def _missing_diagnostics_dependencies() -> list[str]:
    required = ["cv2", "numpy", "pytesseract", "pdf2image"]
    return [name for name in required if importlib.util.find_spec(name) is None]


def _render_diagnostico_ia(usuario):
    missing = _missing_diagnostics_dependencies()
    if missing:
        st.error(
            "El módulo de diagnóstico IA no está disponible en este entorno. "
            f"Faltan dependencias: {', '.join(missing)}."
        )
        st.info("La pestaña de diagnóstico técnico sí puede usarse aunque falten estas dependencias.")
        return

    diagnostico_runtime = importlib.import_module("modules.diagnostico")
    diagnostico_runtime = importlib.reload(diagnostico_runtime)
    diagnostico_module = diagnostico_runtime.render_diagnostico
    diagnostico_module(usuario)


def render_diagnostico(usuario):
    st.title("🧠 Diagnóstico")

    tab_tecnico, tab_ia = st.tabs([
        "🛠️ Diagnóstico técnico ERP",
        "🧠 Diagnóstico IA / OCR",
    ])

    with tab_tecnico:
        render_diagnostico_tecnico(usuario)

    with tab_ia:
        _render_diagnostico_ia(usuario)
