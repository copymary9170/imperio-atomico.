import streamlit as st


def render_publicaciones_marketing(usuario="Sistema"):
    st.title("📣 Publicaciones y marketing")
    st.caption(f"Usuario activo: {usuario}")

    plataformas = [
        "Instagram",
        "Facebook",
        "Promociones",
        "Campañas",
        "Publicaciones pendientes",
    ]

    cols = st.columns(2)

    for index, plataforma in enumerate(plataformas):
        with cols[index % 2]:
            with st.container(border=True):
                st.subheader(plataforma)
                st.write("Estado: pendiente")
                st.write("Fecha: por definir")

    st.info("Módulo preparado para integrarse con CRM y campañas de ventas.")
