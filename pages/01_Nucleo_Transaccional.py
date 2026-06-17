from __future__ import annotations

import streamlit as st

from views.nucleo_transaccional import render_nucleo_transaccional


st.set_page_config(page_title="Núcleo transaccional", layout="wide", page_icon="⚛️")

usuario = st.session_state.get("usuario", "Sistema")
render_nucleo_transaccional(usuario)
