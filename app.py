import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
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
            else:
                st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. GESTIÓN DE DATOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Comisiones_USD", "Ganancia_Real_USD", "Responsable"]

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except:
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)

# --- 3. MOTOR CMYK ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    return {"C": np.clip(c, 0, 1).mean()*100, "M": np.clip(m, 0, 1).mean()*100, 
            "Y": np.clip(y, 0, 1).mean()*100, "K": k.mean()*100}

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "🎨 Analizador Masivo", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR ---
if menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador Multitarea")
    archivos = st.file_uploader("Subir archivos", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)
    if archivos:
        resultados = []
        for archivo in archivos:
            if archivo.type == "application/pdf":
                doc = fitz.open(stream=archivo.read(), filetype="pdf")
                for i in range(len(doc)):
                    pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = f"{archivo.name} (Pág {i+1})"
                    resultados.append(res)
            else:
                img = Image.open(archivo)
                res = analizar_cmyk_pro(img)
                res["Archivo"] = archivo.name
                resultados.append(res)
        df_res = pd.DataFrame(resultados)
        df_res["Total %"] = df_res["C"]+df_res["M"]+df_res["Y"]+df_res["K"]
        st.dataframe(df_res.style.format("{:.1f}%", subset=["C","M","Y","K","Total %"]))

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen Económico")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        c2.metric("Comisiones Pagadas", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        c3.metric("Utilidad Real", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        st.divider()
        st.subheader("⚠️ Alertas de Stock")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty: st.error("⚠️ Reponer: " + ", ".join(bajo["Material"].tolist()))
    else: st.info("Sin registros.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Vent
