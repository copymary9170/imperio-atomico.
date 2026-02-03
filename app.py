import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz 
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Master V7", layout="wide")

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

df_stock = cargar_datos(*archivos["stock"])
df_clientes = cargar_datos(*archivos["clientes"])
df_prod = cargar_datos(*archivos["produccion"])
df_gastos = cargar_datos(*archivos["gastos"])
df_ventas = cargar_datos(*archivos["ventas"])
df_tintas = cargar_datos(*archivos["tintas"])
df_conf = cargar_datos(*archivos["config"])

if df_conf.empty:
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, archivos["config"][0])

t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

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

# --- 3. LÓGICA TÉCNICA ---
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
        f = 1.2
        return img, {"C": c.mean()*f, "M": m.mean()*f, "Y": y.mean()*f, "K": k.mean()*f}
    except: return None, None

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "🎨 Analizador", "🏗️ Producción", "📦 Inventario", "📈 Finanzas Pro", "👥 Clientes", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- NUEVO: MANUALES TÉCNICOS ---
if menu == "🔍 Manuales":
    st.title("🔍 Biblioteca de Manuales Atómicos")
    st.info("Aquí puedes consultar los procesos técnicos de cada impresora.")
    
    sel_manual = st.selectbox("Selecciona el manual:", ["Mantenimiento Epson L1250", "Reset de Almohadillas", "Limpieza de Cabezales HP", "Codigos de Error J210a"])
    
    if sel_manual == "Mantenimiento Epson L1250":
        st.subheader("🛠️ Proceso de Limpieza")
        st.write("1. Verifique que no haya aire en las mangueras.")
        st.write("2. Ejecute la limpieza de cabezal desde el software solo si hay rayas.")
        st.warning("⚠️ No realice más de 3 limpiezas seguidas para evitar saturar las almohadillas.")
    
    # Aquí puedes añadir más contenido o cargarlo desde archivos de texto.
    st.image("https://via.placeholder.com/800x400.png?text=Diagrama+de+Flujo+Mantenimiento", caption="Diagrama de mantenimiento preventivo")

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costo Real")
    c1, c2 = st.columns([2,1])
    with c2:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        mat_sel = st.selectbox("Papel:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else 0.1
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c1:
        f = st.file_uploader("Subir Diseño (PDF, JPG, PNG)", type=["jpg","png","pdf"])
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

# --- DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    v = pd.to_numeric(df_ventas["Monto_USD"], errors='coerce').sum()
    g = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Totales", f"$ {v:,.2f}")
    c2.metric("Gastos Operativos", f"$ {g:,.2f}")
    c3.metric("Utilidad Estimada", f"$ {(v-g):,.2f}")

# --- RESTO DE MÓDULOS (BREVE) ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Taller")
    st.dataframe(df_prod)
elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    st.table(df_gastos)
elif menu == "📦 Inventario":
    st.title("📦 Inventario")
    st.dataframe(df_stock)
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración")
    st.data_editor(df_tintas)
