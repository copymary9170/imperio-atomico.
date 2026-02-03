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
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # Parámetros base e impuestos
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('iva_perc', 0.16)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('igtf_perc', 0.03)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('banco_perc', 0.02)")
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

# --- 2. CONFIGURACIÓN Y LOGIN ---
st.set_page_config(page_title="Imperio Atómico - Master OS", layout="wide")
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

# Carga de datos globales
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
iva, igtf, banco = conf.loc['iva_perc', 'valor'], conf.loc['igtf_perc', 'valor'], conf.loc['banco_perc', 'valor']
t_tinta = conf.loc['costo_tinta_ml', 'valor']
df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📦 Inventario", "📝 Cotizaciones", "🎨 Analizador", "⚙️ Configuración"])
    if st.button("🚪 Salir"):
        st.session_state.login = False
        st.rerun()

# --- 4. DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen Financiero")
    k1, k2, k3 = st.columns(3)
    pagado = df_cots[df_cots['estado'] == 'Pagado']['monto_usd'].sum() if not df_cots.empty else 0
    pendiente = df_cots[df_cots['estado'] == 'Pendiente']['monto_usd'].sum() if not df_cots.empty else 0
    factor_rep = 1 + iva + igtf + banco
    inv_total = (df_inv['cantidad'] * (df_inv['precio_usd'] * factor_rep)).sum() if not df_inv.empty else 0
    
    k1.metric("Ingresos (USD)", f"$ {pagado:,.2f}")
    k2.metric("Pendiente (USD)", f"$ {pendiente:,.2f}")
    k3.metric("Stock Reposición (USD)", f"$ {inv_total:,.2f}")
    
    st.divider()
    st.subheader("💰 Tu Caja en Bolívares")
    c_bcv, c_bin = st.columns(2)
    c_bcv.info(f"🏦 **Caja en BCV:** {(pagado * t_bcv):,.2f} Bs")
    c_bin.warning(f"🔶 **Caja en Binance:** {(pagado * t_bin):,.2f} Bs")

# --- 5. CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.form("fcl"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            if n:
                c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
                st.rerun()
    bus = st.text_input("🔍 Buscar")
    c = conectar(); df_c = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%' ORDER BY id DESC", c); c.close()
    st.dataframe(df_c, use_container_width=True)

# --- 6. INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario con Impuestos")
    with st.form("finv"):
        it = st.text_input("Producto")
        ca, pr = st.number_input("Cant", min_value=0.0), st.number_input("Costo USD", min_value=0.0)
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, 'Unid', pr)); c.commit(); c.close(); st.rerun()
    if not df_inv.empty:
        df_inv['Repo USD'] = df_inv['precio_usd'] * factor_rep
        st.dataframe(df_inv, use_container_width=True)

# --- 7. COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Nueva Cotización")
    c = conectar(); clis = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist(); c.close()
    with st.form("fcot"):
        sel = st.selectbox("Cliente", ["--"] + clis)
        job, m_u = st.text_input("Trabajo"), st.number_input("Precio USD")
        if st.form_submit_button("Guardar"):
            if sel != "--":
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), sel, job, m_u, m_u*t_bcv, m_u*t_bin, "Pendiente"))
                c.commit(); c.close(); st.success("Guardado"); st.rerun()
    st.dataframe(df_cots.tail(10), use_container_width=True)

# --- 8. ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos")
    f = st.file_uploader("Subir diseño", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Costo: {file.name}"):
                    costo = sum(res.values()) * t_tinta
                    st.image(img, width=200)
                    st.write(f"Costo Tinta: ${costo:.4f}")
                    st.write(f"BCV: {costo*t_bcv:.2f} Bs | BIN: {costo*t_bin:.2f} Bs")

# --- 9. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes Globales")
    with st.form("fconf"):
        b, bi = st.number_input("BCV", value=t_bcv), st.number_input("Binance", value=t_bin)
        iv, ig, ba = st.number_input("IVA", value=iva), st.number_input("GTF", value=igtf), st.number_input("Banco", value=banco)
        if st.form_submit_button("Guardar"):
            c = conectar()
            for p, v in [('tasa_bcv', b), ('tasa_binance', bi), ('iva_perc', iv), ('igtf_perc', ig), ('banco_perc', ba)]:
                c.execute("UPDATE configuracion SET valor=? WHERE parametro=?", (v, p))
            c.commit(); c.close(); st.rerun()
