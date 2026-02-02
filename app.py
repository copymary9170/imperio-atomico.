import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - Pro", layout="wide")

# --- SEGURIDAD ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Sistema")
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

# --- GESTIÓN DE DATOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
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

df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)

# --- MENÚ PRINCIPAL ---
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "🎨 Analizador CMYK", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR CMYK ---
if menu == "🎨 Analizador CMYK":
    st.title("🎨 Analizador de Cobertura de Tinta")
    st.write("Calcula el porcentaje de Cyan, Magenta, Yellow y Black de tus diseños.")
    
    file = st.file_uploader("Sube una Imagen o PDF", type=["jpg", "png", "jpeg", "pdf"])
    
    if file:
        img = None
        if file.type == "application/pdf":
            # Procesar PDF (Primera página)
            doc = fitz.open(stream=file.read(), filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(colorspace=fitz.csCMYK)
            img = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
        else:
            # Procesar Imagen
            img = Image.open(file).convert("CMYK")
        
        if img:
            st.image(img.convert("RGB"), caption="Vista previa del diseño", width=400)
            
            # Cálculo de porcentajes
            pix_data = np.array(img)
            # CMYK son los canales 0, 1, 2, 3
            c_p = (pix_data[:,:,0].mean() / 255) * 100
            m_p = (pix_data[:,:,1].mean() / 255) * 100
            y_p = (pix_data[:,:,2].mean() / 255) * 100
            k_p = (pix_data[:,:,3].mean() / 255) * 100
            
            st.subheader("📊 Cobertura por Canal")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cian", f"{c_p:.1f}%")
            c2.metric("Magenta", f"{m_p:.1f}%")
            c3.metric("Amarillo", f"{y_p:.1f}%")
            c4.metric("Negro", f"{k_p:.1f}%")
            
            total = c_p + m_p + y_p + k_p
            st.info(f"**Cobertura Total Combinada:** {total:.1f}%")
            
            if total > 240:
                st.warning("⚠️ ALTA DENSIDAD: Este diseño consumirá mucho tóner. Sugerencia: Cobrar recargo.")

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen Atómico")
    if not df_ventas.empty:
        df_v = df_ventas.copy()
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_v[c] = pd.to_numeric(df_v[c], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Ventas Totales", f"$ {df_v['Monto_USD'].sum():,.2f}")
        col2.metric("Gastos/Comisiones", f"$ {df_v['Comisiones_USD'].sum():,.2f}")
        col3.metric("Ganancia Neta", f"$ {df_v['Ganancia_Real_USD'].sum():,.2f}")
        
        st.subheader("Alertas de Stock")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty:
            st.error("⚠️ Reponer estos materiales pronto:")
            st.table(bajo[["Material", "Cantidad"]])
    else:
        st.info("Aún no hay ventas para mostrar.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Nueva Venta")
    if not df_stock.empty:
        with st.form("v"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Insumo", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad", min_value=0.01)
            monto = st.number_input("Cobrado ($ o equivalente)", min_value=0.0)
            comi = st.number_input("% Comisión/IGTF pagado", value=3.0)
            if st.form_submit_button("Registrar"):
                # Lógica de costos
                costo_u = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                costo_total = cant_u * costo_u
                comi_usd = monto * (comi/100)
                ganancia = monto - comi_usd - costo_total
                
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cliente, insumo, monto, comi_usd, ganancia, "Socia"]], columns=COL_VENTAS)
                nueva.to_csv(CSV_VENTAS, mode='a', header=not os.path.exists(CSV_VENTAS), index=False)
                
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                df_stock.to_csv(CSV_STOCK, index=False)
                st.success(f"Ganancia: ${ganancia:.2f}")
                st.rerun()

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario y Ajustes")
    t1, t2 = st.tabs(["📋 Stock Actual", "✏️ Ajustes/Compras"])
    with t1:
        st.dataframe(df_stock, use_container_width=True)
    with t2:
        st.write("Usa esta sección para añadir stock o corregir errores.")
        # Aquí puedes replicar el formulario de compras anterior...

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Nro de Hoja:")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r") as f: st.info(f.read())
