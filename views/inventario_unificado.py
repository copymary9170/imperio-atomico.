from __future__ import annotations

import streamlit as st

from services.inventario_unificado_service import (
    TIPOS_USO,
    UNIDADES_BASE,
    crear_item_unificado,
    guardar_clasificacion_inventario,
    listar_inventario_unificado,
)


CATEGORIAS_SUGERIDAS = [
    "Papel",
    "Cartulina",
    "Foami",
    "Carpetas",
    "Papelería",
    "Tinta",
    "Consumible",
    "Sublimación",
    "Empaque",
    "Herramienta",
    "General",
]


def render_inventario_unificado(usuario: str) -> None:
    st.subheader("Inventario unificado")
    st.caption("Un mismo artículo puede ser insumo, producto de reventa o ambos.")

    tab_lista, tab_crear, tab_clasificar = st.tabs(["Existencias", "Crear artículo", "Clasificar"])

    with tab_lista:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("Aún no hay artículos.")
        else:
            filtro = st.multiselect("Tipo de uso", TIPOS_USO, default=TIPOS_USO)
            vista = df[df["tipo_uso"].isin(filtro)] if filtro else df.iloc[0:0]
            mostrar = vista.copy()
            mostrar["fraccionable"] = mostrar["permite_fraccionamiento"].astype(int).map({1: "Sí", 0: "No"})
            cols = [
                "id", "sku", "nombre", "categoria", "marca", "color", "tamano",
                "tipo_uso", "unidad_base", "unidad_compra", "fraccionable",
                "stock_actual", "stock_minimo", "punto_reorden", "stock_ideal",
                "costo_unitario_usd", "precio_venta_usd", "ubicacion", "estado",
            ]
            st.dataframe(mostrar[cols], use_container_width=True, hide_index=True)

    with tab_crear:
        st.info("Crea aquí la ficha maestra del artículo. Si luego registrarás una factura de compra, deja el stock inicial y el costo en 0 para evitar duplicar existencias.")
        with st.form("form_crear_item_unificado"):
            st.markdown("#### Identificación")
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU *", placeholder="Ej.: PAP-BOND-CARTA-75G")
            nombre = c2.text_input("Nombre *", placeholder="Ej.: Papel bond carta 75 g")
            categoria_sel = c3.selectbox("Categoría", CATEGORIAS_SUGERIDAS, index=CATEGORIAS_SUGERIDAS.index("General"))
            categoria_otro = st.text_input("Otra categoría", placeholder="Escríbela solo si no aparece en la lista")
            categoria = categoria_otro.strip() or categoria_sel

            d1, d2, d3 = st.columns(3)
            tipo_uso = d1.selectbox("Tipo de uso", TIPOS_USO, index=2, help="Insumo: se consume. Reventa: se vende. Ambos: puede usarse de las dos formas.")
            unidad_base = d2.selectbox("Unidad base", UNIDADES_BASE, help="Unidad mínima que se controla en inventario: hoja, unidad, pliego, ml, etc.")
            fraccionable = d3.checkbox("Permite fraccionamiento", value=True, help="Márcalo si puedes usar o vender solo una parte del artículo.")

            st.markdown("#### Características")
            a1, a2, a3, a4, a5 = st.columns(5)
            marca = a1.text_input("Marca")
            color = a2.text_input("Color")
            tamano = a3.text_input("Tamaño / medida", placeholder="Ej.: Carta, A4, 60 × 40 cm")
            gramaje = a4.text_input("Gramaje / grosor", placeholder="Ej.: 75 g, 2 mm")
            acabado = a5.text_input("Acabado", placeholder="Ej.: mate, brillante, escarchado")

            st.markdown("#### Compra y almacenamiento")
            b1, b2, b3, b4 = st.columns(4)
            unidad_compra = b1.selectbox("Unidad de compra", [""] + UNIDADES_BASE, help="Cómo lo compras al proveedor: resma, paquete, caja, unidad, etc.")
            contenido_compra = b2.number_input("Contenido por unidad de compra", min_value=0.0, step=1.0, format="%.4f", help="Ej.: una resma contiene 500 hojas.")
            proveedor_principal = b3.text_input("Proveedor principal")
            ubicacion = b4.text_input("Ubicación", placeholder="Ej.: Estante A · Gaveta 2")

            st.markdown("#### Control de existencias")
            e1, e2, e3, e4 = st.columns(4)
            stock_actual = e1.number_input("Stock inicial", min_value=0.0, step=1.0, format="%.4f")
            stock_minimo = e2.number_input("Stock mínimo", min_value=0.0, step=1.0, format="%.4f")
            punto_reorden = e3.number_input("Punto de reorden", min_value=0.0, step=1.0, format="%.4f", help="Cantidad en la que conviene volver a comprar.")
            stock_ideal = e4.number_input("Stock ideal", min_value=0.0, step=1.0, format="%.4f")
            stock_maximo = st.number_input("Stock máximo", min_value=0.0, step=1.0, format="%.4f")

            st.markdown("#### Costos y venta")
            f1, f2 = st.columns(2)
            costo = f1.number_input("Costo unitario USD", min_value=0.0, step=0.01, format="%.4f", help="Costo de una unidad base, no del paquete completo.")
            precio = f2.number_input("Precio venta USD", min_value=0.0, step=0.01, format="%.4f")
            observaciones = st.text_area("Observaciones", placeholder="Compatibilidad, presentación, condiciones de uso o cualquier detalle adicional.")

            guardar = st.form_submit_button("Crear artículo", type="primary", use_container_width=True)

        if guardar:
            try:
                item_id = crear_item_unificado(
                    {
                        "sku": sku,
                        "nombre": nombre,
                        "categoria": categoria,
                        "tipo_uso": tipo_uso,
                        "unidad_base": unidad_base,
                        "permite_fraccionamiento": fraccionable,
                        "stock_actual": stock_actual,
                        "stock_minimo": stock_minimo,
                        "costo_unitario_usd": costo,
                        "precio_venta_usd": precio,
                        "marca": marca,
                        "color": color,
                        "tamano": tamano,
                        "gramaje": gramaje,
                        "acabado": acabado,
                        "unidad_compra": unidad_compra,
                        "contenido_compra": contenido_compra,
                        "proveedor_principal": proveedor_principal,
                        "ubicacion": ubicacion,
                        "stock_ideal": stock_ideal,
                        "stock_maximo": stock_maximo,
                        "punto_reorden": punto_reorden,
                        "observaciones": observaciones,
                    },
                    usuario,
                )
                st.success(f"Artículo #{item_id} creado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_clasificar:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("No hay artículos para clasificar.")
        else:
            opciones = {f"#{int(row['id'])} - {row['nombre']} - {row['tipo_uso']}": row for _, row in df.iterrows()}
            seleccion = st.selectbox("Artículo", list(opciones.keys()))
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
                guardar_cambio = st.form_submit_button("Guardar clasificación", type="primary", use_container_width=True)
            if guardar_cambio:
                try:
                    guardar_clasificacion_inventario(int(row["id"]), tipo_uso=tipo_nuevo, unidad_base=unidad_nueva, permite_fraccionamiento=fraccionable_nuevo)
                    st.success("Clasificación actualizada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar: {exc}")
