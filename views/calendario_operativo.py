import streamlit as st


def render_calendario_operativo(usuario="Sistema"):
    st.title("📅 Calendario operativo")
    st.caption(f"Usuario activo: {usuario}")

    eventos = [
        "Surtir material",
        "Pagos",
        "Seguro",
        "Pensión",
        "Exposiciones",
        "Ahorro",
        "Mantenimiento",
        "Clases",
    ]

    for evento in eventos:
        with st.container(border=True):
            st.write(f"📌 {evento}")
            st.caption("Fecha pendiente de programación")

    st.success("Calendario listo para conectar con recordatorios reales.")
