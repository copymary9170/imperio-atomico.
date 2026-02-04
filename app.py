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

# --- 4. LÓGICA DE INVENTARIO (CON EDICIÓN Y CLARIDAD DE COSTOS) ---
if menu == "📦 Inventario":
    st.title("📦 Inventario y Auditoría de Costos")
    
    with st.expander("📥 Registrar Nueva Compra (Paquetes/Lotes)"):
        with st.form("form_inv_final_v2"):
            col_info, col_tasa, col_imp = st.columns([2, 1, 1])
            
            with col_info:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("¿Cuántas unidades trae el lote?", min_value=1.0, value=500.0)
                it_unid = st.selectbox("Unidad de medida", ["Hojas", "ml", "Unidad", "Resma"])
                precio_lote_usd = st.number_input("Precio TOTAL que pagaste por el lote (USD)", min_value=0.0, format="%.2f")

            with col_tasa:
                st.markdown("### 💱 Tasa")
                tipo_tasa = st.radio("Tasa de compra:", ["Binance", "BCV", "Manual"])
                if tipo_tasa == "Binance": tasa_aplicada = t_bin
                elif tipo_tasa == "BCV": tasa_aplicada = t_bcv
                else: tasa_aplicada = st.number_input("Tasa Manual", value=t_bin)

            with col_imp:
                st.markdown("### 🧾 Impuestos")
                pago_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                pago_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)
                pago_banco = st.checkbox(f"Banco ({banco*100}%)", value=False)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre:
                    # Calculamos impuestos sobre el total del lote
                    imp_total = (iva if pago_iva else 0) + (igtf if pago_gtf else 0) + (banco if pago_banco else 0)
                    costo_lote_con_impuestos = precio_lote_usd * (1 + imp_total)
                    
                    # El costo unitario es ese total dividido entre las unidades que trae
                    costo_unit_usd = costo_lote_con_impuestos / it_cant
                    
                    c = conectar()
                    # Guardamos el costo unitario para las cotizaciones
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", 
                              (it_nombre, it_cant, it_unid, costo_unit_usd))
                    c.commit(); c.close()
                    st.success(f"✅ Guardado: {it_nombre}. Costo por {it_unid}: ${costo_unit_usd:.4f}")
                    st.rerun()

    st.divider()

    # --- TABLA DE VISUALIZACIÓN Y MODIFICACIÓN ---
    if not df_inv.empty:
        st.subheader("📋 Control de Existencias")
        
        moneda = st.radio("Ver precios en:", ["USD", "BCV", "Binance"], horizontal=True)
        
        # Preparamos los datos para que sean fáciles de entender
        df_audit = df_inv.copy()
        df_audit.columns = ['Producto', 'Stock Actual', 'Unidad', 'Costo Unitario']
        
        factor = 1.0
        simbolo = "$"
        if moneda == "BCV": factor, simbolo = t_bcv, "Bs"
        elif moneda == "Binance": factor, simbolo = t_bin, "Bs"

        df_audit['Costo Unit.'] = df_audit['Costo Unitario'] * factor
        df_audit['Inversión Stock'] = (df_audit['Stock Actual'] * df_audit['Costo Unitario']) * factor
        
        # Mostramos la tabla principal
        st.dataframe(df_audit[['Producto', 'Stock Actual', 'Unidad', 'Costo Unit.', 'Inversión Stock']].style.format({
            'Costo Unit.': f"{simbolo} {{:.4f}}",
            'Inversión Stock': f"{simbolo} {{:.2f}}"
        }), use_container_width=True, hide_index=True)

        # --- SECCIÓN DE ELIMINACIÓN (Para corregir errores) ---
        st.divider()
        with st.expander("🗑️ Borrar o Corregir Insumos"):
            prod_a_borrar = st.selectbox("Selecciona el producto con error:", df_inv['item'].tolist())
            if st.button("❌ Eliminar Producto"):
                c = conectar()
                c.execute("DELETE FROM inventario WHERE item=?", (prod_a_borrar,))
                c.commit(); c.close()
                st.warning(f"Producto {prod_a_borrar} eliminado.")
                st.rerun()
    else:
        st.info("Inventario vacío.")
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







