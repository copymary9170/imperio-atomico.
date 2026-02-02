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

df_stock = cargar_datos(CSV_STOCK, ["Material", "Cantidad", "Unidad", "Costo_Unit_USD"])
df_ventas = cargar_datos(CSV_VENTAS, ["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa", "USD", "Responsable"])

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "💰 Ventas", "📦 Inventario Real", "🔍 Manuales"])

# --- MÓDULO: INVENTARIO (CON FUNCIÓN DE CORRECCIÓN) ---
if menu == "📦 Inventario Real":
    st.title("📦 Gestión de Inventario")
    tab1, tab2, tab3 = st.tabs(["📋 Existencias", "🛒 Nueva Compra", "✏️ Corregir Error"])
    
    with tab1:
        if not df_stock.empty:
            df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
            df_stock["Costo_Unit_USD"] = pd.to_numeric(df_stock["Costo_Unit_USD"], errors='coerce').fillna(0)
            df_stock["Valor_Total"] = df_stock["Cantidad"] * df_stock["Costo_Unit_USD"]
            st.dataframe(df_stock, use_container_width=True)
            st.metric("Total Invertido", f"$ {df_stock['Valor_Total'].sum():,.2f}")
        else:
            st.info("Bodega vacía.")

    with tab2:
        with st.form("compra"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.01)
            precio = st.number_input("Precio base", min_value=0.0)
            moneda = st.selectbox("Moneda", ["USD", "Bolívares"])
            tasa = st.number_input("Tasa", min_value=1.0, value=40.0)
            if st.form_submit_button("INGRESAR"):
                costo_u = (precio if moneda == "USD" else precio / tasa) / cant
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = costo_u
                else:
                    nueva = pd.DataFrame([[nom, cant, "Unid", costo_u]], columns=df_stock.columns[:4])
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Ingresado")
                st.rerun()

    with tab3:
        st.subheader("⚠️ Corregir Cantidad o Precio")
        if not df_stock.empty:
            mat_editar = st.selectbox("Selecciona el material a corregir", df_stock["Material"].unique())
            fila_idx = df_stock.index[df_stock["Material"] == mat_editar][0]
            
            c1, c2 = st.columns(2)
            nueva_cant = c1.number_input("Nueva Cantidad Correcta", value=float(df_stock.loc[fila_idx, "Cantidad"]))
            nuevo_costo = c2.number_input("Nuevo Costo USD Unitario", value=float(df_stock.loc[fila_idx, "Costo_Unit_USD"]))
            
            if st.button("SOBRESCRIBIR DATOS"):
                df_stock.loc[fila_idx, "Cantidad"] = nueva_cant
                df_stock.loc[fila_idx, "Costo_Unit_USD"] = nuevo_costo
                guardar_datos(df_stock, CSV_STOCK)
                st.warning(f"Se ha corregido {mat_editar} a {nueva_cant} unidades.")
                st.rerun()
        else:
            st.info("No hay materiales para editar.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    with st.form("venta"):
        cliente = st.text_input("Cliente")
        insumo = st.selectbox("Material", df_stock["Material"].unique()) if not df_stock.empty else None
        cant_u = st.number_input("Cantidad usada", min_value=0.0)
        monto = st.number_input("Cobro", min_value=0.0)
        tasa = st.number_input("Tasa", value=40.0)
        if st.form_submit_button("REGISTRAR"):
            eq_usd = monto / tasa
            nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, monto, tasa, eq_usd, "Socia"]], columns=df_ventas.columns)
            df_ventas = pd.concat([df_ventas, nueva_v], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS)
            if insumo:
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
            st.success("Venta Exitosa")
            st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen")
    if not df_ventas.empty:
        st.metric("Ventas Totales ($)", f"$ {pd.to_numeric(df_ventas['USD']).sum():,.2f}")
        st.dataframe(df_ventas)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
