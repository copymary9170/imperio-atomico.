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

# --- 4. LÓGICA DE INVENTARIO (SELECTOR AUTOMÁTICO DE TASAS) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario Inteligente")
    
    with st.expander("📥 Registrar Nueva Compra"):
        with st.form("form_inv_auto"):
            col_info, col_tasa, col_imp = st.columns([2, 1, 1])
            
            with col_info:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("Cantidad", min_value=0.0, step=1.0)
                it_unid = st.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Resma"])
                precio_base_usd = st.number_input("Precio Unitario (USD Limpio)", min_value=0.0, format="%.2f")

            with col_tasa:
                st.markdown("### 💱 Tasa de Compra")
                tipo_tasa = st.radio("Usar tasa de:", ["Binance", "BCV", "Manual"])
                
                # Lógica automática según la configuración
                if tipo_tasa == "Binance":
                    tasa_aplicada = t_bin
                    st.caption(f"Valor actual: {t_bin} Bs")
                elif tipo_tasa == "BCV":
                    tasa_aplicada = t_bcv
                    st.caption(f"Valor actual: {t_bcv} Bs")
                else:
                    tasa_aplicada = st.number_input("Tasa Personalizada", value=t_bin)

            with col_imp:
                st.markdown("### 🧾 Impuestos")
                pago_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                pago_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)
                pago_banco = st.checkbox(f"Banco ({banco*100}%)", value=False)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre:
                    # Cálculo de impuestos seleccionados
                    imp_total = 0
                    if pago_iva: imp_total += iva
                    if pago_gtf: imp_total += igtf
                    if pago_banco: imp_total += banco
                    
                    # El costo real en USD incluyendo los impuestos de la compra
                    costo_real_usd = precio_base_usd * (1 + imp_total)
                    # Solo para tu información en el momento (Costo en Bolívares)
                    costo_en_bs = costo_real_usd * tasa_aplicada
                    
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", 
                              (it_nombre, it_cant, it_unid, costo_real_usd))
                    c.commit(); c.close()
                    
                    st.success(f"✅ Registrado. Costo real: ${costo_real_usd:.2f} (Pagado a {tasa_aplicada} Bs)")
                    st.rerun()

    st.divider()

    # --- TABLA DE INVENTARIO ---
    if not df_inv.empty:
        st.subheader("📋 Tu Mercancía")
        
        # Selector de visualización: ¿En qué moneda quieres ver tu inventario hoy?
        moneda_ver = st.segmented_control("Ver totales en:", ["USD", "BCV", "Binance"], default="USD")
        
        df_ver = df_inv.copy()
        if moneda_ver == "BCV":
            df_ver['Total (Bs)'] = df_ver['cantidad'] * df_ver['precio_usd'] * t_bcv
            col_ver = 'Total (Bs)'
        elif moneda_ver == "Binance":
            df_ver['Total (Bs)'] = df_ver['cantidad'] * df_ver['precio_usd'] * t_bin
            col_ver = 'Total (Bs)'
        else:
            df_ver['Total (USD)'] = df_ver['cantidad'] * df_ver['precio_usd']
            col_ver = 'Total (USD)'

        st.dataframe(df_ver, use_container_width=True, hide_index=True)
    else:
        st.info("Inventario vacío. ¡Carga tu primer material!")
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




