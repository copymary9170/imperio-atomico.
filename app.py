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

# --- 2. CONFIGURACIÓN DE DATOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

# Definición de estructuras (Asegúrate de que coincidan siempre)
COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_Bs", "Tasa", "USD", "Costo_Insumo_USD", "Ganancia_USD", "Responsable"]

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            # ESCUDO: Si faltan columnas, las agregamos con valores por defecto
            for col in columnas:
                if col not in df.columns:
                    df[col] = 0 if "USD" in col or "Cantidad" in col or "Monto" in col or "Tasa" in col else 5
            return df[columnas] # Retornamos solo las columnas que necesitamos
        return pd.DataFrame(columns=columnas)
    except:
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

# Carga global
df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard Maestro", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard Maestro":
    st.title("📊 Resumen del Imperio")
    
    if not df_ventas.empty:
        df_v = df_ventas.copy()
        for c in ["USD", "Costo_Insumo_USD", "Ganancia_USD"]:
            df_v[c] = pd.to_numeric(df_v[c], errors='coerce').fillna(0)
            
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales", f"$ {df_v['USD'].sum():,.2f}")
        c2.metric("Costo Insumos", f"$ {df_v['Costo_Insumo_USD'].sum():,.2f}")
        c3.metric("Utilidad Neta", f"$ {df_v['Ganancia_USD'].sum():,.2f}")
        
        # Alertas de Stock
        df_s = df_stock.copy()
        df_s["Cantidad"] = pd.to_numeric(df_s["Cantidad"], errors='coerce').fillna(0)
        df_s["Minimo_Alerta"] = pd.to_numeric(df_s["Minimo_Alerta"], errors='coerce').fillna(5)
        bajo = df_s[df_s["Cantidad"] <= df_s["Minimo_Alerta"]]
        if not bajo.empty:
            st.warning("🚨 ¡REPONER PRONTO!")
            st.table(bajo[["Material", "Cantidad", "Minimo_Alerta"]])
    else:
        st.info("Esperando primera venta...")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("nueva_v"):
            cliente = st.text_input("Cliente")
            insumo = st.selectbox("Insumo", df_stock["Material"].unique())
            cant_u = st.number_input("Cantidad usada", min_value=0.01)
            
            c1, c2, c3 = st.columns(3)
            monto = c1.number_input("Monto", min_value=0.0)
            moneda = c2.selectbox("Moneda", ["Bs", "USD"])
            tasa = c3.number_input("Tasa", value=40.0)
            
            if st.form_submit_button("REGISTRAR VENTA"):
                usd_v = monto if moneda == "USD" else monto / tasa
                bs_v = monto if moneda == "Bs" else monto * tasa
                
                # Cálculo de ganancia
                costo_u = float(df_stock.loc[df_stock["Material"] == insumo, "Costo_Unit_USD"].values[0])
                costo_t = cant_u * costo_u
                ganancia = usd_v - costo_t
                
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo, bs_v, tasa, usd_v, costo_t, ganancia, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                
                df_stock.loc[df_stock["Material"] == insumo, "Cantidad"] -= cant_u
                guardar_datos(df_stock, CSV_STOCK)
                st.success("¡Venta registrada!")
                st.rerun()
    else:
        st.error("No hay materiales en inventario.")

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    tab1, tab2, tab3 = st.tabs(["📋 Ver", "🛒 Comprar", "✏️ Corregir/Mínimos"])
    
    with tab1:
        st.dataframe(df_stock, use_container_width=True)
        
    with tab2:
        with st.form("compra"):
            nom = st.text_input("Material")
            cant = st.number_input("Cantidad", min_value=0.1)
            pago = st.number_input("Monto Total", min_value=0.0)
            mon = st.selectbox("Moneda", ["USD", "Bs"])
            tasa_c = st.number_input("Tasa", value=40.0)
            if st.form_submit_button("AÑADIR"):
                c_u = (pago if mon == "USD" else pago/tasa_c) / cant
                if nom in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                    df_stock.loc[df_stock["Material"] == nom, "Costo_Unit_USD"] = c_u
                else:
                    nueva_s = pd.DataFrame([[nom, cant, "Unid", c_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva_s], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Stock actualizado.")
                st.rerun()
                
    with tab3:
        if not df_stock.empty:
            mat = st.selectbox("Seleccionar Material", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == mat][0]
            # Convertimos a float para evitar errores de tipo
            c_actual = float(df_stock.loc[idx, "Cantidad"])
            m_actual = float(df_stock.loc[idx, "Minimo_Alerta"])
            
            n_c = st.number_input("Cantidad Real", value=c_actual)
            n_m = st.number_input("Mínimo para Alerta", value=m_actual)
            
            if st.button("GUARDAR CAMBIOS"):
                df_stock.loc[idx, "Cantidad"] = n_c
                df_stock.loc[idx, "Minimo_Alerta"] = n_m
                guardar_datos(df_stock, CSV_STOCK)
                st.rerun()

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos del Imperio")
    # Crear carpeta si no existe
    if not os.path.exists(CARPETA_MANUALES):
        os.makedirs(CARPETA_MANUALES)
        
    hoja = st.text_input("Ingresa el número de Hoja (ej: 088)")
    if hoja:
        nombre_archivo = f"{hoja.zfill(3)}.txt"
        ruta = os.path.join(CARPETA_MANUALES, nombre_archivo)
        
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.markdown(f"### Hoja {hoja}")
                st.info(f.read())
        else:
            st.warning(f"La Hoja {hoja} aún no ha sido redactada.")
            nuevo_texto = st.text_area("Redactar manual ahora:")
            if st.button("Guardar Manual"):
                with open(ruta, "w", encoding="utf-8") as f:
                    f.write(nuevo_texto)
                st.success("Manual guardado con éxito.")
