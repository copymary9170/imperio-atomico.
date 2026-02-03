import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. BASE DE DATOS Y LÓGICA ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # Asegurar columnas
    for col in ['monto_bcv', 'monto_binance']:
        try: c.execute(f'ALTER TABLE cotizaciones ADD COLUMN {col} REAL')
        except: pass
        
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
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

# --- 2. INICIO ---
st.set_page_config(page_title="Imperio Atómico - Full OS", layout="wide")
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

# --- 3. MENÚ ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Salir"):
        st.session_state.login = False
        st.rerun()

# --- 4. MÓDULOS ---

if menu == "🎨 Analizador":
    st.title("🎨 Analizador de Tinta (Costos Reales)")
    imp = st.selectbox("Máquina", ["Epson L1250", "HP Smart Tank", "J210a"])
    f = st.file_uploader("Subir diseño", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Resultado: {file.name}"):
                    st.image(img, width=250)
                    costo_base = sum(res.values()) * t_tinta
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Costo USD", f"${costo_base:.4f}")
                    col2.metric("Precio BCV", f"{costo_base*t_bcv:.2f} Bs")
                    col3.metric("Precio BIN", f"{costo_base*t_bin:.2f} Bs")

elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    m1, m2 = st.columns(2)
    with m1:
        with st.expander("🛠️ Epson L1250 - Reset Almohadillas"):
            st.write("1. Ejecutar AdpProg.exe\n2. Particular Adjustment Mode\n3. Waste Ink Pad Counter\n4. Check & Initialize.")
    with m2:
        with st.expander("💧 HP Smart Tank - Purga"):
            st.write("Si hay aire en mangueras, usar herramienta de cebado o limpieza profunda desde el driver.")

elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    with st.form("fi"):
        it = st.text_input("Item")
        ca = st.number_input("Cant")
        un = st.selectbox("Unid", ["Hojas", "ml", "Unid"])
        pr = st.number_input("Precio USD")
        if st.form_submit_button("Actualizar"):
            c = conectar(); c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr)); c.commit(); c.close(); st.rerun()
    c = conectar(); st.dataframe(pd.read_sql_query("SELECT * FROM inventario", c), use_container_width=True); c.close()

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    c = conectar(); lista = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist(); c.close()
    with st.form("fcot"):
        cl = st.selectbox("Cliente", ["--"] + lista)
        tr = st.text_input("Trabajo")
        mu = st.number_input("Monto USD")
        if st.form_submit_button("Guardar"):
            if cl != "--":
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cl, tr, mu, mu*t_bcv, mu*t_bin, "Pendiente"))
                c.commit(); c.close(); st.success("Guardado"); st.rerun()

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.form("fcl"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close(); st.rerun()
    bus = st.text_input("🔍 Buscar")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "⚙️ Configuración":
    st.title("⚙️ Inflación y Costos")
    with st.form("fcon"):
        nb = st.number_input("Tasa BCV", value=t_bcv)
        ni = st.number_input("Tasa Binance", value=t_bin)
        nt = st.number_input("Precio Tinta ml", value=t_tinta, format="%.4f")
        if st.form_submit_button("Guardar"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nb,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (ni,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (nt,))
            c.commit(); c.close(); st.rerun()
