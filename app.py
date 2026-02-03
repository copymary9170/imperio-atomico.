import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime
import sqlite3

# --- 1. CONFIGURACIÓN Y BASE DE DATOS INTERNA ---
st.set_page_config(page_title="Imperio Atómico - Master", layout="wide")

def inicializar_db():
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cotizaciones 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  fecha TEXT, cliente TEXT, trabajo TEXT, 
                  monto REAL, estado TEXT)''')
    conn.commit()
    conn.close()

def guardar_cotizacion_db(cliente, trabajo, monto):
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    fecha = datetime.now().strftime('%Y-%m-%d')
    c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto, estado) VALUES (?,?,?,?,?)",
              (fecha, cliente, trabajo, monto, 'Pendiente'))
    conn.commit()
    conn.close()

def obtener_cotizaciones_db():
    conn = sqlite3.connect('imperio_data.db')
    df = pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY id DESC", conn)
    conn.close()
    return df

inicializar_db()

# --- 2. FUNCIÓN DEL ANALIZADOR ---
def analizar_cmyk_pro(file):
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

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Panel de Control")
    menu = st.radio("Navegación:", 
        ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])

# --- 4. LÓGICA DE LAS PESTAÑAS (Módulos) ---

if menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    st.info("Aquí irán las barras de tinta de esta tarde.")

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    with st.form("f_cot"):
        cli = st.text_input("Cliente")
        tra = st.text_input("Trabajo")
        mon = st.number_input("Monto USD", min_value=0.0)
        if st.form_submit_button("Guardar"):
            guardar_cotizacion_db(cli, tra, mon)
            st.success("¡Guardado!")
    st.dataframe(obtener_cotizaciones_db(), use_container_width=True)

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    st.text_input("Buscar Cliente")
    st.button("Registrar Nuevo")

elif menu == "🏗️ Producción":
    st.title("🏗️ Producción")
    st.selectbox("Impresora", ["Epson", "HP", "J210a"])
    st.write("Cola de impresión vacía.")

elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    st.write("Materiales en stock:")
    st.table(pd.DataFrame({"Material": ["Papel", "Tinta"], "Stock": [0, 0]}))

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador")
    files = st.file_uploader("Sube imágenes", type=["jpg","png","pdf"], accept_multiple_files=True)
    if files:
        for f in files:
            img, res = analizar_cmyk_pro(f)
            if img:
                st.image(img, caption=f.name, width=300)
                st.write(f"C:{res['C']:.1%} M:{res['M']:.1%} Y:{res['Y']:.1%} K:{res['K']:.1%}")

elif menu == "🔍 Manuales":
    st.title("🔍 Manuales")
    st.text_input("Error a buscar...")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    st.number_input("Tasa BCV", value=36.50)
    st.button("Guardar Cambios")
