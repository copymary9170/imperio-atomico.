import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. MOTOR DE BASE DE DATOS (Con Reparación de Columnas) ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    # Tablas base
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bs REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # --- REPARADOR DE EMERGENCIA ---
    # Si la tabla cotizaciones existe pero es vieja, le faltará monto_bs. La agregamos:
    try:
        c.execute('ALTER TABLE cotizaciones ADD COLUMN monto_bs REAL')
    except:
        pass # Si ya existe, no hace nada
        
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

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

# --- 2. CONFIGURACIÓN Y LOGIN ---
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

# Carga de Precios Actuales
conn = conectar()
try:
    tasa_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='tasa_bcv'", conn).iloc[0,0]
    tinta_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='costo_tinta_ml'", conn).iloc[0,0]
except:
    tasa_val, tinta_val = 36.50, 0.05
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.metric("Tasa Actual", f"{tasa_val} Bs")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 4. MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Estado Financiero")
    conn = conectar()
    df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
    conn.close()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Dólar BCV", f"{tasa_val} Bs")
    if not df_cots.empty:
        # Usamos fillna(0) por si hay registros viejos sin monto
        total_usd = df_cots['monto_usd'].fillna(0).sum()
        c2.metric("Total Cotizado (USD)", f"$ {total_usd:,.2f}")
        c3.metric("Total en Bolívares", f"{total_usd * tasa_val:,.2f} Bs")
    
    st.divider()
    st.subheader("Últimas Cotizaciones")
    st.dataframe(df_cots.tail(10), use_container_width=True)

elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("f_cli"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
            st.success("Registrado")
            st.rerun()
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
        trab = st.text_input("Trabajo")
        m_usd = st.number_input("Precio USD", min_value=0.0)
        est = st.selectbox("Estado", ["Pendiente", "Pagado"])
        if st.form_submit_button("💾 Guardar"):
            if cli != "--":
                m_bs = m_usd * tasa_val
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bs, estado) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cli, trab, m_usd, m_bs, est))
                c.commit(); c.close()
                st.success("Cotización guardada")
                st.rerun()

elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    with st.form("f_inv"):
        it = st.text_input("Item")
        ca = st.number_input("Cant")
        un = st.selectbox("Unid", ["ml", "Hojas", "Unid"])
        pr = st.number_input("Precio USD")
        if st.form_submit_button("Actualizar"):
            c = conectar(); c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr)); c.commit(); c.close()
            st.rerun()
    c = conectar(); st.dataframe(pd.read_sql_query("SELECT * FROM inventario", c), use_container_width=True); c.close()

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    imp = st.selectbox("Impresora", ["Epson L1250", "HP Smart Tank", "J210a"])
    f = st.file_uploader("Subir archivos", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Resultado: {file.name}"):
                    st.image(img, width=200)
                    costo = sum(res.values()) * tinta_val
                    st.write(f"Costo: **${costo:.4f}** / **{costo*tasa_val:.2f} Bs**")

elif menu == "🔍 Manuales":
    st.title("🔍 Manuales Técnicos")
    with st.expander("🛠️ Reset Epson"): st.write("Instrucciones de reset...")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes de Inflación")
    with st.form("f_conf"):
        nt = st.number_input("Tasa BCV", value=tasa_val)
        ni = st.number_input("Precio Tinta ml", value=tinta_val, format="%.4f")
        if st.form_submit_button("Guardar"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nt,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (ni,))
            c.commit(); c.close()
            st.success("Actualizado")
            st.rerun()
