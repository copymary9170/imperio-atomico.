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

# --- 2. COSTOS DE TINTA (Según tus datos) ---
COSTOS_TINTA = {
    "Epson L1250 (Sublimación - 1L)": 20 / 1000,
    "HP Smart Tank 580w (Repuesto)": 20 / 75,
    "HP Deskjet J210a (Cartuchos XL)": 40 / 13.5
}

# --- 3. GESTIÓN DE DATOS ---
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv"
CSV_PRODUCCION = "ordenes_produccion.csv"
CSV_GASTOS = "gastos_fijos.csv"
CSV_VENTAS = "registro_ventas_088.csv"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]
COL_GASTOS = ["Concepto", "Monto_Mensual_USD"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0 if "USD" in col else "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)
df_gastos = cargar_datos(CSV_GASTOS, COL_GASTOS)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)

# --- 4. MOTOR CMYK ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    ml_total = (c.mean() + m.mean() + y.mean() + k.mean()) * 1.2
    return {
        "C": float(np.clip(c, 0, 1).mean() * 100), 
        "M": float(np.clip(m, 0, 1).mean() * 100),
        "Y": float(np.clip(y, 0, 1).mean() * 100), 
        "K": float(k.mean() * 100),
        "ml_estimados": ml_total
    }

# --- 5. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador y Cotizador", "💰 Ventas"])

# --- MÓDULO: ANALIZADOR Y COTIZADOR (VINCULADO A INVENTARIO) ---
if menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Cotizador Automático con Inventario")
    
    col_a, col_b = st.columns([2, 1])
    
    with col_b:
        st.subheader("⚙️ Parámetros Reales")
        maquina = st.selectbox("Impresora:", list(COSTOS_TINTA.keys()))
        
        # AQUÍ JALAMOS EL MATERIAL DEL INVENTARIO
        if not df_stock.empty:
            material_sel = st.selectbox("Papel / Material a usar:", df_stock["Material"].unique())
            papel_costo = float(df_stock.loc[df_stock["Material"] == material_sel, "Costo_Unit_USD"].values[0])
            st.caption(f"Costo en stock: ${papel_costo:.2f} por unidad")
        else:
            st.error("No hay materiales en Inventario.")
            papel_costo = 0.0
            
        margen = st.slider("Ganancia deseada %:", 20, 500, 100)

    with col_a:
        archivos = st.file_uploader("Subir diseño", type=["jpg", "png", "pdf"], accept_multiple_files=True)
        
    if archivos:
        resultados = []
        for a in archivos:
            try:
                if a.type == "application/pdf":
                    doc = fitz.open(stream=a.read(), filetype="pdf")
                    for i in range(len(doc)):
                        pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        res = analizar_cmyk_pro(img)
                        res["Archivo"] = f"{a.name} (P{i+1})"
                        resultados.append(res)
                else:
                    img = Image.open(a)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = a.name
                    resultados.append(res)
            except: st.error(f"Error en {a.name}")

        df_res = pd.DataFrame(resultados)
        if not df_res.empty:
            costo_ml = COSTOS_TINTA[maquina]
            df_res["Costo Tinta"] = df_res["ml_estimados"] * costo_ml
            df_res["Costo Material"] = papel_costo
            df_res["Costo Producción"] = df_res["Costo Tinta"] + df_res["Costo Material"]
            df_res["Precio Venta Sugerido"] = df_res["Costo Producción"] * (1 + margen/100)
            
            st.dataframe(df_res.style.format({
                "C": "{:.1f}%", "M": "{:.1f}%", "Y": "{:.1f}%", "K": "{:.1f}%",
                "Costo Tinta": "${:.3f}", "Costo Material": "${:.2f}", 
                "Costo Producción": "${:.2f}", "Precio Venta Sugerido": "${:.2f}"
            }), use_container_width=True)

# --- MÓDULO: INVENTARIO PRO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario Reales")
    t1, t2 = st.tabs(["📋 Stock", "🛒 Compra"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n = st.text_input("Material")
            c = st.number_input("Cantidad", min_value=0.1)
            p = st.number_input("Total Factura (USD)", min_value=0.0)
            c1, c2 = st.columns(2)
            iva = c1.checkbox("IVA (16%)")
            igtf = c2.number_input("% IGTF/Comisión", value=3.0)
            if st.form_submit_button("Cargar"):
                total = p * 1.16 if iva else p
                total *= (1 + igtf/100)
                cu = total / c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"] == n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = cu
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", cu, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.rerun()

# --- MÓDULO: FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    with st.form("gf"):
        con = st.text_input("Concepto")
        mon = st.number_input("Monto USD", min_value=0.0)
        if st.form_submit_button("Añadir"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS)
            st.rerun()
    st.table(df_gastos)
    total_f = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    st.metric("Total Gastos Fijos", f"$ {total_f:,.2f}")

# (Resto de módulos: Clientes, Producción, Ventas se mantienen igual)
