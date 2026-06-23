from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.inventario_operativo_service import ensure_schema, listar_reservas
from services.inventario_venta_integracion import reservar_receta_producto


def _productos_con_receta() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query(
            "SELECT DISTINCT i.id,i.sku,i.nombre,r.nombre receta FROM recetas_inventario r JOIN inventario i ON i.id=r.producto_inventario_id WHERE r.activo=1 AND lower(COALESCE(i.estado,'activo'))='activo' ORDER BY i.nombre",
            conn,
        )


def render_pedidos_inventario(usuario: str) -> None:
    st.subheader("📋 Pedidos y reservas")
    productos = _productos_con_receta()
    if productos.empty:
        st.info("Primero crea una receta vinculada a un producto.")
    else:
        ids = [int(x) for x in productos["id"].tolist()]
        etiquetas = {int(r["id"]): f"{r['nombre']} · {r['receta']}" for _, r in productos.iterrows()}
        with st.form("reservar_pedido_receta"):
            producto_id = st.selectbox("Producto del pedido", ids, format_func=lambda x: etiquetas[x])
            c1, c2 = st.columns(2)
            cantidad = c1.number_input("Cantidad", min_value=0.0001, step=1.0)
            referencia = c2.text_input("Referencia del pedido *", placeholder="PED-CM-0001")
            confirmar = st.form_submit_button("Confirmar y reservar materiales", type="primary")
        if confirmar:
            try:
                with db_transaction() as conn:
                    creadas = reservar_receta_producto(conn, producto_id=producto_id, cantidad=cantidad, referencia=referencia, usuario=usuario)
                st.success(f"Se crearon {creadas} reservas de materiales.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    st.dataframe(listar_reservas(), use_container_width=True, hide_index=True)
