import streamlit as st
from database.connection import db_transaction


def render_login():

    st.title("🔐 Acceso al Sistema")

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):

        with db_transaction() as conn:

            user = conn.execute(
                "SELECT * FROM usuarios WHERE username=? AND activo=1",
                (usuario,)
            ).fetchone()

        if user and user["password_hash"] == password:

            st.session_state["usuario"] = user["username"]
            st.session_state["rol"] = user["rol"]

            st.success("Acceso concedido")
            st.rerun()

        else:
            st.error("Credenciales inválidas")
