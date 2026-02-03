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

# --- 2. GESTIÓN DE ARCHIVOS ---
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv"
CSV_PRODUCCION = "ordenes_produccion.csv"
CSV_GASTOS = "gastos_fijos.csv"
CSV_VENTAS = "registro_ventas_088.csv"
CSV_TINTAS = "precios_tintas.csv"
CSV_CONFIG = "config_sistema.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]
COL_GASTOS = ["Concepto", "Monto_Mensual_USD"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]
COL_TINTAS = ["Impresora", "Precio_Ref", "ML_Total", "Tipo_Tasa"] # Precio_Ref puede ser $ o Bs

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

# Cargar Datos
df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)
df_gastos = cargar_datos(CSV_GASTOS, COL_GASTOS)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
df_tintas = cargar_datos(CSV_TINTAS, COL_TINTAS)

# Manejo de Tasa de Cambio
if not os.path.exists(CSV_CONFIG):
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, CSV_CONFIG)
else:
    df_conf = pd.read_csv(CSV_CONFIG)

tasa_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
tasa_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

if df_tintas.empty:
    df_tintas = pd.DataFrame([
        ["Epson L1250 (Sublimación)", 20.0, 1000, "Binance"],
        ["HP Smart Tank 580w", 20.0, 75, "BCV"],
        ["HP Deskjet J210a", 40.0, 13.5, "BCV"]
    ], columns=COL_TINTAS)
    guardar_datos(df_tintas, CSV_TINTAS)

# --- 3. FUNCIONES DE CÁLCULO ---
def obtener_costo_usd(row):
    # Si la tinta se compró en BCV, convertimos su precio de referencia a USD real usando la relación de tasas
    if row["Tipo_Tasa"] == "BCV":
        # Ejemplo: Si vale 20$ BCV, en verdad son (20 * tasa_bcv) / tasa_binance en valor real dolar
        return (row["Precio_Ref"] * tasa_bcv) / tasa_bin
    return row["Precio_Ref"]

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador y Cotizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- CONFIGURACIÓN (TASA Y TINTAS) ---
if menu == "⚙️ Configuración":
    st.title("⚙️ Configuración Financiera")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💹 Tasas de Cambio")
        new_bcv = st.number_input("Tasa BCV (Bs/$)", value=tasa_bcv)
        new_bin = st.number_input("Tasa Binance/Paralelo (Bs/$)", value=tasa_bin)
        if st.button("Actualizar Tasas"):
            df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"] = new_bcv
            df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"] = new_bin
            guardar_datos(df_conf, CSV_CONFIG)
            st.rerun()

    st.divider()
    st.subheader("💧 Gestión de Tintas e Inflación")
    st.info("Define aquí si el precio que pagas es a tasa BCV o Efectivo/Binance.")
    ed_tintas = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios de Tintas"):
        guardar_datos(ed_tintas, CSV_TINTAS)
        st.success("¡Precios y métodos de pago actualizados!")
        st.rerun()

# --- ANALIZADOR Y COTIZADOR (CON TASA) ---
elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Analizador Atómico")
    c_a, c_b = st.columns([2, 1])
    with c_b:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        row_t = df_tintas[df_tintas["Impresora"] == m_sel].iloc[0]
        
        # CÁLCULO DINÁMICO SEGÚN TASA
        precio_real_usd = obtener_costo_usd(row_t)
        c_ml = precio_real_usd / row_t["ML_Total"]
        
        st.caption(f"Costo real calculado: ${precio_real_usd:.2f} USD")
        
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_c = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else st.number_input("Costo Mat. USD", value=0.1)
        margen = st.slider("Ganancia %", 20, 500, 100)
    
    # ... (Resto del código del Analizador igual al anterior) ...

# --- INVENTARIO CON AJUSTE ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    t1, t2, t3 = st.tabs(["📋 Stock", "🛒 Compra", "✏️ Ajuste Manual"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n, c, p = st.text_input("Material"), st.number_input("Cantidad"), st.number_input("Precio Ref USD")
            tasa_compra = st.selectbox("Comprado a tasa:", ["Binance", "BCV"])
            if st.form_submit_button("Cargar Stock"):
                # Convertimos el precio de compra a valor USD real si fue por BCV
                p_real = (p * tasa_bcv / tasa_bin) if tasa_compra == "BCV" else p
                cu = p_real / c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"]==n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = cu
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", cu, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK); st.rerun()
    with t3:
        if not df_stock.empty:
            sel = st.selectbox("Corregir:", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == sel][0]
            nv = st.number_input("Cantidad Física Real", value=float(df_stock.at[idx, "Cantidad"]))
            if st.button("Corregir Inventario"):
                df_stock.at[idx, "Cantidad"] = nv
                guardar_datos(df_stock, CSV_STOCK); st.success("¡Corregido!"); st.rerun()

# --- (Mantener el resto de módulos: Clientes con buscador, Producción, Ventas, Manuales) ---
