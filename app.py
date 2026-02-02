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

# --- 2. CONFIGURACIÓN DE ARCHIVOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

def inicializar_archivos():
    if not os.path.exists(CSV_VENTAS):
        pd.DataFrame(columns=["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa_Usada", "Equiv_USD", "Responsable"]).to_csv(CSV_VENTAS, index=False)
    if not os.path.exists(CSV_STOCK):
        pd.DataFrame(columns=["Material", "Cantidad", "Unidad", "Costo_Unit_USD"]).to_csv(CSV_STOCK, index=False)

inicializar_archivos()

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "💰 Ventas (Tasa en Vivo)", "📦 Inventario (Costos USD)", "🔍 Manuales"])

# --- MÓDULO: VENTAS ---
if menu == "💰 Ventas (Tasa en Vivo)":
    st.title("💰 Registro de Venta")
    df_stock = pd.read_csv(CSV_STOCK)
    
    with st.form("venta_dinamica"):
        cliente = st.text_input("Cliente")
        insumo = st.selectbox("Material usado", df_stock["Material"].unique()) if not df_stock.empty else None
        cant_u = st.number_input("Cantidad usada", min_value=0.0)
        
        c1, c2, c3 = st.columns(3)
        tipo_pago = c1.selectbox("Moneda de Pago", ["Bolívares (Bs)", "Dólares ($)"])
        monto_pago = c2.number_input("Monto total", min_value=0.0)
        tasa_ahora = c3.number_input("Tasa (Bs/$)", min_value=1.0, value=1.0)
        
        if st.form_submit_button("FINALIZAR"):
            equiv_usd = monto_pago / tasa_ahora if tipo_pago == "Bolívares (Bs)" else monto_pago
            monto_bs = monto_pago if tipo_pago == "Bolívares (Bs)" else monto_pago * tasa_ahora
            
            nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, monto_bs, tasa_ahora, equiv_usd, "Socia"]], 
                                   columns=["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa_Usada", "Equiv_USD", "Responsable"])
            nueva_v.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            
            if insumo:
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                df_stock.to_csv(CSV_STOCK, index=False)
            st.success("Venta Guardada")
            st.rerun()

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario (Costos USD)":
    st.title("📦 Inventario")
    df_stock = pd.read_csv(CSV_STOCK)
    
    # --- ESCUDO ANTI-KEYERROR ---
    if "Costo_Unit_USD" not in df_stock.columns:
        df_stock["Costo_Unit_USD"] = 0.0

    tab1, tab2 = st.tabs(["📋 Existencias", "🛒 Nueva Compra"])
    
    with tab1:
        # Aseguramos que los datos sean números para que no rompan el cálculo
        df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
        df_stock["Costo_Unit_USD"] = pd.to_numeric(df_stock["Costo_Unit_USD"], errors='coerce').fillna(0)
        
        df_stock["Valor_Total_USD"] = df_stock["Cantidad"] * df_stock["Costo_Unit_USD"]
        st.dataframe(df_stock, use_container_width=True)
        st.metric("Inversión en Stock", f"$ {df_stock['Valor_Total_USD'].sum():,.2f}")

    with tab2:
        with st.form("compra"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.1)
            pago = st.number_input("Monto Pagado", min_value=0.0)
            moneda = st.selectbox("Moneda", ["Bs", "USD"])
            tasa = st.number_input("Tasa usada", min_value=1.0, value=1.0)
            if st.form_submit_button("INGRESAR"):
                costo_usd = (pago / tasa) / cant if moneda == "Bs" else pago / cant
                if not df_stock.empty and nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_usd
                    df_stock.to_csv(CSV_STOCK, index=False)
                else:
                    nueva_c = pd.DataFrame([[nom, cant, "Unid", costo_usd]], columns=["Material", "Cantidad", "Unidad", "Costo_Unit_USD"])
                    nueva_c.to_csv(CSV_STOCK, mode='a', header=False, index=False)
                st.success("Inventario actualizado")
                st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen")
    if os.path.exists(CSV_VENTAS):
        df_v = pd.read_csv(CSV_VENTAS)
        if not df_v.empty:
            df_v["Equiv_USD"] = pd.to_numeric(df_v["Equiv_USD"], errors='coerce')
            st.metric("Ventas Totales ($)", f"$ {df_v['Equiv_USD'].sum():,.2f}")
            st.dataframe(df_v)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
