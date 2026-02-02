import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. CERRADURA DE SEGURIDAD (Esto va de primero) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Sistema Maestro")
        st.write("Bienvenida, Socia. Por favor identifícate.")
        password = st.text_input("Ingresa la clave del Imperio:", type="password")
        if st.button("Entrar"):
            # CAMBIA '1234' POR LA CLAVE QUE TÚ QUIERAS
            if password == "1234": 
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("⚠️ Clave incorrecta. Acceso denegado.")
        return False
    return True

# Si la clave no es correcta, el programa se detiene aquí y no muestra nada más
if not check_password():
    st.stop()

# --- 2. CONFIGURACIÓN DE RUTAS Y DATOS (Tu código anterior) ---
CSV_VENTAS = "registro_ventas_088.csv"
CARPETA_MANUALES = "manuales"

if not os.path.exists(CARPETA_MANUALES):
    os.makedirs(CARPETA_MANUALES)

def cargar_datos():
    if os.path.exists(CSV_VENTAS):
        return pd.read_csv(CSV_VENTAS)
    return pd.DataFrame(columns=["Fecha", "Cliente", "Producto", "Monto", "Metodo", "Responsable"])

# --- 3. INTERFAZ VISUAL DEL SISTEMA ---
st.sidebar.title("💎 IMPERIO ATÓMICO")
menu = st.sidebar.radio("Navegación:", 
    ["📊 Dashboard", "📝 Registro 088", "🔍 Buscador 001-500", "🧮 Calculadora"])

# (Aquí sigue el resto de la lógica de Dashboard, Registro y Buscador que ya tenías)
if menu == "📊 Dashboard":
    st.header("📈 Estado del Imperio")
    df = cargar_datos()
    if not df.empty:
        st.metric("Ventas Totales", f"${df['Monto'].sum():,.2f}")
        st.table(df.tail(10))
    else:
        st.info("Sin datos registrados.")

elif menu == "📝 Registro 088":
    st.header("📝 Entrada de Dinero")
    # ... código de registro ...
    with st.form("venta"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("Cliente")
        prod = c2.selectbox("Producto", ["Carpetas", "Stickers", "Otros"])
        mon = st.number_input("Monto", min_value=0.0)
        res = st.text_input("Responsable")
        if st.form_submit_button("Guardar"):
            df = cargar_datos()
            nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d %H:%M"), cli, prod, mon, "Efectivo", res]], columns=df.columns)
            pd.concat([df, nueva]).to_csv(CSV_VENTAS, index=False)
            st.success("¡Venta guardada!")

elif menu == "🔍 Buscador 001-500":
    st.header("🔍 Manuales de Operación")
    num = st.text_input("Número de hoja:")
    if num:
        ruta = os.path.join(CARPETA_MANUALES, f"{num}.txt")
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.info(f.read())
        else:
            st.warning("Hoja no encontrada.")