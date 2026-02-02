import streamlit as st
import pandas as pd
import os
from datetime import datetime

# CONFIGURACIÓN DE RUTAS
CSV_VENTAS = "registro_ventas_088.csv"
CARPETA_MANUALES = "manuales"

# Asegurar que la carpeta de manuales exista
if not os.path.exists(CARPETA_MANUALES):
    os.makedirs(CARPETA_MANUALES)

def cargar_datos():
    if os.path.exists(CSV_VENTAS):
        return pd.read_csv(CSV_VENTAS)
    return pd.DataFrame(columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])

# INTERFAZ VISUAL
st.set_page_config(page_title="Sistema Maestro - Imperio Atómico", layout="wide")

st.sidebar.title("💎 MENU PRINCIPAL")
menu = st.sidebar.radio("Selecciona una sección:", 
    ["📊 Dashboard (Estado Real)", "📝 Registro de Ventas (088)", "🔍 Buscador de Protocolos (001-500)", "🧮 Calculadora de Precios"])

# --- SECCIÓN: DASHBOARD ---
if menu == "📊 Dashboard (Estado Real)":
    st.header("📈 Estado del Imperio")
    df = cargar_datos()
    if not df.empty:
        col1, col2 = st.columns(2)
        total_ventas = df['Monto'].sum()
        col1.metric("Ventas Totales", f"${total_ventas:,.2f}")
        col2.metric("Total Pedidos", len(df))
        st.subheader("Últimos movimientos")
        st.table(df.tail(5))
    else:
        st.info("Aún no hay ventas registradas. ¡A trabajar!")

# --- SECCIÓN: REGISTRO 088 ---
elif menu == "📝 Registro de Ventas (088)":
    st.header("📝 Hoja 088: Entrada de Dinero")
    df = cargar_datos()
    
    with st.form("nueva_venta"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Nombre del Cliente")
        producto = c2.selectbox("¿Qué compró?", ["Carpetas", "Stickers", "Tesis", "Anillado", "Copia/Impresión", "Diseño"])
        
        c3, c4 = st.columns(2)
        monto = c3.number_input("Precio Cobrado ($)", min_value=0.0, step=0.5)
        metodo = c4.selectbox("Método", ["Efectivo", "Nequi", "Daviplata", "Transferencia"])
        
        responsable = st.text_input("Atendido por:")
        
        if st.form_submit_button("REGISTRAR VENTA"):
            nueva_fila = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, producto, monto, metodo, responsable]], 
                                     columns=df.columns)
            df = pd.concat([df, nueva_fila], ignore_index=True)
            df.to_csv(CSV_VENTAS, index=False)
            st.success("✅ Venta guardada con éxito.")
            st.balloons()

# --- SECCIÓN: BUSCADOR 500 HOJAS ---
elif menu == "🔍 Buscador de Protocolos (001-500)":
    st.header("🔍 Consulta de la Constitución Atómica")
    num_hoja = st.text_input("Escribe el número de la hoja (Ejemplo: 001, 041, 088):")
    
    if num_hoja:
        nombre_archivo = f"{num_hoja}.txt"
        ruta_archivo = os.path.join(CARPETA_MANUALES, nombre_archivo)
        
        if os.path.exists(ruta_archivo):
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                contenido = f.read()
            st.markdown(f"### 📄 HOJA {num_hoja}")
            st.info(contenido)
        else:
            st.warning(f"La Hoja {num_hoja} aún no ha sido redactada. ¿Quieres crearla?")
            nuevo_texto = st.text_area("Escribe el protocolo aquí:")
            if st.button("Guardar Protocolo"):
                with open(ruta_archivo, "w", encoding="utf-8") as f:
                    f.write(nuevo_texto)
                st.success(f"Hoja {num_hoja} creada con éxito.")

# --- SECCIÓN: CALCULADORA ---
elif menu == "🧮 Calculadora de Precios":
    st.header("🧮 Calculadora de Rentabilidad")
    st.write("Usa esto para no perder dinero en los pedidos.")
    costo_luz = 28.0 # Tu gasto fijo
    st.info(f"Gasto Fijo Mensual: ${costo_luz}")
    # Aquí puedes agregar más lógica de costos