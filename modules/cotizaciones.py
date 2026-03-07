from __future__ import annotations

import streamlit as st

from modules.common import as_positive, require_text
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
        try:
            descripcion = require_text(descripcion, "Descripción")
            costo = as_positive(costo, "Costo")
            margen = as_positive(margen, "Margen")
            cid = None if cliente_id == 0 else int(cliente_id)
            cot_id = service.crear_cotizacion(usuario, cid, descripcion, costo, margen)
            precio_sugerido = costo * (1 + (margen / 100))
            st.success(f"Cotización #{cot_id} creada")
            st.info(f"Precio sugerido: $ {precio_sugerido:,.2f}")
        except ValueError as exc:
            st.error(str(exc))
