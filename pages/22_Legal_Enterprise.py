import streamlit as st
from views.legal_enterprise_phase2 import render_legal_enterprise_phase2

st.set_page_config(page_title="Legal Enterprise", page_icon="🏛️", layout="wide")
render_legal_enterprise_phase2(st.session_state.get("usuario", "Sistema"))
