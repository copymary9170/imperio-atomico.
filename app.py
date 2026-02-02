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
CARPETA_MANUALES = "manuales"

# Asegurar que el archivo de ventas exista con sus columnas
if not os.path.exists(CSV_VENTAS) or os.path.getsize(CSV_VENTAS) == 0:
    df_init = pd.DataFrame(columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
    df_init.to_csv(CSV_VENTAS, index=False)

# Función para identificar el Bloque según el número de hoja
def obtener_nombre_bloque(numero):
    try:
        n = int(numero)
        if 1 <= n <= 75: return "🛠️ BLOQUE 1: INFRAESTRUCTURA Y HARDWARE"
        if 76 <= n <= 150: return "💼 BLOQUE 2: ADMINISTRACIÓN Y FINANZAS"
        if 151 <= n <= 225: return "🎯 BLOQUE 3: MARKETING Y VENTAS"
        if 226 <= n <= 300: return "🧩 BLOQUE 4: PRODUCCIÓN Y CALIDAD"
        return "📚 BLOQUE ADICIONAL"
    except:
        return "❓ Número no válido"

# --- 3. INTERFAZ VISUAL ---
st.set_page_config(page_title="Imperio Atómico - VIVO", layout="wide")

st.sidebar.title("💎 PANEL DE CONTROL")
menu = st.sidebar.radio("Navegación:", 
    ["📊 Dashboard Maestro", "💰 Registrar Venta (Hoja 088)", "🔍 Buscador de Protocolos"])

# --- MODULO: DASHBOARD ---
if menu == "📊 Dashboard Maestro":
    st.title("📈 Estado del Imperio en Tiempo Real")
    df = pd.read_csv(CSV_VENTAS)
    
    if not df.empty:
        # Convertir monto a número por si acaso
        df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Ingresos Totales", f"$ {df['Monto'].sum():,.2f}")
        col2.metric("Total Pedidos", len(df))
        col3.metric("Última Venta", f"$ {df['Monto'].iloc[-1]:,.2f}")
        
        st.subheader("Historial Reciente de Operaciones")
        st.dataframe(df.tail(15), use_container_width=True)
    else:
        st.info("No hay ventas registradas todavía. El sistema está listo para recibir datos.")

# --- MODULO: REGISTRO 088 ---
elif menu == "💰 Registrar Venta (Hoja 088)":
    st.title("📝 Registro de Entrada - Hoja 088")
    st.write("Cada dato ingresado aquí se refleja instantáneamente en el Dashboard de la Inversionista.")
    
    with st.form("registro_088"):
        c1, c2 = st.columns(2)
        cliente = c1.text_input("Nombre del Cliente")
        producto = c2.selectbox("Producto/Servicio", ["Stickers", "Carpetas", "Tesis", "Copias", "Diseño", "Otro"])
        
        c3, c4 = st.columns(2)
        monto = c3.number_input("Monto Cobrado ($)", min_value=0.0, step=0.01)
        metodo = c4.selectbox("Método de Pago", ["Efectivo", "Nequi", "Daviplata", "Transferencia"])
        
        responsable = st.text_input("Responsable de la Operación")
        
        if st.form_submit_button("GUARDAR REGISTRO"):
            fecha_ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
            nueva_fila = pd.DataFrame([[fecha_ahora, cliente, producto, monto, metodo, responsable]], 
                                     columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])
            
            nueva_fila.to_csv(CSV_VENTAS, mode='a', header=False, index=False)
            st.success(f"✅ Registro guardado. Fecha: {fecha_ahora}")
            st.balloons()

# --- MODULO: BUSCADOR ---
elif menu == "🔍 Buscador de Protocolos":
    st.title("🔍 Central de Inteligencia (001 - 500)")
    n_hoja = st.text_input("Digita el número de hoja para consultar el protocolo:")
    
    if n_hoja:
        # Normalizar el número para que siempre tenga 3 cifras (ej: 1 -> 001)
        try:
            n_formateado = n_hoja.zfill(3)
            nombre_bloque = obtener_nombre_bloque(n_formateado)
            
            st.subheader(nombre_bloque)
            
            ruta = f"{CARPETA_MANUALES}/{n_formateado}.txt"
            
            if os.path.exists(ruta):
                with open(ruta, "r", encoding="utf-8") as f:
                    contenido = f.read()
                    st.info(f"📄 **Protocolo {n_formateado}**")
                    st.markdown(f"```\n{contenido}\n```")
            else:
                st.warning(f"⚠️ La Hoja {n_formateado} aún no ha sido cargada al sistema.")
                st.write("Socia: Recuerda subir el archivo .txt a la carpeta 'manuales' en GitHub.")
        except:
            st.error("Por favor, ingresa solo números.")
