import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. BASE DE DATOS (Cerebro del Sistema) ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

# --- 2. MOTOR DE ANÁLISIS ---
def analizar_cmyk(file):
    try:
        if file.type == "application/pdf":
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(file).convert("RGB")
        pix_arr = np.array(img) / 255.0
        k = 1 - np.max(pix_arr, axis=2)
        c = (1-pix_arr[:,:,0]-k)/(1-k+1e-9)
        m = (1-pix_arr[:,:,1]-k)/(1-k+1e-9)
        y = (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        return img, {"C": c.mean(), "M": m.mean(), "Y": y.mean(), "K": k.mean()}
    except: return None, None

# --- 3. SEGURIDAD Y ESTADO ---
st.set_page_config(page_title="Imperio Atómico - Full OS", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🛡️ Acceso Master")
    u, p = st.text_input("Usuario"), st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
    st.stop()

# --- 4. BARRA LATERAL (Carga Precios Reales) ---
conn = conectar()
tasa_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='tasa_bcv'", conn).iloc[0,0]
tinta_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='costo_tinta_ml'", conn).iloc[0,0]
conn.close()

with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.metric("Tasa BCV", f"{tasa_val} Bs")
    menu = st.radio("Menú", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "🏗️ Producción", "📦 Inventario", "🎨 Analizador", "💰 Finanzas Pro", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 5. LÓGICA DE MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    col1, col2, col3 = st.columns(3)
    col1.metric("Tasa del Día", f"{tasa_val} Bs")
    st.info("💡 Aquí se conectarán los niveles de tinta esta tarde.")

elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.expander("➕ Nuevo Cliente"):
        with st.form("c_f"):
            n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
            if st.form_submit_button("Guardar"):
                c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
                st.success("Registrado")
    bus = st.text_input("🔍 Buscar Cliente")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    # Formulario para guardar cotizaciones reales en la base de datos
    st.info("Registra aquí los presupuestos para tus clientes.")

elif menu == "🏗️ Producción":
    st.title("🏗️ Cola de Producción")
    st.warning("No hay órdenes activas.")

elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    with st.form("i_f"):
        it, ca, un, pr = st.text_input("Item"), st.number_input("Cant"), st.selectbox
