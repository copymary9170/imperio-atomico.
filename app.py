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
    
    # Parámetros Base
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_bcv', 36.50)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('tasa_binance', 42.00)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('iva_perc', 0.16)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('igtf_perc', 0.03)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('banco_perc', 0.02)")
    c.execute("INSERT OR IGNORE INTO configuracion VALUES ('costo_tinta_ml', 0.05)")
    conn.commit()
    conn.close()

# --- 2. INICIO ---
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
iva = conf.loc['iva_perc', 'valor']
igtf = conf.loc['igtf_perc', 'valor']
banco = conf.loc['banco_perc', 'valor']
df_cots = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.success(f"🏦 BCV: {t_bcv} Bs")
    st.warning(f"🔶 BIN: {t_bin} Bs")
    st.divider()
    menu = st.radio("Módulos", ["📊 Dashboard", "👥 Clientes", "📦 Inventario", "📝 Cotizaciones", "⚙️ Configuración"])
    if st.button("🚪 Salir"):
        st.session_state.login = False
        st.rerun()

# --- 4. DASHBOARD (REPARADO Y COMPLETO) ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen Financiero")
    
    # Métricas en USD
    k1, k2, k3 = st.columns(3)
    pagado = df_cots[df_cots['estado'] == 'Pagado']['monto_usd'].sum() if not df_cots.empty else 0
    pendiente = df_cots[df_cots['estado'] == 'Pendiente']['monto_usd'].sum() if not df_cots.empty else 0
    
    # Inversión de stock con todos los impuestos
    factor_rep = 1 + iva + igtf + banco
    inv_total = (df_inv['cantidad'] * (df_inv['precio_usd'] * factor_rep)).sum() if not df_inv.empty else 0
    
    k1.metric("Ingresos Reales (USD)", f"$ {pagado:,.2f}")
    k2.metric("Cuentas por Cobrar (USD)", f"$ {pendiente:,.2f}")
    k3.metric("Stock Reposición (USD)", f"$ {inv_total:,.2f}")
    
    st.divider()
    
    # Conversión de Caja (Lo que tienes en mano)
    st.subheader("💰 Tu Caja en Bolívares")
    c_bcv, c_bin = st.columns(2)
    with c_bcv:
        st.info(f"🏦 **Total en BCV:**\n### {(pagado * t_bcv):,.2f} Bs")
    with c_bin:
        st.warning(f"🔶 **Total en Binance:**\n### {(pagado * t_bin):,.2f} Bs")

# --- 5. MÓDULO CLIENTES ---
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

# --- 6. MÓDULO INVENTARIO (CON IMPUESTOS) ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario y Costos de Reposición")
    with st.expander("📥 Cargar Stock"):
        with st.form("finv"):
            it = st.text_input("Producto")
            ca = st.number_input("Cantidad", min_value=0.0)
            pr = st.number_input("Precio Costo USD (Base)", min_value=0.0, format="%.2f")
            if st.form_submit_button("Guardar"):
                c = conectar(); c.execute("INSERT OR REPLACE INTO inventario (item, cantidad, unidad, precio_usd) VALUES (?,?,?,?)", (it, ca, 'Unid', pr)); c.commit(); c.close()
                st.rerun()

    if not df_inv.empty:
        df_res = df_inv.copy()
        df_res['Costo Reposición (USD)'] = df_res['precio_usd'] * factor_rep
        df_res['Total Stock (USD)'] = df_res['cantidad'] * df_res['Costo Reposición (USD)']
        st.dataframe(df_res, use_container_width=True)
        st.info(f"**Nota:** El Costo de Reposición incluye {iva*100}% IVA, {igtf*100}% GTF y {banco*100}% Banco.")

# --- 7. CONFIGURACIÓN (PARA MODIFICAR IMPUESTOS) ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes de Tasas e Impuestos")
    st.write("Aquí puedes actualizar los valores para que el sistema se ajuste a la inflación.")
    with st.form("f_conf"):
        col1, col2 = st.columns(2)
        new_bcv = col1.number_input("Tasa BCV", value=t_bcv)
        new_bin = col1.number_input("Tasa Binance", value=t_bin)
        new_iva = col2.number_input("Porcentaje IVA (0.16 = 16%)", value=iva, format="%.2f")
        new_igtf = col2.number_input("Porcentaje GTF (0.03 = 3%)", value=igtf, format="%.2f")
        new_banco = col2.number_input("Comisión Banco (0.02 = 2%)", value=banco, format="%.2f")
        
        if st.form_submit_button("💾 Guardar Cambios Globales"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (new_bcv,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (new_bin,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='iva_perc'", (new_iva,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='igtf_perc'", (new_igtf,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='banco_perc'", (new_banco,))
            c.commit(); c.close()
            st.success("✅ Sistema actualizado correctamente.")
            st.rerun()

# --- ESPACIO PARA COTIZACIONES ---
else:
    st.info("
