import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

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
    
    # Asegurar configuración base e impuestos
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('iva_perc', 0.16)") # 16% IVA
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('igtf_perc', 0.03)") # 3% IGTF
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('banco_perc', 0.02)") # 2% Comisión Banco
    conn.commit()
    conn.close()

# --- 2. INICIO ---
st.set_page_config(page_title="Imperio Atómico OS", layout="wide")
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

# Carga de datos y tasas
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
iva = conf.loc['iva_perc', 'valor']
igtf = conf.loc['igtf_perc', 'valor']
banco = conf.loc['banco_perc', 'valor']
df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 3. MENÚ ---
with st.sidebar:
    st.header("⚛️ Menú Imperio")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📦 Inventario", "📝 Cotizaciones", "⚙️ Configuración"])

# --- 4. LÓGICA DE MÓDULOS ---

if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    k1, k2, k3 = st.columns(3)
    pagado = df_cots[df_cots['estado'] == 'Pagado']['monto_usd'].sum() if not df_cots.empty else 0
    pendiente = df_cots[df_cots['estado'] == 'Pendiente']['monto_usd'].sum() if not df_cots.empty else 0
    
    # Valor de inventario ajustado con impuestos
    factor_total = 1 + iva + igtf + banco
    inv_total = (df_inv['cantidad'] * (df_inv['precio_usd'] * factor_total)).sum() if not df_inv.empty else 0
    
    k1.metric("Ingresos (USD)", f"$ {pagado:,.2f}")
    k2.metric("Pendiente (USD)", f"$ {pendiente:,.2f}")
    k3.metric("Stock Real (USD)", f"$ {inv_total:,.2f}")

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.form("fcl"):
        n, w = st.text_input("Nombre"), st.text_input("WhatsApp")
        if st.form_submit_button("Guardar"):
            if n:
                c = conectar(); c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (n, w)); c.commit(); c.close()
                st.rerun()
    bus = st.text_input("🔍 Buscar")
    c = conectar(); df_c = pd.read_sql_query(f"SELECT * FROM clientes WHERE nombre LIKE '%{bus}%'", c); c.close()
    st.dataframe(df_c, use_container_width=True)

elif menu == "📦 Inventario":
    st.title("📦 Inventario con Impuestos")
    
    with st.expander("📥 Cargar Stock (Precios sin Impuestos)"):
        with st.form("finv"):
            it = st.text_input("Producto")
            ca = st.number_input("Cantidad", min_value=0.0)
            pr = st.number_input("Precio Costo USD (Limpio)", min_value=0.0, format="%.2f")
            if st.form_submit_button("Calcular y Guardar"):
                c = conectar()
                c.execute("INSERT OR REPLACE INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,?,?,?)", (it, ca, 'Unid', pr))
                c.commit(); c.close()
                st.rerun()

    if not df_inv.empty:
        # Cálculo de costos reales
        df_inv['Precio + IVA'] = df_inv['precio_usd'] * (1 + iva)
        df_inv['Costo Final (+GTF+Banc)'] = df_inv['precio_usd'] * (1 + iva + igtf + banco)
        df_inv['Inversión Total USD'] = df_inv['cantidad'] * df_inv['Costo Final (+GTF+Banc)']
        
        st.subheader("📋 Detalle de Costos de Reposición")
        st.dataframe(df_inv, use_container_width=True)
        
        st.info(f"💡 **Nota:** El costo final incluye IVA ({iva*100}%), GTF ({igtf*100}%) y Comisión Bancaria ({banco*100}%
