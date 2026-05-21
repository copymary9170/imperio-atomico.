import streamlit as st

from modules.cmyk_engine import render_cmyk as render_cmyk_modulo
from views.cmyk_control import render_cmyk_control
from views.contadores_clics import render_contadores_clics


def render_cmyk(usuario):
    st.title("🖨️ Impresiones / CMYK")
    st.caption("Análisis funcional de PDF, Word DOCX, JPG/JPEG y PNG, con costo por página, tinta, papel, desgaste, inventario, control y contadores.")

    render_cmyk_modulo(usuario)

    with st.expander("📊 Control CMYK", expanded=False):
        render_cmyk_control(usuario)

    with st.expander("🖨️ Contadores y clics", expanded=False):
        render_contadores_clics(usuario)
