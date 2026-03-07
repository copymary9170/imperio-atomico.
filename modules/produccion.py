from __future__ import annotations

import streamlit as st

from services.inventory_service import InventoryService
from services.produccion_service import ConsumoInsumo, ProduccionService


def _noop_audit(*_args, **_kwargs):
    return None


def render_produccion(usuario: str) -> None:
    st.subheader("Producción")
    inventory_service = InventoryService(money_fn=lambda x: round(float(x), 2), audit_fn=_noop_audit)
    service = ProduccionService(inventory_service=inventory_service)

    with st.form("orden_produccion"):
        tipo = st.selectbox("Tipo", ["CMYK", "Sublimación", "Corte", "Manual"])
        referencia = st.text_input("Referencia")
        costo_estimado = st.number_input("Costo estimado", min_value=0.0)
        inventario_id = st.number_input("Insumo principal (ID)", min_value=1, step=1)
        cantidad = st.number_input("Cantidad insumo", min_value=0.0001, value=1.0)
        costo_u = st.number_input("Costo unitario", min_value=0.0, value=0.0)
        submit = st.form_submit_button("Crear orden")

    if submit:
        orden_id = service.registrar_orden(
            usuario=usuario,
            tipo_produccion=tipo,
            referencia=referencia,
            costo_estimado=costo_estimado,
            insumos=[ConsumoInsumo(inventario_id=int(inventario_id), cantidad=float(cantidad), costo_unitario=float(costo_u))],
        )
        st.success(f"Orden de producción #{orden_id} registrada")
