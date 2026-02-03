import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import numpy as np
from PIL import Image
import fitz

# --- 1. BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bs REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
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

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Full Control", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False

if not st.session_state.login:
    st.title("🔐 Acceso Master")
    u, p = st.text_input("Usuario"), st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u == "admin" and p == "1234":
            st.session_state.login = True
            st.rerun()
    st.stop()

# Carga de Precios (Inflación)
conn = conectar()
tasa_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='tasa_bcv'", conn).iloc[0,0]
tinta_val = pd.read_sql_query("SELECT valor FROM configuracion WHERE parametro='costo_tinta_ml'", conn).iloc[0,0]
conn.close()

# --- 3. MENÚ ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.metric("Tasa BCV", f"{tasa_val} Bs")
    menu = st.radio("Menú", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 4. MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Resumen Financiero")
    conn = conectar()
    df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
    conn.close()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Tasa del Día", f"{tasa_val} Bs")
    if not df_cots.empty:
        total_usd = df_cots[df_cots['estado'] != 'Cancelado']['monto_usd'].sum()
        c2.metric("Ventas Totales (USD)", f"$ {total_usd:,.2f}")
        c3.metric("Ventas Totales (Bs)", f"{total_usd * tasa_val:,.2f} Bs")
    
    st.divider()
    st.subheader("📋 Últimos Movimientos")
    st.dataframe(df_cots.tail(5), use_container_width=True)

elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("form_cliente"):
        nom = st.text_input("Nombre")
        wha = st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nom, wha)); c.commit(); c.close()
            st.success("Cliente guardado")
    bus = st.text_input("🔍 Buscar Cliente")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📝 Cotizaciones":
    st.title("📝 Nueva Cotización")
    c = conectar()
    lista_clis = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist()
    c.close()

    with st.form("form_cot"):
        col_a, col_b = st.columns(2)
        cliente_sel = col_a.selectbox("Cliente", ["--"] + lista_clis)
        trabajo = col_a.text_input("Descripción del Trabajo")
        monto_usd = col_b.number_input("Precio en USD", min_value=0.0, step=0.5)
        monto_bs_sugerido = monto_usd * tasa_val
        col_b.write(f"**Equivalente en Bs: {monto_bs_sugerido:,.2f}**")
        estado = col_b.selectbox("Estado", ["Pendiente", "Pagado", "Cancelado"])
        
        if st.form_submit_button("💾 Guardar Cotización"):
            if cliente_sel != "--":
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bs, estado) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cliente_sel, trabajo, monto_usd, monto_bs_sugerido, estado))
                c.commit(); c.close()
                st.success(f"✅ Guardado: $ {monto_usd} / {monto_bs_sugerido} Bs")
                st.rerun()

    st.subheader("🗂️ Historial de Precios")
    c = conectar()
    df_hist = pd.read_sql_query("SELECT fecha, cliente, trabajo, monto_usd, monto_bs, estado FROM cotizaciones ORDER BY id DESC", c)
    c.close()
    st.dataframe(df_hist, use_container_width=True)

elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    with st.form("form_inv"):
        it = st.text_input("Item")
        ca = st.number_input("Cantidad")
        un = st.selectbox("Unidad", ["ml", "Hojas", "Unids"])
        pr = st.number_input("Precio USD")
        if st.form_submit_button("Actualizar Stock"):
            c = conectar(); c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr)); c.commit(); c.close()
            st.rerun()
    c = conectar(); st.dataframe(pd.read_sql_query("SELECT * FROM inventario", c), use_container_width=True); c.close()

elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico")
    imp = st.selectbox("Impresora", ["Epson L1250", "HP Smart Tank", "J210a"])
    f = st.file_uploader("Subir archivos", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Análisis: {file.name}"):
                    st.image(img, width=200)
                    costo = sum(res.values()) * tinta_val
                    st.write(f"Costo {imp}: **${costo:.4f}** / **{costo*tasa_val:.2f} Bs**")

elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    with st.expander("🛠️ Reset Epson"): st.write("Pasos para el reset...")
    with st.expander("🛠️ Limpieza HP"): st.write("Pasos para la limpieza...")

elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes de Inflación")
    with st.form("form_conf"):
        nt = st.number_input("Nueva Tasa BCV (Bs)", value=tasa_val)
        ni = st.number_input("Nuevo Precio Tinta (USD/ml)", value=tinta_val, format="%.4f")
        if st.form_submit_button("Guardar Cambios"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nt,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='costo_tinta_ml'", (ni,))
            c.commit(); c.close()
            st.success("✅ Tasas actualizadas")
            st.rerun()
