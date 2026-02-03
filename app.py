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
CSV_TINTAS_DETALLE = "detalle_tintas_v3.csv" # Nueva versión detallada
CSV_CONFIG = "config_sistema.csv"

COL_TINTAS_DETALLE = ["Impresora", "Tipo_Tinta", "Precio_Envase_Ref", "ML_Envase", "Tasa_Compra"]

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

# Cargar Configuración de Tasas
if not os.path.exists(CSV_CONFIG):
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, CSV_CONFIG)
else:
    df_conf = pd.read_csv(CSV_CONFIG)

t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

# Cargar Tintas Detalladas
df_tintas = cargar_datos(CSV_TINTAS_DETALLE, COL_TINTAS_DETALLE)
if df_tintas.empty:
    # Datos precisos que me diste
    data_inicial = [
        ["Epson L1250", "Color (CMY) - 1L", 20.0, 1000, "Binance"],
        ["Epson L1250", "Negro (K) - 1L", 20.0, 1000, "Binance"],
        ["HP Smart Tank 580w", "Color (CMY) - 70ml", 20.0, 70, "BCV"],
        ["HP Smart Tank 580w", "Negro (K) - 90ml", 20.0, 90, "BCV"],
        ["HP Deskjet J210a", "Color (CMY) XL - 15ml", 40.0, 15, "BCV"],
        ["HP Deskjet J210a", "Negro (K) XL - 12.4ml", 40.0, 12.4, "BCV"]
    ]
    df_tintas = pd.DataFrame(data_inicial, columns=COL_TINTAS_DETALLE)
    guardar_datos(df_tintas, CSV_TINTAS_DETALLE)

# --- 3. LÓGICA DE COSTEO ---
def get_costo_ml(impresora, tipo):
    row = df_tintas[(df_tintas["Impresora"] == impresora) & (df_tintas["Tipo_Tinta"].str.contains(tipo))]
    if row.empty: return 0.0
    row = row.iloc[0]
    precio_usd = (float(row["Precio_Envase_Ref"]) * t_bcv / t_bin) if row["Tasa_Compra"] == "BCV" else float(row["Precio_Envase_Ref"])
    return precio_usd / float(row["ML_Envase"])

# --- 4. MOTOR CMYK MEJORADO ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1-r-k)/(1-k+1e-9)
    m = (1-g-k)/(1-k+1e-9)
    y = (1-b-k)/(1-k+1e-9)
    # Cobertura promedio
    cov_c, cov_m, cov_y, cov_k = c.mean(), m.mean(), y.mean(), k.mean()
    # 1.2ml es el consumo total de una hoja A4 al 100% de cobertura
    ml_cmy = (cov_c + cov_m + cov_y) * 1.2
    ml_k = cov_k * 1.2
    return {"C": cov_c*100, "M": cov_m*100, "Y": cov_y*100, "K": cov_k*100, "ml_cmy": ml_cmy, "ml_k": ml_k}

# --- 5. MENÚ ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "🎨 Analizador y Cotizador", "📦 Inventario", "⚙️ Configuración"])

if menu == "⚙️ Configuración":
    st.title("⚙️ Configuración de Insumos")
    st.subheader("💹 Tasas")
    c1, c2 = st.columns(2)
    t_bcv = c1.number_input("Tasa BCV", value=t_bcv)
    t_bin = c2.number_input("Tasa Binance", value=t_bin)
    
    st.subheader("💧 Detalle de Tintas por Impresora")
    st.write("Ajusta el precio y los ml exactos de cada envase (Negro o Color).")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios"):
        guardar_datos(ed, CSV_TINTAS_DETALLE)
        st.success("¡Base de datos de tintas actualizada!")

elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Analizador de Costo Real")
    col_a, col_b = st.columns([2, 1])
    
    with col_b:
        imp_sel = st.selectbox("Impresora:", df_tintas["Impresora"].unique())
        costo_ml_cmy = get_costo_ml(imp_sel, "Color")
        costo_ml_k = get_costo_ml(imp_sel, "Negro")
        
        st.caption(f"Costo ML Color: ${costo_ml_cmy:.4f} | Negro: ${costo_ml_k:.4f}")
        
        margen = st.slider("Ganancia %", 20, 500, 100)
    
    with col_a:
        arch = st.file_uploader("Subir diseño", type=["jpg", "png", "pdf"])
        if arch:
            # (Lógica de procesamiento de imagen...)
            img = Image.open(arch)
            res = analizar_cmyk_pro(img)
            
            costo_tinta = (res["ml_cmy"] * costo_ml_cmy) + (res["ml_k"] * costo_ml_k)
            total_usd = costo_tinta + 0.10 # + Papel base
            pvp = total_usd * (1 + margen/100)
            
            st.metric("Precio Sugerido USD", f"$ {pvp:.2f}")
            st.metric("Precio Sugerido Bs", f"Bs. {pvp * t_bin:.2f}")
            
            st.write(f"Consumo Estimado: Color {res['ml_cmy']:.3f}ml | Negro {res['ml_k']:.3f}ml")
