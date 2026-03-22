import streamlit as st

from modules.configuracion import get_current_config, render_rates_overview


def render_tasas(_usuario: str):
    st.info("Consulta rápida de las mismas tasas y comisiones definidas en Configuración, pero en modo solo lectura.")

    try:
        config = get_current_config()
    except Exception as exc:
        st.error("No se pudieron cargar las tasas activas.")
        st.exception(exc)
        return

    render_rates_overview(config)
