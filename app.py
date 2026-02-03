import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Master Sistema", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔐 Acceso al Imperio")
        password = st.text_input("Clave de Acceso:", type="password")
        if st.button("Entrar"):
            if password == "1234":
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. GESTIÓN DE ARCHIVOS ---
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv"
CSV_PRODUCCION = "ordenes_produccion.csv"
CSV_GASTOS = "gastos_fijos.csv"
CSV_VENTAS = "registro_ventas_088.csv"
CSV_TINTAS = "tintas_cmyk_pro.csv"
CSV_CONFIG = "config_tasas.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]
COL_GASTOS = ["Concepto", "Monto_Mensual_USD"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]
COL_TINTAS = ["Impresora", "Color", "Precio_Envase_Ref", "ML_Envase", "Tasa_Compra"]

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

# Cargar Tasas
if not os.path.exists(CSV_CONFIG):
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, CSV_CONFIG)
else:
    df_conf = pd.read_csv(CSV_CONFIG)

t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

# Cargar Tintas (4 por impresora)
df_tintas = cargar_datos(CSV_TINTAS, COL_TINTAS)
if df_tintas.empty:
    maquinas = ["Epson L1250", "HP Smart Tank 580w", "HP Deskjet J210a"]
    colores = ["Cian", "Magenta", "Amarillo", "Negro"]
    data = []
    for m in maquinas:
        p = 40.0 if "J210a" in m else 20.0
        ml = 13.5 if "J210a" in m else (1000 if "Epson" in m else 70)
        tasa = "Binance" if "Epson" in m else "BCV"
        for c in colores: data.append([m, c, p, ml, tasa])
    df_tintas = pd.DataFrame(data, columns=COL_TINTAS)
    guardar_datos(df_tintas, CSV_TINTAS)

# --- 3. LÓGICA DE COSTEO ---
def calcular_costo_ml(impresora, color):
    row = df_tintas[(df_tintas["Impresora"] == impresora) & (df_tintas["Color"] == color)].iloc[0]
    p_usd = (float(row["Precio_Envase_Ref"]) * t_bcv / t_bin) if row["Tasa_Compra"] == "BCV" else float(row["Precio_Envase_Ref"])
    return p_usd / float(row["ML_Envase"])

# --- 4. MOTOR CMYK ---
def analizar_cmyk_pro(img_pil):
    pix = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix[:,:,0], pix[:,:,1], pix[:,:,2]
    k = 1 - np.max(pix, axis=2)
    c, m, y = (1-r-k)/(1-k+1e-9), (1-g-k)/(1-k+1e-9), (1-b-k)/(1-k+1e-9)
    # Consumo: 1.2ml total por A4 al 100%
    factor = 1.2
    return {"C": c.mean()*factor, "M": m.mean()*factor, "Y": y.mean()*factor, "K": k.mean()*factor}

# --- 5. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador y Cotizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- MODULO: CONFIGURACIÓN (TASAS Y TINTAS CMYK) ---
if menu == "⚙️ Configuración":
    st.title("⚙️ Configuración Atómica")
    c1, c2 = st.columns(2)
    t_bcv = c1.number_input("Tasa BCV", value=t_bcv)
    t_bin = c2.number_input("Tasa Binance", value=t_bin)
    if st.button("Actualizar Tasas"):
        df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"] = t_bcv
        df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"] = t_bin
        guardar_datos(df_conf, CSV_CONFIG); st.rerun()
    
    st.subheader("💧 Precios por Color (Cian, Magenta, Amarillo, Negro)")
    ed_t = st.data_editor(df_tintas, column_config={"Tasa_Compra": st.column_config.SelectboxColumn("Tasa", options=["BCV", "Binance"])}, use_container_width=True)
    if st.button("Guardar Precios Tintas"):
        guardar_datos(ed_t, CSV_TINTAS); st.success("¡Actualizado!"); st.rerun()

# --- ANALIZADOR Y COTIZADOR ---
elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Cotizador CMYK Individual")
    col_a, col_b = st.columns([2,1])
    with col_b:
        m_sel = st.selectbox("Impresora:", df_tintas["Impresora"].unique())
        df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else st.number_input("Costo Papel USD", value=0.1)
        margen = st.slider("Ganancia %", 20, 500, 100)
    with col_a:
        arch = st.file_uploader("Subir diseño", type=["jpg", "png", "pdf"])
        if arch:
            res = analizar_cmyk_pro(Image.open(arch))
            costo_total_tinta = (res["C"] * calcular_costo_ml(m_sel, "Cian")) + \
                                (res["M"] * calcular_costo_ml(m_sel, "Magenta")) + \
                                (res["Y"] * calcular_costo_ml(m_sel, "Amarillo")) + \
                                (res["K"] * calcular_costo_ml(m_sel, "Negro"))
            total_usd = costo_total_tinta + p_mat
            pvp = total_usd * (1 + margen/100)
            st.metric("PVP Sugerido USD", f"$ {pvp:.2f}")
            st.metric("PVP Sugerido Bs", f"Bs. {pvp * t_bin:.2f}")
            st.write(f"Consumo (ml): C:{res['C']:.3f} | M:{res['M']:.3f} | Y:{res['Y']:.3f} | K:{res['K']:.3f}")

# --- INVENTARIO PRO (CON AJUSTE) ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
    t1, t2, t3 = st.tabs(["📋 Stock", "🛒 Compra", "✏️ Ajuste"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("com"):
            n, c, p = st.text_input("Material"), st.number_input("Cant"), st.number_input("Precio Ref")
            t_c = st.selectbox("Tasa", ["Binance", "BCV"])
            if st.form_submit_button("Cargar"):
                p_r = (p * t_bcv / t_bin) if t_c == "BCV" else p
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"]==n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = p_r/c
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", p_r/c, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK); st.rerun()
    with t3:
        if not df_stock.empty:
            sel = st.selectbox("Ajustar:", df_stock["Material"].unique())
            nv = st.number_input("Cantidad Real", value=float(df_stock.loc[df_stock["Material"]==sel, "Cantidad"].values[0]))
            if st.button("Corregir"):
                df_stock.loc[df_stock["Material"]==sel, "Cantidad"] = nv
                guardar_datos(df_stock, CSV_STOCK); st.rerun()

# --- CLIENTES (CON BUSCADOR) ---
elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
    bus = st.text_input("🔍 Buscar cliente...")
    if st.button("Añadir"):
        df_clientes = pd.concat([df_clientes, pd.DataFrame([["Nuevo", "0412", "Insta", "2026"]], columns=COL_CLIENTES)], ignore_index=True)
        guardar_datos(df_clientes, CSV_CLIENTES)
    st.dataframe(df_clientes[df_clientes["Nombre"].str.contains(bus, case=False)] if bus else df_clientes)

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registrar Venta")
    df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
    with st.form("v"):
        cli = st.text_input("Cliente")
        ins = st.text_input("Material")
        monto = st.number_input("Cobrado USD")
        if st.form_submit_button("Vender"):
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, monto, 0, monto]], columns=COL_VENTAS)], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS); st.success("Venta guardada")

# --- PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Taller")
    df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)
    st.dataframe(df_prod)

# --- MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Manuales")
    h = st.text_input("Hoja #")
    if h: st.info("Contenido del manual...")

# --- DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
    st.metric("Total Ventas USD", f"$ {pd.to_numeric(df_ventas['Monto_USD'], errors='coerce').sum():.2f}")
