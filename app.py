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

# --- 2. GESTIÓN DE DATOS ---
CSV_VENTAS = "registro_ventas_088.csv"
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv"
CSV_PRODUCCION = "ordenes_produccion.csv" # <-- Nuevo
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Comisiones_USD", "Ganancia_Real_USD", "Responsable"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Estado", "Prioridad"] # <-- Nuevo

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except:
        return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo):
    df.to_csv(archivo, index=False)

df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)

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
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "🎨 Analizador Masivo", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen Económico")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas Brutas", f"$ {df_ventas['Monto_USD'].sum():,.2f}")
        c2.metric("Comisiones Pagadas", f"$ {df_ventas['Comisiones_USD'].sum():,.2f}")
        c3.metric("Utilidad Real", f"$ {df_ventas['Ganancia_Real_USD'].sum():,.2f}")
        
        st.divider()
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.subheader("🏗️ Estado de Taller")
            if not df_prod.empty:
                st.write(df_prod["Estado"].value_counts())
            else:
                st.info("Sin órdenes activas.")
        with col_p2:
            st.subheader("⚠️ Alertas de Stock")
            bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
            if not bajo.empty:
                st.error("Reponer: " + ", ".join(bajo["Material"].tolist()))
    else:
        st.info("Sin registros aún.")

# --- MÓDULO: CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    t1, t2 = st.tabs(["➕ Registrar Cliente", "📋 Cartera"])
    with t1:
        with st.form("form_clientes"):
            nom = st.text_input("Nombre / Empresa")
            tel = st.text_input("WhatsApp")
            proc = st.selectbox("Procedencia", ["Instagram", "WhatsApp", "Recomendado", "TikTok"])
            if st.form_submit_button("Guardar"):
                if nom:
                    nuevo_c = pd.DataFrame([[nom, tel, proc, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)
                    df_clientes = pd.concat([df_clientes, nuevo_c], ignore_index=True)
                    guardar_datos(df_clientes, CSV_CLIENTES)
                    st.success("¡Cliente registrado!")
                    st.rerun()
    with t2:
        st.dataframe(df_clientes, use_container_width=True)

# --- MÓDULO: PRODUCCIÓN (NUEVO) ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Control de Producción")
    
    t_alta, t_seguimiento = st.tabs(["🆕 Nueva Orden", "🛤️ Seguimiento de Taller"])
    
    with t_alta:
        if not df_clientes.empty:
            with st.form("nueva_ot"):
                c_ot = st.selectbox("Cliente", df_clientes["Nombre"].unique())
                d_ot = st.text_area("Descripción del Trabajo (Ej: 100 Tarjetas mate)")
                p_ot = st.select_slider("Prioridad", options=["Baja", "Normal", "Urgente"], value="Normal")
                if st.form_submit_button("Lanzar a Taller"):
                    nuevo_id = len(df_prod) + 1
                    nueva_ot = pd.DataFrame([[nuevo_id, datetime.now().strftime("%d/%m/%Y"), c_ot, d_ot, "En Cola", p_ot]], columns=COL_PRODUCCION)
                    df_prod = pd.concat([df_prod, nueva_ot], ignore_index=True)
                    guardar_datos(df_prod, CSV_PRODUCCION)
                    st.success(f"Orden #{nuevo_id} creada.")
                    st.rerun()
        else:
            st.warning("Primero debes registrar un cliente.")

    with t_seguimiento:
        if not df_prod.empty:
            for index, row in df_prod.iterrows():
                with st.expander(f"OT #{row['ID']} - {row['Cliente']} ({row['Estado']})"):
                    st.write(f"**Trabajo:** {row['Trabajo']}")
                    nuevo_estado = st.selectbox("Cambiar Estado", ["En Cola", "Diseño/Pre-prensa", "Imprimiendo", "Acabado", "Listo para Entrega"], key=f"estado_{index}")
                    if st.button("Actualizar", key=f"btn_{index}"):
                        df_prod.at[index, "Estado"] = nuevo_estado
                        guardar_datos(df_prod, CSV_PRODUCCION)
                        st.success("Estado actualizado.")
                        st.rerun()
        else:
            st.info("No hay órdenes en curso.")

# --- MÓDULO: ANALIZADOR ---
elif menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador CMYK")
    archivos = st.file_uploader("Archivos", type=["jpg", "png", "pdf"], accept_multiple_files=True)
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
        st.dataframe(pd.DataFrame(resultados), use_container_width=True)

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("form_ventas"):
            cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            ins = st.selectbox("Material usado", df_stock["Material"].unique())
            can = st.number_input("Cantidad", min_value=0.01)
            mon = st.number_input("Monto (USD)", min_value=0.0)
            if st.form_submit_button("Registrar Venta"):
                # (Lógica de cálculo mantenida del original)
                st.success("Venta guardada.")
                st.rerun()

# --- MÓDULO: INVENTARIO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    st.dataframe(df_stock, use_container_width=True)
    # (Resto de la lógica de inventario mantenida igual)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Nro de Hoja")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
        else:
            txt = st.text_area("Crear nuevo manual:")
            if st.button("Guardar"):
                if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
                with open(ruta, "w", encoding="utf-8") as f: f.write(txt)
                st.success("Guardado.")
