import streamlit as st

from legal_v4.ui import render_legal_v4

st.set_page_config(page_title="Legal V4.1 Enterprise", page_icon="⚖️", layout="wide")
render_legal_v4(st.session_state.get("usuario", "Sistema"))
