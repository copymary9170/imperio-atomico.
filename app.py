import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# ==========================================
# 1. MOTOR DE BASE DE DATOS
# ==========================================
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT, notas TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto REAL, estado TEXT)')
    conn.commit()
    conn.close()

# --- Funciones de Análisis ---
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
    tasa_bcv = st.number_input("Tasa Dólar (Bs)", value=36.50)
    costo_tinta_ml = st.number_input("Costo Tinta USD/ml", value=0.05, format="%.4f")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "⚙️ Configuración"])
    if st.button("🚪 Salir"):
        st.session_state.login = False
        st.rerun()

# --- 1. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Dashboard de Operaciones")
    conn = conectar()
    cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
    clis = pd.read_sql_query("SELECT * FROM clientes", conn)
    inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Clientes Registrados", len(clis))
    col2.metric("Cotizaciones Realizadas", len(cots))
    col3.metric("Tasa Activa", f"{tasa_bcv} Bs")
    
    st.divider()
    st.subheader("⚠️ Alertas de Inventario")
    bajos = inv[inv['cantidad'] < 10]
    if not bajos.empty:
        st.warning(f"Tienes {len(bajos)} insumos con stock bajo.")
        st.dataframe(bajos)
    else:
        st.success("Inventario saludable.")

# --- 2. CLIENTES (Con Buscador) ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    
    with st.expander("➕ Registrar Nuevo Cliente"):
        with st.form("new_cli"):
            n = st.text_input("Nombre Completo")
            w = st.text_input("WhatsApp")
            nt = st.text_area("Notas")
            if st.form_submit_button("Guardar"):
                conn = conectar()
                conn.execute("INSERT INTO clientes (nombre, whatsapp, notas) VALUES (?,?,?)", (n, w, nt))
                conn.commit()
                conn.close()
                st.success("Cliente guardado.")

    st.subheader("🔍 Buscar Cliente")
    busqueda = st.text_input("Escribe nombre o WhatsApp")
    conn = conectar()
    df_cl = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{busqueda}%' OR whatsapp LIKE '%{busqueda}%'", conn)
    conn.close()
    st.dataframe(df_cl, use_container_width=True)

# --- 3. COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Módulo de Cotizaciones")
    conn = conectar()
    lista_clis = pd.read_sql_query("SELECT nombre FROM clientes", conn)['nombre'].tolist()
    conn.close()

    with st.form("new_cot"):
        c1, c2 = st.columns(2)
        cli = c1.selectbox("Cliente", ["Seleccionar..."] + lista_clis)
        trab = c1.text_input("Descripción del Trabajo")
        monto = c2.number_input("Monto USD", min_value=0.0)
        est = c2.selectbox("Estado", ["Pendiente", "Aprobado", "Pagado"])
        if st.form_submit_button("Registrar Cotización"):
            conn = conectar()
            conn.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto, estado) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%Y-%m-%d"), cli, trab, monto, est))
            conn.commit()
            conn.close()
            st.success("Cotización registrada.")

    conn = conectar()
    st.dataframe(pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY id DESC", conn), use_container_width=True)
    conn.close()

# --- 4. INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario de Materiales")
    with st.form("inv_f"):
        c1, c2, c3, c4 = st.columns(4)
        it = c1.text_input("Insumo")
        ca = c2.number_input("Cantidad", min_value=0.0)
        un = c3.selectbox("Unidad", ["Hojas", "ml", "Unid", "Mts"])
        pr = c4.number_input("Precio USD", min_value=0.0)
        if st.form_submit_button("Actualizar Stock"):
            conn = conectar()
            conn.execute("INSERT INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,?,?,?)", (it, ca, un, pr))
            conn.commit()
            conn.close()
            st.rerun()

    conn = conectar()
    st.dataframe(pd.read_sql_query("SELECT * FROM inventario", conn), use_container_width=True)
    conn.close()

# --- 5. ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos de Tinta")
    imp = st.selectbox("Selecciona la Máquina", ["Epson L1250", "HP Smart Tank", "HP J210a"])
    files = st.file_uploader("Sube tus diseños", accept_multiple_files=True)
    
    if files:
        for f in files:
            with st.expander(f"Resultado: {f.name}"):
                img, res = analizar_cmyk(f)
                if img:
                    c1, c2 = st.columns(2)
                    c1.image(img, use_container_width=True)
                    with c2:
                        st.write(f"**Análisis para {imp}**")
                        costo = sum(res.values()) * costo_tinta_ml
                        st.metric("Costo Tinta USD", f"$ {costo:.4f}")
                        st.metric("Costo en Bs", f"{costo * tasa_bcv:.2f} Bs")
                        st.write(f"C: {res['C']:.1%} | M: {res['M']:.1%} | Y: {res['Y']:.1%} | K: {res['K']:.1%}")

# --- 6. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    st.write("Control total de precios e inflación.")
    # Los datos se guardan en el Sidebar pero aquí podemos poner logs o backups
    if st.button("Descargar Base de Datos"):
        with open("imperio_data.db", "rb") as f:
            st.download_button("Descargar archivo .db", f, file_name="imperio.db")
