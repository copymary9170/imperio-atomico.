from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from database.connection import db_transaction
from services.contabilidad_service import (
    obtener_libro_diario,
    obtener_libro_mayor,
    obtener_resumen_contable,
    sincronizar_contabilidad,
)


def _render_resumen_cards(resumen: dict[str, float]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asientos", f"{int(resumen.get('asientos', 0))}")
    c2.metric("Líneas", f"{int(resumen.get('lineas', 0))}")
    c3.metric("Debe (USD)", f"$ {float(resumen.get('debe_usd', 0.0)):,.2f}")
    c4.metric("Haber (USD)", f"$ {float(resumen.get('haber_usd', 0.0)):,.2f}")


def render_contabilidad_dashboard(usuario: str) -> None:
    st.title("📚 Contabilidad integrada")
    st.caption("Libro diario, mayor y resumen construidos desde eventos reales de ventas, compras, CxC, CxP, gastos y tesorería.")

    f1, f2, f3 = st.columns([1, 1, 2])
    hoy = date.today()
    fecha_desde = f1.date_input("Desde", value=hoy - timedelta(days=30), key="conta_desde").isoformat()
    fecha_hasta = f2.date_input("Hasta", value=hoy, key="conta_hasta").isoformat()

    if f3.button("🔄 Sincronizar contabilidad", use_container_width=True):
        try:
            with db_transaction() as conn:
                sync = sincronizar_contabilidad(conn, usuario=usuario)
            st.success(
                "Sincronización contable ejecutada: "
                f"ventas={sync['ventas']}, cobros={sync['cobros']}, compras={sync['compras']}, "
                f"pagos={sync['pagos_proveedores']}, gastos={sync['gastos']}, ajustes={sync['ajustes']}."
            )
        except Exception as exc:
            st.error("No se pudo sincronizar la contabilidad.")
            st.exception(exc)

    try:
        with db_transaction() as conn:
            sincronizar_contabilidad(conn, usuario=usuario)
            resumen = obtener_resumen_contable(conn, fecha_desde, fecha_hasta)
            diario = obtener_libro_diario(conn, fecha_desde, fecha_hasta)
            mayor = obtener_libro_mayor(conn, fecha_desde, fecha_hasta)
    except Exception as exc:
        st.error("Error cargando información contable.")
        st.exception(exc)
        return

    _render_resumen_cards(resumen)

    tabs = st.tabs(["📘 Libro diario", "📙 Libro mayor", "📊 Resumen contable"])

    with tabs[0]:
        st.subheader("Libro diario")
        if diario.empty:
            st.info("No hay asientos en el rango seleccionado.")
        else:
            st.dataframe(diario, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Exportar libro diario (CSV)",
                diario.to_csv(index=False).encode("utf-8"),
                file_name=f"libro_diario_{fecha_desde}_{fecha_hasta}.csv",
                mime="text/csv",
            )

    with tabs[1]:
        st.subheader("Libro mayor básico")
        if mayor.empty:
            st.info("No hay movimientos por cuenta para el período.")
        else:
            st.dataframe(mayor, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Exportar libro mayor (CSV)",
                mayor.to_csv(index=False).encode("utf-8"),
                file_name=f"libro_mayor_{fecha_desde}_{fecha_hasta}.csv",
                mime="text/csv",
            )

    with tabs[2]:
        st.subheader("Resumen contable")
        if diario.empty:
            st.info("No hay información contable para resumir.")
        else:
            por_evento = (
                diario.groupby("evento_tipo", as_index=False)
                .agg(
                    asientos=("asiento_id", "nunique"),
                    debe_usd=("debe_usd", "sum"),
                    haber_usd=("haber_usd", "sum"),
                )
                .sort_values("asientos", ascending=False)
            )
            st.dataframe(por_evento, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Exportar resumen contable (CSV)",
                por_evento.to_csv(index=False).encode("utf-8"),
                file_name=f"resumen_contable_{fecha_desde}_{fecha_hasta}.csv",
                mime="text/csv",
            )


__all__ = ["render_contabilidad_dashboard"]
