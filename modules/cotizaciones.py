from __future__ import annotations

import streamlit as st
import pandas as pd

from modules.common import as_positive, require_text
from services.cotizacion_service import CotizacionService


# ============================================================
# 📝 INTERFAZ DE COTIZACIONES
# ============================================================

def render_cotizaciones(usuario: str) -> None:

    st.subheader("📝 Cotizaciones")

    service = CotizacionService()

    # ------------------------------------------------
    # FORMULARIO CREAR COTIZACIÓN
    # ------------------------------------------------

    with st.form("crear_cotizacion"):

        st.write("Crear nueva cotización")

        c1, c2 = st.columns(2)

        cliente_id = c1.number_input(
            "ID Cliente (opcional)",
            min_value=0,
            step=1,
            value=0
        )

        margen = c2.number_input(
            "Margen %",
            min_value=0.0,
            value=30.0
        )

        descripcion = st.text_area("Descripción del trabajo")

        costo = st.number_input(
            "Costo estimado USD",
            min_value=0.0,
            value=0.0
        )

        submit = st.form_submit_button("💾 Crear cotización")

    # ------------------------------------------------
    # CREAR COTIZACIÓN
    # ------------------------------------------------

    if submit:

        try:

            descripcion = require_text(descripcion, "Descripción")

            costo = as_positive(costo, "Costo")

            margen = as_positive(margen, "Margen")

            cliente = None if cliente_id == 0 else int(cliente_id)

            cot_id = service.crear_cotizacion(
                usuario,
                cliente,
                descripcion,
                costo,
                margen
            )

            precio_sugerido = costo * (1 + (margen / 100))

            st.success(f"Cotización #{cot_id} creada")

            st.metric(
                "Precio sugerido",
                f"$ {precio_sugerido:,.2f}"
            )

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error creando cotización")

            st.exception(e)

    st.divider()

    # ------------------------------------------------
    # HISTORIAL DE COTIZACIONES
    # ------------------------------------------------

    try:

        cotizaciones = service.obtener_cotizaciones()

    except Exception as e:

        st.error("Error cargando cotizaciones")

        st.exception(e)

        return

    if not cotizaciones:

        st.info("No hay cotizaciones registradas.")

        return

    df = pd.DataFrame(cotizaciones)

    # ------------------------------------------------
    # BUSCADOR
    # ------------------------------------------------

    buscar = st.text_input("🔎 Buscar cotización")

    if buscar:

        df = df[
            df.astype(str)
            .apply(lambda col: col.str.contains(buscar, case=False, na=False))
            .any(axis=1)
        ]

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric("Cotizaciones", len(df))

    if "precio" in df.columns:

        c2.metric(
            "Valor cotizado",
            f"$ {df['precio'].sum():,.2f}"
        )

    if "estado" in df.columns:

        aprobadas = len(df[df["estado"] == "aprobada"])

        c3.metric("Aprobadas", aprobadas)

    st.divider()

    # ------------------------------------------------
    # TABLA
    # ------------------------------------------------

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
