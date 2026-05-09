import streamlit as st


def render_nomina_trabajadores(usuario="Sistema"):
    st.title("👨‍💼 Nómina y trabajadores")
    st.caption(f"Usuario activo: {usuario}")

    st.info("Control de pagos, bienestar, seguro, pensión, extras y total mensual por trabajador.")

    st.subheader("Resumen de nómina")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Trabajadores", "0")
    col2.metric("Pago base", "$0")
    col3.metric("Seguro + pensión", "$0")
    col4.metric("Total mensual", "$0")

    st.subheader("Campos clave")
    st.write("• Trabajador")
    st.write("• Puesto")
    st.write("• Pago base")
    st.write("• Seguro")
    st.write("• Pensión")
    st.write("• Extras")
    st.write("• Total mensual")
    st.write("• Estado")

    st.warning("Pendiente: conectar esta vista a la tabla real de trabajadores/nomina en la base de datos.")
