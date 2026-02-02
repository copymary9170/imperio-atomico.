import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
st.set_page_config(page_title="Imperio Atómico - Full Pro", layout="wide")

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
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "🎨 Analizador CMYK", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR CMYK ---
if menu == "🎨 Analizador CMYK":
    st.title("🎨 Analizador de Cobertura de Tinta")
    st.info("Sube un diseño para calcular el porcentaje de tóner (CMYK) por canal.")
    
    file = st.file_uploader("Subir Imagen o PDF", type=["jpg", "png", "jpeg", "pdf"])
    
    if file:
        img = None
        with st.spinner('Analizando píxeles...'):
            if file.type == "application/pdf":
                doc = fitz.open(stream=file.read(), filetype="pdf")
                page = doc.load_page(0)
                pix = page.get_pixmap(colorspace=fitz.csCMYK)
                img = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
            else:
                img = Image.open(file).convert("CMYK")
        
        if img:
            st.image(img.convert("RGB"), caption="Vista previa del diseño", width=400)
            
            pix_data = np.array(img)
            # CMYK son canales 0, 1, 2, 3
            c = (pix_data[:,:,0].mean() / 255) * 100
            m = (pix_data[:,:,1].mean() / 255) * 100
            y = (pix_data[:,:,2].mean() / 255) * 100
            k = (pix_data[:,:,3].mean() / 255) * 100
            
            
            
            st.subheader("📊 Resultados de Cobertura")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cian (C)", f"{c:.1f}%")
            c2.metric("Magenta (M)", f"{m:.1f}%")
            c3.metric("Amarillo (Y)", f"{y:.1f}%")
            c4.metric("Negro (K)", f"{k:.1f}%")
            
            total = c + m + y + k
            st.write(f"**Cobertura Total Combinada:** {total:.1f}%")
            
            if total > 240:
                st.warning("⚠️ ALTA DENSIDAD: Este diseño consumirá mucho material. Sugerencia: Cobrar recargo de tinta.")
            elif total < 15:
                st.success("✅ DISEÑO ECONÓMICO: Muy bajo consumo de tóner.")

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        col2.metric("Gastos/Comisiones", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        col3.metric("Utilidad Real", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        
        st.divider()
        st.subheader("⚠️ Alertas de Reposición")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty:
            st.error("Materiales agotándose:")
            st.dataframe(bajo[["Material", "Cantidad", "Minimo_Alerta"]])
        else:
            st.success("Stock en niveles óptimos.")
    else:
        st.info("Aún no hay registros de ventas.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("v"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Material usado", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad usada", min_value=0.01)
            monto = st.number_input("Monto Cobrado (USD o equiv.)", min_value=0.0)
            comi = st.number_input("% Comisión/IGTF/Punto que te quitan", value=3.0)
            
            if st.form_submit_button("Finalizar Registro"):
                costo_u = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                costo_t = cant_u * costo_u
                comi_usd = monto * (comi/100)
                ganancia = monto - comi_usd - costo_t
                
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cliente, insumo, monto, comi_usd, ganancia, "Socia"]], columns=COL_VENTAS)
                nueva.to_csv(CSV_VENTAS, mode='a', header=not os.path.exists(CSV_VENTAS), index=False)
                
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Venta Guardada. Ganancia Real: ${ganancia:.2f}")
                st.rerun()
    else:
        st.error("Carga materiales en el inventario primero.")

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Gestión de Inventario")
    t1, t2, t3 = st.tabs(["📋 Existencias", "🛒 Compra", "✏️ Ajustes"])
    
    with t1:
        st.dataframe(df_stock, use_container_width=True)
    
    with t2:
        with st.form("c"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.1)
            pago = st.number_input("Monto Pagado", min_value=0.0)
            c1, c2 = st.columns(2)
            iva = c1.checkbox("¿Paga IVA (16%)?")
            igtf = c2.number_input("% IGTF/Comisión", value=0.0)
            if st.form_submit_button("Ingresar Stock"):
                costo_usd = pago
                if iva: costo_usd *= 1.16
                costo_usd *= (1 + (igtf/100))
                costo_u = costo_usd / cant
                
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
            mat = st.selectbox("Corregir Material", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == mat][0]
            n_c = st.number_input("Cantidad Real", value=float(df_stock.loc[idx, "Cantidad"]))
            n_m = st.number_input("Mínimo Alerta", value=float(df_stock.loc[idx, "Minimo_Alerta"]))
            if st.button("Guardar Cambios"):
                df_stock.loc[idx, "Cantidad"] = n_c
                df_stock.loc[idx, "Minimo_Alerta"] = n_m
                guardar_datos(df_stock, CSV_STOCK)
                st.rerun()

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Nro de Hoja (ej: 088):")
    if hoja:
        if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r") as f: st.info(f.read())
        else:
            texto = st.text_area("Redactar Hoja:")
            if st.button("Guardar"):
                with open(ruta, "w") as f: f.write(texto)
                st.success("Guardado.")
