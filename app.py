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

# --- 4. LÓGICA DE INVENTARIO (CON COSTO POR UNIDAD) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario con Desglose por Unidad")
    
    with st.expander("📥 Registrar Nueva Compra"):
        with st.form("form_inv_unidad"):
            col_info, col_tasa, col_imp = st.columns([2, 1, 1])
            
            with col_info:
                it_nombre = st.text_input("Nombre del Producto (Ej: Resma Bond A4)")
                it_cant = st.number_input("Cantidad que trae el paquete (Ej: 500)", min_value=0.01, step=1.0)
                it_unid = st.selectbox("Unidad de medida", ["Hojas", "ml", "Unidad", "Mts", "Resma"])
                precio_paquete_usd = st.number_input("Precio del PAQUETE Completo (USD Limpio)", min_value=0.0, format="%.2f")

            with col_tasa:
                st.markdown("### 💱 Tasa de Compra")
                tipo_tasa = st.radio("Comprado a tasa:", ["Binance", "BCV", "Manual"])
                if tipo_tasa == "Binance": tasa_aplicada = t_bin
                elif tipo_tasa == "BCV": tasa_aplicada = t_bcv
                else: tasa_aplicada = st.number_input("Tasa Especial", value=t_bin)
                st.caption(f"Valor: {tasa_aplicada} Bs")

            with col_imp:
                st.markdown("### 🧾 Impuestos")
                pago_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                pago_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)
                pago_banco = st.checkbox(f"Banco ({banco*100}%)", value=False)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre and it_cant > 0:
                    # Cálculo de impuestos de la compra
                    imp_total = 0
                    if pago_iva: imp_total += iva
                    if pago_gtf: imp_total += igtf
                    if pago_banco: imp_total += banco
                    
                    # Costo total del paquete con impuestos
                    costo_paquete_real_usd = precio_paquete_usd * (1 + imp_total)
                    
                    # GUARDAMOS: El precio_usd en la base de datos será el costo por unidad
                    # Para que sea más fácil cotizar luego.
                    costo_unitario_usd = costo_paquete_real_usd / it_cant
                    
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", 
                              (it_nombre, it_cant, it_unid, costo_unitario_usd))
                    c.commit(); c.close()
                    
                    st.success(f"✅ ¡Listo! Cada {it_unid[:-1]} de {it_nombre} te sale en ${costo_unitario_usd:.4f}")
                    st.rerun()

    st.divider()

    # --- TABLA DE INVENTARIO CON DESGLOSE ---
    if not df_inv.empty:
        st.subheader("📋 Tu Stock y Costos Unitarios")
        
        # Preparar tabla para mostrar
        df_ver = df_inv.copy()
        df_ver.columns = ['Producto', 'Cantidad Stock', 'Unidad', 'Costo Unitario (USD)']
        
        # Cálculos de valorización para la tabla
        df_ver['Inversión Total (USD)'] = df_ver['Cantidad Stock'] * df_ver['Costo Unitario (USD)']
        df_ver['Costo Unitario (BCV)'] = df_ver['Costo Unitario (USD)'] * t_bcv
        df_ver['Costo Unitario (BIN)'] = df_ver['Costo Unitario (USD)'] * t_bin
        
        # Reordenar para que lo primero sea el costo por unidad
        columnas_orden = ['Producto', 'Costo Unitario (USD)', 'Costo Unitario (BCV)', 'Costo Unitario (BIN)', 'Cantidad Stock', 'Unidad', 'Inversión Total (USD)']
        
        st.dataframe(df_ver[columnas_orden].style.format({
            'Costo Unitario (USD)': '{:.4f}',
            'Costo Unitario (BCV)': '{:.2f} Bs',
            'Costo Unitario (BIN)': '{:.2f} Bs',
            'Inversión Total (USD)': '{:.2f}'
        }), use_container_width=True, hide_index=True)
        
        st.info("💡 **Dato maestro:** El 'Costo Unitario' ya incluye los impuestos y la tasa que seleccionaste al comprar.")
    else:
        st.info("Inventario vacío. Carga un paquete para ver el desglose por unidad.")
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





