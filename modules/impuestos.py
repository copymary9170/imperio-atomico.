from __future__ import annotations

from datetime import date

import streamlit as st

from database.connection import db_transaction
from services.fiscal_service import exportar_resumen_fiscal_csv, obtener_detalle_fiscal_periodo, obtener_resumen_fiscal_periodo


def render_impuestos(usuario: str) -> None:
    st.subheader("🧾 Fiscalidad operativa básica")
    st.caption("Consolidación de IVA por período usando ventas, compras y gastos ya registrados.")

    hoy = date.today()
    periodo_default = hoy.strftime("%Y-%m")
    periodo = st.text_input("Período fiscal (YYYY-MM)", value=periodo_default).strip()

    if not periodo:
        st.info("Indica un período para generar el resumen fiscal.")
        return

    try:
        with db_transaction() as conn:
            resumen = obtener_resumen_fiscal_periodo(conn, periodo=periodo)
            detalle = obtener_detalle_fiscal_periodo(conn, periodo=periodo)
            csv_bytes = exportar_resumen_fiscal_csv(conn, periodo=periodo)
    except Exception as exc:
        st.error("No se pudo calcular el resumen fiscal del período.")
        st.exception(exc)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IVA débito", f"$ {float(resumen['iva_debito_usd']):,.2f}")
    c2.metric("IVA crédito", f"$ {float(resumen['iva_credito_usd']):,.2f}")
    c3.metric("IVA neto período", f"$ {float(resumen['iva_neto_periodo_usd']):,.2f}")
    c4.metric("Estado período", "Cerrado" if bool(resumen["periodo_cerrado"]) else "Abierto")

    st.caption(
        f"Rango considerado: {resumen['fecha_desde']} a {resumen['fecha_hasta']} · Usuario: {usuario}."
    )
    st.dataframe(detalle, use_container_width=True)

    st.download_button(
        label="⬇️ Exportar resumen fiscal CSV",
        data=csv_bytes,
        file_name=f"resumen_fiscal_{periodo}.csv",
        mime="text/csv",
    )
