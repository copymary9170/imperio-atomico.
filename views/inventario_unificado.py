from __future__ import annotations

import streamlit as st

from services.inventario_unificado_service import (
    TIPOS_USO,
    UNIDADES_BASE,
    crear_item_unificado,
    guardar_clasificacion_inventario,
    listar_inventario_unificado,
)


def render_inventario_unificado(usuario: str) -> None:
    st.subheader("Inventario unificado")
    st.caption("Un mismo articulo puede ser insumo, producto de reventa o ambos.")

    tab_lista, tab_crear, tab_clasificar = st.tabs(["Existencias", "Crear articulo", "Clasificar"])

    with tab_lista:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("Aun no hay articulos.")
        else:
            filtro = st.multiselect("Tipo de uso", TIPOS_USO, default=TIPOS_USO)
            vista = df[df["tipo_uso"].isin(filtro)] if filtro else df.iloc[0:0]
            mostrar = vista.copy()
            mostrar["fraccionable"] = mostrar["permite_fraccionamiento"].astype(int).map({1: "Si", 0: "No"})
            cols = ["id", "sku", "nombre", "categoria", "tipo_uso", "unidad_base", "fraccionable", "stock_actual", "stock_minimo", "costo_unitario_usd", "precio_venta_usd", "estado"]
            st.dataframe(mostrar[cols], use_container_width=True, hide_index=True)

    with tab_crear:
        with st.form("form_crear_item_unificado"):
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU")
            nombre = c2.text_input("Nombre")
            categoria = c3.text_input("Categoria", value="General")
            d1, d2, d3 = st.columns(3)
            tipo_uso = d1.selectbox("Tipo de uso", TIPOS_USO, index=2)
            unidad_base = d2.selectbox("Unidad base", UNIDADES_BASE)
            fraccionable = d3.checkbox("Permite fraccionamiento", value=True)
            e1, e2, e3, e4 = st.columns(4)
            stock_actual = e1.number_input("Stock inicial", min_value=0.0, step=1.0, format="%.4f")
            stock_minimo = e2.number_input("Stock minimo", min_value=0.0, step=1.0, format="%.4f")
            costo = e3.number_input("Costo unitario USD", min_value=0.0, step=0.01, format="%.4f")
            precio = e4.number_input("Precio venta USD", min_value=0.0, step=0.01, format="%.4f")
            guardar = st.form_submit_button("Crear articulo", type="primary", use_container_width=True)
        if guardar:
            try:
                item_id = crear_item_unificado({"sku": sku, "nombre": nombre, "categoria": categoria, "tipo_uso": tipo_uso, "unidad_base": unidad_base, "permite_fraccionamiento": fraccionable, "stock_actual": stock_actual, "stock_minimo": stock_minimo, "costo_unitario_usd": costo, "precio_venta_usd": precio}, usuario)
                st.success(f"Articulo #{item_id} creado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_clasificar:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("No hay articulos para clasificar.")
        else:
            opciones = {f"#{int(row['id'])} - {row['nombre']} - {row['tipo_uso']}": row for _, row in df.iterrows()}
            seleccion = st.selectbox("Articulo", list(opciones.keys()))
            row = opciones[seleccion]
            tipo_actual = str(row.get("tipo_uso") or "Ambos")
            unidad_actual = str(row.get("unidad_base") or row.get("unidad") or "unidad")
            unidades = list(UNIDADES_BASE)
            if unidad_actual not in unidades:
                unidades.insert(0, unidad_actual)
            with st.form("form_clasificar_item"):
                c1, c2, c3 = st.columns(3)
                tipo_nuevo = c1.selectbox("Tipo de uso", TIPOS_USO, index=TIPOS_USO.index(tipo_actual) if tipo_actual in TIPOS_USO else 2)
                unidad_nueva = c2.selectbox("Unidad base", unidades, index=unidades.index(unidad_actual))
                fraccionable_nuevo = c3.checkbox("Permite fraccionamiento", value=bool(int(row.get("permite_fraccionamiento") or 0)))
                guardar_cambio = st.form_submit_button("Guardar clasificacion", type="primary", use_container_width=True)
            if guardar_cambio:
                try:
                    guardar_clasificacion_inventario(int(row["id"]), tipo_uso=tipo_nuevo, unidad_base=unidad_nueva, permite_fraccionamiento=fraccionable_nuevo)
                    st.success("Clasificacion actualizada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar: {exc}")
