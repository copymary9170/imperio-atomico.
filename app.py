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
    
    # Asegurar columnas por si acaso
    columnas = [('monto_bcv', 'REAL'), ('monto_binance', 'REAL')]
    for col, tipo in columnas:
        try: c.execute(f'ALTER TABLE cotizaciones ADD COLUMN {col} {tipo}')
        except: pass
        
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
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

# --- 2. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Imperio Atómico - Dashboard Pro", layout="wide")
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
t_tinta = conf.loc['costo_tinta_ml', 'valor']
df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 3. MENÚ ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.success(f"🏦 BCV: {t_bcv} Bs")
    st.warning(f"🔶 BIN: {t_bin} Bs")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 4. DASHBOARD (REPARADO) ---
if menu == "📊 Dashboard":
    st.title("📊 Centro de Control de Ingresos")
    
    # Métricas principales
    m1, m2, m3 = st.columns(3)
    
    if not df_cots.empty:
        total_usd = df_cots[df_cots['estado'] == 'Pagado']['monto_usd'].sum()
        pendiente_usd = df_cots[df_cots['estado'] == 'Pendiente']['monto_usd'].sum()
        
        m1.metric("Ingresos Reales (USD)", f"$ {total_usd:,.2f}")
        m2.metric("Por Cobrar (Pendiente)", f"$ {pendiente_usd:,.2f}")
        m3.metric("Total en Inventario", f"$ { (df_inv['cantidad'] * df_inv['precio_usd']).sum() if not df_inv.empty else 0 :,.2f}")
    
        st.divider()
        
        # Conversión en tiempo real para el usuario
        st.subheader("💰 Equivalencia de Caja (Ingresos Pagados)")
        c1, c2 = st.columns(2)
        c1.info(f"🏦 **Total en BCV:** { (total_usd * t_bcv) :,.2f} Bs")
        c2.warning(f"🔶 **Total en Binance:** { (total_usd * t_bin) :,.2f} Bs")
        
        st.divider()
        st.subheader("📈 Últimas 5 Ventas")
        st.table(df_cots.tail(5)[['fecha', 'cliente', 'trabajo', 'monto_usd', 'estado']])
    else:
        st.info("Aún no tienes ventas registradas para mostrar estadísticas.")

# --- 5. MÓDULO INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    with st.form("fi"):
        it = st.text_input("Item")
        ca = st.number_input("Cantidad", min_value=0.0)
        un = st.selectbox("Unid", ["ml", "Hojas", "Unid"])
        pr = st.number_input("Precio USD", min_value=0.0)
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it, ca, un, pr)); c.commit(); c.close(); st.rerun()
    st.dataframe(df_inv, use_container_width=True)

# --- 6. MÓDULO ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos")
    f = st.file_uploader("Sube tu diseño", accept_multiple_files=True)
    if f:
        for file in f:
            img, res = analizar_cmyk(file)
            if img:
                with st.expander(f"Resultado: {file.name}"):
                    costo = sum(res.values()) * t_tinta
                    st.image(img, width=200)
                    st.write(f"Costo Tinta: ${costo:.4f}")
                    st.write(f"BCV: {costo*t_bcv:.2f} Bs | BIN: {costo*t_bin:.2f} Bs")

# --- 7. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración de Tasas")
    with st.form("f_conf"):
        nb = st.number_input("Tasa BCV", value=t_bcv)
        ni = st.number_input("Tasa Binance", value=t_bin)
        if st.form_submit_button("Actualizar Todo"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (nb,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (ni,))
            c.commit(); c.close(); st.rerun()

# --- RELLENO DE MÓDULOS FALTANTES PARA QUE NO DEN ERROR ---
elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.form("fcl"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close(); st.rerun()
    bus = st.text_input("Buscar")
    c = conectar(); df = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df, use_container_width=True)

elif menu == "📝 Cotizaciones":
    st.title("📝 Cotizaciones")
    c = conectar(); lista = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist(); c.close()
    with st.form("fcot"):
        cl = st.selectbox("Cliente", ["--"] + lista)
        tr = st.text_input("Trabajo")
        mu = st.number_input("Monto USD")
        if st.form_submit_button("Guardar"):
            if cl != "--":
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cl, tr, mu, mu*t_bcv, mu*t_bin, "Pendiente"))
                c.commit(); c.close(); st.rerun()

elif menu == "🔍 Manuales":
    st.title("🔍 Manuales")
    st.write("Epson L1250: Reset de Almohadillas en Manuales Técnicos.")
