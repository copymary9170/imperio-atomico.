"""Compatibilidad de entrada para Streamlit.

Este archivo existía con una versión monolítica y antigua de la app.
Para evitar que despliegues o comandos heredados sigan mostrando la UI vieja,
redirecciona al entrypoint actual modular (`app.py`).
"""

import app  # noqa: F401
