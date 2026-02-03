import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# ==========================================
# 1. MOTOR UNIFICADO (Base de Datos + Lógica)
# ==========================================
def conectar():
    # check_same_thread=False es vital para Streamlit
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    # Tabla Usuarios
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (user TEXT PRIMARY KEY, pw TEXT, rol TEXT)')
    # ASEGURAR USUARIO ADMIN (Si no existe, lo crea)
    c.execute("SELECT * FROM usuarios WHERE user='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios VALUES ('admin', '1234', 'master')")
    
    # Tabla Clientes Real
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)')
    
    # Tabla Inventario Real
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    
    # Tabla Cotizaciones Real
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    
    conn.commit()
    conn.close()

# ==========================================
# 2. CONFIGURACIÓN E INICIO
# ==========================================
st.set_page_config(page_title="Imperio Atómico OS", layout="wide")
inicializar_sistema()

# Control de Estado de Login
if 'login' not in st.session_state:
    st.session_state.login = False

# ==========================================
# 3. PANTALLA DE ACCESO (LOGIN)
# ==========================================
if not st.session_state.login:
    st.title("🔐 Acceso al Sistema Administrativo")
    col1, col2 = st.columns([1, 2])
    with col1:
        u = st.text_input("Usuario (admin)")
        p = st.text_input("Contraseña (1234)", type="password")
        if st.button("Iniciar Sesión"):
            conn = conectar()
            c = conn.cursor()
            c.execute("SELECT rol FROM usuarios WHERE user=? AND pw=?", (u, p))
            res = c.fetchone()
            conn.close()
            if res:
                st.session_state.login = True
                st.session_state.user = u
                st.session_state.rol = res[0]
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# ==========================================
# 4. INTERFAZ PRINCIPAL (Sidebar)
# ==========================================
with st.sidebar:
    st.title("⚛️ Imperio Atómico")
    st.write(f"Conectado: **{st.session_state.user}**")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# ==========================================
# 5. MÓDULOS CONECTADOS A SQLITE
# ==========================================

# --- MÓDULO CLIENTES ---
if menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("cli_form"):
        nom = st.text_input("Nombre Completo")
        wha = st.text_input("WhatsApp")
        if st.form_submit_button("Guardar Cliente"):
            conn = conectar()
            conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nom, wha))
            conn.commit()
            conn.close()
            st.success("✅ Registrado")
    
    conn = conectar()
    df_cl = pd.read_sql_query("SELECT * FROM clientes", conn)
    conn.close()
    st.dataframe(df_cl, use_container_width=True)

# --- MÓDULO INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario Real")
    with st.expander("📥 Cargar Nuevo Insumo"):
        item = st.text_input("Nombre (ej. Papel Glossy)")
        cant = st.number_input("Cantidad Actual", min_value=0.0)
        unid = st.selectbox("Unidad", ["Hojas", "ml", "Metros", "Unid"])
        prec = st.number_input("Precio Costo USD", min_value=0.0)
        if st.button("Actualizar Stock"):
            conn = conectar()
            conn.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (item, cant, unid, prec))
            conn.commit()
            conn.close()
            st.rerun()
    
    conn = conectar()
    df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()
    st.table(df_inv)

# --- MÓDULO ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos")
    impresora = st.selectbox("Impresora Destino", ["Epson L1250", "HP Smart Tank", "J210a"])
    # Aquí puedes agregar lógica de costo por ml según impresora
    files = st.file_uploader("Subir diseños", accept_multiple_files=True)
    if files:
        st.info(f"Analizando para {impresora}...")
        # (Aquí va tu función de analizar_cmyk que ya tienes)

# --- MÓDULO CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración e Inflación")
    st.subheader("Control de Precios")
    tasa = st.number_input("Tasa del Dólar (Bs)", value=36.50)
    st.write("---")
    st.write("Aquí podrás gestionar los roles de usuario y las copias de seguridad de la base de datos.")
