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
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "💰 Ventas (Tasa en Vivo)", "📦 Inventario (Costo Real)", "🔍 Manuales"])

# --- MÓDULO: INVENTARIO CON CÁLCULO DE COMISIONES ---
if menu == "📦 Inventario (Costo Real)":
    st.title("📦 Inventario con Cálculo de Costo Real (Venezuela)")
    df_stock = pd.read_csv(CSV_STOCK)
    
    if "Costo_Unit_USD" not in df_stock.columns:
        df_stock["Costo_Unit_USD"] = 0.0

    tab1, tab2 = st.tabs(["📋 Existencias", "🛒 Nueva Compra (Calculador)"])
    
    with tab1:
        df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
        df_stock["Costo_Unit_USD"] = pd.to_numeric(df_stock["Costo_Unit_USD"], errors='coerce').fillna(0)
        df_stock["Valor_Total_USD"] = df_stock["Cantidad"] * df_stock["Costo_Unit_USD"]
        st.dataframe(df_stock, use_container_width=True)
        st.metric("Capital Real en Bodega", f"$ {df_stock['Valor_Total_USD'].sum():,.2f}")

    with tab2:
        st.info("Este formulario calcula el costo neto después de impuestos y comisiones.")
        with st.form("compra_avanzada"):
            c1, c2 = st.columns(2)
            nom = c1.text_input("Nombre del Material")
            cant = c2.number_input("Cantidad Comprada", min_value=0.01)
            
            st.subheader("💰 Detalles del Pago")
            c3, c4, c5 = st.columns(3)
            precio_base = c3.number_input("Precio en Factura/Etiqueta", min_value=0.0)
            moneda_pago = c4.selectbox("Moneda de Pago", ["USD", "Bolívares"])
            tasa_dia = c5.number_input("Tasa del momento (Bs/$)", min_value=1.0, value=1.0)
            
            st.subheader("⚖️ Cargos Adicionales")
            c6, c7 = st.columns(2)
            usa_iva = c6.checkbox("¿Pagaste IVA (16%)?")
            comision = c7.number_input("% Comisión Banco/IGTF (Ej: 3)", min_value=0.0)
            
            if st.form_submit_button("CALCULAR E INGRESAR"):
                # 1. Convertir base a USD
                costo_inicial_usd = precio_base if moneda_pago == "USD" else precio_base / tasa_dia
                
                # 2. Aplicar IVA si aplica
                if usa_iva: costo_inicial_usd *= 1.16
                
                # 3. Aplicar comisiones bancarias
                costo_final_usd = costo_inicial_usd * (1 + (comision/100))
                
                costo_unit_final = costo_final_usd / cant
                
                if not df_stock.empty and nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_unit_final
                    df_stock.to_csv(CSV_STOCK, index=False)
                else:
                    nueva_c = pd.DataFrame([[nom, cant, "Unid", costo_unit_final]], columns=["Material", "Cantidad", "Unidad", "Costo_Unit_USD"])
                    nueva_c.to_csv(CSV_STOCK, mode='a', header=False, index=False)
                
                st.success(f"Costo unitario real calculado: ${costo_unit_final:.4f}")
                st.rerun()

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas (Tasa en Vivo)":
    st.title("💰 Registrar Venta")
    df_stock = pd.read_csv(CSV_STOCK)
    with st.form("venta"):
        cliente = st.text_input("Cliente")
        insumo = st.selectbox("Insumo", df_stock["Material"].unique()) if not df_stock.empty else None
        c_u = st.number_input("Cantidad usada", min_value=0.0)
        monto = st.number_input("Monto Cobrado", min_value=0.0)
        t_v = st.selectbox("Moneda", ["Bs", "USD"])
        tasa = st.number_input("Tasa", min_value=1.0, value=1.0)
        if st.form_submit_button("REGISTRAR"):
            eq_usd = monto / tasa if t_v == "Bs" else monto
            pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, monto, tasa, eq_usd, "Socia"]], 
                         columns=["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa_Usada", "Equiv_USD", "Responsable"]).to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            if insumo:
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= c_u
                df_stock.to_csv(CSV_STOCK, index=False)
            st.success("Venta Exitosa")
            st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Control de Capital")
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
