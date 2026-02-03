import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
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
            else:
                st.error("⚠️ Clave Incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- 2. GESTIÓN DE DATOS (Bases de datos en CSV) ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv" # <-- Nuevo: Base de datos de clientes
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Comisiones_USD", "Ganancia_Real_USD", "Responsable"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"] # <-- Nuevo: Columnas de clientes

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except:
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

# Carga inicial de datos
df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)

# --- 3. MOTOR CMYK ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    return {
        "C": np.clip(c, 0, 1).mean() * 100,
        "M": np.clip(m, 0, 1).mean() * 100,
        "Y": np.clip(y, 0, 1).mean() * 100,
        "K": k.mean() * 100
    }

# --- 4. NAVEGACIÓN ---
# He añadido "👥 Clientes" al menú
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🎨 Analizador Masivo", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen Económico")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        c2.metric("Comisiones Pagadas", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}", delta_color="inverse")
        c3.metric("Utilidad Real", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        st.divider()
        st.subheader("⚠️ Alertas de Stock")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty:
            st.error("⚠️ Reponer: " + ", ".join(bajo["Material"].tolist()))
    else:
        st.info("Sin registros de ventas aún.")

# --- MÓDULO: CLIENTES (NUEVO) ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    t1, t2 = st.tabs(["➕ Registrar Cliente", "📋 Cartera de Clientes"])
    
    with t1:
        with st.form("form_clientes"):
            nom = st.text_input("Nombre o Razón Social")
            tel = st.text_input("WhatsApp / Teléfono")
            proc = st.selectbox("¿Cómo nos contactó?", ["Instagram", "WhatsApp", "Recomendado", "TikTok", "Publicidad Directa"])
            if st.form_submit_button("Guardar Cliente"):
                if nom:
                    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                    nuevo_c = pd.DataFrame([[nom, tel, proc, fecha_hoy]], columns=COL_CLIENTES)
                    df_clientes = pd.concat([df_clientes, nuevo_c], ignore_index=True)
                    guardar_datos(df_clientes, CSV_CLIENTES)
                    st.success(f"¡{nom} registrado con éxito!")
                    st.rerun()
                else:
                    st.warning("El nombre es obligatorio.")
    
    with t2:
        st.dataframe(df_clientes, use_container_width=True)

# --- MÓDULO: ANALIZADOR ---
elif menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador Multitarea")
    archivos = st.file_uploader("Subir archivos", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)
    if archivos:
        resultados = []
        for archivo in archivos:
            if archivo.type == "application/pdf":
                doc = fitz.open(stream=archivo.read(), filetype="pdf")
                for i in range(len(doc)):
                    pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = f"{archivo.name} (Pág {i+1})"
                    resultados.append(res)
            else:
                img = Image.open(archivo)
                res = analizar_cmyk_pro(img)
                res["Archivo"] = archivo.name
                resultados.append(res)
        df_res = pd.DataFrame(resultados)
        df_res["Total %"] = df_res["C"] + df_res["M"] + df_res["Y"] + df_res["K"]
        st.dataframe(df_res.style.format("{:.1f}%", subset=["C", "M", "Y", "K", "Total %"]), use_container_width=True)

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("form_ventas"):
            # Ahora seleccionamos clientes de nuestra lista
            if not df_clientes.empty:
                cli = st.selectbox("Cliente", df_clientes["Nombre"].unique())
            else:
                cli = st.text_input("Cliente (No hay lista aún)")
                
            ins = st.selectbox("Material usado", df_stock["Material"].unique())
            can = st.number_input("Cantidad usada", min_value=0.01)
            mon = st.number_input("Monto Cobrado (USD)", min_value=0.0)
            com = st.number_input("% Comisión/Punto/IGTF", value=3.0)
            
            if st.form_submit_button("Guardar Venta"):
                costo_u = float(df_stock.loc[df_stock["Material"] == ins, "Costo_Unit_USD"].values[0])
                c_usd = mon * (com/100)
                gan = mon - c_usd - (can * costo_u)
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, mon, c_usd, gan, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                
                # Descontar del stock
                idx_stock = df_stock.index[df_stock["Material"] == ins][0]
                df_stock.at[idx_stock, "Cantidad"] -= can
                guardar_datos(df_stock, CSV_STOCK)
                
                st.success(f"Venta registrada. Ganancia: ${gan:.2f}")
                st.rerun()
    else:
        st.warning("No hay materiales en stock.")

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario y Costos Reales")
    t1, t2, t3 = st.tabs(["📋 Stock Actual", "🛒 Nueva Compra", "✏️ Ajustes Manuales"])
    with t1:
        st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("form_compra"):
            n = st.text_input("Material")
            c = st.number_input("Cantidad", min_value=0.1)
            p = st.number_input("Precio en Factura USD", min_value=0.0)
            st.divider()
            c1, c2 = st.columns(2)
            iva = c1.checkbox("¿Pagaste IVA (16%)?")
            igtf_banco = c2.number_input("% Comisión/IGTF/GTF", value=3.0)
            if st.form_submit_button("Añadir al Stock"):
                total_usd = p
                if iva: total_usd *= 1.16
                total_usd *= (1 + (igtf_banco/100))
                c_u = total_usd / c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"] == n][0]
                    df_stock.loc[idx, "Costo_Unit_USD"] = c_u
                    df_stock.loc[idx, "Cantidad"] += c
                else:
                    nueva = pd.DataFrame([[n, c, "Unid", c_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Ingresado. Costo Unitario Real: ${c_u:.4f}")
                st.rerun()
    with t3:
        if not df_stock.empty:
            m = st.selectbox("Seleccionar Material", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == m][0]
            nc = st.number_input("Stock Real en Físico", value=float(df_stock.loc[idx, "Cantidad"]))
            nu = st.number_input("Costo Unit. USD Manual", value=float(df_stock.loc[idx, "Costo_Unit_USD"]))
            nm = st.number_input("Mínimo para Alerta", value=float(df_stock.loc[idx, "Minimo_Alerta"]))
            if st.button("Actualizar Valores"):
                df_stock.loc[idx, ["Cantidad", "Costo_Unit_USD", "Minimo_Alerta"]] = [nc, nu, nm]
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Ajuste realizado.")
                st.rerun()

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos del Imperio")
    hoja = st.text
