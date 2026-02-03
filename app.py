import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime
import database  # Tu cerebro de datos

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Sistema Vivo", layout="wide")
database.inicializar_sistema() 

# --- FUNCIÓN TÉCNICA (Analizador) ---
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
        c, m, y = (1-pix_arr[:,:,0]-k)/(1-k+1e-9), (1-pix_arr[:,:,1]-k)/(1-k+1e-9), (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        return img, {"C": c.mean(), "M": m.mean(), "Y": y.mean(), "K": k.mean()}
    except: return None, None

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Panel de Control")
    menu = st.radio("Navegación:", 
        ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    st.info("Esperando datos de diagnóstico de esta tarde para activar las barras de tinta.")
    c1, c2 = st.columns(2)
    c1.metric("Pendientes por Cobrar", "$ 0.00")
    c2.metric("Órdenes en Cola", "0")

# --- COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Presupuestos")
    with st.form("nueva_cot"):
        col1, col2 = st.columns(2)
        with col1:
            c_nombre = st.text_input("Nombre del Cliente")
            c_trabajo = st.text_input("Trabajo (Ej: 50 Libretas)")
        with col2:
            c_monto = st.number_input("Precio USD", min_value=0.0)
            btn = st.form_submit_button("Guardar Cotización")
        if btn:
            database.guardar_cotizacion(c_nombre, c_trabajo, c_monto)
            st.success(f"✅ Cotización para {c_nombre} guardada.")
    st.subheader("📋 Historial")
    st.dataframe(database.obtener_cotizaciones(), use_container_width=True)

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    st.write("Aquí podrás buscar y registrar tus clientes VIP.")
    # Buscador rápido
    bus = st.text_input("🔍 Buscar por nombre o WhatsApp")
    st.warning("Módulo en migración a base de datos...")

# --- PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Línea de Producción")
    st.write("Control de trabajos en máquinas.")
    st.selectbox("Filtrar por Máquina", ["Epson L1250", "HP Smart Tank", "HP Deskjet"])
    st.info("No hay órdenes activas actualmente.")

# --- INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Almacén Central")
    st.write("Control de papel, tintas y materiales.")
    # Tabla simple por ahora
    st.table(pd.DataFrame({"Material": ["Papel Glossy", "Tinta Negra"], "Stock": [100, 500], "Unidad": ["Hojas", "ML"]}))

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico (Múltiple)")
    archivos_subidos = st.file_uploader("Sube uno o varios archivos", type=["jpg","png","pdf"], accept_multiple_files=True)
    if archivos_subidos:
        for f in archivos_subidos:
            with st.expander(f"🖼️ Analizando: {f.name}", expanded=True):
                img, res = analizar_cmyk_pro(f)
                if img:
                    c1, c2 = st.columns([1, 1])
                    with c1: st.image(img, use_container_width=True)
                    with c2:
                        st.write(f"💧 C: {res['C']:.2%} | 🌸 M: {res['M']:.2%}")
                        st.write(f"🟡 Y: {res['Y']:.2%} | ⚫ K: {res['K']:.2%}")

# --- MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    busqueda = st.text_input("Buscar manual o error...")
    st.info("Próximamente: Manual de limpieza de cabezales Epson.")

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes del Sistema")
    st.subheader("💹 Tasas de Cambio")
    st.number_input("Tasa BCV", value=36.50)
    st.number_input("Tasa Binance", value=45.00)
    if st.button("Guardar Ajustes"):
        st.success("Configuración actualizada.")
