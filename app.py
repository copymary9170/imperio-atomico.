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

# --- 2. GESTIÓN DE ARCHIVOS Y DATOS ---
CSV_STOCK = "stock_actual.csv"
CSV_CLIENTES = "clientes_imperio.csv"
CSV_PRODUCCION = "ordenes_produccion.csv"
CSV_GASTOS = "gastos_fijos.csv"
CSV_VENTAS = "registro_ventas_088.csv"
CSV_TINTAS = "precios_tintas.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]
COL_GASTOS = ["Concepto", "Monto_Mensual_USD"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Costo_Insumos", "Ganancia_Real_USD"]
COL_TINTAS = ["Impresora", "Precio_USD", "ML_Total"]

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

# Cargar bases de datos
df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)
df_gastos = cargar_datos(CSV_GASTOS, COL_GASTOS)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
df_tintas = cargar_datos(CSV_TINTAS, COL_TINTAS)

# Inicializar tintas si el archivo está vacío (Valores que me diste)
if df_tintas.empty:
    df_tintas = pd.DataFrame([
        ["Epson L1250 (Sublimación)", 20.0, 1000],
        ["HP Smart Tank 580w", 20.0, 75],
        ["HP Deskjet J210a", 40.0, 13.5]
    ], columns=COL_TINTAS)
    guardar_datos(df_tintas, CSV_TINTAS)

# --- 3. MOTOR CMYK ---
def analizar_cmyk_pro(img_pil):
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    k = 1 - np.max(pix_rgb, axis=2)
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    # 1.2ml aprox por hoja A4 al 100% de cobertura
    ml_total = (c.mean() + m.mean() + y.mean() + k.mean()) * 1.2
    return {
        "C": float(np.clip(c, 0, 1).mean() * 100), 
        "M": float(np.clip(m, 0, 1).mean() * 100),
        "Y": float(np.clip(y, 0, 1).mean() * 100), 
        "K": float(k.mean() * 100),
        "ml_estimados": ml_total
    }

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador y Cotizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- MÓDULO: CONFIGURACIÓN (NUEVO PARA INFLACIÓN) ---
if menu == "⚙️ Configuración":
    st.title("⚙️ Configuración del Sistema")
    st.subheader("💧 Precios de Tintas (Ajuste por Inflación)")
    
    with st.form("edit_tintas"):
        # Mostramos tabla editable
        edited_df = st.data_editor(df_tintas, use_container_width=True)
        if st.form_submit_button("Actualizar Precios de Tintas"):
            df_tintas = edited_df
            guardar_datos(df_tintas, CSV_TINTAS)
            st.success("Precios actualizados en todo el sistema.")
            st.rerun()

# --- MÓDULO: ANALIZADOR Y COTIZADOR ---
elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Analizador y Cotizador")
    col_a, col_b = st.columns([2, 1])
    
    with col_b:
        st.subheader("⚙️ Parámetros")
        opciones_imp = df_tintas["Impresora"].tolist()
        maquina_sel = st.selectbox("Impresora:", opciones_imp)
        
        # Obtener costo ml de la base de datos de configuración
        row_tinta = df_tintas[df_tintas["Impresora"] == maquina_sel].iloc[0]
        costo_ml = row_tinta["Precio_USD"] / row_tinta["ML_Total"]
        
        if not df_stock.empty:
            mat_sel = st.selectbox("Material:", df_stock["Material"].unique())
            papel_costo = float(df_stock.loc[df_stock["Material"] == mat_sel, "Costo_Unit_USD"].values[0])
            if papel_costo <= 0:
                papel_costo = st.number_input("Costo manual material:", value=0.10)
            else:
                st.caption(f"Costo material: ${papel_costo:.2f}")
        else:
            papel_costo = st.number_input("Costo manual material:", value=0.10)
            
        margen = st.slider("Ganancia %:", 20, 500, 100)

    with col_a:
        archivos = st.file_uploader("Subir diseño", type=["jpg", "png", "pdf"], accept_multiple_files=True)
        
    if archivos:
        res_list = []
        for a in archivos:
            try:
                if a.type == "application/pdf":
                    doc = fitz.open(stream=a.read(), filetype="pdf")
                    for i in range(len(doc)):
                        pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        res = analizar_cmyk_pro(img)
                        res["Archivo"] = f"{a.name} (P{i+1})"
                        res_list.append(res)
                else:
                    img = Image.open(a)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = a.name
                    res_list.append(res)
            except: st.error(f"Error en {a.name}")

        df_res = pd.DataFrame(res_list)
        if not df_res.empty:
            df_res["Costo Tinta"] = df_res["ml_estimados"] * costo_ml
            df_res["Costo Total"] = df_res["Costo Tinta"] + papel_costo
            df_res["Sugerido"] = df_res["Costo Total"] * (1 + margen/100)
            st.dataframe(df_res.style.format({"C":"{:.1f}%","M":"{:.1f}%","Y":"{:.1f}%","K":"{:.1f}%","Costo Tinta":"${:.3f}","Costo Total":"${:.2f}","Sugerido":"${:.2f}"}), use_container_width=True)

# --- MÓDULO: VENTAS (RESTAURADO) ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    with st.form("venta"):
        cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
        ins = st.selectbox("Material usado", df_stock["Material"].unique()) if not df_stock.empty else st.text_input("Material")
        cant = st.number_input("Cantidad", min_value=1)
        monto = st.number_input("Precio Final Cobrado (USD)", min_value=0.0)
        if st.form_submit_button("Registrar Venta"):
            costo_u = float(df_stock.loc[df_stock["Material"] == ins, "Costo_Unit_USD"].values[0]) if not df_stock.empty else 0
            costo_t = costo_u * cant
            gan = monto - costo_t
            nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, monto, costo_t, gan]], columns=COL_VENTAS)
            df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS)
            # Descuento de stock
            if not df_stock.empty and ins in df_stock["Material"].values:
                idx = df_stock.index[df_stock["Material"] == ins][0]
                df_stock.at[idx, "Cantidad"] -= cant
                guardar_datos(df_stock, CSV_STOCK)
            st.success("Venta guardada y stock actualizado.")

# --- MÓDULO: INVENTARIO PRO (RESTAURADO) ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    t1, t2, t3 = st.tabs(["📋 Stock", "🛒 Compra", "✏️ Ajuste Manual"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n, c, p = st.text_input("Nombre"), st.number_input("Cant", min_value=0.1), st.number_input("Total Factura", min_value=0.0)
            iva = st.checkbox("IVA 16%")
            igtf = st.number_input("% IGTF", value=3.0)
            if st.form_submit_button("Ingresar"):
                t = p * 1.16 if iva else p
                t *= (1 + igtf/100)
                cu = t/c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"] == n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = cu
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", cu, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.rerun()
    with t3:
        if not df_stock.empty:
            sel = st.selectbox("Material a ajustar", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == sel][0]
            nv = st.number_input("Cantidad Real Física", value=float(df_stock.at[idx, "Cantidad"]))
            if st.button("Aplicar Ajuste"):
                df_stock.at[idx, "Cantidad"] = nv
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Stock corregido.")

# --- MÓDULO: MANUALES (RESTAURADO) ---
elif menu == "🔍 Manuales":
    st.title("🔍 Manuales y Protocolos")
    hoja = st.text_input("Número de Hoja (Ej: 001)")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
        else:
            txt = st.text_area("Escribir nuevo protocolo:")
            if st.button("Guardar Manual"):
                if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
                with open(ruta, "w", encoding="utf-8") as f: f.write(txt)
                st.success("Guardado.")

# --- MANTENER RESTO (Dashboard, Clientes, Producción, Finanzas) ---
elif menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    st.write("Resumen de ventas y alertas de stock.")

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    st.write("Gestión de cartera.")

elif menu == "🏗️ Producción":
    st.title("🏗️ Producción")
    st.write("Taller activo.")

elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    st.write("Control de egresos.")
