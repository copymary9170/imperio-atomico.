from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from services.inventario_unificado_service import (
    TIPOS_USO,
    UNIDADES_BASE,
    crear_item_unificado,
    guardar_clasificacion_inventario,
    listar_inventario_unificado,
)

CATEGORIAS_SUGERIDAS = ["Papel", "Cartulina", "Foami", "Carpetas", "Papelería", "Tinta", "Consumible", "Sublimación", "Empaque", "Herramienta", "General"]


def _actualizar_articulo(item_id: int, values: dict, usuario: str) -> None:
    with db_transaction() as conn:
        duplicado = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?) AND id<>?", (values["sku"].strip(), int(item_id))).fetchone()
        if duplicado:
            raise ValueError("Ya existe otro artículo con ese SKU.")
        conn.execute("""
            UPDATE inventario SET sku=?, nombre=?, categoria=?, unidad=?, unidad_base=?, tipo_uso=?,
            permite_fraccionamiento=?, stock_minimo=?, punto_reorden=?, stock_ideal=?, stock_maximo=?,
            costo_unitario_usd=?, precio_venta_usd=?, marca=?, color=?, tamano=?, gramaje=?, acabado=?,
            unidad_compra=?, contenido_compra=?, proveedor_principal=?, ubicacion=?, observaciones=?,
            actualizado_por=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?
        """, (
            values["sku"].strip(), values["nombre"].strip(), values["categoria"].strip(), values["unidad_base"],
            values["unidad_base"], values["tipo_uso"], 1 if values["fraccionable"] else 0,
            values["stock_minimo"], values["punto_reorden"], values["stock_ideal"], values["stock_maximo"],
            values["costo"], values["precio"], values["marca"].strip(), values["color"].strip(),
            values["tamano"].strip(), values["gramaje"].strip(), values["acabado"].strip(),
            values["unidad_compra"], values["contenido_compra"], values["proveedor"].strip(),
            values["ubicacion"].strip(), values["observaciones"].strip(), usuario, int(item_id),
        ))


def _cambiar_estado(item_id: int, estado: str, usuario: str) -> None:
    with db_transaction() as conn:
        conn.execute("UPDATE inventario SET estado=?, actualizado_por=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?", (estado, usuario, int(item_id)))


def render_inventario_unificado(usuario: str) -> None:
    st.subheader("Inventario unificado")
    st.caption("Un mismo artículo puede ser insumo, producto de reventa o ambos.")
    tab_lista, tab_crear, tab_editar, tab_clasificar = st.tabs(["Existencias", "Crear artículo", "Editar / desactivar", "Clasificar"])

    with tab_lista:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("Aún no hay artículos.")
        else:
            filtro = st.multiselect("Tipo de uso", TIPOS_USO, default=TIPOS_USO)
            vista = df[df["tipo_uso"].isin(filtro)] if filtro else df.iloc[0:0]
            mostrar = vista.copy()
            mostrar["fraccionable"] = mostrar["permite_fraccionamiento"].astype(int).map({1: "Sí", 0: "No"})
            cols = ["id", "sku", "nombre", "categoria", "marca", "color", "tamano", "tipo_uso", "unidad_base", "unidad_compra", "fraccionable", "stock_actual", "stock_minimo", "punto_reorden", "stock_ideal", "costo_unitario_usd", "precio_venta_usd", "ubicacion", "estado"]
            st.dataframe(mostrar[cols], use_container_width=True, hide_index=True)

    with tab_crear:
        st.info("Si registrarás una factura de compra, deja el stock inicial y el costo en 0 para evitar duplicar existencias.")
        with st.form("form_crear_item_unificado"):
            st.markdown("#### Identificación")
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU *", placeholder="Ej.: PAP-BOND-CARTA-75G")
            nombre = c2.text_input("Nombre *", placeholder="Ej.: Papel bond carta 75 g")
            categoria_sel = c3.selectbox("Categoría", CATEGORIAS_SUGERIDAS, index=CATEGORIAS_SUGERIDAS.index("General"))
            categoria_otro = st.text_input("Otra categoría")
            categoria = categoria_otro.strip() or categoria_sel
            d1, d2, d3 = st.columns(3)
            tipo_uso = d1.selectbox("Tipo de uso", TIPOS_USO, index=2)
            unidad_base = d2.selectbox("Unidad base", UNIDADES_BASE)
            fraccionable = d3.checkbox("Permite fraccionamiento", value=True)
            st.markdown("#### Características")
            a1, a2, a3, a4, a5 = st.columns(5)
            marca = a1.text_input("Marca"); color = a2.text_input("Color"); tamano = a3.text_input("Tamaño / medida"); gramaje = a4.text_input("Gramaje / grosor"); acabado = a5.text_input("Acabado")
            st.markdown("#### Compra y almacenamiento")
            b1, b2, b3, b4 = st.columns(4)
            unidad_compra = b1.selectbox("Unidad de compra", [""] + UNIDADES_BASE)
            contenido_compra = b2.number_input("Contenido por unidad de compra", min_value=0.0, step=1.0, format="%.4f")
            proveedor_principal = b3.text_input("Proveedor principal"); ubicacion = b4.text_input("Ubicación")
            st.markdown("#### Control de existencias")
            e1, e2, e3, e4 = st.columns(4)
            stock_actual = e1.number_input("Stock inicial", min_value=0.0, step=1.0, format="%.4f")
            stock_minimo = e2.number_input("Stock mínimo", min_value=0.0, step=1.0, format="%.4f")
            punto_reorden = e3.number_input("Punto de reorden", min_value=0.0, step=1.0, format="%.4f")
            stock_ideal = e4.number_input("Stock ideal", min_value=0.0, step=1.0, format="%.4f")
            stock_maximo = st.number_input("Stock máximo", min_value=0.0, step=1.0, format="%.4f")
            f1, f2 = st.columns(2)
            costo = f1.number_input("Costo unitario USD", min_value=0.0, step=0.01, format="%.4f")
            precio = f2.number_input("Precio venta USD", min_value=0.0, step=0.01, format="%.4f")
            observaciones = st.text_area("Observaciones")
            guardar = st.form_submit_button("Crear artículo", type="primary", use_container_width=True)
        if guardar:
            try:
                item_id = crear_item_unificado({"sku": sku, "nombre": nombre, "categoria": categoria, "tipo_uso": tipo_uso, "unidad_base": unidad_base, "permite_fraccionamiento": fraccionable, "stock_actual": stock_actual, "stock_minimo": stock_minimo, "costo_unitario_usd": costo, "precio_venta_usd": precio, "marca": marca, "color": color, "tamano": tamano, "gramaje": gramaje, "acabado": acabado, "unidad_compra": unidad_compra, "contenido_compra": contenido_compra, "proveedor_principal": proveedor_principal, "ubicacion": ubicacion, "stock_ideal": stock_ideal, "stock_maximo": stock_maximo, "punto_reorden": punto_reorden, "observaciones": observaciones}, usuario)
                st.success(f"Artículo #{item_id} creado."); st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_editar:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("No hay artículos para editar.")
        else:
            opciones = {f"#{int(r['id'])} · {r['nombre']} · {r['sku']}": r for _, r in df.iterrows()}
            seleccion = st.selectbox("Artículo a editar", list(opciones.keys()), key="editar_item_inventario")
            row = opciones[seleccion]
            with st.form("form_editar_item_unificado"):
                c1, c2, c3 = st.columns(3)
                sku_e = c1.text_input("SKU *", value=str(row["sku"] or "")); nombre_e = c2.text_input("Nombre *", value=str(row["nombre"] or "")); categoria_e = c3.text_input("Categoría", value=str(row["categoria"] or "General"))
                d1, d2, d3 = st.columns(3)
                tipo_e = d1.selectbox("Tipo de uso", TIPOS_USO, index=TIPOS_USO.index(str(row["tipo_uso"])) if str(row["tipo_uso"]) in TIPOS_USO else 2)
                unidades = list(UNIDADES_BASE); unidad_actual = str(row["unidad_base"] or "unidad")
                if unidad_actual not in unidades: unidades.insert(0, unidad_actual)
                unidad_e = d2.selectbox("Unidad base", unidades, index=unidades.index(unidad_actual)); fracc_e = d3.checkbox("Permite fraccionamiento", value=bool(int(row["permite_fraccionamiento"] or 0)))
                a1, a2, a3, a4, a5 = st.columns(5)
                marca_e = a1.text_input("Marca", value=str(row["marca"] or "")); color_e = a2.text_input("Color", value=str(row["color"] or "")); tamano_e = a3.text_input("Tamaño / medida", value=str(row["tamano"] or "")); gramaje_e = a4.text_input("Gramaje / grosor", value=str(row["gramaje"] or "")); acabado_e = a5.text_input("Acabado", value=str(row["acabado"] or ""))
                b1, b2, b3, b4 = st.columns(4)
                uc_actual = str(row["unidad_compra"] or ""); uc_opts = [""] + UNIDADES_BASE
                if uc_actual not in uc_opts: uc_opts.insert(1, uc_actual)
                uc_e = b1.selectbox("Unidad de compra", uc_opts, index=uc_opts.index(uc_actual)); contenido_e = b2.number_input("Contenido por unidad de compra", min_value=0.0, value=float(row["contenido_compra"] or 0), step=1.0); proveedor_e = b3.text_input("Proveedor principal", value=str(row["proveedor_principal"] or "")); ubicacion_e = b4.text_input("Ubicación", value=str(row["ubicacion"] or ""))
                e1, e2, e3, e4 = st.columns(4)
                e1.metric("Stock actual", f"{float(row['stock_actual'] or 0):g} {unidad_actual}")
                minimo_e = e2.number_input("Stock mínimo", min_value=0.0, value=float(row["stock_minimo"] or 0), step=1.0); reorden_e = e3.number_input("Punto de reorden", min_value=0.0, value=float(row["punto_reorden"] or 0), step=1.0); ideal_e = e4.number_input("Stock ideal", min_value=0.0, value=float(row["stock_ideal"] or 0), step=1.0)
                maximo_e = st.number_input("Stock máximo", min_value=0.0, value=float(row["stock_maximo"] or 0), step=1.0)
                f1, f2 = st.columns(2)
                costo_e = f1.number_input("Costo unitario USD", min_value=0.0, value=float(row["costo_unitario_usd"] or 0), step=0.01, format="%.4f"); precio_e = f2.number_input("Precio venta USD", min_value=0.0, value=float(row["precio_venta_usd"] or 0), step=0.01, format="%.4f")
                obs_e = st.text_area("Observaciones", value=str(row["observaciones"] or ""))
                actualizar = st.form_submit_button("Guardar cambios", type="primary", use_container_width=True)
            if actualizar:
                try:
                    _actualizar_articulo(int(row["id"]), {"sku": sku_e, "nombre": nombre_e, "categoria": categoria_e, "tipo_uso": tipo_e, "unidad_base": unidad_e, "fraccionable": fracc_e, "stock_minimo": minimo_e, "punto_reorden": reorden_e, "stock_ideal": ideal_e, "stock_maximo": maximo_e, "costo": costo_e, "precio": precio_e, "marca": marca_e, "color": color_e, "tamano": tamano_e, "gramaje": gramaje_e, "acabado": acabado_e, "unidad_compra": uc_e, "contenido_compra": contenido_e, "proveedor": proveedor_e, "ubicacion": ubicacion_e, "observaciones": obs_e}, usuario)
                    st.success("Artículo actualizado correctamente."); st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar: {exc}")
            st.divider()
            estado_actual = str(row["estado"] or "activo").lower()
            st.warning("Desactivar conserva el artículo y su historial, pero evita utilizarlo como artículo activo.")
            if estado_actual == "activo":
                confirmar = st.checkbox("Confirmo que deseo desactivar este artículo", key=f"confirmar_desactivar_{int(row['id'])}")
                if st.button("Desactivar artículo", disabled=not confirmar, use_container_width=True):
                    _cambiar_estado(int(row["id"]), "inactivo", usuario); st.success("Artículo desactivado."); st.rerun()
            else:
                if st.button("Reactivar artículo", use_container_width=True):
                    _cambiar_estado(int(row["id"]), "activo", usuario); st.success("Artículo reactivado."); st.rerun()

    with tab_clasificar:
        df = listar_inventario_unificado(activos_only=False)
        if df.empty:
            st.info("No hay artículos para clasificar.")
        else:
            opciones = {f"#{int(row['id'])} - {row['nombre']} - {row['tipo_uso']}": row for _, row in df.iterrows()}
            seleccion = st.selectbox("Artículo", list(opciones.keys()))
            row = opciones[seleccion]; tipo_actual = str(row.get("tipo_uso") or "Ambos"); unidad_actual = str(row.get("unidad_base") or row.get("unidad") or "unidad")
            unidades = list(UNIDADES_BASE)
            if unidad_actual not in unidades: unidades.insert(0, unidad_actual)
            with st.form("form_clasificar_item"):
                c1, c2, c3 = st.columns(3)
                tipo_nuevo = c1.selectbox("Tipo de uso", TIPOS_USO, index=TIPOS_USO.index(tipo_actual) if tipo_actual in TIPOS_USO else 2)
                unidad_nueva = c2.selectbox("Unidad base", unidades, index=unidades.index(unidad_actual)); fraccionable_nuevo = c3.checkbox("Permite fraccionamiento", value=bool(int(row.get("permite_fraccionamiento") or 0)))
                guardar_cambio = st.form_submit_button("Guardar clasificación", type="primary", use_container_width=True)
            if guardar_cambio:
                try:
                    guardar_clasificacion_inventario(int(row["id"]), tipo_uso=tipo_nuevo, unidad_base=unidad_nueva, permite_fraccionamiento=fraccionable_nuevo)
                    st.success("Clasificación actualizada."); st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar: {exc}")
