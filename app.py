import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime
import database  # Tu cerebro de datos

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - Master", layout="wide")
database.inicializar_sistema() 

# --- FUNCIÓN TÉCNICA: ANALIZADOR CMYK ---
def analizar_cmyk_pro(file):
    try:
        if file.type == "application/pdf":
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(file).convert("RGB")
        pix_arr = np.array(img) / 255.0
        # Fórmula de conversión a CMYK
        k = 1 - np.max(pix_arr, axis=2)
        c = (1-pix_arr[:,:,0]-k)/(1-k+1e-9)
        m = (1-pix_arr[:,:,1]-k)/(1-k+1e-9)
        y = (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        return img, {"C": c.mean(), "M": m.mean(), "Y": y.mean(), "K": k.mean()}
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None, None

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Panel de Control")
    menu = st.radio("Navegación:", 
        ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Estado del Imperio")
    st.info("Esperando datos de diagnóstico de esta tarde (niveles de inyectores).")
    col1, col2, col3 = st.columns(3)
    col1.metric("Tasa BCV", "36.50")
    col2.metric("Tasa Binance", "45.00")
    col3.metric("Cotizaciones Hoy", len(database.obtener_cotizaciones()))

# --- 2. COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Presupuestos")
    with st.form("nueva_cot"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Cliente")
            trab = st.text_input("Trabajo")
        with c2:
            prec = st.number_input("Monto USD", min_value=0.0)
            enviar = st.form_submit_button("Guardar Cotización")
        if enviar:
            database.guardar_cotizacion(nom, trab, prec)
            st.success("✅ Guardado.")
    st.dataframe(database.obtener_cotizaciones(), use_container_width=True)

# --- 3. CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Directorio de Clientes")
    st.write("Registra y busca clientes aquí.")
    # Por ahora lectura simple, luego migramos a DB
    nombre = st.text_input("Nuevo Cliente")
    if st.button("Registrar"):
        st.success(f"Cliente {nombre} registrado (Simulado)")

# --- 4. PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Taller y Máquinas")
    st.selectbox("Ver impresora:", ["Epson L1250", "HP Smart Tank", "J210a"])
    st.warning("No hay órdenes en cola.")

# --- 5. INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Almacén de Insumos")
    with st.expander("➕ Agregar Material"):
        mat = st.text_input("Insumo")
        cant = st.number_input("Cantidad")
        if st.button("Guardar en Stock"):
            st.success(f"Agregado {mat}")

# --- 6. ANALIZADOR (EL QUE TENÍA PROBLEMAS) ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico Múltiple")
    files = st.file_uploader("Sube tus diseños", type=["jpg","png","pdf"], accept_multiple_files=True)
    if files:
        for f in files:
            with st.expander(f"🖼️ Resultado: {f.name}", expanded=True):
                img, res = analizar_cmyk_pro(f)
                if img:
                    col_i, col_d = st.columns([1,1])
                    with col_i: st.image(img, use_container_width=True)
                    with col_d:
                        st.write("**Uso de Tinta:**")
                        st.write(f"💧 C: {res['C']:.2%} | 🌸 M: {res['M']:.2%}")
                        st.write(f"🟡 Y: {res['Y']:.2%} | ⚫ K: {res['K']:.2%}")

# --- 7. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes y Tasas")
    st.subheader("Modificar Precios de Tintas")
    # Aquí puedes modificar precios por inflación como pediste
    st.info("Aquí aparecerá la tabla de precios que podrás editar y guardar.")
    t_bcv = st.number_input("Editar Tasa BCV", value=36.50)
    if st.button("Actualizar Tasas"):
        st.success(f"Tasa actualizada a {t_bcv}")
