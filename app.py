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
        "C": float(np.clip(c, 0, 1).mean() * 100), 
        "M": float(np.clip(m, 0, 1).mean() * 100),
        "Y": float(np.clip(y, 0, 1).mean() * 100), 
        "K": float(k.mean() * 100)
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
        st.subheader("🏗️ Carga de Trabajo por Máquina")
        if not df_prod.empty:
            pendientes = df_prod[df_prod["Estado"] != "Listo para Entrega"]
            if not pendientes.empty:
                st.bar_chart(pendientes["Impresora"].value_counts())
            else:
                st.info("Todo al día. No hay trabajos pendientes.")
    else:
        st.info("Sin registros suficientes.")

# --- MÓDULO: CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestión de Clientes")
    t1, t2 = st.tabs(["➕ Registrar Cliente", "📋 Cartera"])
    with t1:
        with st.form("form_clientes"):
            nom = st.text_input("Nombre / Empresa")
            tel = st.text_input("WhatsApp")
            proc = st.selectbox("Origen", ["Instagram", "WhatsApp", "Recomendado", "TikTok", "Publicidad"])
            if st.form_submit_button("Guardar"):
                if nom:
                    nuevo_c = pd.DataFrame([[nom, tel, proc, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)
                    df_clientes = pd.concat([df_clientes, nuevo_c], ignore_index=True)
                    guardar_datos(df_clientes, CSV_CLIENTES)
                    st.success("¡Cliente guardado!")
                    st.rerun()
    with t2:
        busqueda = st.text_input("🔍 Buscar cliente...")
        df_f = df_clientes[df_clientes["Nombre"].str.contains(busqueda, case=False, na=False)] if busqueda else df_clientes
        st.dataframe(df_f, use_container_width=True)

# --- MÓDULO: PRODUCCIÓN (RESTAURADO) ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Control de Máquinas")
    MIS_IMPRESORAS = ["Epson L1250 (Sublimación)", "HP Smart Tank 580w (Inyección)", "HP Deskjet J210a (Cartuchos)"]
    t1, t2 = st.tabs(["🆕 Nueva Orden", "🛤️ Taller Activo"])
    
    with t1:
        with st.form("ot"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t = st.text_area("Trabajo")
            imp = st.selectbox("Asignar a", MIS_IMPRESORAS)
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Lanzar"):
                new_id = len(df_prod) + 1
                row = pd.DataFrame([[new_id, datetime.now().strftime("%d/%m"), c, t, imp, "En Cola", prio]], columns=COL_PRODUCCION)
                df_prod = pd.concat([df_prod, row], ignore_index=True)
                guardar_datos(df_prod, CSV_PRODUCCION)
                st.success("Orden enviada a cola.")
                st.rerun()
    
    with t2:
        # Aquí restauramos la vista detallada por impresora
        for imp_name in MIS_IMPRESORAS:
            st.markdown(f"### 🖨️ {imp_name}")
            maquina_df = df_prod[(df_prod["Impresora"] == imp_name) & (df_prod["Estado"] != "Listo para Entrega")]
            if not maquina_df.empty:
                for i, r in maquina_df.iterrows():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        p_emoji = "🔴" if r['Prioridad'] == "Urgente" else "⚪"
                        st.write(f"{p_emoji} **#{r['ID']} - {r['Cliente']}**: {r['Trabajo']}")
                    with col2:
                        n_st = st.selectbox("Estado", ["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo para Entrega"], key=f"s_{i}", index=["En Cola", "Diseño", "Imprimiendo", "Acabado", "Listo para Entrega"].index(r['Estado']))
                        if st.button("Actualizar", key=f"b_{i}"):
                            df_prod.at[i, "Estado"] = n_st
                            guardar_datos(df_prod, CSV_PRODUCCION)
                            st.rerun()
            else:
                st.write("✨ Sin pedidos en cola.")
            st.divider()

# --- MÓDULO: FINANZAS PRO ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Análisis de Gastos")
    with st.form("g"):
        con = st.text_input("Concepto (Alquiler, Luz, etc.)")
        mon = st.number_input("Monto USD", min_value=0.0)
        if st.form_submit_button("Añadir Gasto"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS)
            st.rerun()
    st.table(df_gastos)
    total_f = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
    st.metric("Punto de Equilibrio Mensual", f"$ {total_f:,.2f}")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    if not df_stock.empty:
        with st.form("form_ventas"):
            cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            ins = st.selectbox("Material", df_stock["Material"].unique())
            can = st.number_input("Cantidad usada", min_value=0.01)
            mon = st.number_input("Precio Cobrado (USD)", min_value=0.0)
            if st.form_submit_button("Cobrar"):
                costo_u = float(df_stock.loc[df_stock["Material"] == ins, "Costo_Unit_USD"].values[0])
                gan = mon - (mon * 0.03) - (can * costo_u)
                nueva = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, mon, mon*0.03, gan, "Socia"]], columns=COL_VENTAS)
                df_ventas = pd.concat([df_ventas, nueva], ignore_index=True)
                guardar_datos(df_ventas, CSV_VENTAS)
                # Restar stock automáticamente
                idx = df_stock.index[df_stock["Material"] == ins][0]
                df_stock.at[idx, "Cantidad"] -= can
                guardar_datos(df_stock, CSV_STOCK)
                st.success(f"Venta guardada. Ganancia: ${gan:.2f}")
                st.rerun()

# --- MÓDULO: INVENTARIO PRO ---
elif menu == "📦 Inventario Pro":
    st.title("📦 Inventario")
    t1, t2 = st.tabs(["📋 Stock", "🛒 Compras"])
    with t1: st.dataframe(df_stock, use_container_width=True)
    with t2:
        with st.form("compra"):
            n = st.text_input("Material")
            c = st.number_input("Cantidad", min_value=0.1)
            p = st.number_input("Total Pagado (USD)", min_value=0.0)
            if st.form_submit_button("Ingresar"):
                c_u = p / c
                if n in df_stock["Material"].values:
                    idx = df_stock.index[df_stock["Material"] == n][0]
                    df_stock.at[idx, "Cantidad"] += c
                    df_stock.at[idx, "Costo_Unit_USD"] = c_u
                else:
                    nueva = pd.DataFrame([[n, c, "Unid", c_u, 5]], columns=COL_STOCK)
                    df_stock = pd.concat([df_stock, nueva], ignore_index=True)
                guardar_datos(df_stock, CSV_STOCK)
                st.rerun()

# --- MÓDULO: ANALIZADOR (CORREGIDO) ---
elif menu == "🎨 Analizador Masivo":
    st.title("🎨 Analizador CMYK de Precisión")
    archivos = st.file_uploader("Subir archivos", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)
    if archivos:
        resultados = []
        for archivo in archivos:
            try:
                if archivo.type == "application/pdf":
                    doc = fitz.open(stream=archivo.read(), filetype="pdf")
                    for i in range(len(doc)):
                        pix = doc.load_page(i).get_pixmap(colorspace=fitz.csRGB)
                        # Paréntesis y argumentos corregidos
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        res = analizar_cmyk_pro(img)
                        res["Archivo"] = f"{archivo.name} (P{i+1})"
                        resultados.append(res)
                else:
                    img = Image.open(archivo)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = archivo.name
                    resultados.append(res)
            except Exception as e:
                st.error(f"Error con {archivo.name}: {e}")
        
        df_res = pd.DataFrame(resultados)
        if not df_res.empty:
            for col in ["C", "M", "Y", "K"]:
                df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
            df_res["Total %"] = df_res["C"] + df_res["M"] + df_res["Y"] + df_res["K"]
            st.dataframe(df_res.style.format("{:.1f}%", subset=["C", "M", "Y", "K", "Total %"]), use_container_width=True)

# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Protocolos")
    hoja = st.text_input("Hoja #")
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
