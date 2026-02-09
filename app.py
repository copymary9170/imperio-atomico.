import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime
from PIL import Image
import numpy as np
import io

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Imperio Atómico - ERP Pro", layout="wide")
# --- 2. MOTOR DE BASE DE DATOS ---
def conectar():
    return sqlite3.connect('imperio_v2.db', check_same_thread=False)
def inicializar_sistema():
    conn = conectar()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    c.execute('CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, whatsapp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, cantidad REAL, unidad TEXT, precio_usd REAL, minimo REAL DEFAULT 5.0)')
    c.execute('CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS activos (id INTEGER PRIMARY KEY AUTOINCREMENT, equipo TEXT, categoria TEXT, inversion REAL, unidad TEXT, desgaste REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, rol TEXT, nombre TEXT)')

    c.execute('CREATE TABLE IF NOT EXISTS inventario_movs (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, tipo TEXT, cantidad REAL, motivo TEXT, usuario TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, monto_total REAL, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS gastos (id INTEGER PRIMARY KEY AUTOINCREMENT, descripcion TEXT, monto REAL, categoria TEXT, metodo TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)')

    c.execute("""
    CREATE TRIGGER IF NOT EXISTS prevent_negative_stock
    BEFORE UPDATE ON inventario
    FOR EACH ROW
    BEGIN
        SELECT CASE
            WHEN NEW.cantidad < 0 THEN
                RAISE(ABORT, 'Error: Stock insuficiente.')
        END;
    END;
    """)

    c.execute("SELECT COUNT(*) FROM usuarios")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO usuarios VALUES (?,?,?,?)", [
            ('jefa', 'atomica2026', 'Admin', 'Dueña del Imperio'),
            ('mama', 'admin2026', 'Administracion', 'Mamá'),
            ('pro', 'diseno2026', 'Produccion', 'Hermana')
        ])

    config_init = [
        ('tasa_bcv', 36.50), ('tasa_binance', 38.00),
        ('iva_perc', 0.16), ('igtf_perc', 0.03),
        ('banco_perc', 0.02), ('costo_tinta_ml', 0.10)
    ]

    for param, valor in config_init:
        c.execute("INSERT OR IGNORE INTO configuracion VALUES (?,?)", (param, valor))

    conn.commit()
    conn.close()
def obtener_tintas_disponibles():
    if 'df_inv' not in st.session_state or st.session_state.df_inv.empty:
        return pd.DataFrame()

    df = st.session_state.df_inv.copy()
    df['unidad_check'] = df['unidad'].fillna('').str.strip().str.lower()
    return df[df['unidad_check'] == 'ml'].copy()
def cargar_datos():
    try:
        conn = conectar()
        st.session_state.df_inv = pd.read_sql("SELECT * FROM inventario", conn)
        st.session_state.df_cli = pd.read_sql("SELECT * FROM clientes", conn)

        conf = pd.read_sql("SELECT * FROM configuracion", conn).set_index('parametro')

        st.session_state.tasa_bcv = float(conf.loc['tasa_bcv','valor'])
        st.session_state.tasa_binance = float(conf.loc['tasa_binance','valor'])
        st.session_state.costo_tinta_ml = float(conf.loc['costo_tinta_ml','valor'])

        conn.close()
    except Exception as e:
        st.error(f"Error cargando datos: {e}")

def cargar_datos_seguros():
    cargar_datos()
    st.toast("Datos actualizados")
t_bcv = st.session_state.tasa_bcv
t_bin = st.session_state.tasa_binance
ROL = st.session_state.rol
with st.sidebar:
    st.header(f"Hola {st.session_state.usuario_nombre}")
    st.info(f"BCV: {t_bcv:.2f} | Binance: {t_bin:.2f}")

    opciones = ["📝 Cotizaciones", "🎨 Análisis CMYK", "👥 Clientes"]

    if ROL == "Admin":
        opciones += [
            "💰 Ventas",
            "📉 Gastos",
            "📦 Inventario",
            "📊 Dashboard",
            "🏗️ Activos",
            "⚙️ Configuración"
        ]

    menu = st.radio("Menú:", opciones)

    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
if menu == "📦 Inventario":
    st.title("Inventario")

    df = st.session_state.df_inv

    if not df.empty:
        st.dataframe(df)
elif menu == "👥 Clientes":
    st.title("Clientes")

    with st.form("cli"):
        nombre = st.text_input("Nombre")
        ws = st.text_input("WhatsApp")

        if st.form_submit_button("Guardar"):
            conn = conectar()
            conn.execute("INSERT INTO clientes (nombre, whatsapp) VALUES (?,?)", (nombre, ws))
            conn.commit()
            conn.close()
            st.success("Cliente registrado")
            st.rerun()

    st.dataframe(st.session_state.df_cli)
elif menu == "📝 Cotizaciones":
    st.title("Cotizaciones")

    datos_pre = st.session_state.get('datos_pre_cotizacion', {
        'trabajo': "Trabajo",
        'costo_base': 0.0,
        'unidades': 1
    })

    with st.container(border=True):
        st.subheader("Detalles")

        descr = st.text_input("Descripción", value=datos_pre['trabajo'])

        if not st.session_state.df_cli.empty:
            nombres = st.session_state.df_cli['nombre'].tolist()
            cliente = st.selectbox("Cliente", nombres)

        unidades = st.number_input("Cantidad", value=int(datos_pre['unidades']))

        costo = st.number_input("Costo base $", value=float(datos_pre['costo_base']))

        margen = st.slider("Margen %", 10, 300, 100)

        precio = costo * (1 + margen/100)

        st.metric("Precio Final", f"${precio:.2f}")
st.write("Sistema listo 🚀")
