from __future__ import annotations

import streamlit as st

from services.inventario_calidad_service import (
    actualizar_datos_clave,
    diagnostico_calidad,
    resumen_calidad,
)


def render_inventario_calidad_elite(usuario: str) -> None:
    st.subheader("🏆 Control elite de inventario")
    st.caption(
        "Auditoría automática de calidad, completitud y preparación operativa de cada artículo."
    )

    resumen = resumen_calidad()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Artículos activos", int(resumen["articulos"]))
    c2.metric("Calidad promedio", f"{resumen['calidad_promedio']:.1f}%")
    c3.metric("Excelentes", int(resumen["excelentes"]))
    c4.metric("Por completar", int(resumen["incompletos"]))
    c5.metric("Críticos", int(resumen["criticos"]))

    df = diagnostico_calidad()
    if df.empty:
        st.warning(
            "El inventario todavía no tiene artículos. Crea el primer artículo en Operación y existencias → Maestro."
        )
        st.markdown(
            "**Configuración recomendada del primer artículo:** SKU, nombre, categoría, unidad base, "
            "clasificación, proveedor, ubicación, costo, stock mínimo, punto de reorden, stock ideal y máximo."
        )
        return

    st.markdown("### Semáforo de calidad")
    vista = df[[
        "sku", "nombre", "categoria", "clase_articulo", "stock_actual",
        "calidad_pct", "estado_calidad", "cantidad_faltantes", "campos_faltantes",
    ]].copy()
    st.dataframe(vista, use_container_width=True, hide_index=True)

    pendientes = df[df["cantidad_faltantes"] > 0].copy()
    if pendientes.empty:
        st.success("Todos los artículos cumplen el estándar profesional de datos.")
        return

    st.divider()
    st.markdown("### Bandeja de corrección")
    st.info(
        "Selecciona un artículo incompleto y completa sus datos clave. El porcentaje de calidad se recalcula automáticamente."
    )

    ids = [int(x) for x in pendientes["id"].tolist()]
    mapa = {
        int(row["id"]): f"{row['sku'] or 'SIN-SKU'} · {row['nombre']} · {row['calidad_pct']:.1f}%"
        for _, row in pendientes.iterrows()
    }
    item_id = st.selectbox("Artículo pendiente", ids, format_func=lambda value: mapa[value])
    row = pendientes[pendientes["id"] == item_id].iloc[0]
    st.warning(f"Campos faltantes: {row['campos_faltantes']}")

    with st.form("inventario_calidad_form"):
        c1, c2 = st.columns(2)
        ubicacion = c1.text_input("Ubicación física", value=str(row["ubicacion"] or ""), placeholder="Estante A · Nivel 2 · Caja 3")
        proveedor = c2.text_input("Proveedor principal", value=str(row["proveedor_principal"] or ""))
        c3, c4 = st.columns(2)
        costo = c3.number_input("Costo unitario USD", min_value=0.0, value=float(row["costo_unitario_usd"] or 0), format="%.6f")
        factor = c4.number_input("Contenido por unidad de compra", min_value=0.0001, value=max(float(row["factor_compra_base"] or 1), 0.0001), format="%.4f")
        c5, c6, c7, c8 = st.columns(4)
        minimo = c5.number_input("Stock mínimo", min_value=0.0, value=float(row["stock_minimo_operativo"] or 0))
        reorden = c6.number_input("Punto de reorden", min_value=0.0, value=float(row["punto_reorden"] or 0))
        ideal = c7.number_input("Stock ideal", min_value=0.0, value=float(row["stock_ideal"] or 0))
        maximo = c8.number_input("Stock máximo", min_value=0.0, value=float(row["stock_maximo"] or 0))
        guardar = st.form_submit_button("Guardar y recalcular calidad", type="primary", use_container_width=True)

    if guardar:
        try:
            actualizar_datos_clave(
                item_id,
                ubicacion=ubicacion,
                proveedor=proveedor,
                costo_unitario_usd=costo,
                stock_minimo=minimo,
                punto_reorden=reorden,
                stock_ideal=ideal,
                stock_maximo=maximo,
                factor_compra=factor,
            )
            st.success("Datos actualizados y calidad recalculada.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
