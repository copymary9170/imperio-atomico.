import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz
import base_datos as db # Importamos nuestra arquitectura limpia

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Enterprise", layout="wide")
db.inicializar_sistema()

# --- SESIÓN Y SEGURIDAD ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Imperio")
    user = st.text_input("Usuario")
    pw = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        rol = db.login_user(user, pw)
        if rol:
            st.session_state.autenticado = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.stop()

# --- INTERFAZ PRINCIPAL ---
with st.sidebar:
    st.write(f"👤 Usuario: {st.session_state.user}")
    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
    
    st.divider()
    menu = st.radio("Menú Principal", ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "📦 Inventario", "🎨 Analizador"])
    tasa_bcv = st.number_input("Tasa Dólar (Bs)", value=36.50)

# --- MÓDULO CLIENTES ---
if menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes Real")
    with st.form("nuevo_cliente"):
        nom = st.text_input("Nombre")
        tel = st.text_input("WhatsApp")
        not_cl = st.text_area("Notas")
        if st.form_submit_button("Registrar"):
            db.add_cliente(nom, tel, not_cl)
            st.success("Cliente guardado.")
    
    st.subheader("Directorio")
    st.dataframe(db.get_clientes(), use_container_width=True)

# --- MÓDULO COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    clientes_list = db.get_clientes()['nombre'].tolist()
    
    with st.form("cots"):
        c_cli = st.selectbox("Seleccionar Cliente", clientes_list if clientes_list else ["Registrar cliente primero"])
        c_trab = st.text_input("Descripción del Trabajo")
        c_monto = st.number_input("Precio USD", min_value=0.0)
        if st.form_submit_button("Guardar"):
            db.add_cotizacion(c_cli, c_trab, c_monto)
            st.success("Cotización guardada exitosamente.")
    
    st.dataframe(db.get_cotizaciones(), use_container_width=True)

# --- MÓDULO INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario Real")
    with st.expander("➕ Cargar/Actualizar Insumo"):
        i_nom = st.text_input("Nombre del Insumo (Ej: Papel Glossy)")
        i_cant = st.number_input("Cantidad", min_value=0.0)
        i_un = st.selectbox("Unidad", ["Hojas", "ml", "Unidades", "Metros"])
        i_pre = st.number_input("Precio Costo USD", min_value=0.0)
        if st.button("Actualizar Stock"):
            db.update_inventario(i_nom, i_cant, i_un, i_pre)
            st.rerun()
            
    st.dataframe(db.get_inventario(), use_container_width=True)
