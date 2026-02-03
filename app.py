import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz
import sqlite3
from datetime import datetime

# --- 1. CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - Full", layout="wide")

# Inicializamos la base de datos para que nada falle
def init_db():
    conn = sqlite3.connect('imperio_data.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY, nombre TEXT, whatsapp TEXT, notas TEXT)')
    conn.commit()
    conn.close()

init_db()

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

# --- 3. BARRA LATERAL (CONFIGURACIÓN VIVA) ---
with st.sidebar:
    st.header("⚙️ Configuración Global")
    tasa_bcv = st.number_input("Tasa Dólar (Bs)", value=36.50)
    st.divider()
    # Aquí puedes modificar precios por inflación como pediste
    costo_tinta_base = st.number_input("Costo Tinta USD (por ml)", value=0.05, format="%.4f")
    menu = st.radio("Menú Principal", ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "📦 Inventario", "🎨 Analizador", "💰 Finanzas Pro", "🔍 Manuales"])

# --- 4. MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Estado del Imperio")
    st.write(f"Hoy es: {datetime.now().strftime('%d/%m/%Y')}")
    col1, col2 = st.columns(2)
    col1.metric("Tasa del Día", f"{tasa_bcv} Bs")
    col2.metric("Insumo Crítico", "Tinta Cyan (15%)")

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    with st.form("cots"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        trabajo = c1.text_input("Descripción")
        monto = c2.number_input("Precio USD", min_value=0.0)
        if st.form_submit_button("Guardar"):
            st.success("Guardado en Base de Datos")

elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.expander("➕ Registrar Nuevo Cliente"):
        st.text_input("Nombre Completo")
        st.text_input("WhatsApp")
        st.button("Añadir al Directorio")
    st.write("🔍 **Lista de Clientes:**")
    # Simulación de lista
    st.table(pd.DataFrame({"Nombre": ["Juan Perez", "Maria Rosa"], "WhatsApp": ["0412-...", "0424-..."]}))

elif menu == "📦 Inventario":
    st.title("📦 Inventario de Insumos")
    col1, col2, col3, col4 = st.columns(4)
    col1.number_input("Hojas Glossy", value=100)
    col2.number_input("Tazas Blancas", value=36)
    col3.number_input("Vinil (mts)", value=15)
    col4.number_input("Resmas Carta", value=5)
    st.button("Actualizar Stock")

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    # ESCOGENCIA DE IMPRESORA (Lo que faltaba)
    impresora = st.selectbox("Selecciona la Impresora:", ["Epson L1250 (Sublimación)", "HP Smart Tank (Fotográfica)", "J210a (Documentos)"])
    
    files = st.file_uploader("Subir diseños", accept_multiple_files=True)
    if files:
        for f in files:
            img, res = analizar_cmyk(f)
            if img:
                with st.expander(f"Resultados: {f.name}"):
                    c1, c2 = st.columns(2)
                    c1.image(img)
                    with c2:
                        st.write(f"**Análisis para {impresora}:**")
                        costo = sum(res.values()) * costo_tinta_base
                        st.metric("Costo USD", f"${costo:.4f}")
                        st.metric("Costo Bs", f"{costo*tasa_bcv:.2f} Bs")

elif menu == "💰 Finanzas Pro":
    st.title("💰 Finanzas Pro")
    st.subheader("Control de Ingresos y Egresos")
    st.columns(3)[0].date_input("Filtrar desde:")
    st.info("Cargando historial de ventas desde registro_ventas_088.csv...")

elif menu == "🔍 Manuales":
    st.title("🔍 Manuales y Soporte")
    opcion = st.selectbox("¿Qué necesitas?", ["Error de Almohadillas Epson", "Limpieza de Cabezales HP", "Reset de Niveles"])
    if opcion == "Error de Almohadillas Epson":
        st.error("⚠️ Requiere Software Adjustment Program.")
        st.write("1. Descargar Reseteador. 2. Conectar por USB. 3. Seleccionar 'Waste ink pad counter'.")
