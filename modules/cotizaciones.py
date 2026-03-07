from __future__ import annotations

import streamlit as st

from services.cotizacion_service import CotizacionService


def render_cotizaciones(usuario: str) -> None:
    st.subheader("Cotizaciones")
    service = CotizacionService()

    with st.form("crear_cotizacion"):
        cliente_id = st.number_input("ID Cliente (opcional)", min_value=0, step=1, value=0)
        descripcion = st.text_area("Descripción")
        costo = st.number_input("Costo estimado USD", min_value=0.0, value=0.0)
        margen = st.number_input("Margen %", min_value=0.0, value=30.0)
        submit = st.form_submit_button("Crear cotización")

    if submit:
        cid = None if cliente_id == 0 else int(cliente_id)
        cot_id = service.crear_cotizacion(usuario, cid, descripcion, costo, margen)
        st.success(f"Cotización #{cot_id} creada")
