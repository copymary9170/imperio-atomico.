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

# --- 2. CONFIGURACIÓN ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_Neto_USD", "Comisiones_USD", "Ganancia_Real_USD", "Responsable"]

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

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "💰 Ventas (Con Comisiones)", "📦 Inventario (Costo Real)", "🔍 Manuales"])

# --- MÓDULO: INVENTARIO (EL CALCULADOR) ---
if menu == "📦 Inventario (Costo Real)":
    st.title("📦 Compras: Cálculo de Costo de Reposición")
    tab1, tab2, tab3 = st.tabs(["📋 Existencias", "🛒 Nueva Compra", "✏️ Ajustes"])
    
    with tab2:
        with st.form("compra_avanzada"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.01)
            precio = st.number_input("Precio en Factura/Etiqueta", min_value=0.0)
            tasa = st.number_input("Tasa Pago (Bs/$)", value=45.0)
            moneda = st.selectbox("Pagaste en:", ["Dólares ($)", "Bolívares (Bs)"])
            
            st.subheader("🛡️ Cargos Adicionales")
            c1, c2 = st.columns(2)
            usa_iva = c1.checkbox("¿Pagaste IVA (16%)?")
            comision_c = c2.number_input("% Comisión/IGTF (Ej: 3)", min_value=0.0, value=0.0)
            
            if st.form_submit_button("CALCULAR E INGRESAR"):
                # 1. Convertir a USD base
                costo_usd = precio if moneda == "Dólares ($)" else precio / tasa
                # 2. Sumar IVA
                if usa_iva: costo_usd *= 1.16
                # 3. Sumar Comisión/IGTF
                costo_usd *= (1 + (comision_c / 100))
                
                costo_u_final = costo_usd / cant
                
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_u_final
                else:
                    nueva = pd.DataFrame([[nom, cant, "Unid", costo_u_final, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Costo Real: ${costo_u_final:.4f} (Incluye cargos)")
                st.rerun()

    with tab1:
        st.dataframe(df_stock, use_container_width=True)

# --- MÓDULO: VENTAS (RESTANDO COMISIONES) ---
elif menu == "💰 Ventas (Con Comisiones)":
    st.title("💰 Registrar Venta y Descontar Gastos")
    if not df_stock.empty:
        with st.form("venta_real"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Insumo", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad usada", min_value=0.01)
            monto_recibido = st.number_input("Monto cobrado al cliente", min_value=0.0)
            tasa_v = st.number_input("Tasa del momento", value=45.0)
            moneda_v = st.selectbox("Recibiste en:", ["Bolívares (Bs)", "Dólares ($)"])
            
            comision_v = st.number_input("% Comisión Banco/Punto/IGTF que te quitan a TI", value=3.0)
            
            if st.form_submit_button("FINALIZAR VENTA"):
                # 1. Convertir ingreso a USD
                ingreso_usd = monto_recibido if moneda_v == "Dólares ($)" else monto_recibido / tasa_v
                # 2. Restar lo que el banco te quita
                perdida_banco = ingreso_usd * (comision_v / 100)
                ingreso_neto = ingreso_usd - perdida_banco
                
                # 3. Restar costo del material
                costo_u = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                costo_total_mat = cant_u * costo_u
                ganancia_real = ingreso_neto - costo_total_mat
                
                nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, ingreso_usd, perdida_banco, ganancia_real, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva_v], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Ganancia Limpia: ${ganancia_real:.2f} (Ya restamos material y banco)")
                st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 La Verdad del Negocio")
    if not df_ventas.empty:
        df_v = df_ventas.copy()
        for c in ["Monto_Neto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_v[c] = pd.to_numeric(df_v[c], errors='coerce').fillna(0)
            
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Brutas", f"$ {df_v['Monto_Neto_USD'].sum():,.2f}")
        c2.metric("Pérdida en Comisiones", f"$ {df_v['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        c3.metric("Utilidad REAL", f"$ {df_v['Ganancia_Real_USD'].sum():,.2f}")
        
        st.subheader("Análisis de Stock")
        st.dataframe(df_stock)
    else:
        st.info("Sin datos.")

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
