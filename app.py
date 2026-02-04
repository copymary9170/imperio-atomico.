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

# --- 4. LÓGICA DE INVENTARIO (CON SELECTOR DE MONEDA Y UNIDADES) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario Profesional")
    
    with st.expander("📥 Registrar Nueva Compra (Paquetes/Lotes)"):
        with st.form("form_inv_final"):
            col_info, col_tasa, col_imp = st.columns([2, 1, 1])
            
            with col_info:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("Cantidad que trae el lote (Ej: 500)", min_value=0.01)
                it_unid = st.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Mts"])
                precio_lote_usd = st.number_input("Precio del LOTE Completo (USD)", min_value=0.0, format="%.2f")

            with col_tasa:
                st.markdown("### 💱 Tasa de Compra")
                tipo_tasa = st.radio("Comprado a tasa:", ["Binance", "BCV", "Manual"])
                if tipo_tasa == "Binance": tasa_aplicada = t_bin
                elif tipo_tasa == "BCV": tasa_aplicada = t_bcv
                else: tasa_aplicada = st.number_input("Tasa Especial", value=t_bin)

            with col_imp:
                st.markdown("### 🧾 Impuestos")
                pago_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                pago_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)
                pago_banco = st.checkbox(f"Banco ({banco*100}%)", value=False)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre and it_cant > 0:
                    # Cálculo de impuestos
                    imp_total = (iva if pago_iva else 0) + (igtf if pago_gtf else 0) + (banco if pago_banco else 0)
                    costo_lote_real = precio_lote_usd * (1 + imp_total)
                    costo_unit_usd = costo_lote_real / it_cant
                    
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", 
                              (it_nombre, it_cant, it_unid, costo_unit_usd))
                    c.commit(); c.close()
                    st.success(f"✅ ¡Guardado! Costo unitario: ${costo_unit_usd:.4f}")
                    st.rerun()

    st.divider()

    # --- TABLA DINÁMICA CON SELECTOR ---
    if not df_inv.empty:
        st.subheader("📋 Visualización de Stock")
        
        # El selector que tanto te gustaba (Actualizado a st.radio horizontal o segmented_control)
        moneda = st.radio("Ver inventario en:", ["USD", "BCV", "Binance"], horizontal=True)
        
        df_display = df_inv.copy()
        df_display.columns = ['Producto', 'Stock', 'Unidad', 'Costo Unit']

        # Aplicar conversión según la moneda elegida
        if moneda == "BCV":
            df_display['Costo Unit'] = df_display['Costo Unit'] * t_bcv
            df_display['Inversión Total'] = df_display['Stock'] * df_display['Costo Unit']
            formato = "{:.2f} Bs"
        elif moneda == "Binance":
            df_display['Costo Unit'] = df_display['Costo Unit'] * t_bin
            df_display['Inversión Total'] = df_display['Stock'] * df_display['Costo Unit']
            formato = "{:.2f} Bs"
        else:
            df_display['Inversión Total'] = df_display['Stock'] * df_display['Costo Unit']
            formato = "${:.4f}"

        # Mostrar tabla formateada
        st.dataframe(df_display.style.format({
            'Costo Unit': formato,
            'Inversión Total': "{:.2f}"
        }), use_container_width=True, hide_index=True)
        
        # Métricas de resumen rápidas
        st.divider()
        total_usd = (df_inv['cantidad'] * df_inv['precio_usd']).sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor Total (USD)", f"$ {total_usd:,.2f}")
        c2.metric("Valor en BCV", f"{total_usd * t_bcv:,.2f} Bs")
        c3.metric("Valor en Binance", f"{total_usd * t_bin:,.2f} Bs")
    else:
        st.info("No hay nada en el inventario. ¡Empieza a cargar tus tesoros!")
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






