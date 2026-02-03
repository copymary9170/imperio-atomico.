import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. BASE DE DATOS (Cerebro) ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
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

# --- 2. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Imperio Atómico - Enterprise", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False

# --- 3. LOGIN ---
if not st.session_state.login:
    st.title("🔐 Acceso Master")
    u = st.text_input("Usuario")
    p = st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
        else:
            st.error("Clave incorrecta")
    st.stop()

# --- 4. CARGA DE PRECIOS (Inflación) ---
conn = conectar()
tasa_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='tasa_bcv'", conn).iloc[0,0]
tinta_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='costo_tinta_ml'", conn).iloc[0,0]
conn.close()

# --- 5. NAVEGACIÓN ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.metric("Tasa BCV", f"{tasa_val} Bs")
    menu = st.radio("Menú", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "💰 Finanzas Pro", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 6. LÓGICA DE MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    col1, col2, col3 = st.columns(3)
    col1.metric("Dólar Hoy", f"{tasa_val} Bs")
    st.info("💡 Esperando datos de inyectores para el gráfico de barras.")

elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("form_cliente"):
        nom = st.text_input("Nombre del Cliente")
        wha = st.text_input("WhatsApp")
        submit_cl = st.form_submit_button("Guardar Cliente")
        if submit_cl:
            c = conectar()
            c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nom, wha))
            c.commit(); c.close()
            st.success("✅ Cliente guardado")
    
    bus = st.text_input("🔍 Buscar Cliente")
    c = conectar()
    df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c)
    c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📦 Inventario":
    st.title("📦 Inventario de Insumos")
    with st.form("form_inv"):
        it = st.text_input("Nombre del Item")
        ca = st.number_input("Cantidad", min_value=0.0)
        un = st.selectbox("Unidad", ["ml", "Hojas", "Unids", "Mts"])
        pr = st.number_input("Precio USD", min_value=0.0)
        submit_inv = st.form_submit_button("Actualizar Stock")
        if submit_inv:
            c = conectar()
            c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr))
            c.commit(); c.close()
            st.rerun()
    
    c = conectar()
    df_inv = pd.read_sql_query("SELECT * FROM inventario", c)
    c.close()
    st.dataframe(df_inv, use_container_width=True)

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    imp = st.selectbox("Selecciona Impresora", ["Epson L1250", "HP Smart Tank", "J210a"])
    f = st.file_uploader("Subir archivos", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Análisis: {file.name}"):
                    c1, c2 = st.columns(2)
                    c1.image(img, use_container_width=True)
                    costo = sum(res.values()) * tinta_val
                    c2.metric("Costo USD", f"${costo:.4f}")
                    c2.metric("Costo Bs", f"{costo*tasa_val:.2f} Bs")

elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    with st.expander("🛠️ Epson L1250 - Reset Almohadillas"):
        st.write("1. Usar WIC Reset o Adjustment Program.")
        st.write("2. Resetear contador 'Main Pad'.")
    with st.expander("🛠️ HP Smart Tank - Cabezales"):
        st.write("Realizar limpieza nivel 2 si hay rayas en la impresión.")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes de Inflación")
    with st.form("form_config"):
        nt = st.number_input("Nueva Tasa BCV (Bs)", value=tasa_val)
        ni = st.number_input("Nuevo Precio Tinta (USD/ml)", value=tinta_val, format="%.4f")
        if st.form_submit_button("Guardar Cambios Globales"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nt,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (ni,))
            c.commit(); c.close()
            st.success("✅ Sistema actualizado")
            st.rerun()
