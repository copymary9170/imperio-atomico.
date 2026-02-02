import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SEGURIDAD ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 IMPERIO ATÓMICO: Acceso")
        password = st.text_input("Clave de Acceso:", type="password")
        if st.button("Activar"):
            if password == "1234":
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. GESTIÓN ROBUSTA DE ARCHIVOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            return pd.read_csv(archivo)
        else:
            return pd.DataFrame(columns=columnas)
    except Exception:
        # Si el archivo está corrupto (ParserError), creamos uno nuevo limpio
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

# Inicializamos DataFrames limpios
df_ventas = cargar_datos(CSV_VENTAS, ["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa", "USD", "Responsable"])
df_stock = cargar_datos(CSV_STOCK, ["Material", "Cantidad", "Unidad", "Costo_Unit_USD"])

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "💰 Ventas", "📦 Inventario Real", "🔍 Manuales"])

# --- MÓDULO: INVENTARIO (CON CALCULADOR VENEZUELA) ---
if menu == "📦 Inventario Real":
    st.title("📦 Compras y Costo Real")
    tab1, tab2 = st.tabs(["📋 Existencias", "🛒 Nueva Compra"])
    
    with tab1:
        if not df_stock.empty:
            df_stock["Costo_Unit_USD"] = pd.to_numeric(df_stock["Costo_Unit_USD"], errors='coerce').fillna(0)
            df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
            df_stock["Valor_Total"] = df_stock["Cantidad"] * df_stock["Costo_Unit_USD"]
            st.dataframe(df_stock, use_container_width=True)
            st.metric("Total Invertido", f"$ {df_stock['Valor_Total'].sum():,.2f}")
        else:
            st.info("Bodega vacía.")

    with tab2:
        with st.form("compra_avanzada"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.01)
            precio = st.number_input("Precio en Factura", min_value=0.0)
            moneda = st.selectbox("Moneda", ["USD", "Bolívares"])
            tasa = st.number_input("Tasa del día", min_value=1.0, value=40.0) # Valor ref sugerido
            
            c1, c2 = st.columns(2)
            iva = c1.checkbox("¿Paga IVA (16%)?")
            comision = c2.number_input("% Comisión/IGTF", min_value=0.0)
            
            if st.form_submit_button("CALCULAR E INGRESAR"):
                # Cálculo de costo real
                base_usd = precio if moneda == "USD" else precio / tasa
                if iva: base_usd *= 1.16
                base_usd *= (1 + (comision/100))
                costo_u = base_usd / cant
                
                # Actualizar o Crear
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_u
                else:
                    nueva_fila = pd.DataFrame([[nom, cant, "Unid", costo_u]], columns=df_stock.columns[:4])
                    df_stock = pd.concat([df_stock, nueva_fila], ignore_index=True)
                
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Costo Real Unitario: ${costo_u:.4f}")
                st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    with st.form("venta"):
        cliente = st.text_input("Cliente")
        insumo = st.selectbox("Material", df_stock["Material"].unique()) if not df_stock.empty else None
        c_u = st.number_input("Cantidad usada", min_value=0.0)
        monto = st.number_input("Monto Cobrado", min_value=0.0)
        t_v = st.selectbox("Moneda de cobro", ["Bs", "USD"])
        tasa = st.number_input("Tasa", min_value=1.0, value=40.0)
        
        if st.form_submit_button("REGISTRAR"):
            eq_usd = monto / tasa if t_v == "Bs" else monto
            nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, monto, tasa, eq_usd, "Socia"]], 
                                   columns=df_ventas.columns)
            df_ventas = pd.concat([df_ventas, nueva_v], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS)
            
            if insumo:
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= c_u
                guardar_datos(df_stock, CSV_STOCK)
            
            st.success("Operación Exitosa")
            st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen")
    if not df_ventas.empty:
        df_ventas["USD"] = pd.to_numeric(df_ventas["USD"], errors='coerce')
        st.metric("Ventas Totales ($)", f"$ {df_ventas['USD'].sum():,.2f}")
        st.dataframe(df_ventas)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
