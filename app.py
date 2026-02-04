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
    
    # Parámetros base e impuestos
    params = [('tasa_bcv', 36.50), ('tasa_binance', 42.00), ('iva_perc', 0.16), 
              ('igtf_perc', 0.03), ('banco_perc', 0.02), ('costo_tinta_ml', 0.05)]
    for p, v in params:
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (p, v))
    conn.commit()
    conn.close()

# --- 2. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Imperio Atómico - Sistema Pro", layout="wide")
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
df_cots_global = pd.read_sql_query("SELECT * FROM cotizaciones", conn)
conn.close()

# --- 3. MENÚ LATERAL ---
with st.sidebar:
    st.header("⚛️ Imperio Atómico")
    st.info(f"🏦 BCV: {t_bcv} | 🔶 BIN: {t_bin}")
    menu = st.radio("Módulos", ["📦 Inventario", "📝 Cotizaciones", "📊 Dashboard", "⚙️ Configuración"])

# --- 4. LÓGICA DE INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Inventario y Auditoría")
    
    with st.expander("📥 Registrar Nueva Compra (Paquetes/Lotes)"):
        with st.form("form_inv"):
            col_info, col_tasa, col_imp = st.columns([2, 1, 1])
            with col_info:
                it_nombre = st.text_input("Nombre del Producto")
                it_cant = st.number_input("¿Unidades que trae el lote?", min_value=1, value=500, step=1)
                it_unid = st.selectbox("Unidad", ["Hojas", "ml", "Unidad", "Resma"])
                precio_lote_usd = st.number_input("Precio TOTAL Lote (USD)", min_value=0.0, format="%.2f")
            with col_tasa:
                st.markdown("### 💱 Tasa")
                tipo_t = st.radio("Tasa de compra:", ["Binance", "BCV"])
                tasa_a = t_bin if tipo_t == "Binance" else t_bcv
            with col_imp:
                st.markdown("### 🧾 Impuestos")
                p_iva = st.checkbox(f"IVA ({iva*100}%)", value=True)
                p_gtf = st.checkbox(f"GTF ({igtf*100}%)", value=True)

            if st.form_submit_button("🚀 Cargar a Inventario"):
                if it_nombre:
                    imp = (iva if p_iva else 0) + (igtf if p_gtf else 0)
                    costo_u = (precio_lote_usd * (1 + imp)) / it_cant
                    c = conectar()
                    c.execute("INSERT OR REPLACE INTO inventario VALUES (?,?,?,?)", (it_nombre, float(it_cant), it_unid, costo_u))
                    c.commit(); c.close()
                    st.success(f"✅ Guardado: {it_nombre}")
                    st.rerun()

    st.divider()
    if not df_inv.empty:
        moneda = st.radio("Ver precios en:", ["USD", "BCV", "Binance"], horizontal=True)
        df_audit = df_inv.copy()
        df_audit.columns = ['Producto', 'Stock', 'Unidad', 'Costo Unitario']
        f = t_bcv if moneda == "BCV" else (t_bin if moneda == "Binance" else 1.0)
        sim = "Bs" if moneda != "USD" else "$"
        
        df_audit['Costo Unit.'] = df_audit['Costo Unitario'] * f
        df_audit['Inversión'] = (df_audit['Stock'] * df_audit['Costo Unitario']) * f
        
        st.dataframe(df_audit[['Producto', 'Stock', 'Unidad', 'Costo Unit.', 'Inversión']].style.format({
            'Stock': '{:,.0f}', 'Costo Unit.': f"{sim} {{:.4f}}", 'Inversión': f"{sim} {{:.2f}}"
        }), use_container_width=True, hide_index=True)
        
        with st.expander("🗑️ Borrar Insumo"):
            prod_b = st.selectbox("Producto a eliminar:", df_inv['item'].tolist())
            if st.button("❌ Eliminar"):
                c = conectar(); c.execute("DELETE FROM inventario WHERE item=?", (prod_b,))
                c.commit(); c.close(); st.rerun()

# --- 5. LÓGICA DE COTIZACIONES ---
elif menu == "📝 Cotizaciones":
    st.title("📝 Generador de Cotizaciones")
    c = conectar()
    clis = pd.read_sql_query("SELECT nombre FROM clientes", c)['nombre'].tolist()
    inv_list = pd.read_sql_query("SELECT item, precio_usd FROM inventario", c)
    c.close()

    with st.form("form_cot"):
        c1, c2 = st.columns(2)
        cli = c1.selectbox("Cliente", ["--"] + clis)
        trab = c1.text_input("Descripción del trabajo")
        mat = c2.selectbox("Material a descontar", ["--"] + inv_list['item'].tolist())
        cant_m = c2.number_input("Cantidad a usar", min_value=0, step=1)
        
        monto_f = st.number_input("Precio Final (USD)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("📋 Guardar Cotización"):
            if cli != "--" and monto_f > 0:
                c = conectar()
                c.execute("INSERT INTO cotizaciones (fecha, cliente, trabajo, monto_usd, monto_bcv, monto_binance, estado) VALUES (?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%d/%m/%Y"), cli, trab, monto_f, monto_f*t_bcv, monto_f*t_bin, "Pagado"))
                if mat != "--":
                    c.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE item = ?", (cant_m, mat))
                c.commit(); c.close(); st.success("✅ Cotización registrada"); st.rerun()

    st.subheader("📑 Historial")
    st.dataframe(df_cots_global.sort_values('id', ascending=False), use_container_width=True)

# --- 6. DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    if not df_cots_global.empty:
        col1, col2 = st.columns(2)
        total_usd = df_cots_global['monto_usd'].sum()
        col1.metric("Ingresos Totales", f"$ {total_usd:.2f}")
        col2.metric("Total en Bs (BCV)", f"{total_usd * t_bcv:.2f} Bs")
        
        st.subheader("📈 Ventas por Fecha")
        # Agrupar ventas por fecha para la gráfica
        df_grafica = df_cots_global.groupby('fecha')['monto_usd'].sum()
        st.line_chart(df_grafica)
    else:
        st.info("Aún no hay ventas registradas para mostrar estadísticas.")

# --- 7. CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración de Tasas")
    with st.form("f_config"):
        c1, c2 = st.columns(2)
        n_bcv = c1.number_input("Tasa BCV", value=t_bcv)
        n_bin = c2.number_input("Tasa Binance", value=t_bin)
        if st.form_submit_button("💾 Guardar Cambios Globales"):
            c = conectar()
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_bcv'", (n_bcv,))
            c.execute("UPDATE configuracion SET valor=? WHERE parametro='tasa_binance'", (n_bin,))
            c.commit(); c.close(); st.success("✅ Tasas actualizadas"); st.rerun()
