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
CSV_PRODUCCION = "ordenes_produccion.csv"
CSV_GASTOS = "gastos_fijos.csv"
CARPETA_MANUALES = "manuales"

COL_STOCK = ["Material", "Cantidad", "Unidad", "Costo_Unit_USD", "Minimo_Alerta"]
COL_VENTAS = ["Fecha", "Cliente", "Insumo", "Monto_USD", "Comisiones_USD", "Ganancia_Real_USD", "Responsable"]
COL_CLIENTES = ["Nombre", "WhatsApp", "Procedencia", "Fecha_Registro"]
COL_PRODUCCION = ["ID", "Fecha", "Cliente", "Trabajo", "Impresora", "Estado", "Prioridad"]
COL_GASTOS = ["Concepto", "Monto_Mensual_USD"]

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
df_gastos = cargar_datos(CSV_GASTOS, COL_GASTOS)

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
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "💰 Ventas", "📈 Finanzas Pro", "📦 Inventario Pro", "🎨 Analizador Masivo", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    if not df_ventas.empty:
        for c in ["Monto_USD", "Comisiones_USD", "Ganancia_Real_USD"]:
            df_ventas[c] = pd.to_numeric(df_ventas[c], errors='coerce').fillna(0)
        
        total_ganancia = df_ventas["Ganancia_Real_USD"].sum()
        total_gastos = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Utilidad Bruta", f"$ {total_ganancia:,.2f}")
        c2.metric("Gastos Fijos", f"$ {total_gastos:,.2f}")
        c3.metric("Balance Neto", f"$ {(total_ganancia - total_gastos):,.2f}")
        
        st.divider()
        st.subheader("🏗️ Carga por Impresora (Órdenes Activas)")
        if not df_prod.empty:
            pendientes = df_prod[df_prod["Estado"] != "Listo para Entrega"]
            if not pendientes.empty:
                st.bar_chart(pendientes["Impresora"].value_counts())
            else:
                st.info("No hay trabajos en cola.")
        
        st.subheader("⚠️ Alertas de Almacén")
        bajo = df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])]
        if not bajo.empty:
            st.error("⚠️ Reponer: " + ", ".join(bajo["Material"].tolist()))
    else:
        st.info("Sin registros suficientes para estadísticas.")

# --- MÓDULO: CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    t1, t2 = st.tabs(["➕ Registrar Cliente", "📋 Cartera y Búsqueda"])
    with t1:
        with st.form("form_clientes"):
            nom = st.text_input("Nombre o Razón Social")
            tel = st.text_input("WhatsApp / Teléfono")
            proc = st.selectbox("¿Cómo nos contactó?", ["Instagram", "WhatsApp", "Recomendado", "TikTok", "Publicidad"])
            if st.form_submit_button("Guardar"):
                if nom:
                    nuevo_c = pd.DataFrame([[nom, tel, proc, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)
                    df_clientes = pd.concat([df_clientes, nuevo_c], ignore_index=True)
                    guardar_datos(df_clientes, CSV_CLIENTES)
                    st.success("¡Cliente guardado!")
                    st.rerun()
    with t2:
        busqueda = st.text_input("🔍 Buscar por nombre...")
        if busqueda:
            df_f = df_clientes[df_clientes["Nombre"].str.contains(busqueda, case=False, na=False)]
            st.dataframe(df_f, use_container_width=True)
        else:
            st.dataframe(df_clientes, use_container_width=True)

# --- MÓDULO: PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Control de Máquinas")
    t1, t2 = st.tabs(["🆕 Nueva Orden", "🛤️ Taller Activo"])
    with t1:
        with st.form("ot"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t = st.text_area("Trabajo (Ej: 100 Tarjetas mate)")
            imp = st.selectbox("Asignar Impresora", ["Impresora 1 (Láser)", "Impresora 2 (Inyección)", "Impresora 3 (Gran Formato)"])
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Lanzar a Taller"):
                new_id = len(df_prod) + 1
                row = pd.DataFrame([[new_id, datetime.now().strftime("%d/%m"), c, t, imp, "En Cola", prio]], columns=COL_PRODUCCION)
                df_prod = pd.concat([df_prod, row], ignore_index=True)
                guardar_datos(df_prod, CSV_PRODUCCION)
                st.success(f"Orden #{new_id} enviada.")
                st.rerun()
    with t2:
        for imp_name in ["Impresora 1 (Láser)", "Impresora 2 (Inyección)", "Impresora 3 (Gran Formato)"]:
            st.subheader(f"📟 {imp_name}")
            maquina_df = df_prod[(df_prod["Impresora"] == imp_name) & (df_prod["Estado"] != "Listo para Entrega")]
            if not maquina_df.empty:
                for i, r in maquina_df.iterrows():
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**#{r['ID']} - {r['Cliente']}**: {r['Trabajo']}")
                    n_st = col2.selectbox("Estado", ["En Cola", "Imprimiendo", "Acabado", "Listo para Entrega"], key=f"s_{i}")
                    if col2.button("Update", key=f"b_{i}"):
                        df_prod.at[i, "Estado"] = n_st
                        guardar_datos(df_prod, CSV_PRODUCCION)
                        st.rerun()
            else: st.write("✅ Sin pendientes.")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("form_ventas"):
            cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
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
                idx = df_stock.index[df_stock["Material"] == ins][0]
                df_stock.at[idx, "Cantidad"] -= can
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Venta registrada. Ganancia: ${gan:.2f}")
                st.rerun()

# --- MÓDULO: FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Análisis de Rentabilidad")
    st.subheader("💰 Gastos Fijos Mensuales")
    with st.form("g"):
        c1, c2 = st.columns(2)
        con = c1.text_input("Concepto (Luz, Local, etc)")
        mon = c2.number_input("Monto USD", min_value=0.0)
        if st.form_submit_button("Añadir Gasto"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS)
            st.rerun()
    st.table(df_gastos)
    total_f = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    st.metric("Meta Mensual de Utilidad", f"$ {total_f:,.2f}")

# --- MÓDULO: INVENTARIO PRO (RECUPERADO) ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario y Costos Reales")
    t1, t2, t3 = st.tabs(["📋 Stock Actual", "🛒 Nueva Compra", "✏️ Ajustes"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n = st.text_input("Material")
            c = st.number_input("Cantidad", min_value=0.1)
            p = st.number_input("Precio Factura USD", min_value=0.0)
            c1, c2 = st.columns(2)
            iva = c1.checkbox("¿Pagaste IVA (16%)?")
            igtf = c2.number_input("% Comisión/IGTF", value=3.0)
            if st.form_submit_button("Ingresar"):
                total = p
                if iva: total *= 1.16
                total *= (1 + (igtf/100))
                c_u = total / c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"] == n][0]
                    df_stock.at[idx, "Costo_Unit_USD"] = c_u
                    df_stock.at[idx, "Cantidad"] += c
                else:
                    nueva = pd.DataFrame([[n, c, "Unid", c_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Stock actualizado.")
                st.rerun()
    with t3:
        if not df_stock.empty:
            m = st.selectbox("Seleccionar", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == m][0]
            nc = st.number_input("Stock Real", value=float(df_stock.at[idx, "Cantidad"]))
            if st.button("Actualizar"):
                df_stock.at[idx, "Cantidad"] = nc
                guardar_datos(df_stock, CSV_STOCK)
                st.success("Ajuste hecho.")

# --- MÓDULO: ANALIZADOR ---
elif menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador CMYK")
    archivos = st.file_uploader("Subir", type=["jpg", "png", "pdf"], accept_multiple_files=True)
    if archivos:
        res = []
        for a in archivos:
            if a.type == "application/pdf":
                doc = fitz.open(stream=a.read(), filetype="pdf")
                for i in range(len(doc)):
                    pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    d = analizar_cmyk_pro(img)
                    d["Archivo"] = f"{a.name} (P{i+1})"
                    res.append(d)
            else:
                img = Image.open(a)
                d = analizar_cmyk_pro(img)
                d["Archivo"] = a.name
                res.append(d)
        st.dataframe(pd.DataFrame(res), use_container_width=True)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Nro de Hoja (ej: 088)")
    if hoja:
        ruta = f"{CARPETA_MANUALES}/{hoja.zfill(3)}.txt"
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f: st.info(f.read())
        else:
            txt = st.text_area("Crear nuevo:")
            if st.button("Guardar"):
                if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
                with open(ruta, "w", encoding="utf-8") as f: f.write(txt)
                st.success("Guardado.")
