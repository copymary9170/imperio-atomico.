import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime
import database  # Importamos tu nuevo cerebro

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Sistema Vivo", layout="wide")
database.inicializar_sistema() # Arranca la base de datos

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Panel de Control")
    menu = st.radio("Navegación:", 
        ["📊 Dashboard", "📝 Cotizaciones", "👥 Clientes", "🏗️ Producción", "📦 Inventario", "🎨 Analizador", "🔍 Manuales", "⚙️ Configuración"])

# --- MÓDULO: COTIZACIONES (EL NUEVO) ---
if menu == "📝 Cotizaciones":
    st.title("📝 Generador de Presupuestos")
    
    with st.form("nueva_cot"):
        col1, col2 = st.columns(2)
        with col1:
            c_nombre = st.text_input("Nombre del Cliente")
            c_trabajo = st.text_input("Trabajo (Ej: 50 Libretas)")
        with col2:
            c_monto = st.number_input("Precio USD", min_value=0.0)
            btn = st.form_submit_button("Guardar Cotización")
            
        if btn:
            database.guardar_cotizacion(c_nombre, c_trabajo, c_monto)
            st.success(f"✅ Cotización para {c_nombre} guardada.")

    st.subheader("📋 Historial de Presupuestos")
    df_cot = database.obtener_cotizaciones()
    st.dataframe(df_cot, use_container_width=True)

# --- MÓDULO: DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Estado del Imperio")
    st.info("Esta tarde añadiremos aquí las barras de tinta con los datos que me traigas.")
    # Aquí pondremos las barras CMYK más tarde

# --- MÓDULO: ANALIZADOR (TU MOTOR CMYK) ---
# --- MÓDULO: ANALIZADOR (VERSIÓN MÚLTIPLE) ---
elif menu == "🎨 Analizador":
    st.title("🎨 Analizador de Costos Atómico (Múltiple)")
    
    # 1. El selector ahora acepta varios archivos
    archivos_subidos = st.file_uploader("Arrastra aquí todos tus diseños", 
                                        type=["jpg","png","pdf"], 
                                        accept_multiple_files=True)
    
    if archivos_subidos:
        st.success(f"Se han cargado {len(archivos_subidos)} archivos.")
        
        # 2. Esto hace que el sistema analice uno por uno
        for f in archivos_subidos:
            # Usamos un expander para que no se haga una lista infinita hacia abajo
            with st.expander(f"🖼️ Analizando: {f.name}", expanded=True):
                img, res = analizar_cmyk_pro(f)
                
                if img:
                    col_img, col_datos = st.columns([1, 1])
                    
                    with col_img:
                        st.image(img, use_container_width=True)
                    
                    with col_datos:
                        st.write("**Gasto de Tinta Estimado:**")
                        # Aquí mostramos los porcentajes que calcula tu función
                        st.write(f"💧 Cian: {res['C']:.2%}")
                        st.write(f"🌸 Magenta: {res['M']:.2%}")
                        st.write(f"🟡 Amarillo: {res['Y']:.2%}")
                        st.write(f"⚫ Negro: {res['K']:.2%}")
                        
                        # Cálculo de costo rápido (puedes ajustar el margen aquí)
                        costo_aprox = (res['C'] + res['M'] + res['Y'] + res['K']) * 0.50 
                        st.metric("Costo Tinta USD", f"$ {costo_aprox:.4f}")
# --- MÓDULO: MANUALES ---
elif menu == "🔍 Manuales":
    st.title("🔍 Biblioteca Técnica")
    busqueda = st.text_input("Buscar manual...")
    st.write("Resultados para:", busqueda)

# (Los demás módulos irán apareciendo según los necesites usar hoy)


