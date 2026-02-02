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
CSV_ALERTAS = "alertas_inventario.csv"
CARPETA_MANUALES = "manuales"

def inicializar_archivos():
    # Estructura actualizada con Precio_Unitario
    if not os.path.exists(CSV_VENTAS):
        pd.DataFrame(columns=["Fecha", "Cliente", "Insumo_Usado", "Monto", "Responsable"]).to_csv(CSV_VENTAS, index=False)
    if not os.path.exists(CSV_STOCK):
        pd.DataFrame(columns=["Material", "Cantidad", "Unidad", "Precio_Unitario"]).to_csv(CSV_STOCK, index=False)
    if not os.path.exists(CSV_ALERTAS):
        pd.DataFrame(columns=["Fecha", "Insumo", "Estado", "Responsable"]).to_csv(CSV_ALERTAS, index=False)

inicializar_archivos()

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "💰 Venta y Descuento (088)", "📦 Inventario y Precios", "🔍 Manuales"])

# --- MÓDULO: VENTA CON DESCUENTO ---
if menu == "💰 Venta y Descuento (088)":
    st.title("📝 Registrar Venta y Descontar Stock")
    df_stock = pd.read_csv(CSV_STOCK)
    
    with st.form("venta_descuento"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        monto = c2.number_input("Precio Cobrado ($)", min_value=0.0)
        
        st.subheader("🛠️ ¿Qué material se consumió?")
        if not df_stock.empty:
            insumo_usado = st.selectbox("Selecciona el material", df_stock["Material"].unique())
            cantidad_usada = st.number_input("Cantidad usada", min_value=0.0, step=1.0)
        else:
            st.warning("Primero debes agregar materiales en la pestaña de Inventario.")
            insumo_usado, cantidad_usada = None, 0

        responsable = st.text_input("Operador:")
        
        if st.form_submit_button("REGISTRAR VENTA Y RESTAR STOCK"):
            if insumo_usado:
                # 1. Registrar la venta
                nueva_v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, insumo_usado, monto, responsable]], 
                                       columns=["Fecha", "Cliente", "Insumo_Usado", "Monto", "Responsable"])
                nueva_v.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
                
                # 2. Descontar del Stock
                df_stock.loc[df_stock["Material"] == insumo_usado, "Cantidad"] -= cantidad_usada
                df_stock.to_csv(CSV_STOCK, index=False)
                st.success(f"✅ Venta guardada. Se restaron {cantidad_usada} de {insumo_usado}.")
                st.balloons()
            else:
                st.error("No se puede registrar venta sin insumos en stock.")

# --- MÓDULO: INVENTARIO CON PRECIOS ---
elif menu == "📦 Inventario y Precios":
    st.title("📦 Valor del Inventario")
    df_stock = pd.read_csv(CSV_STOCK)
    
    tab1, tab2 = st.tabs(["📋 Ver Bodega", "🛒 Nueva Compra"])
    
    with tab1:
        if not df_stock.empty:
            # Cálculo seguro de valor total
            df_stock["Precio_Unitario"] = pd.to_numeric(df_stock["Precio_Unitario"], errors='coerce').fillna(0)
            df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
            df_stock["Valor_Total"] = df_stock["Cantidad"] * df_stock["Precio_Unitario"]
            
            st.dataframe(df_stock, use_container_width=True)
            st.metric("Inversión Total en Bodega", f"$ {df_stock['Valor_Total'].sum():,.2f}")
        else:
            st.info("La bodega está vacía. Ve a 'Nueva Compra' para empezar.")

    with tab2:
        with st.form("compra_precio"):
            c1, c2, c3 = st.columns(3)
            nom = c1.text_input("Material (Ej: Papel Foto)")
            cant = c2.number_input("Cantidad", min_value=0.0)
            pre = c3.number_input("Precio de Costo Unitario", min_value=0.0)
            uni = st.selectbox("Unidad", ["Hojas", "Metros", "Unidades"])
            
            if st.form_submit_button("AGREGAR A BODEGA"):
                if nom:
                    # Si el material ya existe, lo actualizamos
                    if not df_stock.empty and nom in df_stock["Material"].values:
                        df_stock.loc[df_stock["Material"] == nom, "Cantidad"] += cant
                        df_stock.loc[df_stock["Material"] == nom, "Precio_Unitario"] = pre
                        df_stock.to_csv(CSV_STOCK, index=False)
                    else:
                        nueva_c = pd.DataFrame([[nom, cant, uni, pre]], columns=["Material", "Cantidad", "Unidad", "Precio_Unitario"])
                        nueva_c.to_csv(CSV_STOCK, mode='a', header=False, index=False)
                    st.success(f"✅ {nom} agregado con éxito.")
                    st.rerun()

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📈 Resumen del Negocio")
    if os.path.exists(CSV_VENTAS):
        df_v = pd.read_csv(CSV_VENTAS)
        if not df_v.empty:
            st.metric("Ventas Totales Registradas", f"$ {df_v['Monto'].sum():,.2f}")
            st.subheader("Últimos Movimientos")
            st.dataframe(df_v.tail(10), use_container_width=True)
        else:
            st.info("Sin ventas registradas aún.")

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja # (Ej: 001)")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
        else: st.error("Hoja no encontrada en la carpeta manuales.")
