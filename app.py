import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF para PDFs
from datetime import datetime

# --- 1. CONFIGURACIÓN DEL SISTEMA ---
st.set_page_config(page_title="Imperio Atómico - Sistema Integral", layout="wide")

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

# Cargas iniciales
df_stock = cargar_datos(*archivos["stock"])
df_clientes = cargar_datos(*archivos["clientes"])
df_prod = cargar_datos(*archivos["produccion"])
df_gastos = cargar_datos(*archivos["gastos"])
df_ventas = cargar_datos(*archivos["ventas"])
df_tintas = cargar_datos(*archivos["tintas"])
df_conf = cargar_datos(*archivos["config"])

# Tasas
if df_conf.empty:
    df_conf = pd.DataFrame([["Tasa_BCV", 36.50], ["Tasa_Binance", 45.00]], columns=["Parametro", "Valor"])
    guardar_datos(df_conf, archivos["config"][0])
t_bcv = float(df_conf.loc[df_conf["Parametro"] == "Tasa_BCV", "Valor"].values[0])
t_bin = float(df_conf.loc[df_conf["Parametro"] == "Tasa_Binance", "Valor"].values[0])

# --- 3. MANUALES (Base de datos interna) ---
manuales_db = [
    {"titulo": "Limpieza de Cabezal Epson L1250", "cat": "Mantenimiento", "contenido": "Manten presionado el botón de tinta 5 segundos hasta que el power parpadee."},
    {"titulo": "Error E3 HP Smart Tank", "cat": "Errores", "contenido": "Atasco de carro. Revisar que no haya trozos de papel o la cinta encoder sucia."},
    {"titulo": "Reset Cartucho HP J210a", "cat": "Reseteos", "contenido": "Limpiar contactos con borrador blanco o alcohol isopropílico."},
    {"titulo": "Prueba de Inyectores CMYK", "cat": "Diagnóstico", "contenido": "Realizar test desde el software para verificar corte de líneas por color."}
]

# --- 4. FUNCIONES TÉCNICAS ---
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
        return img, {"C": c.mean()*1.2, "M": m.mean()*1.2, "Y": y.mean()*1.2, "K": k.mean()*1.2}
    except: return None, None

# --- 5. NAVEGACIÓN ---
menu = st.sidebar.radio("Atómica Master:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "📈 Finanzas Pro", "🎨 Analizador", "💰 Ventas", "🔍 Manuales", "⚙️ Configuración"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    v_t = pd.to_numeric(df_ventas["Monto_USD"], errors='coerce').sum()
    g_t = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos Totales", f"$ {v_t:,.2f}")
    c2.metric("Gastos Fijos", f"$ {g_t:,.2f}")
    c3.metric("Utilidad Neto", f"$ {(v_t - g_t):,.2f}")
    st.divider()
    st.subheader("⚠️ Stock Crítico")
    st.dataframe(df_stock[pd.to_numeric(df_stock["Cantidad"]) <= pd.to_numeric(df_stock["Minimo_Alerta"])])

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Clientes")
    with st.expander("➕ Nuevo Cliente"):
        with st.form("fc"):
            n, w, p = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "TikTok"])
            if st.form_submit_button("Guardar"):
                df_clientes = pd.concat([df_clientes, pd.DataFrame([[n, w, p, datetime.now().strftime("%Y-%m-%d")]], columns=archivos["clientes"][1])], ignore_index=True)
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
            p = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Añadir"):
                df_prod = pd.concat([df_prod, pd.DataFrame([[len(df_prod)+1, datetime.now().strftime("%d/%m"), c, t, m, "En Cola", p]], columns=archivos["produccion"][1])], ignore_index=True)
                guardar_datos(df_prod, archivos["produccion"][0]); st.rerun()
    
    # Mostrar por impresora
    for maq in df_tintas["Impresora"].unique():
        st.subheader(f"🖨️ {maq}")
        filas = df_prod[df_prod["Impresora"] == maq]
        for i, r in filas.iterrows():
            col1, col2, col3 = st.columns([1,3,1])
            col1.write(f"#{r['ID']}")
            col2.write(f"**{r['Cliente']}**: {r['Trabajo']} ({r['Prioridad']})")
            nst = col3.selectbox("Estado", ["En Cola", "Diseño", "Imprimiendo", "Listo"], key=f"p_{i}", index=["En Cola", "Diseño", "Imprimiendo", "Listo"].index(r['Estado']))
            if nst != r['Estado']:
                df_prod.at[i, "Estado"] = nst
                guardar_datos(df_prod, archivos["produccion"][0]); st.rerun()

# --- INVENTARIO ---
elif menu == "📦 Inventario":
    st.title("📦 Almacén de Insumos")
    t1, t2 = st.tabs(["📋 Ver Stock", "✏️ Ajustar Cantidad"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("aj"):
            mat, cant, prec = st.text_input("Insumo"), st.number_input("Cantidad"), st.number_input("Precio Total USD")
            tasa = st.selectbox("Tasa Compra", ["Binance", "BCV"])
            if st.form_submit_button("Actualizar"):
                p_u = (prec * t_bcv / t_bin) if tasa == "BCV" else prec
                if mat in df_stock["Material"].values:
                    df_stock.loc[df_stock["Material"]==mat, "Cantidad"] = cant
                    df_stock.loc[df_stock["Material"]==mat, "Costo_Unit_USD"] = p_u/cant if cant>0 else 0
                else:
                    df_stock = pd.concat([df_stock, pd.DataFrame([[mat, cant, "Unid", p_u/cant, 5]], columns=archivos["stock"][1])], ignore_index=True)
                guardar_datos(df_stock, archivos["stock"][0]); st.rerun()

# --- FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Control de Gastos Fijos")
    with st.form("gf"):
        concepto = st.text_input("Concepto (Alquiler, Luz, Internet...)")
        monto = st.number_input("Monto Mensual USD")
        if st.form_submit_button("Registrar Gasto"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[concepto, monto]], columns=archivos["gastos"][1])], ignore_index=True)
            guardar_datos(df_gastos, archivos["gastos"][0]); st.rerun()
    st.table(df_gastos)

# --- ANALIZADOR ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador Atómico de Costos")
    c1, c2 = st.columns([2,1])
    with c2:
        m_sel = st.selectbox("Máquina:", df_tintas["Impresora"].unique())
        mat_sel = st.selectbox("Papel:", df_stock["Material"].unique()) if not df_stock.empty else "Manual"
        p_mat = float(df_stock.loc[df_stock["Material"]==mat_sel, "Costo_Unit_USD"].values[0]) if mat_sel != "Manual" else 0.1
        margen = st.slider("Ganancia %", 20, 500, 100)
    with c1:
        f = st.file_uploader("Subir diseño", type=["jpg","png","pdf"])
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

# --- VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Ventas")
    with st.form("v"):
        cl, ins, mon = st.text_input("Cliente"), st.text_input("Trabajo realizado"), st.number_input("Cobrado USD")
        if st.form_submit_button("Registrar Venta"):
            df_ventas = pd.concat([df_ventas, pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cl, ins, mon, 0, mon]], columns=archivos["ventas"][1])], ignore_index=True)
            guardar_datos(df_ventas, archivos["ventas"][0]); st.success("¡Venta Guardada!"); st.rerun()
    st.dataframe(df_ventas.tail(10))

# --- MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca de Manuales")
    bus_man = st.text_input("🔍 Buscar por título o categoría...")
    filtro = [m for m in manuales_db if bus_man.lower() in m["titulo"].lower() or bus_man.lower() in m["cat"].lower()]
    for m in filtro:
        with st.expander(f"{m['cat']} - {m['titulo']}"):
            st.write(m["contenido"])

# --- CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("⚙️ Configuración y Tasas")
    c1, c2 = st.columns(2)
    t_bcv = c1.number_input("Tasa BCV", value=t_bcv)
    t_bin = c2.number_input("Tasa Binance", value=t_bin)
    if st.button("Actualizar Tasas"):
        df_conf.loc[df_conf["Parametro"]=="Tasa_BCV","Valor"]=t_bcv
        df_conf.loc[df_conf["Parametro"]=="Tasa_Binance","Valor"]=t_bin
        guardar_datos(df_conf, archivos["config"][0]); st.rerun()
    st.divider()
    st.subheader("💧 Costos de Tinta e Insumos")
    ed = st.data_editor(df_tintas, use_container_width=True)
    if st.button("Guardar Cambios Tintas"):
        guardar_datos(ed, archivos["tintas"][0]); st.success("Precios actualizados")
