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

# --- 3. MENÚ LATERAL ---
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "🎨 Analizador CMYK Pro", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR CMYK PRO (EXTRACCIÓN DE NEGRO REAL) ---
if menu == "🎨 Analizador CMYK Pro":
    st.title("🎨 Analizador de Cobertura de Tinta")
    st.info("Detecta bordes negros, fondos oscuros y consumo real de tóner CMYK.")
    
    file = st.file_uploader("Subir Imagen o PDF", type=["jpg", "png", "jpeg", "pdf"])
    
    if file:
        img = None
        with st.spinner('Analizando densidades...'):
            if file.type == "application/pdf":
                doc = fitz.open(stream=file.read(), filetype="pdf")
                page = doc.load_page(0)
                pix = page.get_pixmap(colorspace=fitz.csCMYK)
                img = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
            else:
                img = Image.open(file).convert("RGB") # Primero RGB para detectar oscuridad
        
        if img:
            st.image(img.convert("RGB"), caption="Diseño detectado", width=400)
            
            # Lógica de detección de Negro Profundo y Bordes
            pix_rgb = np.array(img.convert("RGB")) / 255.0
            r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]

            # El Negro (K) es la falta de brillo. Si RGB es (0,0,0), K es 1 (100%)
            k = 1 - np.max(pix_rgb, axis=2)
            
            # Extraemos C, M, Y basándonos en la oscuridad detectada
            c = (1 - r - k) / (1 - k + 1e-9)
            m = (1 - g - k) / (1 - k + 1e-9)
            y = (1 - b - k) / (1 - k + 1e-9)

            c_p, m_p, y_p, k_p = np.clip(c,0,1).mean()*100, np.clip(m,0,1).mean()*100, np.clip(y,0,1).mean()*100, k.mean()*100
            
            
            
            st.subheader("📊 Cobertura Estimada por Hoja")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cian", f"{c_p:.1f}%")
            c2.metric("Magenta", f"{m_p:.1f}%")
            c3.metric("Amarillo", f"{y_p:.1f}%")
            c4.metric("Negro (K)", f"{k_p:.1f}%")
            
            total = c_p + m_p + y_p + k_p
            st.write(f"**Cobertura Total Combinada:** {total:.1f}%")
            
            if k_p > 30 or total > 200:
                st.warning("⚠️ ALTA DENSIDAD DETECTADA: Los bordes negros o fondos oscuros consumirán mucho tóner. Considera recargo.")

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen de Ganancias Reales")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        col2.metric("Comisiones/IGTF", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        col3.metric("Utilidad Neta", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        
        st.divider()
        st.subheader("🚨 Alertas de Inventario")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty:
            st.error("Materiales por agotarse:")
            st.table(bajo[["Material", "Cantidad", "Minimo_Alerta"]])
    else:
        st.info("Sin ventas registradas.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("v"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Insumo", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad", min_value=0.01)
            monto = st.number_input("Monto Cobrado (USD)", min_value=0.0)
            comi = st.number_input("% Comisión/Punto/IGTF", value=3.0)
            
            if st.form_submit_button("Registrar Venta"):
                costo_u = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                comi_usd = monto * (comi/100)
                ganancia = monto - comi_usd - (cant_u * costo_u)
                
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cliente, insumo, monto, comi_usd, ganancia, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Venta guardada. Utilidad: ${ganancia:.2f}")
                st.rerun()

# --- MÓDULO: INVENTARIO PRO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario y Costos Reales")
    t1, t2, t3 = st.tabs(["📋 Stock", "🛒 Compras", "✏️ Ajustes"])
    
    with t1:
        st.dataframe(df_stock, use_container_width=True)
    
    with t2:
        with st.form("compra"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.1)
            pago = st.number_input("Monto Total Pago (USD)", min_value=0.0)
            c1, c2 = st.columns(2)
            iva = c1.checkbox("¿Pagó IVA (16%)?")
            igtf = c2.number_input("% IGTF/Comisión", value=0.0)
            if st.form_submit_button("Añadir Stock"):
                costo_t = pago
                if iva: costo_t *= 1.16
                costo_t *= (1 + (igtf/100))
                costo_u = costo_t / cant
                
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_u
                else:
                    nueva_s = pd.DataFrame([[nom, cant, "Unid", costo_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva_s], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Inventario actualizado.")
                st.rerun()

    with t3:
        if not df_stock.empty:
            mat = st.selectbox("Seleccionar para ajustar", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == mat][0]
            n_c = st.number_input("Cantidad Real", value=float(df_stock.loc[idx, "Cantidad"]))
            n_u = st.number_input("Costo Unitario USD", value=float(df_stock.loc[idx, "Costo_Unit_USD"]))
            n_m = st.number_input("Mínimo para Alerta", value=float(df_stock.loc[idx, "Minimo_Alerta"]))
            if st.button("Guardar Ajustes"):
                df_stock.loc[idx, ["Cantidad", "Costo_Unit_USD", "Minimo_Alerta"]] = [n_c, n_u, n_m]
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Corregido.")
                st.rerun()

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #:")
    if hoja:
        if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r") as f: st.info(f.read())
        else:
            txt = st.text_area("Redactar manual:")
            if st.button("Guardar"):
                with open(ruta, "w") as f: f.write(txt)
                st.success("Guardado.")
