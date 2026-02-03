import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_data.db', check_same_thread=False)

def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (item TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, precio_usd REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente TEXT, trabajo TEXT, monto_usd REAL, monto_bcv REAL, monto_binance REAL, estado TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    
    # Parámetros base e impuestos (Aseguramos que existan)
    params = [('tasa_bcv', 36.50), ('tasa_binance', 42.00), ('iva_perc', 0.16), 
              ('igtf_perc', 0.03), ('banco_perc', 0.02), ('costo_tinta_ml', 0.05)]
    for p, v in params:
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
    conn.commit()
    conn.close()

# --- 2. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Imperio Atómico - Inventario Pro", layout="wide")
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
df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
conn.close()

# --- 3. MENÚ ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📦 Inventario", "📊 Dashboard", "⚙️ Configuración"])

# --- 4. LÓGICA DE INVENTARIO (DETALLADO CON TASA DE COMPRA) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario y Costos de Adquisición")
    
    with st.expander("📥 Registrar Compra de Material"):
        with st.form("form_inventario_pro"):
            c1, c2, c3 = st.columns(3)
            
            # Datos básicos
            it_nombre = c1.text_input("Nombre del Producto")
            it_cant = c1.number_input("Cantidad Comprada", min_value=0.0, step=1.0)
            it_unid = c1.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Resma"])
            
            # Datos de la Compra (Tasa)
            precio_base_usd = c2.number_input("Precio Unitario (USD Limpio)", min_value=0.0, format="%.2f")
            tasa_compra = c2.number_input("Tasa de Cambio aplicada (Bs/$)", value=t_bin, format="%.2f")
            
            # Impuestos Pagados en la compra
            st.markdown("### Impuestos Pagados en esta compra:")
            pago_iva = c3.checkbox(f"IVA ({iva*100}%)", value=True)
            pago_gtf = c3.checkbox(f"GTF ({igtf*100}%)", value=True)
            pago_banco = c3.checkbox(f"Comisión Banco ({banco*100}%)", value=False)
            
            if st.form_submit_button("💾 Registrar Entrada"):
                if it_nombre:
                    # Calcular el costo real de esta compra específica
                    impuestos_totales = 0
                    if pago_iva: impuestos_totales += iva
                    if pago_gtf: impuestos_totales += igtf
                    if pago_banco: impuestos_totales += banco
                    
                    costo_real_usd = precio_base_usd * (1 + impuestos_totales)
                    costo_real_bs = costo_real_usd * tasa_compra
                    
                    c = conectar()
                    # Guardamos el precio_usd como el costo real ya con sus impuestos de compra
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", 
                              (it_nombre, it_cant, it_unid, costo_real_usd))
                    c.commit(); c.close()
                    
                    st.success(f"✅ Registrado: {it_nombre}")
                    st.info(f"Costo Real: ${costo_real_usd:.2f} | Tasa: {tasa_compra} Bs")
                    st.rerun()

    st.divider()

    # Tabla de Existencias
    if not df_inv.empty:
        df_calc = df_inv.copy()
        
        # Ahora el 'precio_usd' en la DB ya es el costo real con impuestos de compra
        df_calc['Costo Unitario (USD)'] = df_calc['precio_usd']
        df_calc['Total en Bolívares (Tasa Hoy)'] = df_calc['cantidad'] * df_calc['precio_usd'] * t_bin
        df_calc['Inversión Total (USD)'] = df_calc['cantidad'] * df_calc['precio_usd']
        
        st.subheader("📋 Inventario Actualizado")
        st.dataframe(df_calc[['item', 'cantidad', 'unidad', 'Costo Unitario (USD)', 'Inversión Total (USD)', 'Total en Bolívares (Tasa Hoy)']], 
                     use_container_width=True, hide_index=True)
        
        # Resumen de Valor de Reposición (Usando tasas actuales de configuración)
        st.divider()
        st.subheader("🔄 Valor de Reposición (Precios de Hoy)")
        r1, r2, r3 = st.columns(3)
        total_inv_usd = df_calc['Inversión Total (USD)'].sum()
        
        r1.metric("Inversión en Stock", f"$ {total_inv_usd:,.2f}")
        r2.metric("Valor a Tasa BCV", f"{total_inv_usd * t_bcv:,.2f} Bs")
        r3.metric("Valor a Tasa Binance", f"{total_inv_usd * t_bin:,.2f} Bs")
    else:
        st.info("No hay productos en inventario.")

# ... (El resto de los elif se mantienen igual)
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración de Tasas e Impuestos")
    with st.form("f_config"):
        c1, c2 = st.columns(2)
        n_bcv = c1.number_input("Tasa BCV", value=t_bcv)
        n_bin = c1.number_input("Tasa Binance", value=t_bin)
        n_iva = c2.number_input("IVA (0.16 = 16%)", value=iva)
        n_igtf = c2.number_input("GTF (0.03 = 3%)", value=igtf)
        n_banco = c2.number_input("Banco (0.02 = 2%)", value=banco)
        
        if st.form_submit_button("Guardar Cambios"):
            c = conectar()
            for p, v in [('tasa_bcv', n_bcv), ('tasa_binance', n_bin), ('iva_perc', n_iva), 
                         ('igtf_perc', n_igtf), ('banco_perc', n_banco)]:
                c.execute("UPDATE configuracion SET valor=? WHERE parametro=?", (v, p))
            c.commit(); c.close(); st.rerun()

else:
    st.info("Módulo en construcción (Próxima parte).")



