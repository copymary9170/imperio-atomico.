import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. BLOQUE DE SEGURIDAD (LA CERRADURA) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Imperio Atómico")
        st.write("Bienvenida, Socia. Identifícate para entrar al centro de mando.")
        password = st.text_input("Ingresa la clave maestra:", type="password")
        if st.button("Entrar"):
            if password == "mary": # CAMBIA ESTO POR TU CLAVE REAL
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("⚠️ Clave incorrecta.")
        return False
    return True

if not check_password():
    st.stop() # Si no hay clave, no muestra nada de lo que sigue

# --- 2. CONFIGURACIÓN DEL SISTEMA VIVO ---
CSV_VENTAS = "registro_ventas_088.csv"
CARPETA_MANUALES = "manuales"

# Asegurar que el archivo de ventas tenga encabezados si está vacío
if not os.path.exists(CSV_VENTAS) or os.path.getsize(CSV_VENTAS) == 0:
    pd.DataFrame(columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"]).to_csv(CSV_VENTAS, index=False)

# --- 3. INTERFAZ Y NAVEGACIÓN ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")

menu = st.sidebar.radio("CENTRAL DE MANDO", 
    ["📈 Dashboard de Control", "💰 Registrar Venta (088)", "📦 Alerta de Inventario", "🔍 Buscador de Protocolos"])

# --- MODULO: DASHBOARD ---
if menu == "📈 Dashboard de Control":
    st.title("🏛️ Estado Real del Negocio")
    df = pd.read_csv(CSV_VENTAS)
    
    if not df.empty:
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
        c1, c2 = st.columns(2)
        c1.metric("Ventas Totales", f"$ {df['Monto'].sum():,.2f}")
        c2.metric("Total Pedidos", len(df))
        
        st.subheader("Últimos 10 registros")
        st.dataframe(df.tail(10), use_container_width=True)
    else:
        st.info("Esperando el primer registro del día...")

# --- MODULO: REGISTRO 088 ---
elif menu == "💰 Registrar Venta (088)":
    st.title("📝 Registro de Operación")
    with st.form("venta_viva"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        producto = c2.selectbox("Servicio", ["Stickers", "Carpetas", "Tesis", "Copias", "Diseño", "Otros"])
        
        c3, c4 = st.columns(2)
        monto = c3.number_input("Monto ($)", min_value=0.0)
        metodo = c4.selectbox("Método", ["Efectivo", "Nequi", "Daviplata"])
        
        responsable = st.text_input("¿Quién atiende?")
        
        if st.form_submit_button("GUARDAR EN HOJA 088"):
            nueva_fila = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, producto, monto, metodo, responsable]], 
                                     columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
            nueva_fila.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            st.success("✅ Venta guardada físicamente en el servidor.")
            st.balloons()

# --- MODULO: INVENTARIO ---
elif menu == "📦 Alerta de Inventario":
    st.title("📦 Reporte de Insumos Bajos")
    st.warning("Usa esto para avisar a la Inversionista qué falta comprar.")
    insumo = st.text_input("¿Qué material falta?")
    nivel = st.select_slider("Nivel actual", options=["Crítico", "Bajo", "Medio"])
    if st.button("Enviar Alerta"):
        st.error(f"ALERTA: El material '{insumo}' está en nivel {nivel}.")

# --- MODULO: BUSCADOR ---
elif menu == "🔍 Buscador de Protocolos":
    st.title("🔍 Consulta de Manuales")
    hoja = st.text_input("Ingresa el número de hoja (Ej: 001)")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.info(f.read())
        else:
            st.error("Esa hoja aún no ha sido creada en la carpeta manuales.")
