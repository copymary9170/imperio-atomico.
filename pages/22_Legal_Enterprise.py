import os

import streamlit as st

st.set_page_config(page_title="Legal Enterprise", page_icon="⚖️", layout="wide")

if os.getenv("IMPERIO_LEGAL_ENTERPRISE_UI", "0") == "1":
    from legal.ui.enterprise import render_legal_enterprise

    render_legal_enterprise(st.session_state.get("usuario", "Sistema"))
else:
    from legal_v4.ui import render_legal_v4

    st.info("Legal Enterprise nuevo está disponible bajo feature flag `IMPERIO_LEGAL_ENTERPRISE_UI=1`. Se muestra Legal V4.1 estable.")
    render_legal_v4(st.session_state.get("usuario", "Sistema"))
