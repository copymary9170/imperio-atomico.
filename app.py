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

# --- 2. GESTIÓN DE ARCHIVOS ---
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
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

# Columnas robustas
df_stock = cargar_datos(CSV_STOCK, ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"])
df_ventas = cargar_datos(CSV_VENTAS, ["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa", "USD", "Costo_Insumo_USD", "Ganancia_USD", "Responsable"])

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Menú:", ["📊 Dashboard Maestro", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD (GANANCIA REAL) ---
if menu == "📊 Dashboard Maestro":
    st.title("📊 Análisis de Rentabilidad")
    
    if not df_ventas.empty:
        # Limpieza de datos
        for col in ["USD", "Costo_Insumo_USD", "Ganancia_USD"]:
            df_ventas[col] = pd.to_numeric(df_ventas[col], errors='coerce').fillna(0)
        
        c1, c2, c3 = st.columns(3)
        ingresos = df_ventas["USD"].sum()
        costos = df_ventas["Costo_Insumo_USD"].sum()
        utilidad = ingresos - costos
        
        c1.metric("Ingresos Totales", f"$ {ingresos:,.2f}")
        c2.metric("Costo de Ventas (Reposición)", f"$ {costos:,.2f}", delta_color="inverse")
        c3.metric("Utilidad Neta Real", f"$ {utilidad:,.2f}")
        
        # Alertas de Stock Bajo
        if not df_stock.empty:
            df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
            df_stock["Minimo_Alerta"] = pd.to_numeric(df_stock["Minimo_Alerta"], errors='coerce').fillna(5)
            bajo_stock = df_stock[df_stock["Cantidad"] <= df_stock["Minimo_Alerta"]]
            if not bajo_stock.empty:
                st.error("⚠️ ¡ALERTA DE REPOSICIÓN! Los siguientes materiales se están agotando:")
                st.table(bajo_stock[["Material", "Cantidad", "Minimo_Alerta"]])
        
        st.subheader("Historial de Operaciones")
        st.dataframe(df_ventas.tail(10), use_container_width=True)
    else:
        st.info("Sin datos de ventas suficientes para el análisis.")

# --- MÓDULO: INVENTARIO (CON MÍNIMOS) ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario con Alertas de Stock")
    tab1, tab2, tab3 = st.tabs(["📋 Existencias", "🛒 Compra", "✏️ Editar/Mínimos"])
    
    with tab1:
        if not df_stock.empty:
            df_stock["Valor_Total"] = pd.to_numeric(df_stock["Cantidad"]) * pd.to_numeric(df_stock["Costo_Unit_USD"])
            st.dataframe(df_stock, use_container_width=True)
            st.metric("Capital en Mercancía", f"$ {df_stock['Valor_Total'].sum():,.2f}")
    
    with tab2:
        with st.form("nueva_compra"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.01)
            precio = st.number_input("Precio Total Pago", min_value=0.0)
            tasa = st.number_input("Tasa Usada", value=40.0)
            moneda = st.selectbox("Moneda Pago", ["USD", "Bs"])
            if st.form_submit_button("REGISTRAR"):
                costo_u = (precio if moneda=="USD" else precio/tasa) / cant
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_u
                else:
                    nueva = pd.DataFrame([[nom, cant, "Unid", costo_u, 5]], columns=df_stock.columns)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Inventario actualizado.")
                st.rerun()

    with tab3:
        if not df_stock.empty:
            mat = st.selectbox("Material a editar", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == mat][0]
            new_cant = st.number_input("Corregir Cantidad", value=float(df_stock.loc[idx, "Cantidad"]))
            new_min = st.number_input("Mínimo para Alerta (Punto de Re-orden)", value=float(df_stock.loc[idx, "Minimo_Alerta"]))
            if st.button("ACTUALIZAR"):
                df_stock.loc[idx, "Cantidad"] = new_cant
                df_stock.loc[idx, "Minimo_Alerta"] = new_min
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Datos actualizados.")
                st.rerun()

# --- MÓDULO: VENTAS (CON GANANCIA) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("venta_ganancia"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Insumo usado", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad consumida", min_value=0.0)
            monto = st.number_input("Cobro Cliente", min_value=0.0)
            tasa = st.number_input("Tasa Cobro", value=40.0)
            moneda_v = st.selectbox("Moneda Cobro", ["Bs", "USD"])
            
            if st.form_submit_button("REGISTRAR VENTA"):
                # Cálculo de ganancia
                cobro_usd = monto if moneda_v == "USD" else monto / tasa
                costo_u_usd = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                costo_total_v = cant_u * costo_u_usd
                ganancia = cobro_usd - costo_total_v
                
                nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, (monto if moneda_v=="Bs" else monto*tasa), tasa, cobro_usd, costo_total_v, ganancia, "Socia"]], columns=df_ventas.columns)
                df_ventas = pd.concat([df_ventas, nueva_v], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                
                # Descontar stock
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
                
                st.success(f"Venta registrada. Ganancia estimada: $ {ganancia:.2f}")
                st.rerun()
    else:
        st.warning("Debe haber productos en inventario para vender.")
