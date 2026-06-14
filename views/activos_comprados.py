from __future__ import annotations

import streamlit as st

from services.activos_compra_service import listar_activos_comprados


def render_activos_comprados(usuario: str) -> None:
    st.subheader("🧾 Activos comprados por factura")
    st.caption("Equipos y herramientas registrados automáticamente desde Facturas de compra con línea tipo Activo / equipo.")

    df = listar_activos_comprados()
    if df.empty:
        st.info("Aún no hay activos comprados desde facturas.")
        st.caption("Registra una factura de compra con una línea tipo 'Activo / equipo' para que aparezca aquí.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Activos", len(df))
    c2.metric("Valor total", f"${float(df['costo_total_usd'].sum()):,.2f}")
    c3.metric("Costo promedio", f"${float(df['costo_total_usd'].sum()) / max(len(df), 1):,.2f}")

    buscar = st.text_input("Buscar activo / proveedor / factura", key="buscar_activos_comprados")
    vista = df.copy()
    if buscar.strip():
        txt = buscar.strip()
        mask = (
            vista["nombre"].astype(str).str.contains(txt, case=False, na=False)
            | vista["proveedor"].astype(str).str.contains(txt, case=False, na=False)
            | vista["factura"].astype(str).str.contains(txt, case=False, na=False)
            | vista["tipo_activo"].astype(str).str.contains(txt, case=False, na=False)
        )
        vista = vista[mask]

    st.dataframe(vista, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Descargar activos comprados CSV",
        data=vista.to_csv(index=False).encode("utf-8-sig"),
        file_name="activos_comprados.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.caption(f"Usuario: {usuario}")
