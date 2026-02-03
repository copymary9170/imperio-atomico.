import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Master Sistema", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Imperio")
        password = st.text_input("Clave de Acceso:", type="password")
        if st.button("Entrar"):
            if password == "1234":
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. GESTIÓN DE BASES DE DATOS ---
archivos = {
    "stock": ("stock_actual.csv", ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]),
    "clientes": ("clientes_imperio.csv", ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]),
    "produccion": ("ordenes_produccion.csv", ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]),
    "gastos": ("gastos_fijos.csv", ["Concepto", "Monto_Mensual_USD"]),
    "ventas": ("registro_ventas_088.csv", ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]),
    "tintas": ("tintas_v7_final.csv", ["Impresora", "Componente", "Precio_Envase_USD", "ML_Envase", "Capacidad_Tanque_ML", "Tasa_Compra"]),
    "config": ("config_tasas.csv", ["Parametro", "Valor"])
}

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

df_stock = cargar_datos(*archivos["stock"])
df_clientes = cargar_datos(*archivos["clientes"])
df_prod = cargar_datos(*archivos["produccion"])
df_gastos = cargar_datos(*archivos["gastos"])
df_ventas = cargar_datos(*archivos["ventas"])
df_tintas = cargar_datos(*archivos["tintas"])
df_conf = cargar_datos(*archivos["config"])

if df_conf.empty:
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, archivos["config"][0])
t_bcv, t_bin = float(df_conf.iloc[0,1]), float(df_conf.iloc[1,1])

# --- 3. CONTENIDO DE MANUALES (Base de datos interna) ---
manuales_db = [
    {"titulo": "Epson L1250: Limpieza de Cabezal", "cat": "Mantenimiento", "contenido": "1. Mantener presionado el botón de tinta 5 seg..."},
    {"titulo": "HP 580w: Error de Cabezal E3", "cat": "Errores", "contenido": "Indica atasco de carro o problema con los contactos del cabezal..."},
    {"titulo": "J210a: Reset de Cartucho", "cat": "Reseteos", "contenido": "Limpiar contactos con alcohol isopropílico y presionar Cancelar + Copia Color..."},
    {"titulo": "Diagnóstico: Test de Inyectores", "cat": "Diagnóstico", "contenido": "Imprimir hoja de prueba para verificar líneas faltantes en CMYK..."}
]

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú Principal:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- MÓDULO MANUALES CON BUSCADOR ---
if menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica del Imperio")
    bus_man = st.text_input("🔍 ¿Qué proceso o error buscas?", placeholder="Ej: Limpieza, Error E3, Reset...")
    
    filtro_man = [m for m in manuales_db if bus_man.lower() in m["titulo"].lower() or bus_man.lower() in m["cat"].lower()]
    
    if filtro_man:
        for m in filtro_man:
            with st.expander(f"{m['cat']} - {m['titulo']}"):
                st.write(m["contenido"])
    else:
        st.warning("No se encontró ningún manual con ese nombre.")

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    c1, c2 = st.columns([2,1])
    with c2:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else 0.1
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c1:
        f = st.file_uploader("Subir diseño", type=["jpg","png","pdf"])
        if f:
            try:
                if f.type == "application/pdf":
                    doc = fitz.open(stream=f.read(), filetype="pdf")
                    pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                else:
                    img = Image.open(f).convert("RGB")
                st.image(img, use_container_width=True)
            except: st.error("Error al leer archivo.")

# --- MÓDULOS RESTANTES (DASHBOARD, PRODUCCIÓN, FINANZAS, etc.) ---
elif menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    st.metric("Ventas USD", f"$ {pd.to_numeric(df_ventas['Monto_USD']).sum():.2f}")
    st.subheader("⚠️ Alertas")
    st.dataframe(df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])])

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    bus = st.text_input("Buscar...")
    st.dataframe(df_clientes[df_clientes["Nombre"].str.contains(bus, case=False)] if bus else df_clientes)

elif menu == "🏗️ Producción":
    st.title("🏗️ Taller")
    st.dataframe(df_prod)

elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    st.table(df_gastos)

elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    st.subheader("💧 Precios y Capacidades")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Tintas"):
        guardar_datos(ed, archivos["tintas"][0]); st.rerun()
