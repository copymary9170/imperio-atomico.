import streamlit as st
import pandas as pd
import os
import numpy as np
from PIL import Image
import fitz  # PyMuPDF
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Imperio Atómico - Master Pre-Prensa", layout="wide")

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

# --- FUNCIONES DE ANÁLISIS ---
def analizar_cmyk_pro(img_pil):
    # Convertimos a RGB para extraer el Negro Real (K)
    pix_rgb = np.array(img_pil.convert("RGB")) / 255.0
    r, g, b = pix_rgb[:,:,0], pix_rgb[:,:,1], pix_rgb[:,:,2]
    
    # El Negro es la falta de brillo (K = 1 - Max de RGB)
    k = 1 - np.max(pix_rgb, axis=2)
    
    # Extraemos CMY basándonos en la oscuridad
    c = (1 - r - k) / (1 - k + 1e-9)
    m = (1 - g - k) / (1 - k + 1e-9)
    y = (1 - b - k) / (1 - k + 1e-9)
    
    return {
        "C": np.clip(c, 0, 1).mean() * 100,
        "M": np.clip(m, 0, 1).mean() * 100,
        "Y": np.clip(y, 0, 1).mean() * 100,
        "K": k.mean() * 100
    }

# --- MENÚ ---
menu = st.sidebar.radio("Navegación:", ["📊 Dashboard", "🎨 Analizador Masivo CMYK", "💰 Ventas", "📦 Inventario Pro", "🔍 Manuales"])

# --- MÓDULO: ANALIZADOR MASIVO CMYK ---
if menu == "🎨 Analizador Masivo CMYK":
    st.title("🎨 Analizador Multitarea (PDF y Fotos)")
    st.info("Sube varios archivos a la vez. El sistema analizará cada imagen y cada página de tus PDFs.")
    
    archivos = st.file_uploader("Subir Imágenes o PDFs", type=["jpg", "png", "jpeg", "pdf"], accept_multiple_files=True)
    
    if archivos:
        resultados = []
        
        for archivo in archivos:
            with st.status(f"Procesando {archivo.name}...", expanded=False) as status:
                if archivo.type == "application/pdf":
                    # --- PROCESAR PDF HOJA POR HOJA ---
                    doc = fitz.open(stream=archivo.read(), filetype="pdf")
                    for i in range(len(doc)):
                        page = doc.load_page(i)
                        pix = page.get_pixmap(colorspace=fitz.csRGB) # Extraemos en RGB para nuestra lógica de K
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        res = analizar_cmyk_pro(img)
                        res["Archivo"] = f"{archivo.name} (Pág {i+1})"
                        resultados.append(res)
                else:
                    # --- PROCESAR IMAGEN INDIVIDUAL ---
                    img = Image.open(archivo)
                    res = analizar_cmyk_pro(img)
                    res["Archivo"] = archivo.name
                    resultados.append(res)
                status.update(label=f"✅ {archivo.name} analizado", state="complete")

        # --- MOSTRAR RESULTADOS ---
        df_res = pd.DataFrame(resultados)
        df_res["Total (%)"] = df_res["C"] + df_res["M"] + df_res["Y"] + df_res["K"]
        
        st.subheader("📊 Tabla de Cobertura por Hoja/Imagen")
        st.dataframe(df_res.style.format({
            "C": "{:.1f}%", "M": "{:.1f}%", "Y": "{:.1f}%", "K": "{:.1f}%", "Total (%)": "{:.1f}%"
        }), use_container_width=True)
        
        # Resumen visual
        st.divider()
        st.subheader("💡 Resumen de Consumo Crítico")
        col1, col2 = st.columns(2)
        
        max_tinta = df_res.loc[df_res["Total (%)"].idxmax()]
        col1.warning(f"**Hoja más costosa:**\n{max_tinta['Archivo']} ({max_tinta['Total (%)']:.1f}%)")
        
        promedio_k = df_res["K"].mean()
        col2.info(f"**Promedio de Negro (K) total:** {promedio_k:.1f}%")

# (Aquí seguirían los demás módulos de Ventas, Dashboard e Inventario igual que antes...)
