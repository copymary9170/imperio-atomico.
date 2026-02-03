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
                if col not in df.columns: df[col] = "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

df_stock = cargar_datos(CSV_STOCK, COL_STOCK)
df_clientes = cargar_datos(CSV_CLIENTES, COL_CLIENTES)
df_prod = cargar_datos(CSV_PRODUCCION, COL_PRODUCCION)
df_gastos = cargar_datos(CSV_GASTOS, COL_GASTOS)
df_ventas = cargar_datos(CSV_VENTAS, COL_VENTAS)
df_tintas = cargar_datos(CSV_TINTAS, COL_TINTAS)

# Inicializar tintas si está vacío
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

# --- CLIENTES (CON BUSCADOR) ---
if menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    t1, t2 = st.tabs(["➕ Nuevo Cliente", "🔍 Buscar y Lista"])
    with t1:
        with st.form("nc"):
            n, w, p = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "TikTok", "Otro"])
            if st.form_submit_button("Guardar"):
                df_clientes = pd.concat([df_clientes, pd.DataFrame([[n, w, p, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)], ignore_index=True)
                guardar_datos(df_clientes, CSV_CLIENTES); st.rerun()
    with t2:
        bus = st.text_input("🔍 Buscar por nombre...")
        f = df_clientes[df_clientes["Nombre"].str.contains(bus, case=False, na=False)] if bus else df_clientes
        st.dataframe(f, use_container_width=True)

# --- PRODUCCIÓN (COMPLETA) ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Taller Ativo")
    t1, t2 = st.tabs(["🆕 Nueva Orden", "🛤️ Línea de Producción"])
    with t1:
        with st.form("no"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t = st.text_area("Descripción del Trabajo")
            imp = st.selectbox("Máquina", df_tintas["Impresora"].unique())
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Lanzar a Taller"):
                new_id = len(df_prod) + 1
                row = pd.DataFrame([[new_id, datetime.now().strftime("%d/%m"), c, t, imp, "En Cola", prio]], columns=COL_PRODUCCION)
                df_prod = pd.concat([df_prod, row], ignore_index=True)
                guardar_datos(df_prod, CSV_PRODUCCION); st.rerun()
    with t2:
        for m in df_tintas["Impresora"].unique():
            st.subheader(f"🖨️ {m}")
            maquina_df = df_prod[(df_prod["Impresora"] == m) & (df_prod["Estado"] != "Listo")]
            if not maquina_df.empty:
                for i, r in maquina_df.iterrows():
                    c1, c2, c3 = st.columns([1, 3, 1])
                    p_emoji = "🔴" if r['Prioridad'] == "Urgente" else "⚪"
                    c1.write(f"**#{r['ID']}** {p_emoji}")
                    c2.write(f"**{r['Cliente']}**: {r['Trabajo']}")
                    n_st = c3.selectbox("Estado", ["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo"], key=f"st_{i}", index=["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo"].index(r['Estado']))
                    if n_st != r['Estado']:
                        df_prod.at[i, "Estado"] = n_st
                        guardar_datos(df_prod, CSV_PRODUCCION); st.rerun()
            else: st.write("✅ Sin pedidos.")

# --- ANALIZADOR Y COTIZADOR ---
elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Analizador de Costos")
    col_a, col_b = st.columns([2, 1])
    with col_b:
        imp_sel = st.selectbox("Impresora:", df_tintas["Impresora"].unique())
        row_t = df_tintas[df_tintas["Impresora"] == imp_sel].iloc[0]
        c_ml = row_t["Precio_USD"] / row_t["ML_Total"]
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "N/A"
        p_costo = float(df_stock.loc[df_stock["Material"] == mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "N/A" else st.number_input("Costo Manual", value=0.1)
        margen = st.slider("Ganancia %", 20, 500, 100)
    with col_a:
        archs = st.file_uploader("Subir archivos", type=["jpg", "png", "pdf"], accept_multiple_files=True)
        if archs:
            results = []
            for a in archs:
                if a.type == "application/pdf":
                    doc = fitz.open(stream=a.read(), filetype="pdf")
                    for i in range(len(doc)):
                        pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        res = analizar_cmyk_pro(img); res["Archivo"] = f"{a.name} (P{i+1})"; results.append(res)
                else:
                    img = Image.open(a); res = analizar_cmyk_pro(img); res["Archivo"] = a.name; results.append(res)
            df_res = pd.DataFrame(results)
            df_res["Costo Tinta"] = df_res["ml_estimados"] * c_ml
            df_res["Total"] = df_res["Costo Tinta"] + p_costo
            df_res["Precio"] = df_res["Total"] * (1 + margen/100)
            st.dataframe(df_res.style.format({"C":"{:.1f}%","M":"{:.1f}%","Y":"{:.1f}%","K":"{:.1f}%","Costo Tinta":"${:.3f}","Total":"${:.2f}","Precio":"${:.2f}"}))

# --- RESTO DE MÓDULOS (VENTAS, INVENTARIO, GASTOS, CONFIG, MANUALES) ---
# ... (Igual que el anterior pero asegurando que lean bien los CSV) ...
elif menu == "⚙️ Configuración":
    st.title("⚙️ Ajuste de Precios por Inflación")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios de Tintas"):
        guardar_datos(ed, CSV_TINTAS); st.success("¡Precios actualizados!"); st.rerun()

elif menu == "💰 Ventas":
    st.title("💰 Cobros y Ventas")
    with st.form("v"):
        c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
        i = st.selectbox("Insumo", df_stock["Material"].unique()) if not df_stock.empty else st.text_input("Insumo")
        mon = st.number_input("Cobrado USD", min_value=0.0)
        if st.form_submit_button("Vender"):
            costo = float(df_stock.loc[df_stock["Material"]==i, "Costo_Unit_USD"].values[0]) if i in df_stock["Material"].values else 0
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), c, i, mon, costo, mon-costo]], columns=COL_VENTAS)], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS); st.success("Venta guardada"); st.rerun()

elif menu == "📊 Dashboard":
    st.title("📊 Resumen")
    total_g = pd.to_numeric(df_ventas["Ganancia_Real_USD"], errors='coerce').sum()
    total_f = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    st.metric("Utilidad Bruta", f"$ {total_g:,.2f}")
    st.metric("Balance", f"$ {total_g-total_f:,.2f}")
    st.divider()
    st.subheader("⚠️ Stock Bajo")
    st.table(df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])])

elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    with st.form("gf"):
        con, mon = st.text_input("Concepto"), st.number_input("Monto", min_value=0.0)
        if st.form_submit_button("Añadir"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS); st.rerun()
    st.table(df_gastos)

elif menu == "📦 Inventario Pro":
    st.title("📦 Almacén")
    st.dataframe(df_stock, use_container_width=True)
    with st.expander("Añadir Compra"):
        with st.form("ac"):
            n, c, p = st.text_input("Material"), st.number_input("Cant"), st.number_input("Precio")
            if st.form_submit_button("Cargar"):
                cu = p/c
                df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", cu, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK); st.rerun()

elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    h = st.text_input("Hoja #")
    if h:
        p = f"{CARPETA_MANUALES}/{h.zfill(3)}.txt"
        if os.path.exists(p): st.info(open(p).read())
        elif st.button("Crear"):
            if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
            with open(p, "w") as f: f.write("Manual nuevo.")
