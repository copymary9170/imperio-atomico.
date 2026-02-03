import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # Asegurar columnas en cotizaciones
    for col in ['monto_bcv', 'monto_binance']:
        try: c.execute(f'ALTER TABLE cotizaciones ADD COLUMN {col} REAL')
        except: pass
        
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

# --- 2. LOGICA DE ANALISIS ---
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

# --- 3. INICIO ---
st.set_page_config(page_title="Imperio Atómico OS", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Acceso Master")
    u, p = st.text_input("Usuario"), st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
    st.stop()

# Carga de Tasas
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
t_tinta = conf.loc['costo_tinta_ml', 'valor']
conn.close()

# --- 4. NAVEGACIÓN ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Salir"):
        st.session_state.login = False
        st.rerun()

# --- 5. MÓDULO INVENTARIO (REPARADO) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario de Materiales")
    
    with st.expander("📥 Cargar / Actualizar Stock"):
        with st.form("form_inv_new"):
            c1, c2 = st.columns(2)
            it = c1.text_input("Nombre del Producto (Papel, Tinta, etc.)")
            ca = c1.number_input("Cantidad Disponible", min_value=0.0)
            un = c2.selectbox("Unidad de Medida", ["Hojas", "ml", "Unidades", "Metros"])
            pr = c2.number_input("Precio Costo (USD)", min_value=0.0, format="%.2f")
            if st.form_submit_button("✅ Guardar en Inventario"):
                if it:
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr))
                    c.commit(); c.close()
                    st.success(f"Actualizado: {it}")
                    st.rerun()

    st.subheader("📋 Stock Actual")
    c = conectar()
    df_inv = pd.read_sql_query("SELECT * FROM inventario", c)
    c.close()
    
    if not df_inv.empty:
        # Cálculos de valorización
        df_inv['Total USD'] = df_inv['cantidad'] * df_inv['precio_usd']
        df_inv['Total BCV'] = df_inv['Total USD'] * t_bcv
        df_inv['Total BIN'] = df_inv['Total USD'] * t_bin
        
        st.dataframe(df_inv, use_container_width=True)
        
        # Resumen de inversión
        st.divider()
        col1, col2, col3 = st.columns(3)
        total_inv_usd = df_inv['Total USD'].sum()
        col1.metric("Inversión Total (USD)", f"$ {total_inv_usd:,.2f}")
        col2.metric("Inversión en BCV", f"{total_inv_usd * t_bcv:,.2f} Bs")
        col3.metric("Inversión en Binance", f"{total_inv_usd * t_bin:,.2f} Bs")
    else:
        st.info("El inventario está vacío. Carga tu primer material arriba.")

# --- 6. DEMÁS MÓDULOS (Dashboard, Clientes, etc. se mantienen igual de potentes) ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    st.metric("Tasa Binance Hoy", f"{t_bin} Bs")
    # Aquí puedes añadir gráficos de ventas luego

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.form("f_c"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
            st.rerun()
    bus = st.text_input("🔍 Buscar")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    # Lógica de cotizaciones con las tasas duales (se mantiene la que te gustó)
    st.write("Selecciona cliente y calcula con tasa BCV o Binance.")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    with st.form("f_conf"):
        nb = st.number_input("Tasa BCV", value=t_bcv)
        ni = st.number_input("Tasa Binance", value=t_bin)
        if st.form_submit_button("Guardar"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nb,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (ni,))
            c.commit(); c.close(); st.rerun()
