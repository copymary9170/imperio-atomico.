import streamlit as st


def render_presupuesto_mensual(usuario="Sistema"):
    st.title("💰 Presupuesto mensual")
    st.caption(f"Usuario activo: {usuario}")

    st.subheader("Categorías financieras")

    categorias = [
        "Nómina",
        "Materiales",
        "Exposiciones",
        "Clases y aprendizaje",
        "Marketing",
        "Seguros",
        "Pensiones",
        "Ahorro objetivo",
    ]

    for categoria in categorias:
        with st.container(border=True):
            col1, col2, col3 = st.columns(3)
            col1.write(categoria)
            col2.metric("Presupuesto", "$0")
            col3.metric("Gastado", "$0")

    st.info("Este módulo ayudará a controlar flujo financiero y ahorro empresarial.")
