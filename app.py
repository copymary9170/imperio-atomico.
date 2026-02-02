import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURACIÓN DE CORAZÓN DEL SISTEMA ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_INVENTARIO = "inventario_critico.csv"
CARPETA_MANUALES = "manuales"

# Asegurar archivos base
for file in [CSV_VENTAS, CSV_INVENTARIO]:
    if not os.path.exists(file):
        pd.DataFrame().to_csv(file, index=False)

# --- INTERFAZ VIVA ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")

# Estilos para que se vea profesional
st.markdown("""
    <style>
    .stMetric { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .stDataFrame { border: 1px solid #e6e9ef; }
    </style>
    """, unsafe_allow_html=True)

# --- NAVEGACIÓN VIVA ---
menu = st.sidebar.radio("CENTRAL DE MANDO", 
    ["📈 Dashboard de Control", "💰 Registrar Venta", "📦 Inventario Real", "🔍 Buscador de Protocolos"])

# --- 1. DASHBOARD DE CONTROL (VIGILANCIA EN TIEMPO REAL) ---
if menu == "📈 Dashboard de Control":
    st.title("🏛️ Estado del Imperio")
    df = pd.read_csv(CSV_VENTAS) if os.path.getsize(CSV_VENTAS) > 0 else pd.DataFrame()
    
    if not df.empty:
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
        c1, c2, c3 = st.columns(3)
        c1.metric("Dinero en Caja Today", f"$ {df['Monto'].sum():,.2f}")
        c2.metric("Pedidos Realizados", len(df))
        c3.metric("Ticket Promedio", f"$ {df['Monto'].mean():,.2f}")
        
        st.subheader("Últimos Movimientos")
        st.table(df.tail(5))
    else:
        st.warning("El sistema está encendido pero no hay ventas hoy. ¡A vender!")

# --- 2. REGISTRAR VENTA (EL MOTOR) ---
elif menu == "💰 Registrar Venta":
    st.title("📝 Nueva Operación - Hoja 088")
    with st.form("venta_viva"):
        col1, col2 = st.columns(2)
        cliente = col1.text_input("Nombre del Cliente")
        producto = col2.selectbox("Servicio", ["Stickers", "Carpetas", "Tesis", "Copias", "Diseño"])
        monto = st.number_input("Monto Cobrado ($)", min_value=0.0)
        metodo = st.selectbox("Método de Pago", ["Efectivo", "Nequi", "Daviplata"])
        vendedor = st.text_input("¿Quién operó la máquina?")
        
        if st.form_submit_button("REGISTRAR Y GUARDAR"):
            nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, producto, monto, metodo, vendedor]], 
                                 columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
            nueva.to_csv(CSV_VENTAS, mode='a', header=not os.path.exists(CSV_VENTAS), index=False)
            st.success("✅ Venta Guardada. La Inversionista ya puede ver este reporte.")
            st.balloons()

# --- 3. INVENTARIO REAL (ALERTA DE INSUMOS) ---
elif menu == "📦 Inventario Real":
    st.title("📦 Alertas de Insumos")
    st.info("Cuando un material llegue al mínimo, regístralo aquí para que la Inversionista compre repuestos.")
    # Lógica de inventario simple para avisarte a ti
    item = st.text_input("Material que se está acabando")
    cantidad = st.text_input("¿Cuánto queda? (Ej: 2 hojas, 10%)")
    if st.button("Enviar Alerta de Compra"):
        st.error(f"⚠️ ALERTA ENVIADA: Necesitamos comprar {item} urgente.")

# --- 4. BUSCADOR DE PROTOCOLOS (EL CEREBRO) ---
elif menu == "🔍 Buscador de Protocolos":
    st.title("🔍 Consulta Técnica")
    hoja = st.text_input("Número de Hoja (001-500)")
    if hoja:
        ruta = f"manuales/{hoja}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.markdown(f"### 📋 Manual {hoja}")
                st.write(f.read())
        else:
            st.error("Esa hoja no existe aún. Por favor, crea el archivo .txt en GitHub.")
