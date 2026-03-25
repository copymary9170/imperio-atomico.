import streamlit as st

from modules.crm import render_crm as crm_module



def render_crm(usuario):
    st.title("🤝 CRM")
    crm_module(usuario)
