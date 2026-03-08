import streamlit as st
from modules.dashboard import render_dashboard as dashboard_module


def render_dashboard():
    st.title("Dashboard")

    dashboard_module()
