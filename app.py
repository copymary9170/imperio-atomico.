import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# ==========================================
# 1. MOTOR DE BASE DE DATOS (Conexión Segura)
# ==========================================
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    try:
        conn = conectar()
        c = conn.cursor()
        # Creamos las tablas necesarias
        c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error al inicializar DB: {e}")

# ==========================================
# 2. SISTEMA DE LOGIN (HARD-CODED / VIRTUAL)
# ==========================================
st.set_page_config(page_title="Imperio Atómico - Master OS", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state:
    st.session_state.login = False

# --- PANTALLA DE LOGIN ---
if not st.session_state.login:
    st.title("🛡️ Acceso de Seguridad Imperio Atómico")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        # Definimos las credenciales maestras aquí mismo
        USUARIO_MAESTRO = "admin"
        CLAVE_MAESTRA = "1234"
        
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        
        if st.button("🔓 Entrar al Sistema"):
            # Validación directa (No depende de la base de datos)
            if u == USUARIO_MAESTRO and p == CLAVE_MAESTRA:
                st.session_state.login = True
                st.session_state.user = "admin"
                st.success("Acceso concedido. Cargando...")
                st.rerun()
            else:
                st.error("❌ Usuario o Clave incorrectos")
    st.stop()

# ==========================================
# 3. INTERFAZ PRINCIPAL (Solo si logueó)
# ==========================================
with st.sidebar:
    st.title("⚛️ Imperio Atómico")
    st.write(f"Sesión activa: **{st.session_state.user}**")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "⚙️ Configuración"])
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- MÓDULO CLIENTES ---
if menu == "👥 Clientes":
    st.title("👥 Directorio de Clientes")
    with st.form("cli_f"):
        n = st.text_input("Nombre")
        w = st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            try:
                conn = conectar()
                conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w))
                conn.commit()
                conn.close()
                st.success(f"✅ {n} guardado con éxito")
            except:
                st.error("No se pudo guardar. Revisa permisos de DB.")

    try:
        conn = conectar()
        df_cl = pd.read_sql_query("SELECT * FROM clientes", conn)
        conn.close()
        st.dataframe(df_cl, use_container_width=True)
    except:
        st.info("Directorio vacío.")

# --- MÓDULO CONFIGURACIÓN (Inflación) ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes y Finanzas")
    st.subheader("💰 Control de Inflación")
    tasa = st.number_input("Dólar BCV (Bs)", value=36.50)
    costo_tinta = st.number_input("Costo Tinta USD/ml", value=0.05, format="%.4f")
    
    st.divider()
    st.subheader("💾 Base de Datos")
    if st.button("Descargar Respaldo (.db)"):
        with open("imperio_data.db", "rb") as f:
            st.download_button("Click para bajar archivo", f, file_name="imperio_backup.db")
