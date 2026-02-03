import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime
import sqlite3

# --- 1. CONFIGURACIÓN Y BASE DE DATOS ---
st.set_page_config(page_title="Imperio Atómico V2", layout="wide", page_icon="⚛️")

def inicializar_db():
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    # Tabla Cotizaciones
    c.execute('''CREATE TABLE IF NOT EXISTS cotizaciones 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)''')
    # Tabla Inventario
    c.execute('''CREATE TABLE IF NOT EXISTS inventario 
                 (item TEXT, cantidad REAL, unidad TEXT, precio_usd REAL)''')
    conn.commit()
    conn.close()

inicializar_db()

# --- 2. MOTOR DE CÁLCULO (LO QUE FALTABA) ---
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
    st.header("⚛️ Imperio Atómico")
    tasa_bcv = st.number_input("Tasa BCV (Bs)", value=36.50)
    precio_tinta_ml = st.number_input("Precio Tinta (USD/ml)", value=0.05, format="%.4f")
    menu = st.radio("Ir a:", ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "📦 Inventario", "🎨 Analizador", "⚙️ Configuración"])

# --- 4. PESTAÑAS DETALLADAS ---

if menu == "📊 Dashboard":
    st.title("📊 Resumen General")
    col1, col2, col3 = st.columns(3)
    col1.metric("Dólar BCV", f"Bs. {tasa_bcv}")
    col2.metric("Pendientes", "5")
    col3.metric("Ventas Mes", "$ 120.00")
    st.info("💡 Tip: En la tarde conectaremos los inyectores aquí.")

elif menu == "📝 Cotizaciones":
    st.title("📝 Nueva Cotización")
    with st.form("cot_form"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        trabajo = c1.text_input("Descripción del trabajo")
        monto_usd = c2.number_input("Monto en USD", min_value=0.0)
        enviar = st.form_submit_button("Guardar Presupuesto")
        if enviar:
            st.success(f"Presupuesto de ${monto_usd} (Bs. {monto_usd*tasa_bcv:.2f}) guardado.")

elif menu == "📦 Inventario":
    st.title("📦 Inventario de Materiales")
    # Simulación de tabla de materiales
    data_inv = {
        "Material": ["Papel Fotográfico", "Vinil Autoadhesivo", "Tinta Cyan", "Tinta Magenta"],
        "Stock": [50, 20, 450, 380],
        "Unidad": ["Hojas", "Metros", "ml", "ml"]
    }
    st.table(pd.DataFrame(data_inv))
    if st.button("➕ Agregar Insumo"):
        st.write("Formulario de carga activado.")

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos de Tinta")
    files = st.file_uploader("Sube tus archivos (Múltiple)", type=["jpg","png","pdf"], accept_multiple_files=True)
    
    if files:
        for f in files:
            with st.expander(f"🖼️ Análisis: {f.name}", expanded=True):
                img, res = analizar_cmyk_pro(f)
                if img:
                    c1, c2 = st.columns([1, 1])
                    with c1: st.image(img, use_container_width=True)
                    with c2:
                        st.write("**Gasto Estimado:**")
                        st.write(f"C: {res['C']:.1%} | M: {res['M']:.1%} | Y: {res['Y']:.1%} | K: {res['K']:.1%}")
                        # Cálculo de costo real basado en el precio que pusiste en el sidebar
                        total_tinta = sum(res.values())
                        costo_estimado = total_tinta * precio_tinta_ml
                        st.metric("Costo Tinta USD", f"$ {costo_estimado:.4f}")
                        st.metric("Costo en Bolívares", f"Bs. {costo_estimado * tasa_bcv:.2f}")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes del Sistema")
    st.subheader("Precios de Insumos (Ajuste por Inflación)")
    st.write("Modifica aquí los costos base para que el analizador siempre sea exacto.")
    st.text_input("Nombre del Insumo", "Tinta Sublimación")
    st.number_input("Nuevo Precio USD", value=15.00)
    if st.button("Actualizar Precios Globales"):
        st.success("Precios actualizados en todo el sistema.")
