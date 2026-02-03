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

# --- 7. MÓDULO CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    
    # Formulario de registro
    with st.expander("➕ Registrar Nuevo Cliente"):
        with st.form("form_cliente"):
            nom = st.text_input("Nombre Completo")
            wha = st.text_input("WhatsApp (Ej: +58412...)")
            if st.form_submit_button("Guardar Cliente"):
                if nom:
                    c = conectar()
                    c.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nom, wha))
                    c.commit(); c.close()
                    st.success(f"✅ {nom} registrado con éxito.")
                    st.rerun()
                else:
                    st.error("El nombre es obligatorio.")

    st.divider()
    
    # Buscador dinámico
    bus = st.text_input("🔍 Buscar cliente por nombre...")
    c = conectar()
    query = f"SELECT id as ID, nombre as Nombre, whatsapp as WhatsApp FROM clientes WHERE nombre LIKE '%{bus}%' ORDER BY id DESC"
    df_busqueda = pd.read_sql_query(query, c)
    c.close()
    
    if not df_busqueda.empty:
        st.dataframe(df_busqueda, use_container_width=True, hide_index=True)
    else:
        st.info("No se encontraron clientes con ese nombre.")

# --- 8. MÓDULO INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Inventario de Materiales")
    
    # Formulario de carga
    with st.expander("📥 Cargar / Actualizar Stock"):
        with st.form("form_inv"):
            col_a, col_b = st.columns(2)
            item_name = col_a.text_input("Nombre del Insumo (Papel, Tinta, etc.)")
            cantidad = col_a.number_input("Cantidad actual", min_value=0.0, step=1.0)
            unidad = col_b.selectbox("Unidad", ["Hojas", "ml", "Unidades", "Mts", "Resmas"])
            precio_u = col_b.number_input("Precio Costo USD (Unidad)", min_value=0.0, format="%.2f")
            
            if st.form_submit_button("💾 Actualizar Inventario"):
                if item_name:
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (item_name, cantidad, unidad, precio_u))
                    c.commit(); c.close()
                    st.success(f"✅ Stock de {item_name} actualizado.")
                    st.rerun()

    st.divider()

    # Visualización y Valorización
    if not df_inv.empty:
        # Creamos una copia para mostrar cálculos sin alterar la DB
        df_display = df_inv.copy()
        df_display['Inversión USD'] = df_display['cantidad'] * df_display['precio_usd']
        df_display['Valor BCV'] = df_display['Inversión USD'] * t_bcv
        df_display['Valor BIN'] = df_display['Inversión USD'] * t_bin
        
        st.subheader("📋 Resumen de Existencias")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Totales de inventario
        st.divider()
        t1, t2, t3 = st.columns(3)
        total_usd = df_display['Inversión USD'].sum()
        t1.metric("Total Invertido (USD)", f"$ {total_usd:,.2f}")
        t2.info(f"🏦 Valor BCV: {total_usd * t_bcv:,.2f} Bs")
        t3.warning(f"🔶 Valor Binance: {total_usd * t_bin:,.2f} Bs")
    else:
        st.info("Aún no tienes productos en inventario.")

# --- MÓDULOS RESTANTES (PARTE 3) ---
else:
    st.info(f"Módulo **{menu}** pendiente por cargar en la siguiente parte.")
