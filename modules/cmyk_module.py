import streamlit as st


def render_cmyk():
    st.title("Motor CMYK")

    st.write("Sistema de cálculo de tinta CMYK")

    c = st.number_input("Cyan %", 0.0, 100.0)
    m = st.number_input("Magenta %", 0.0, 100.0)
    y = st.number_input("Yellow %", 0.0, 100.0)
    k = st.number_input("Black %", 0.0, 100.0)

    if st.button("Calcular cobertura"):
        cobertura = (c + m + y + k) / 4
        st.success(f"Cobertura promedio: {cobertura:.2f}%")
