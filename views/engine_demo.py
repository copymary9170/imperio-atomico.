import streamlit as st
from PIL import Image

from modules.engine import (
    calcular_consumo_por_pixel,
    calcular_corte_cameo,
    simular_ganancia_pre_impresion
)


def render_engine_demo(usuario):

    st.title("⚙️ Motor Industrial de Producción")

    tab1, tab2, tab3 = st.tabs([
        "🎨 Análisis CMYK",
        "✂️ Corte Cameo",
        "💰 Simulación de Ganancia"
    ])

    # --------------------------------------------------
    # CMYK
    # --------------------------------------------------

    with tab1:

        st.subheader("Análisis de Consumo de Tinta")

        archivo = st.file_uploader("Subir imagen", type=["png", "jpg", "jpeg"])

        if archivo:

            imagen = Image.open(archivo)

            resultado = calcular_consumo_por_pixel(imagen)

            st.image(imagen)

            st.write("Pixeles:", resultado["pixeles_totales"])
            st.write("Consumo estimado ML:", resultado["consumo_real_ml"])
            st.write("Precisión:", resultado["precision"])

    # --------------------------------------------------
    # CORTE
    # --------------------------------------------------

    with tab2:

        st.subheader("Simulación Corte Cameo")

        archivo = st.file_uploader("Subir archivo diseño", type=["png", "svg", "dxf"], key="corte")

        if archivo:

            datos = calcular_corte_cameo(archivo.read(), nombre_archivo=archivo.name)

            st.write(datos)

    # --------------------------------------------------
    # GANANCIA
    # --------------------------------------------------

    with tab3:

        st.subheader("Simulación de Precio")

        costo = st.number_input("Costo", 0.0)

        margen = st.slider("Margen %", 0, 200, 30)

        if st.button("Calcular"):

            r = simular_ganancia_pre_impresion(costo, margen)

            st.write("Precio sugerido:", r["precio_sugerido"])
            st.write("Ganancia:", r["ganancia_estimada"])
