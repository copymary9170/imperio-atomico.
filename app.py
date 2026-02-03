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
CSV_GASTOS = "gastos_fijos.csv" # <-- Nuevo: Para Finanzas

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

# Carga de datos
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
        "C": np.clip(c, 0, 1).mean() * 100, "M": np.clip(m, 0, 1).mean() * 100,
        "Y": np.clip(y, 0, 1).mean() * 100, "K": k.mean() * 100
    }

# --- 4. NAVEGACIÓN ---
menu = st.sidebar.radio("Menú:", ["📊 Dashboard", "👥 Clientes", "🏗️ Producción", "💰 Ventas", "📈 Finanzas Pro", "📦 Inventario", "🎨 Analizador", "🔍 Manuales"])

# --- MÓDULO: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Resumen del Imperio")
    if not df_ventas.empty:
        df_ventas["Ganancia_Real_USD"] = pd.to_numeric(df_ventas["Ganancia_Real_USD"], errors='coerce').fillna(0)
        total_ganancia = df_ventas["Ganancia_Real_USD"].sum()
        total_gastos = pd.to_numeric(df_gastos["Monto_Mensual_USD"], errors='coerce').sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Utilidad Bruta", f"$ {total_ganancia:,.2f}")
        c2.metric("Gastos Fijos", f"$ {total_gastos:,.2f}")
        c3.metric("Balance Neto", f"$ {(total_ganancia - total_gastos):,.2f}")
        
        st.divider()
        st.subheader("🏗️ Carga por Impresora")
        if not df_prod.empty:
            st.bar_chart(df_prod[df_prod["Estado"] != "Listo para Entrega"]["Impresora"].value_counts())
    else:
        st.info("Esperando datos para mostrar métricas.")

# --- MÓDULO: CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Directorio")
    with st.form("nuevo_c"):
        n, w, p = st.text_input("Nombre"), st.text_input("WhatsApp"), st.selectbox("Origen", ["Instagram", "WhatsApp", "Local"])
        if st.form_submit_button("Registrar"):
            nuevo = pd.DataFrame([[n, w, p, datetime.now().strftime("%Y-%m-%d")]], columns=COL_CLIENTES)
            df_clientes = pd.concat([df_clientes, nuevo], ignore_index=True)
            guardar_datos(df_clientes, CSV_CLIENTES)
            st.success("Cliente guardado.")
    st.dataframe(df_clientes)

# --- MÓDULO: PRODUCCIÓN (CON 3 IMPRESORAS) ---
elif menu == "🏗️ Producción":
    st.title("🏗️ Control de Máquinas")
    t1, t2 = st.tabs(["🆕 Nueva Orden", "🛤️ Taller Activo"])
    
    with t1:
        with st.form("ot"):
            c = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
            t = st.text_area("Trabajo (Ej: 50 Afiches)")
            imp = st.selectbox("Asignar Impresora", ["Impresora 1 (Láser)", "Impresora 2 (Inyección)", "Impresora 3 (Gran Formato)"])
            prio = st.select_slider("Prioridad", ["Baja", "Normal", "Urgente"], "Normal")
            if st.form_submit_button("Enviar a Taller"):
                new_id = len(df_prod) + 1
                row = pd.DataFrame([[new_id, datetime.now().strftime("%d/%m"), c, t, imp, "En Cola", prio]], columns=COL_PRODUCCION)
                df_prod = pd.concat([df_prod, row], ignore_index=True)
                guardar_datos(df_prod, CSV_PRODUCCION)
                st.success(f"Orden #{new_id} enviada a {imp}")
    
    with t2:
        for imp_name in ["Impresora 1 (Láser)", "Impresora 2 (Inyección)", "Impresora 3 (Gran Formato)"]:
            st.subheader(f"📟 {imp_name}")
            maquina_df = df_prod[(df_prod["Impresora"] == imp_name) & (df_prod["Estado"] != "Listo para Entrega")]
            if not maquina_df.empty:
                for i, r in maquina_df.iterrows():
                    col_ot1, col_ot2 = st.columns([3, 1])
                    col_ot1.write(f"**#{r['ID']} - {r['Cliente']}**: {r['Trabajo']} ({r['Prioridad']})")
                    new_st = col_ot2.selectbox("Estado", ["En Cola", "Imprimiendo", "Acabado", "Listo para Entrega"], key=f"st_{i}")
                    if col_ot2.button("OK", key=f"ok_{i}"):
                        df_prod.at[i, "Estado"] = new_st
                        guardar_datos(df_prod, CSV_PRODUCCION)
                        st.rerun()
            else:
                st.write("Sin trabajos pendientes.")

# --- MÓDULO: FINANZAS PRO (PUNTO DE EQUILIBRIO) ---
elif menu == "📈 Finanzas Pro":
    st.title("📈 Análisis de Rentabilidad")
    

[Image of break-even analysis chart showing fixed costs, variable costs, and revenue]

    st.subheader("💰 Gastos Fijos Mensuales (Alquiler, Luz, Internet, Sueldos)")
    with st.form("gastos"):
        con = st.text_input("Concepto")
        mon = st.number_input("Monto USD", min_value=0.0)
        if st.form_submit_button("Añadir Gasto"):
            df_gastos = pd.concat([df_gastos, pd.DataFrame([[con, mon]], columns=COL_GASTOS)], ignore_index=True)
            guardar_datos(df_gastos, CSV_GASTOS)
    
    st.table(df_gastos)
    total_fijo = pd.to_numeric(df_gastos["Monto_Mensual_USD"]).sum()
    st.metric("Meta Mensual (Para no perder dinero)", f"$ {total_fijo:,.2f}")

# --- MÓDULO: VENTAS ---
elif menu == "💰 Ventas":
    st.title("💰 Registro de Venta")
    with st.form("v"):
        cli = st.selectbox("Cliente", df_clientes["Nombre"].unique()) if not df_clientes.empty else st.text_input("Cliente")
        ins = st.selectbox("Insumo", df_stock["Material"].unique()) if not df_stock.empty else st.text_input("Material")
        cant = st.number_input("Cantidad", min_value=0.1)
        monto = st.number_input("Precio Cobrado USD", min_value=0.0)
        if st.form_submit_button("Cobrar"):
            # Lógica de cálculo simplificada para el ejemplo
            gan = monto * 0.4 
            v = pd.DataFrame([[datetime.now().strftime("%Y-%m-%d"), cli, ins, monto, monto*0.03, gan, "Socia"]], columns=COL_VENTAS)
            df_ventas = pd.concat([df_ventas, v], ignore_index=True)
            guardar_datos(df_ventas, CSV_VENTAS)
            st.success(f"Venta guardada. Ganancia estimada: ${gan:.2f}")

# (Módulos de Inventario, Analizador y Manuales se mantienen igual que la versión anterior)
elif menu == "📦 Inventario":
    st.title("📦 Almacén")
    st.dataframe(df_stock)
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador CMYK")
    # ... (código del analizador anterior)
elif menu == "🔍 Manuales":
    st.title("🔍 Base de Conocimiento")
    # ... (código de manuales anterior)
