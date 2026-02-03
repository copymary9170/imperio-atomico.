import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF para manejar PDFs
from datetime import datetime

# --- 1. CONFIGURACIÓN DEL SISTEMA ---
st.set_page_config(page_title="Imperio Atómico - Master", layout="wide")

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
    "tintas": ("tintas_cmyk_v5.csv", ["Impresora", "Componente", "Precio_Ref", "ML_Envase", "Tasa_Compra"]),
    "config": ("config_tasas.csv", ["Parametro", "Valor"])
}

def cargar_datos(archivo, columnas):
    try:
        if os.path.exists(archivo) and os.path.getsize(archivo) > 0:
            df = pd.read_csv(archivo)
            for col in columnas:
                if col not in df.columns: df[col] = 0 if "USD" in col or "Precio" in col else "N/A"
            return df[columnas]
        return pd.DataFrame(columns=columnas)
    except: return pd.DataFrame(columns=columnas)

def guardar_datos(df, archivo): df.to_csv(archivo, index=False)

# Cargas iniciales
df_stock = cargar_datos(*archivos["stock"])
df_clientes = cargar_datos(*archivos["clientes"])
df_prod = cargar_datos(*archivos["produccion"])
df_gastos = cargar_datos(*archivos["gastos"])
df_ventas = cargar_datos(*archivos["ventas"])
df_tintas = cargar_datos(*archivos["tintas"])
df_conf = cargar_datos(*archivos["config"])

# Inicializar Tasas (BCV / Binance)
if df_conf.empty:
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, archivos["config"][0])

t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

# Inicializar Tintas CMYK (4 para tanques, 2 para cartuchos)
if df_tintas.empty:
    data = [
        ["Epson L1250", "Cian", 20.0, 1000, "Binance"], ["Epson L1250", "Magenta", 20.0, 1000, "Binance"],
        ["Epson L1250", "Amarillo", 20.0, 1000, "Binance"], ["Epson L1250", "Negro", 20.0, 1000, "Binance"],
        ["HP Smart Tank 580w", "Cian", 20.0, 70, "BCV"], ["HP Smart Tank 580w", "Magenta", 20.0, 70, "BCV"],
        ["HP Smart Tank 580w", "Amarillo", 20.0, 70, "BCV"], ["HP Smart Tank 580w", "Negro", 20.0, 90, "BCV"],
        ["HP Deskjet J210a", "Tricolor", 40.0, 15, "BCV"], ["HP Deskjet J210a", "Negro", 40.0, 12.4, "BCV"]
    ]
    df_tintas = pd.DataFrame(data, columns=archivos["tintas"][1])
    guardar_datos(df_tintas, archivos["tintas"][0])

# --- 3. LÓGICA DE CÁLCULOS ---
def get_costo_ml(imp, comp):
    try:
        row = df_tintas[(df_tintas["Impresora"] == imp) & (df_tintas["Componente"].str.contains(comp, case=False))].iloc[0]
        p_real = (float(row["Precio_Ref"]) * t_bcv / t_bin) if row["Tasa_Compra"] == "BCV" else float(row["Precio_Ref"])
        return p_real / float(row["ML_Envase"])
    except: return 0.0

def analizar_cmyk_seguro(file):
    try:
        if file.type == "application/pdf":
            doc = fitz.open(stream=file.read(), filetype="pdf")
            pix = doc.load_page(0).get_pixmap(colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(file).convert("RGB")
        
        pix_arr = np.array(img) / 255.0
        k = 1 - np.max(pix_arr, axis=2)
        c = (1-pix_arr[:,:,0]-k)/(1-k+1e-9)
        m = (1-pix_arr[:,:,1]-k)/(1-k+1e-9)
        y = (1-pix_arr[:,:,2]-k)/(1-k+1e-9)
        f = 1.2 # ml por A4 al 100% cobertura
        return img, {"C": c.mean()*f, "M": m.mean()*f, "Y": y.mean()*f, "K": k.mean()*f}
    except Exception as e:
        st.error(f"Error procesando archivo: {e}")
        return None, None

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Atómica Navigation:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "📈 Finanzas Pro", "🎨 Analizador", "💰 Ventas", "⚙️ Config"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    v_total = pd.to_numeric(df_ventas["Monto_USD"], errors='coerce').sum()
    g_total = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas Totales", f"$ {v_total:,.2f}")
    c2.metric("Gastos Fijos", f"$ {g_total:,.2f}")
    c3.metric("Utilidad Estimada", f"$ {(v_total - g_total):,.2f}")
    st.divider()
    st.subheader("⚠️ Stock por Agotarse")
    st.dataframe(df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])])

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    with st.expander("➕ Registrar"):
        with st.form("fc"):
            n, w, o = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "TikTok"])
            if st.form_submit_button("Guardar"):
                df_clientes = pd.concat([df_clientes, pd.DataFrame([[n, w, o, datetime.now().strftime("%Y-%m-%d")]], columns=archivos["clientes"][1])], ignore_index=True)
                guardar_datos(df_clientes, archivos["clientes"][0]); st.rerun()
    bus = st.text_input("🔍 Buscar cliente...")
    st.dataframe(df_clientes[df_clientes["Nombre"].str.contains(bus, case=False, na=False)] if bus else df_clientes)

# --- PRODUCCIÓN ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Línea de Producción")
    with st.expander("🆕 Nueva Orden"):
        with st.form("no"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t, m = st.text_input("Trabajo"), st.selectbox("Impresora", df_tintas["Impresora"].unique())
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], value="Normal")
            if st.form_submit_button("Crear"):
                df_prod = pd.concat([df_prod, pd.DataFrame([[len(df_prod)+1, datetime.now().strftime("%d/%m"), c, t, m, "En Cola", prio]], columns=archivos["produccion"][1])], ignore_index=True)
                guardar_datos(df_prod, archivos["produccion"][0]); st.rerun()
    
    for maq in df_tintas["Impresora"].unique():
        st.subheader(f"🖨️ {maq}")
        filas = df_prod[(df_prod["Impresora"] == maq) & (df_prod["Estado"] != "Listo")]
        for i, r in filas.iterrows():
            col1, col2, col3 = st.columns([1,3,1])
            col1.write(f"#{r['ID']} {'🔴' if r['Prioridad']=='Urgente' else ''}")
            col2.write(f"**{r['Cliente']}**: {r['Trabajo']}")
            nst = col3.selectbox("Estado", ["En Cola", "Diseño", "Imprimiendo", "Listo"], key=f"p_{i}", index=["En Cola", "Diseño", "Imprimiendo", "Listo"].index(r['Estado']))
            if nst != r['Estado']:
                df_prod.at[i, "Estado"] = nst
                guardar_datos(df_prod, archivos["produccion"][0]); st.rerun()

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico CMYK")
    c_izq, c_der = st.columns([2,1])
    with c_der:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        mat_sel = st.selectbox("Material:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else st.number_input("Papel USD", value=0.1)
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c_izq:
        f = st.file_uploader("Subir diseño", type=["jpg", "png", "pdf"])
        if f:
            img, res = analizar_cmyk_seguro(f)
            if img:
                st.image(img, use_container_width=True)
                if "J210a" in m_sel:
                    c_t = (res["K"] * get_costo_ml(m_sel, "Negro")) + ((res["C"]+res["M"]+res["Y"]) * get_costo_ml(m_sel, "Tricolor"))
                else:
                    c_t = sum(res[col] * get_costo_ml(m_sel, c_name) for col, c_name in [("C","Cian"),("M","Magenta"),("Y","Amarillo"),("K","Negro")])
                
                pvp = (c_t + p_mat) * (1 + margen/100)
                st.metric("PVP Sugerido USD", f"$ {pvp:.2f}")
                st.metric("PVP Sugerido Bs", f"Bs. {pvp * t_bin:.2f}")

# --- FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Gastos Fijos")
    with st.form("gf"):
        con, mon = st.text_input("Concepto"), st.number_input("Monto USD")
        if st.form_submit_button("Añadir"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=archivos["gastos"][1])], ignore_index=True)
            guardar_datos(df_gastos, archivos["gastos"][0]); st.rerun()
    st.table(df_gastos)

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Config":
    st.title("⚙️ Ajustes de Inflación")
    c1, c2 = st.columns(2)
    nb = c1.number_input("Tasa BCV", value=t_bcv)
    np = c2.number_input("Tasa Binance", value=t_bin)
    if st.button("Actualizar Tasas"):
        df_conf.loc[df_conf["Parametro"]=="Tasa_BCV","Valor"]=nb
        df_conf.loc[df_conf["Parametro"]=="Tasa_Binance","Valor"]=np
        guardar_datos(df_conf, archivos["config"][0]); st.rerun()
    st.divider()
    st.subheader("💧 Detalle de Tintas (Cian, Magenta, Amarillo, Negro)")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Tintas"): guardar_datos(ed, archivos["tintas"][0]); st.rerun()

# --- INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Control de Almacén")
    t1, t2 = st.tabs(["📋 Stock", "✏️ Ajuste"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("aj"):
            m, c, p = st.text_input("Material"), st.number_input("Cant"), st.number_input("Precio Total USD")
            t = st.selectbox("Tasa de Compra", ["Binance", "BCV"])
            if st.form_submit_button("Actualizar"):
                pr = (p * t_bcv / t_bin) if t == "BCV" else p
                if m in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"]==m, "Cantidad"] = c
                    df_stock.loc[df_stock["Material"]==m, "Costo_Unit_USD"] = pr/c if c>0 else 0
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[m, c, "Unid", pr/c, 5]], columns=archivos["stock"][1])], ignore_index=True)
                guardar_datos(df_stock, archivos["stock"][0]); st.rerun()

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    with st.form("v"):
        cl, ins, mon = st.text_input("Cliente"), st.text_input("Insumo"), st.number_input("Monto Cobrado USD")
        if st.form_submit_button("Vender"):
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cl, ins, mon, 0, mon]], columns=archivos["ventas"][1])], ignore_index=True)
            guardar_datos(df_ventas, archivos["ventas"][0]); st.success("¡Vendido!"); st.rerun()
