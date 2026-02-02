import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. CERRADURA DE SEGURIDAD ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔐 IMPERIO ATÓMICO: Acceso Restringido")
        st.write("Bienvenida, Socia. Inicia el sistema para operar.")
        password = st.text_input("Clave de Acceso:", type="password")
        if st.button("Activar Sistema"):
            if password == "1234": # <--- CAMBIA TU CLAVE AQUÍ
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. CONFIGURACIÓN DE RUTAS Y DATOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_ALERTAS = "alertas_inventario.csv"
CARPETA_MANUALES = "manuales"

# Asegurar que los archivos existan
for archivo, columnas in {CSV_VENTAS: ["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"], 
                          CSV_ALERTAS: ["Fecha", "Insumo", "Estado", "Responsable"]}.items():
    if not os.path.exists(archivo) or os.path.getsize(archivo) == 0:
        pd.DataFrame(columns=columnas).to_csv(archivo, index=False)

def obtener_nombre_bloque(numero):
    try:
        n = int(numero)
        if 1 <= n <= 75: return "🛠️ BLOQUE 1: INFRAESTRUCTURA Y HARDWARE"
        if 76 <= n <= 150: return "💼 BLOQUE 2: ADMINISTRACIÓN Y FINANZAS"
        if 151 <= n <= 225: return "🎯 BLOQUE 3: MARKETING Y VENTAS"
        if 226 <= n <= 300: return "🧩 BLOQUE 4: PRODUCCIÓN Y CALIDAD"
        return "📚 BLOQUE ADICIONAL"
    except: return "❓ Número no válido"

# --- 3. INTERFAZ VISUAL ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")
st.sidebar.title("💎 PANEL DE CONTROL")
menu = st.sidebar.radio("Navegación:", 
    ["📊 Dashboard Maestro", "💰 Registrar Venta (088)", "📦 Alerta de Inventario", "🔍 Buscador de Protocolos"])

# --- MODULO: DASHBOARD ---
if menu == "📊 Dashboard Maestro":
    st.title("📈 Estado del Imperio")
    df = pd.read_csv(CSV_VENTAS)
    df_inv = pd.read_csv(CSV_ALERTAS)
    
    col1, col2 = st.columns(2)
    if not df.empty:
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0)
        col1.metric("Ingresos Totales", f"$ {df['Monto'].sum():,.2f}")
    
    if not df_inv.empty:
        criticos = len(df_inv[df_inv['Estado'] == 'Crítico'])
        col2.metric("Alertas Críticas", criticos, delta_color="inverse")

    st.subheader("Últimas Ventas")
    st.dataframe(df.tail(10), use_container_width=True)

# --- MODULO: REGISTRO 088 ---
elif menu == "💰 Registrar Venta (088)":
    st.title("📝 Registro de Entrada - Hoja 088")
    with st.form("registro_088"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Cliente")
        producto = c2.selectbox("Servicio", ["Stickers", "Carpetas", "Tesis", "Copias", "Diseño", "Otro"])
        monto = st.number_input("Monto ($)", min_value=0.0)
        metodo = st.selectbox("Método", ["Efectivo", "Nequi", "Daviplata"])
        responsable = st.text_input("Atendido por:")
        if st.form_submit_button("GUARDAR VENTA"):
            nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, producto, monto, metodo, responsable]], columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
            nueva.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            st.success("✅ Venta registrada.")

# --- MODULO: INVENTARIO (EL QUE FALTABA) ---
elif menu == "📦 Alerta de Inventario":
    st.title("📦 Sensor de Insumos")
    st.info("Registra aquí cuando algo se esté agotando para que la Inversionista lo vea en el Dashboard.")
    with st.form("alerta_inv"):
        insumo = st.text_input("¿Qué material falta? (Ej: Papel Fotográfico)")
        estado = st.select_slider("Nivel de Urgencia", options=["Bajo", "Medio", "Crítico"])
        quien = st.text_input("Reportado por:")
        if st.form_submit_button("ENVIAR ALERTA"):
            nueva_alerta = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), insumo, estado, quien]], columns=["Fecha", "Insumo", "Estado", "Responsable"])
            nueva_alerta.to_csv(CSV_ALERTAS, mode='a', header=False, index=False)
            st.error(f"⚠️ Alerta de {insumo} enviada al sistema.")

# --- MODULO: BUSCADOR ---
elif menu == "🔍 Buscador de Protocolos":
    st.title("🔍 Central de Inteligencia")
    n_hoja = st.text_input("Número de hoja (Ej: 001):")
    if n_hoja:
        n_formateado = n_hoja.zfill(3)
        st.caption(obtener_nombre_bloque(n_formateado))
        ruta = f"{CARPETA_MANUALES}/{n_formateado}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.info(f.read())
        else:
            st.warning("Hoja no encontrada.")
