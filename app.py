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

# --- 2. GESTIÓN DE BASES DE DATOS ---
archivos = {
    "stock": ("stock_actual.csv", ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]),
    "clientes": ("clientes_imperio.csv", ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]),
    "produccion": ("ordenes_produccion.csv", ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]),
    "gastos": ("gastos_fijos.csv", ["Concepto", "Monto_Mensual_USD"]),
    "ventas": ("registro_ventas_088.csv", ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]),
    "tintas": ("tintas_v7_final.csv", ["Impresora", "Componente", "Precio_Envase_USD", "ML_Envase", "Capacidad_Tanque_ML", "Tasa_Compra"]),
    "config": ("config_tasas.csv", ["Parametro", "Valor"])
}

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

# Cargas iniciales de datos
df_stock = cargar_datos(*archivos["stock"])
df_clientes = cargar_datos(*archivos["clientes"])
df_prod = cargar_datos(*archivos["produccion"])
df_gastos = cargar_datos(*archivos["gastos"])
df_ventas = cargar_datos(*archivos["ventas"])
df_tintas = cargar_datos(*archivos["tintas"])
df_conf = cargar_datos(*archivos["config"])

# Tasas
if df_conf.empty:
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, archivos["config"][0])
t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

# Inicializar Tintas CMYK Detalladas
if df_tintas.empty:
    data = [
        ["Epson L1250", "Cian", 20.0, 1000, 65, "Binance"], ["Epson L1250", "Magenta", 20.0, 1000, 65, "Binance"],
        ["Epson L1250", "Amarillo", 20.0, 1000, 65, "Binance"], ["Epson L1250", "Negro", 20.0, 1000, 65, "Binance"],
        ["HP Smart Tank 580w", "Cian", 20.0, 70, 70, "BCV"], ["HP Smart Tank 580w", "Magenta", 20.0, 70, 70, "BCV"],
        ["HP Smart Tank 580w", "Amarillo", 20.0, 70, 70, "BCV"], ["HP Smart Tank 580w", "Negro", 20.0, 90, 90, "BCV"],
        ["HP Deskjet J210a", "Tricolor", 40.0, 15, 15, "BCV"], ["HP Deskjet J210a", "Negro", 40.0, 12.4, 12.4, "BCV"]
    ]
    df_tintas = pd.DataFrame(data, columns=archivos["tintas"][1])
    guardar_datos(df_tintas, archivos["tintas"][0])

# --- 3. LÓGICA DE COSTEO ---
def get_costo_ml(imp, comp):
    try:
        row = df_tintas[(df_tintas["Impresora"] == imp) & (df_tintas["Componente"].str.contains(comp, case=False))].iloc[0]
        p_real = (float(row["Precio_Envase_USD"]) * t_bcv / t_bin) if row["Tasa_Compra"] == "BCV" else float(row["Precio_Envase_USD"])
        return p_real / float(row["ML_Envase"])
    except: return 0.0

def analizar_cmyk_pro(file):
    try:
        if file.type == "application/pdf":
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(file).convert("RGB")
        pix_arr = np.array(img) / 255.0
        k = 1 - np.max(pix_arr, axis=2)
        c, m, y = (1-pix_arr[:,:,0]-k)/(1-k+1e-9), (1-pix_arr[:,:,1]-k)/(1-k+1e-9), (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        return img, {"C": c.mean()*1.2, "M": m.mean()*1.2, "Y": y.mean()*1.2, "K": k.mean()*1.2}
    except: return None, None

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú Principal:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Operativo")
    v = pd.to_numeric(df_ventas["Monto_USD"], errors='coerce').sum()
    g = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Totales", f"$ {v:,.2f}")
    c2.metric("Gastos Fijos", f"$ {g:,.2f}")
    c3.metric("Neto del Mes", f"$ {(v-g):,.2f}")
    st.divider()
    st.subheader("⚠️ Alertas de Stock")
    st.dataframe(df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])])

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Directorio de Clientes")
    with st.expander("➕ Registrar Nuevo Cliente"):
        with st.form("fc"):
            n, w, p = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "TikTok"])
            if st.form_submit_button("Guardar"):
                df_clientes = pd.concat([df_clientes, pd.DataFrame([[n, w, p, datetime.now().strftime("%Y-%m-%d")]], columns=archivos["clientes"][1])], ignore_index=True)
                guardar_datos(df_clientes, archivos["clientes"][0]); st.rerun()
    bus = st.text_input("🔍 Buscar cliente por nombre...")
    st.dataframe(df_clientes[df_clientes["Nombre"].str.contains(bus, case=False, na=False)] if bus else df_clientes)

# --- PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Gestión de Taller")
    with st.expander("🆕 Nueva Orden de Producción"):
        with st.form("np"):
            cl = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            tr = st.text_input("Trabajo")
            ma = st.selectbox("Máquina", df_tintas["Impresora"].unique())
            pr = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Lanzar"):
                df_prod = pd.concat([df_prod, pd.DataFrame([[len(df_prod)+1, datetime.now().strftime("%d/%m"), cl, tr, ma, "En Cola", pr]], columns=archivos["produccion"][1])], ignore_index=True)
                guardar_datos(df_prod, archivos["produccion"][0]); st.rerun()
    st.dataframe(df_prod)

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos CMYK")
    c1, c2 = st.columns([2,1])
    with c2:
        m_sel = st.selectbox("Impresora:", df_tintas["Impresora"].unique())
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else 0.1
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c1:
        f = st.file_uploader("Subir diseño", type=["jpg","png","pdf"])
        if f:
            img, res = analizar_cmyk_pro(f)
            if img:
                st.image(img, use_container_width=True)
                if "J210a" in m_sel:
                    costo_t = (res["K"]*get_costo_ml(m_sel,"Negro")) + ((res["C"]+res["M"]+res["Y"])*get_costo_ml(m_sel,"Tricolor"))
                else:
                    costo_t = (res["C"]*get_costo_ml(m_sel,"Cian")) + (res["M"]*get_costo_ml(m_sel,"Magenta")) + (res["Y"]*get_costo_ml(m_sel,"Amarillo")) + (res["K"]*get_costo_ml(m_sel,"Negro"))
                pvp = (costo_t + p_mat) * (1 + margen/100)
                st.metric("PVP Sugerido USD", f"$ {pvp:.2f}")
                st.metric("PVP Sugerido Bs", f"Bs. {pvp * t_bin:.2f}")

# --- FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos Mensuales")
    with st.form("gf"):
        con, mon = st.text_input("Concepto"), st.number_input("Monto USD")
        if st.form_submit_button("Añadir Gasto"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=archivos["gastos"][1])], ignore_index=True)
            guardar_datos(df_gastos, archivos["gastos"][0]); st.rerun()
    st.table(df_gastos)

# --- MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    st.write("Selecciona un manual para ver los procesos.")
    # Espacio para contenido de manuales

# --- INVENTARIO PRO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    t1, t2 = st.tabs(["📋 Lista de Stock", "✏️ Ajuste de Inventario"])
    with t1: st.dataframe(df_stock)
    with t2:
        with st.form("aj"):
            m, c, p = st.text_input("Material"), st.number_input("Cantidad"), st.number_input("Precio Ref USD")
            t = st.selectbox("Tasa", ["Binance", "BCV"])
            if st.form_submit_button("Actualizar Stock"):
                pr_r = (p * t_bcv / t_bin) if t == "BCV" else p
                if m in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"]==m, "Cantidad"] = c
                    df_stock.loc[df_stock["Material"]==m, "Costo_Unit_USD"] = pr_r/c if c>0 else 0
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[m, c, "Unid", pr_r/c, 5]], columns=archivos["stock"][1])], ignore_index=True)
                guardar_datos(df_stock, archivos["stock"][0]); st.rerun()

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    with st.form("v"):
        cl, ins, mon = st.text_input("Cliente"), st.text_input("Insumo"), st.number_input("Monto USD")
        if st.form_submit_button("Registrar Venta"):
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cl, ins, mon, 0, mon]], columns=archivos["ventas"][1])], ignore_index=True)
            guardar_datos(df_ventas, archivos["ventas"][0]); st.success("Venta guardada")

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajustes de Sistema")
    st.subheader("💹 Tasas de Cambio")
    c1, c2 = st.columns(2)
    nb = c1.number_input("Tasa BCV", value=t_bcv)
    np = c2.number_input("Tasa Binance", value=t_bin)
    if st.button("Actualizar Tasas"):
        df_conf.loc[df_conf["Parametro"]=="Tasa_BCV","Valor"]=nb
        df_conf.loc[df_conf["Parametro"]=="Tasa_Binance","Valor"]=np
        guardar_datos(df_conf, archivos["config"][0]); st.rerun()
    st.divider()
    st.subheader("💧 Precios de Tintas por Color")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios Tintas"):
        guardar_datos(ed, archivos["tintas"][0]); st.success("Tintas actualizadas")
