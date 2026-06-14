from __future__ import annotations

import pandas as pd
import streamlit as st

from services.gastos_operativos_service import listar_gastos_operativos


def render_gastos_operativos(usuario: str) -> None:
    st.subheader("📌 Gastos operativos")
    st.caption("Gastos y servicios registrados automáticamente desde Facturas de compra.")

    df = listar_gastos_operativos()
    if df.empty:
        st.info("Aún no hay gastos operativos registrados.")
        st.caption("Registra una factura de compra con línea tipo 'Gasto' o 'Servicio' para que aparezca aquí.")
        return

    total = float(pd.to_numeric(df["monto_usd"], errors="coerce").fillna(0).sum())
    categorias = int(df["categoria"].nunique()) if "categoria" in df.columns else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(df))
    c2.metric("Total gastos", f"${total:,.2f}")
    c3.metric("Categorías", categorias)

    c_buscar, c_categoria = st.columns([2, 1])
    buscar = c_buscar.text_input("Buscar concepto / proveedor / factura", key="buscar_gastos_operativos")
    categorias_opciones = ["Todas"] + sorted(df["categoria"].dropna().astype(str).unique().tolist())
    categoria = c_categoria.selectbox("Categoría", categorias_opciones, key="filtro_categoria_gastos_operativos")

    vista = df.copy()
    if categoria != "Todas":
        vista = vista[vista["categoria"].astype(str) == categoria]
    if buscar.strip():
        txt = buscar.strip()
        mask = (
            vista["concepto"].astype(str).str.contains(txt, case=False, na=False)
            | vista["proveedor"].astype(str).str.contains(txt, case=False, na=False)
            | vista["factura"].astype(str).str.contains(txt, case=False, na=False)
            | vista["categoria"].astype(str).str.contains(txt, case=False, na=False)
        )
        vista = vista[mask]

    if vista.empty:
        st.warning("No hay gastos con esos filtros.")
        return

    resumen = vista.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
    st.caption("Resumen por categoría")
    st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.caption("Detalle")
    st.dataframe(vista, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Descargar gastos operativos CSV",
        data=vista.to_csv(index=False).encode("utf-8-sig"),
        file_name="gastos_operativos.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.caption(f"Usuario: {usuario}")
