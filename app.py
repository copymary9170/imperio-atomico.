import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. MOTOR DE BASE DE DATOS (Reparador de Tasas) ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # REPARADOR: Asegurar que existan ambas columnas de tasa
    columnas = [('monto_bcv', 'REAL'), ('monto_binance', 'REAL')]
    for col, tipo in columnas:
        try:
            c.execute(f'ALTER TABLE cotizaciones ADD COLUMN {col} {tipo}')
        except: pass
        
    # Valores por defecto de las tasas
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

# --- 3. INICIO Y SEGURIDAD ---
st.set_page_config(page_title="Imperio Atómico - Tasas Duales", layout="wide")
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

# Carga de Tasas Reales
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
t_tinta = conf.loc['costo_tinta_ml', 'valor']
conn.close()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 **BCV:** {t_bcv} Bs\n\n🔶 **Binance:** {t_bin} Bs")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 5. MODULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Resumen General")
    c1, c2, c3 = st.columns(3)
    c1.metric("Tasa BCV", f"{t_bcv} Bs")
    c2.metric("Tasa Binance", f"{t_bin} Bs")
    c3.metric("Diferencia", f"{round(t_bin - t_bcv, 2)} Bs")

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.form("fc"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
            st.success("Guardado"); st.rerun()
    bus = st.text_input("🔍 Buscar")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📝 Cotizaciones":
    st.title("📝 Nueva Cotización")
    c = conectar()
    lista_clis = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist()
    c.close()

    with st.form("f_cot"):
        cli = st.selectbox("Cliente", ["--"] + lista_clis)
        trab = st.text_input("Descripción del Trabajo")
        m_usd = st.number_input("Precio en USD", min_value=0.0)
        
        st.write(f"💵 **Cobro BCV:** {round(m_usd * t_bcv, 2)} Bs")
        st.write(f"🔶 **Cobro Binance:** {round(m_usd * t_bin, 2)} Bs")
        
        if st.form_submit_button("💾 Guardar Cotización"):
            if cli != "--":
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cli, trab, m_usd, m_usd*t_bcv, m_usd*t_bin, "Pendiente"))
                c.commit(); c.close()
                st.success("✅ Cotización Registrada")
                st.rerun()

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    f = st.file_uploader("Diseños", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Resultado: {file.name}"):
                    costo = sum(res.values()) * t_tinta
                    st.image(img, width=200)
                    st.write(f"Costo: ${costo:.4f}")
                    st.write(f"BCV: {round(costo*t_bcv, 2)} Bs | Binance: {round(costo*t_bin, 2)} Bs")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Centro de Inflación")
    with st.form("f_conf"):
        nbcv = st.number_input("Tasa BCV Hoy", value=t_bcv)
        nbin = st.number_input("Tasa Binance Hoy", value=t_bin)
        ntin = st.number_input("Precio Tinta (USD/ml)", value=t_tinta, format="%.4f")
        if st.form_submit_button("Actualizar Tasas"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nbcv,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (nbin,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (ntin,))
            c.commit(); c.close()
            st.success("Tasas actualizadas con éxito")
            st.rerun()
