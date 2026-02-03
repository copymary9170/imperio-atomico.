import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. MOTOR DE BASE DE DATOS (REPARADO) ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    # Clientes
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    # Inventario
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    # Cotizaciones (con tasas duales)
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    # Configuración
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # Reparación de columnas por si acaso
    columnas = [('monto_bcv', 'REAL'), ('monto_binance', 'REAL')]
    for col, tipo in columnas:
        try: c.execute(f'ALTER TABLE cotizaciones ADD COLUMN {col} {tipo}')
        except: pass
        
    # Valores iniciales de inflación
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

# --- 2. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico OS", layout="wide")
inicializar_sistema()

if 'login' not in st.session_state: st.session_state.login = False

# --- 3. LOGIN DE SEGURIDAD ---
if not st.session_state.login:
    st.title("🔐 Acceso Master - Imperio Atómico")
    col_log, _ = st.columns([1, 2])
    with col_log:
        u = st.text_input("Usuario")
        p = st.text_input("Clave", type="password")
        if st.button("Entrar al Sistema"):
            if u == "admin" and p == "1234":
                st.session_state.login = True
                st.rerun()
            else:
                st.error("Credenciales Incorrectas")
    st.stop()

# --- 4. CARGA DE DATOS PARA EL DASHBOARD ---
conn = conectar()
conf = pd.read_sql_query("SELECT * FROM configuracion", conn).set_index('parametro')
t_bcv = conf.loc['tasa_bcv', 'valor']
t_bin = conf.loc['tasa_binance', 'valor']
df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 5. INTERFAZ PRINCIPAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.metric("🏦 Tasa BCV", f"{t_bcv} Bs")
    st.metric("🔶 Tasa Binance", f"{t_bin} Bs")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📝 Cotizaciones", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.login = False
        st.rerun()

# --- 6. LÓGICA DEL DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen de Operaciones")
    
    # KPIs Superiores
    kpi1, kpi2, kpi3 = st.columns(3)
    
    total_pagado = df_cots[df_cots['estado'] == 'Pagado']['monto_usd'].sum() if not df_cots.empty else 0
    total_pendiente = df_cots[df_cots['estado'] == 'Pendiente']['monto_usd'].sum() if not df_cots.empty else 0
    valor_stock = (df_inv['cantidad'] * df_inv['precio_usd']).sum() if not df_inv.empty else 0
    
    kpi1.metric("Ventas Pagadas (USD)", f"$ {total_pagado:,.2f}")
    kpi2.metric("Cuentas por Cobrar (USD)", f"$ {total_pendiente:,.2f}", delta_color="inverse")
    kpi3.metric("Valor en Stock (USD)", f"$ {valor_stock:,.2f}")
    
    st.divider()
    
    # Equivalencias en Bolívares
    st.subheader("🏦 Conversión de Caja")
    c_bcv, c_bin = st.columns(2)
    with c_bcv:
        st.info(f"**Total Pagado en BCV:**\n### {(total_pagado * t_bcv):,.2f} Bs")
    with c_bin:
        st.warning(f"**Total Pagado en Binance:**\n### {(total_pagado * t_bin):,.2f} Bs")

    st.divider()
    st.subheader("📋 Últimos Trabajos")
    if not df_cots.empty:
        st.dataframe(df_cots.tail(5), use_container_width=True)
    else:
        st.write("No hay datos para mostrar.")

# --- ESPACIO PARA LAS SIGUIENTES PARTES ---
else:
    st.info(f"Módulo **{menu}** en proceso de carga. Por favor, solicita la siguiente parte del código.")
