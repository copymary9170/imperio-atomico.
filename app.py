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
    c, m, y = (1-r-k)/(1-k+1e-9), (1-g-k)/(1-k+1e-9), (1-b-k)/(1-k+1e-9)
    ml_total = (c.mean() + m.mean() + y.mean() + k.mean()) * 1.2
    return {"C": float(np.clip(c,0,1).mean()*100), "M": float(np.clip(m,0,1).mean()*100), "Y": float(np.clip(y,0,1).mean()*100), "K": float(k.mean()*100), "ml_estimados": ml_total}

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario Pro", "📈 Finanzas Pro", "🎨 Analizador y Cotizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    c1, c2, c3 = st.columns(3)
    ganancia = pd.to_numeric(df_ventas["Ganancia_Real_USD"], errors='coerce').sum()
    gastos = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    c1.metric("Utilidad Bruta", f"$ {ganancia:,.2f}")
    c2.metric("Gastos Fijos", f"$ {gastos:,.2f}")
    c3.metric("Neto", f"$ {(ganancia - gastos):,.2f}")
    
    st.divider()
    st.subheader("⚠️ Alertas de Stock Bajo")
    if not df_stock.empty:
        df_stock["Cantidad"] = pd.to_numeric(df_stock["Cantidad"], errors='coerce').fillna(0)
        df_stock["Minimo_Alerta"] = pd.to_numeric(df_stock["Minimo_Alerta"], errors='coerce').fillna(0)
        bajos = df_stock[df_stock["Cantidad"] <= df_stock["Minimo_Alerta"]]
        st.dataframe(bajos)

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    t1, t2 = st.tabs(["➕ Registrar", "🔍 Buscar"])
    with t1:
        with st.form("fc"):
            n, w, p = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "TikTok", "Otro"])
            if st.form_submit_button("Guardar"):
                df_clientes = pd.concat([df_clientes, pd.DataFrame([[n, w, p, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)], ignore_index=True)
                guardar_datos(df_clientes, CSV_CLIENTES); st.rerun()
    with t2:
        bus = st.text_input("🔍 Buscar cliente...")
        st.dataframe(df_clientes[df_clientes["Nombre"].str.contains(bus, case=False, na=False)] if bus else df_clientes)

# --- PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Taller")
    t1, t2 = st.tabs(["🆕 Nueva Orden", "🛤️ Taller Activo"])
    with t1:
        with st.form("ot"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t = st.text_area("Trabajo")
            imp = st.selectbox("Máquina", df_tintas["Impresora"].unique())
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Lanzar"):
                nid = len(df_prod) + 1
                df_prod = pd.concat([df_prod, pd.DataFrame([[nid, datetime.now().strftime("%d/%m"), c, t, imp, "En Cola", prio]], columns=COL_PRODUCCION)], ignore_index=True)
                guardar_datos(df_prod, CSV_PRODUCCION); st.rerun()
    with t2:
        for m in df_tintas["Impresora"].unique():
            st.subheader(f"🖨️ {m}")
            sub = df_prod[(df_prod["Impresora"] == m) & (df_prod["Estado"] != "Listo")]
            for i, r in sub.iterrows():
                col1, col2, col3 = st.columns([1, 3, 1])
                col1.write(f"#{r['ID']} {'🔴' if r['Prioridad']=='Urgente' else ''}")
                col2.write(f"**{r['Cliente']}**: {r['Trabajo']}")
                nst = col3.selectbox("Estado", ["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo"], key=f"s_{i}", index=["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo"].index(r['Estado']))
                if nst != r['Estado']:
                    df_prod.at[i, "Estado"] = nst
                    guardar_datos(df_prod, CSV_PRODUCCION); st.rerun()

# --- INVENTARIO PRO (CORREGIDO) ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario y Almacén")
    t1, t2, t3 = st.tabs(["📋 Stock Actual", "🛒 Nueva Compra", "✏️ Ajuste Manual"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n, c, p = st.text_input("Material"), st.number_input("Cantidad"), st.number_input("Precio Base USD")
            iva, igtf = st.checkbox("IVA 16%"), st.number_input("% IGTF", value=3.0)
            if st.form_submit_button("Cargar"):
                total = (p * 1.16 if iva else p) * (1 + igtf/100)
                cu = total/c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"]==n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = cu
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[n, c, "Unid", cu, 5]], columns=COL_STOCK)], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK); st.rerun()
    with t3:
        st.subheader("✏️ Corregir Inventario Físico")
        if not df_stock.empty:
            sel = st.selectbox("Material a ajustar", df_stock["Material"].unique())
            idx = df_stock.index[df_stock["Material"] == sel][0]
            nv = st.number_input("Cantidad Real en Estante", value=float(df_stock.at[idx, "Cantidad"]))
            if st.button("Aplicar Ajuste"):
                df_stock.at[idx, "Cantidad"] = nv
                guardar_datos(df_stock, CSV_STOCK); st.success("Ajustado"); st.rerun()

# --- ANALIZADOR Y COTIZADOR ---
elif menu == "🎨 Analizador y Cotizador":
    st.title("🎨 Analizador CMYK")
    c_a, c_b = st.columns([2, 1])
    with c_b:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        t_row = df_tintas[df_tintas["Impresora"] == m_sel].iloc[0]
        c_ml = t_row["Precio_USD"] / t_row["ML_Total"]
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_c = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else st.number_input("Costo Manual Material", value=0.1)
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c_a:
        archs = st.file_uploader("Subir archivos", type=["jpg", "png", "pdf"], accept_multiple_files=True)
        if archs:
            res = []
            for a in archs:
                if a.type == "application/pdf":
                    doc = fitz.open(stream=a.read(), filetype="pdf")
                    for i in range(len(doc)):
                        p = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                        res.append({**analizar_cmyk_pro(Image.frombytes("RGB", [p.width, p.height], p.samples)), "Archivo": f"{a.name} P{i+1}"})
                else: res.append({**analizar_cmyk_pro(Image.open(a)), "Archivo": a.name})
            df_r = pd.DataFrame(res)
            df_r["Costo Tinta"] = df_r["ml_estimados"] * c_ml
            df_r["Total"] = df_r["Costo Tinta"] + p_c
            df_r["Precio Sugerido"] = df_r["Total"] * (1 + margen/100)
            st.dataframe(df_r.style.format({"C":"{:.1f}%","M":"{:.1f}%","Y":"{:.1f}%","K":"{:.1f}%","Costo Tinta":"${:.3f}","Total":"${:.2f}","Precio Sugerido":"${:.2f}"}))

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registrar Venta")
    with st.form("v"):
        cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
        ins = st.selectbox("Material", df_stock["Material"].unique()) if not df_stock.empty else st.text_input("Material")
        mon = st.number_input("Monto Cobrado USD")
        if st.form_submit_button("Vender"):
            costo = float(df_stock.loc[df_stock["Material"]==ins, "Costo_Unit_USD"].values[0]) if not df_stock.empty and ins in df_stock["Material"].values else 0
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, mon, costo, mon-costo]], columns=COL_VENTAS)], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS)
            if not df_stock.empty and ins in df_stock["Material"].values:
                df_stock.loc[df_stock["Material"]==ins, "Cantidad"] -= 1
                guardar_datos(df_stock, CSV_STOCK)
            st.success("Venta guardada"); st.rerun()

# --- GASTOS / MANUALES / CONFIG ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    with st.form("gf"):
        con, mon = st.text_input("Concepto"), st.number_input("Monto")
        if st.form_submit_button("Añadir"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS); st.rerun()
    st.table(df_gastos)

elif menu == "⚙️ Configuración":
    st.title("⚙️ Precios de Tinta (Inflación)")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios"):
        guardar_datos(ed, CSV_TINTAS); st.success("Actualizado"); st.rerun()

elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    h = st.text_input("Hoja #")
    if h:
        p = f"{CARPETA_MANUALES}/{h.zfill(3)}.txt"
        if os.path.exists(p): st.info(open(p).read())
        elif st.button("Crear"):
            if not os.path.exists(CARPETA_MANUALES): os.makedirs(CARPETA_MANUALES)
            with open(p, "w") as f: f.write("Manual nuevo")
