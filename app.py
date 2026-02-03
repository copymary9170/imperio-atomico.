import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
st.set_page_config(page_title="Imperio Atómico - Sistema Integral", layout="wide")

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

# --- 2. GESTIÓN DE DATOS (CSV) ---
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

# --- 3. MOTOR DE ANÁLISIS CMYK ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    return {
        "C": np.clip(c, 0, 1).mean() * 100,
        "M": np.clip(m, 0, 1).mean() * 100,
        "Y": np.clip(y, 0, 1).mean() * 100,
        "K": k.mean() * 100
    }

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú Principal:", ["📊 Dashboard", "🎨 Analizador Masivo", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR ---
if menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador Multitarea (PDF y Fotos)")
    archivos = st.file_uploader("Subir archivos", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)
    if archivos:
        resultados = []
        for archivo in archivos:
            if archivo.type == "application/pdf":
                doc = fitz.open(stream=archivo.read(), filetype="pdf")
                for i in range(len(doc)):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(colorspace=fitz.csRGB)
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
        df_res["Total (%)"] = df_res["C"] + df_res["M"] + df_res["Y"] + df_res["K"]
        st.dataframe(df_res.style.format("{:.1f}%", subset=["C","M","Y","K","Total (%)"]), use_container_width=True)

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Análisis de Ganancias")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        c2.metric("Comisiones/Gastos", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        c3.metric("Utilidad Limpia", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        
        st.divider()
        st.subheader("🚨 Alertas de Stock")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty: st.error("Reponer: " + ", ".join(bajo["Material"].tolist()))
    else:
        st.info("Sin datos.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("v"):
            cli = st.text_input("Cliente")
            ins = st.selectbox("Material", df_stock["Material"].unique())
            can = st.number_input("Cantidad", min_value=0.01)
            mon = st.number_input("Monto USD", min_value=0.0)
            com = st.number_input("% Comisión/IGTF", value=3.0)
            if st.form_submit_button("Guardar Venta"):
                costo_u = float(df_stock.loc[df_stock["Material"] == ins, "Costo_Unit_USD"].values[0])
                c_usd = mon * (com/100)
                gan = mon - c_usd - (can * costo_u)
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, mon, c_usd, gan, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                df_stock.loc[df_stock["Material"] == ins, "Cantidad"] -= can
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Ganancia: ${gan:.2f}"); st.rerun()
    else: st.warning("Carga stock primero.")

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    t1, t2, t3 = st.tabs(["📋 Stock", "🛒 Compra", "✏️ Ajustes"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("c"):
            n = st.text_input("Nombre")
            c = st.number_input("Cantidad", min_value=0.1)
            p = st.number_input("Precio Pago USD", min_value=0.0)
            iva = st.checkbox("¿IVA 16%?")
            if st.form_submit_button("Añadir"):
                costo = p * 1.16 if iva else p
                c_u = costo / c
                if n in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == n, ["Cantidad", "Costo_Unit_USD"]] = [df_stock.loc[df_stock["Material"] == n, "Cantidad"].values[0]+c, c_u]
                else:
                    nueva = pd.DataFrame([[n, c, "Unid", c_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK); st.rerun()
    with t3:
        if not df_stock.empty:
            m = st.selectbox("Material", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == m][0]
            nc = st.number_input("Stock Real", value=float(df_stock.loc[idx, "Cantidad"]))
            nm = st.number_input("Mínimo Alerta", value=float(df_stock.loc[idx, "Minimo_Alerta"]))
            if st.button("Actualizar"):
                df_stock.loc[idx, ["Cantidad", "Minimo_Alerta"]] = [nc, nm]
                guardar_datos(df_stock, CSV_STOCK); st.rerun()

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja # (ej: 088)")
    if hoja:
        if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r") as f: st.info(f.read())
        else:
            txt = st.text_area("Redactar:")
            if st.button("Guardar"):
                with open(ruta, "w") as f: f.write(txt)
                st.success("Listo.")
