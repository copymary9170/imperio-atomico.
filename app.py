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
CSV_STOCK = "stock_actual.csv"
CARPETA_MANUALES = "manuales"

# Asegurar que los archivos existan con sus columnas correctas
def inicializar_archivos():
    if not os.path.exists(CSV_VENTAS) or os.path.getsize(CSV_VENTAS) == 0:
        pd.DataFrame(columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"]).to_csv(CSV_VENTAS, index=False)
    
    if not os.path.exists(CSV_ALERTAS) or os.path.getsize(CSV_ALERTAS) == 0:
        pd.DataFrame(columns=["Fecha", "Insumo", "Estado", "Responsable"]).to_csv(CSV_ALERTAS, index=False)
    
    if not os.path.exists(CSV_STOCK) or os.path.getsize(CSV_STOCK) == 0:
        df_stock = pd.DataFrame(columns=["Material", "Cantidad", "Unidad"])
        df_stock.to_csv(CSV_STOCK, index=False)

inicializar_archivos()

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
    ["📊 Dashboard Maestro", "💰 Registrar Venta (088)", "📦 Gestión de Stock e Inventario", "🔍 Buscador de Protocolos"])

# --- MODULO: DASHBOARD ---
if menu == "📊 Dashboard Maestro":
    st.title("📈 Estado General del Imperio")
    df = pd.read_csv(CSV_VENTAS)
    df_inv = pd.read_csv(CSV_ALERTAS)
    
    c1, c2, c3 = st.columns(3)
    if not df.empty:
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0)
        c1.metric("Ingresos Totales", f"$ {df['Monto'].sum():,.2f}")
        c2.metric("Total Pedidos", len(df))
    
    if not df_inv.empty:
        criticos = len(df_inv[df_inv['Estado'] == 'Crítico'])
        c3.metric("Alertas Críticas", criticos, delta_color="inverse")

    st.subheader("Últimos Movimientos en Caja")
    st.dataframe(df.tail(10), use_container_width=True)

# --- MODULO: REGISTRO 088 ---
elif menu == "💰 Registrar Venta (088)":
    st.title("📝 Registro de Operación - Hoja 088")
    with st.form("registro_088"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Nombre del Cliente")
        producto = c2.selectbox("Servicio Prestado", ["Stickers", "Carpetas", "Tesis", "Copias", "Diseño", "Otro"])
        
        c3, c4 = st.columns(2)
        monto = c3.number_input("Monto Recibido ($)", min_value=0.0)
        metodo = c4.selectbox("Método de Pago", ["Efectivo", "Nequi", "Daviplata", "Transferencia"])
        
        responsable = st.text_input("Operador responsable:")
        
        if st.form_submit_button("GUARDAR EN BASE DE DATOS"):
            nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cliente, producto, monto, metodo, responsable]], 
                                 columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
            nueva.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            st.success("✅ Venta registrada correctamente.")
            st.balloons()

# --- MODULO: GESTIÓN DE STOCK ---
elif menu == "📦 Gestión de Stock e Inventario":
    st.title("📦 Gestión de Suministros")
    tab1, tab2, tab3 = st.tabs(["📋 Existencias Actuales", "🛒 Registrar Compra", "⚠️ Reportar Faltante"])
    
    with tab1:
        st.subheader("Estado de la Bodega")
        df_stock = pd.read_csv(CSV_STOCK)
        if not df_stock.empty:
            st.dataframe(df_stock, use_container_width=True)
        else:
            st.info("La bodega está vacía. Registra una compra para empezar.")
    
    with tab2:
        st.subheader("Entrada de Nuevo Material")
        with st.form("nueva_compra"):
            mat_nom = st.text_input("Nombre del Material (Ej: Papel Fotográfico)")
            mat_cant = st.number_input("Cantidad que ingresa", min_value=0.0)
            mat_unid = st.selectbox("Unidad de Medida", ["Hojas", "Metros", "Unidades", "%", "Rollos"])
            
            if st.form_submit_button("REGISTRAR INGRESO"):
                nueva_compra = pd.DataFrame([[mat_nom, mat_cant, mat_unid]], columns=["Material", "Cantidad", "Unidad"])
                nueva_compra.to_csv(CSV_STOCK, mode='a', header=False, index=False)
                st.success(f"✅ {mat_nom} añadido al inventario.")

    with tab3:
        st.subheader("Sistema de Alerta de Compras")
        with st.form("alerta_inv"):
            insumo = st.text_input("Material que falta o se acabó")
            estado = st.select_slider("Nivel de Urgencia", options=["Bajo", "Medio", "Crítico"])
            quien = st.text_input("¿Quién detectó la falta?")
            if st.form_submit_button("ENVIAR REQUERIMIENTO"):
                nueva_alerta = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), insumo, estado, quien]], 
                                            columns=["Fecha", "Insumo", "Estado", "Responsable"])
                nueva_alerta.to_csv(CSV_ALERTAS, mode='a', header=False, index=False)
                st.error(f"⚠️ Alerta por '{insumo}' enviada a la Inversionista.")

# --- MODULO: BUSCADOR ---
elif menu == "🔍 Buscador de Protocolos":
    st.title("🔍 Central de Inteligencia (Manual 500)")
    n_hoja = st.text_input("Número de hoja (Ej: 001):")
    if n_hoja:
        n_formateado = n_hoja.zfill(3)
        st.subheader(obtener_nombre_bloque(n_formateado))
        ruta = f"{CARPETA_MANUALES}/{n_formateado}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.info(f.read())
        else:
            st.warning(f"La Hoja {n_formateado} no se encuentra cargada.")
