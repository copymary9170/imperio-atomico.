from __future__ import annotations

import pandas as pd
import streamlit as st

from services.productos_terminados_service import (
    crear_producto_terminado,
    listar_inventario_para_bom,
    listar_productos_terminados,
)


def _precio_con_margen(costo: float, margen_pct: float) -> float:
    margen = max(0.0, float(margen_pct or 0.0)) / 100.0
    if margen >= 0.95:
        margen = 0.95
    return float(costo or 0.0) / max(1.0 - margen, 0.05)


def render_productos_terminados(usuario: str) -> None:
    st.subheader("🧩 Productos terminados / Recetas")
    st.caption(
        "Aquí van productos ya armados o listos para vender. No es materia prima simple: "
        "cada producto terminado se calcula con una receta de insumos, costos operativos y margen."
    )

    inventario = listar_inventario_para_bom()
    tab_crear, tab_historial = st.tabs(["Crear producto terminado", "Historial"])

    with tab_crear:
        if inventario.empty:
            st.warning(
                "No hay materia prima activa disponible para seleccionar. "
                "Puedes ver este formulario, pero para guardar un producto terminado necesitas crear primero insumos en 📦 Materia prima → Productos."
            )
            st.info(
                "Ejemplos de materia prima: papel bond, tinta, opalina, acetato, empaque, lápices, carpetas, cartulina, vinil o rollos."
            )

        st.markdown("##### Datos del producto terminado")
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código / SKU terminado", placeholder="PT-0001")
        nombre = c2.text_input("Nombre", placeholder="Kit escolar básico")
        unidad_venta = c3.text_input("Unidad de venta", value="unidad")
        descripcion = st.text_area("Descripción", placeholder="Qué incluye, presentación, tamaño, color, etc.")

        st.markdown("##### Receta / materia prima usada")
        st.caption("Selecciona los insumos desde Inventario. Puedes agregar varios materiales antes de guardar.")

        if "producto_terminado_insumos" not in st.session_state:
            st.session_state["producto_terminado_insumos"] = []

        if not inventario.empty:
            opciones = {
                f"#{int(row['id'])} · {row['nombre']} · stock {row['stock_actual']} {row['unidad']}": row
                for _, row in inventario.iterrows()
            }
            i1, i2, i3 = st.columns([3, 1, 1])
            insumo_label = i1.selectbox("Materia prima / insumo", list(opciones.keys()))
            cantidad = i2.number_input("Cantidad usada", min_value=0.0, value=1.0, step=0.1, format="%.4f")
            notas = i3.text_input("Notas", placeholder="opcional")

            row = opciones[insumo_label]
            costo_unitario = float(row.get("costo_unitario_usd") or 0.0)
            costo_total = costo_unitario * float(cantidad or 0.0)
            st.info(f"Costo estimado del insumo: ${costo_total:,.4f} ({cantidad:g} {row.get('unidad')} × ${costo_unitario:,.4f})")

            if st.button("➕ Agregar insumo", use_container_width=True):
                st.session_state["producto_terminado_insumos"].append(
                    {
                        "inventario_id": int(row["id"]),
                        "insumo_nombre": str(row["nombre"]),
                        "cantidad": float(cantidad or 0.0),
                        "unidad": str(row.get("unidad") or "unidad"),
                        "costo_unitario_usd": costo_unitario,
                        "costo_total_usd": costo_total,
                        "notas": str(notas or ""),
                    }
                )
                st.success("Insumo agregado a la receta.")
        else:
            st.error("No puedes agregar insumos todavía porque no hay materia prima activa en inventario.")

        insumos = st.session_state.get("producto_terminado_insumos", [])
        if insumos:
            df_insumos = pd.DataFrame(insumos)
            st.dataframe(df_insumos, use_container_width=True, hide_index=True)
            if st.button("🧹 Limpiar receta", use_container_width=True):
                st.session_state["producto_terminado_insumos"] = []
                st.rerun()
        else:
            st.caption("Aún no has agregado insumos.")

        st.markdown("##### Costos y precio")
        costo_materiales = sum(float(item.get("costo_total_usd") or 0.0) for item in insumos)
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Costo materiales", f"${costo_materiales:,.4f}")
        costo_operativo = p2.number_input("Costo operativo USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")
        margen_pct = p3.number_input("Margen %", min_value=0.0, value=40.0, step=1.0)
        stock_inicial = p4.number_input("Stock terminado inicial", min_value=0.0, value=0.0, step=1.0)

        costo_total_producto = costo_materiales + float(costo_operativo or 0.0)
        precio_sugerido = _precio_con_margen(costo_total_producto, float(margen_pct or 0.0))
        r1, r2, r3 = st.columns(3)
        r1.metric("Costo total", f"${costo_total_producto:,.4f}")
        r2.metric("Precio sugerido", f"${precio_sugerido:,.4f}")
        r3.metric("Ganancia estimada", f"${(precio_sugerido - costo_total_producto):,.4f}")

        if st.button("💾 Guardar producto terminado", use_container_width=True, disabled=not bool(insumos)):
            try:
                producto_id = crear_producto_terminado(
                    usuario=usuario,
                    codigo=codigo,
                    nombre=nombre,
                    descripcion=descripcion,
                    unidad_venta=unidad_venta,
                    insumos=insumos,
                    costo_operativo_usd=float(costo_operativo or 0.0),
                    margen_pct=float(margen_pct or 0.0),
                    stock_actual=float(stock_inicial or 0.0),
                )
                st.session_state["producto_terminado_insumos"] = []
                st.success(f"Producto terminado guardado con ID #{producto_id}.")
            except Exception as exc:
                st.error(f"No se pudo guardar: {exc}")

    with tab_historial:
        st.markdown("##### Productos terminados registrados")
        try:
            df = listar_productos_terminados(limit=100)
            if df.empty:
                st.caption("Aún no hay productos terminados registrados.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"No se pudo cargar el historial: {exc}")

    st.caption(f"Usuario: {usuario}")
