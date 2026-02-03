import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# ==========================================
# 1. MOTOR DE BASE DE DATOS Y LÓGICA
# ==========================================
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    # Nueva tabla para configuración de precios por inflación
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    # Valores por defecto
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

def analizar_cmyk(file):
    try:
        if file.type == "application/pdf":
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(file).convert("RGB")
        pix_arr = np.array(img) / 255.0
        k = 1 - np.max(pix_arr, axis=2)
        c = (1-pix_arr[:,:,0]-k)/(1-k+1e-9)
        m = (1-pix_arr[:,:,1]-k)/(1-k+1e-9)
        y = (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        return img, {"C": c.mean(), "M": m.mean(), "Y": y.mean(), "K": k.mean()}
    except: return None, None

# ==========================================
# 2. INICIO Y SEGURIDAD
# ==========================================
st.set_page_config(page_title="Imperio Atómico Enterprise", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state:
    st.session_state.login = False

if not st.session_state.login:
    st.title("🛡️ Acceso de Seguridad")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("🔓 Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
    st.stop()

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
with st.sidebar:
    st.title("⚛️ Menú Imperio")
    # Cargar valores de configuración desde la DB
    conn = conectar()
    tasa_db = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='tasa_bcv'", conn).iloc[0,0]
    tinta_db = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='costo_tinta_ml'", conn).iloc[0,0]
    conn.close()
    
    st.metric("Tasa Activa", f"{tasa_db} Bs")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("🚪 Salir"):
        st.session_state.login = False
        st.rerun()

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Estado del Imperio")
    # Métricas rápidas
    c1, c2, c3 = st.columns(3)
    c1.metric("Tasa BCV", f"{tasa_db} Bs")
    c2.metric("Insumos en Stock", "Conectado")
    c3.metric("Analizador", "Listo")

# --- 2. CLIENTES (Con Buscador) ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.expander("➕ Registrar Nuevo Cliente"):
        with st.form("new_cli"):
            n = st.text_input("Nombre")
            w = st.text_input("WhatsApp")
            if st.form_submit_button("Guardar"):
                conn = conectar()
                conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w))
                conn.commit() ; conn.close()
                st.success("Guardado.")
    
    busqueda = st.text_input("🔍 Buscar Cliente por nombre...")
    conn = conectar()
    df_cl = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{busqueda}%'", conn)
    conn.close()
    st.dataframe(df_cl, use_container_width=True)

# --- 3. INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario Real")
    # Formulario y tabla (igual al anterior pero persistente)
    conn = conectar()
    st.dataframe(pd.read_sql_query("SELECT * FROM inventario", conn), use_container_width=True)
    conn.close()

# --- 4. ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Tinta")
    imp = st.selectbox("Máquina", ["Epson L1250", "HP Smart Tank", "J210a"])
    f = st.file_uploader("Diseños", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                st.image(img, width=200)
                costo = sum(res.values()) * tinta_db
                st.write(f"Costo: ${costo:.4f} / {costo*tasa_db:.2f} Bs")

# --- 5. MANUALES (VUELVEN) ---
elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    st.write("Guía rápida para solución de problemas en el taller.")
    
    with st.expander("🖨️ Epson L1250 - Error de Almohadillas"):
        st.error("Luz de tinta y papel parpadean alternadamente.")
        st.write("1. Descarga el Adjustment Program.")
        st.write("2. Selecciona 'Waste Ink Pad Counter'.")
        st.write("3. Marca 'Main Pad' y dale a 'Check' y luego 'Initialize'.")
        
    with st.expander("💧 HP Smart Tank - Purga de Aire"):
        st.write("Si los tubos tienen aire, realiza una limpieza de cabezal nivel 2 desde el software oficial.")

# --- 6. CONFIGURACIÓN (REPARADA) ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Centro de Control de Inflación")
    st.subheader("Ajuste de Precios Globales")
    
    new_tasa = st.number_input("Editar Tasa BCV (Bs)", value=tasa_db)
    new_tinta = st.number_input("Editar Costo Tinta por ml (USD)", value=tinta_db, format="%.4f")
    
    if st.button("💾 Guardar Cambios en el Sistema"):
        conn = conectar()
        conn.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (new_tasa,))
        conn.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (new_tinta,))
        conn.commit()
        conn.close()
        st.success("¡Sistema actualizado! Los cambios se aplicarán en todos los módulos.")
        st.rerun()
