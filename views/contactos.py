from __future__ import annotations

import streamlit as st

from views.proveedores_compras import render_proveedores


def render_contactos(usuario: str = "Sistema") -> None:
    st.title("🏢 Proveedores")
    st.caption("Módulo único de proveedores: ficha maestra, proveedor-producto, compras, documentos, evaluaciones, cuentas por pagar y pagos.")
    render_proveedores(usuario)
