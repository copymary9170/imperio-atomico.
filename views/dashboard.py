import streamlit as st
from modules.dashboard import render_dashboard as dashboard_module


def render_dashboard():
    st.title("📊  Panel de control")

    dashboard_module()
