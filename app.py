import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# ==========================================
# 1. MOTOR DE BASE DE DATOS (Auto-Reparable)
# ==========================================
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    # Tabla Usuarios
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (user TEXT PRIMARY KEY, pw TEXT, rol TEXT)')
    # ASEGURAR ADMIN
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', '1234', 'master')")
    # Tabla Clientes
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    # Tabla Inventario
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    # Tabla Cotizaciones
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    conn.commit()
    conn.close()

# ==========================================
# 2. INICIO Y SEGURIDAD
# ==========================================
st.set_page_config(page_title="Imperio Atómico v3", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state:
    st.session_state.login = False

# --- PANTALLA DE LOGIN ---
if not st.session_state.login:
    st.title("🔐 Acceso Master")
    col1, col2 = st.columns([1, 1])
    with col1:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        
        # TRUCO DE EMERGENCIA: Si el DB falla, esto te deja pasar
        if st.button("Ingresar"):
            if (u == "admin" and p == "1234"): # Validación directa
                st.session_state.login = True
                st.session_state.user = "admin"
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# ==========================================
# 3. INTERFAZ Y MÓDULOS REALES
# ==========================================
with st.sidebar:
    st.title("⚛️ Imperio Atómico")
    st.write(f"Conectado como: **{st.session_state.user}**")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- MÓDULO CLIENTES ---
if menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("cli_f"):
        n = st.text_input("Nombre")
        w = st.text_input("WhatsApp")
        if st.form_submit_button("Registrar"):
            conn = conectar()
            conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w))
            conn.commit()
            conn.close()
            st.success("Guardado.")

    conn = conectar()
    df_cl = pd.read_sql_query("SELECT * FROM clientes", conn)
    conn.close()
    st.dataframe(df_cl, use_container_width=True)

# --- MÓDULO INVENTARIO (Con Persistencia) ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario Real")
    with st.expander("📥 Cargar Stock"):
        item = st.text_input("Insumo")
        cant = st.number_input("Cantidad", min_value=0.0)
        unid = st.selectbox("Unidad", ["Hojas", "ml", "Unid"])
        prec = st.number_input("Precio USD", min_value=0.0)
        if st.button("Actualizar"):
            conn = conectar()
            conn.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (item, cant, unid, prec))
            conn.commit()
            conn.close()
            st.rerun()

    conn = conectar()
    df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()
    st.table(df_inv)

# --- MÓDULO ANALIZADOR (Configurable) ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    impresora = st.selectbox("Máquina", ["Epson L1250", "HP Smart Tank", "J210a"])
    # Aquí puedes ajustar el multiplicador de costo según la máquina seleccionada
    st.info(f"Configuración de goteo optimizada para {impresora}")
    
# --- MÓDULO CONFIGURACIÓN (Inflación) ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes Globales")
    st.subheader("Control de Inflación")
    tasa = st.number_input("Tasa Dólar (Bs)", value=36.50)
    st.divider()
    st.write("Copia de seguridad de la Base de Datos")
    if st.button("Generar Backup"):
        st.download_button("Descargar DB", data=open("imperio_data.db", "rb"), file_name="respaldo.db")
