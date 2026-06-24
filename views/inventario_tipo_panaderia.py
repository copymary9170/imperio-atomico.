from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from services.facturas_compra_service import listar_facturas_compra
from services.inventario_factura_lote_service import registrar_lote_con_factura
from services.inventario_operativo_service import listar_recetas
from services.inventario_tipo_panaderia_service import (
    CLASES_ARTICULO,
    guardar_clasificacion,
    listar_articulos_clasificados,
    listar_lotes,
    listar_produccion_diaria,
    registrar_produccion_diaria,
    resumen_panaderia,
)


def _selector_articulo(df, label: str, key: str) -> int:
    ids = [int(x) for x in df["id"].tolist()]
    etiquetas = {
        int(row["id"]): f"{row['sku']} · {row['nombre']} · {row['stock_actual']:.2f} {row['unidad']}"
        for _, row in df.iterrows()
    }
    return st.selectbox(label, ids, format_func=lambda value: etiquetas[value], key=key)


def render_inventario_tipo_panaderia(usuario: str) -> None:
    st.subheader("🥖 Inventario tipo panadería")
    st.caption(
        "Organiza el negocio por materias primas, recetas, producción diaria, lotes, "
        "vencimientos, rendimiento y producto terminado."
    )

    resumen = resumen_panaderia()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Artículos", int(resumen["articulos"]))
    c2.metric("Bajo mínimo", int(resumen["bajo_minimo"]))
    c3.metric("Lotes por vencer", int(resumen["lotes_por_vencer"]))
    c4.metric("Producido hoy", f"{resumen['producido_hoy']:,.2f}")
    c5.metric("Merma de hoy", f"{resumen['merma_hoy']:,.2f}")

    tabs = st.tabs([
        "🧺 Clasificación",
        "📦 Lotes y vencimientos",
        "🗓️ Producción diaria",
        "📈 Rendimiento",
    ])

    articulos = listar_articulos_clasificados()

    with tabs[0]:
        st.markdown("### Separar como una panadería")
        st.write(
            "Materia prima es lo que se consume para producir; empaque acompaña el producto; "
            "producto terminado es lo que ya puede venderse; mercancía para reventa se vende sin transformación."
        )
        if articulos.empty:
            st.info("Primero crea artículos en el Maestro.")
        else:
            item_id = _selector_articulo(articulos, "Artículo", "pan_clas_item")
            row = articulos[articulos["id"] == item_id].iloc[0]
            with st.form("clasificacion_panaderia"):
                clase = st.selectbox(
                    "Clase",
                    CLASES_ARTICULO,
                    index=CLASES_ARTICULO.index(str(row["clase_articulo"]))
                    if str(row["clase_articulo"]) in CLASES_ARTICULO else 0,
                )
                c1, c2, c3 = st.columns(3)
                controla_lotes = c1.checkbox("Controlar por lotes", value=bool(row["controla_lotes"]))
                controla_vencimiento = c2.checkbox("Controlar vencimiento", value=bool(row["controla_vencimiento"]))
                vida_util = c3.number_input("Vida útil estimada (días)", min_value=0, value=int(row["dias_vida_util"] or 0))
                ok = st.form_submit_button("Guardar clasificación", type="primary")
            if ok:
                try:
                    guardar_clasificacion(
                        item_id,
                        clase_articulo=clase,
                        controla_lotes=controla_lotes,
                        controla_vencimiento=controla_vencimiento,
                        dias_vida_util=int(vida_util),
                    )
                    st.success("Clasificación guardada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            vista = articulos[[
                "sku", "nombre", "clase_articulo", "unidad", "stock_actual",
                "stock_minimo", "controla_lotes", "controla_vencimiento",
                "dias_vida_util", "ubicacion",
            ]].copy()
            st.dataframe(vista, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.markdown("### Entrada por lote y factura")
        st.info(
            "Primero registra la factura de compra. Después selecciona aquí esa factura para "
            "crear el lote sin duplicar la entrada de stock."
        )
        if articulos.empty:
            st.info("No hay artículos activos.")
        else:
            facturas = listar_facturas_compra(limit=200)
            factura_opciones = {"Sin factura registrada": None}
            if not facturas.empty:
                for _, factura in facturas.iterrows():
                    etiqueta = (
                        f"#{int(factura['id'])} · {factura.get('numero_factura') or 'S/N'} · "
                        f"{factura.get('proveedor') or 'Proveedor N/D'} · ${float(factura.get('total_usd') or 0):,.2f}"
                    )
                    factura_opciones[etiqueta] = int(factura["id"])

            with st.form("entrada_lote_panaderia"):
                factura_label = st.selectbox("Factura de compra", list(factura_opciones.keys()))
                factura_id = factura_opciones[factura_label]
                item_id = _selector_articulo(articulos, "Artículo recibido", "pan_lote_item")
                c1, c2, c3 = st.columns(3)
                codigo = c1.text_input("Código de lote *", placeholder="LOT-2026-001")
                cantidad = c2.number_input("Cantidad recibida", min_value=0.0001, step=1.0)
                costo = c3.number_input("Costo por unidad base USD", min_value=0.0, step=0.01)
                c4, c5 = st.columns(2)
                fecha_entrada = c4.date_input("Fecha de entrada", value=date.today())
                sin_vencimiento = c5.checkbox("Sin vencimiento", value=True)
                fecha_vencimiento = st.date_input(
                    "Fecha de vencimiento",
                    value=date.today() + timedelta(days=180),
                    disabled=sin_vencimiento,
                )
                c6, c7 = st.columns(2)
                proveedor = c6.text_input("Proveedor opcional")
                ubicacion = c7.text_input("Ubicación física", placeholder="Estante A · Nivel 2 · Caja 3")
                stock_ya_contabilizado = st.checkbox(
                    "La factura ya agregó esta compra al inventario",
                    value=bool(factura_id),
                    disabled=not bool(factura_id),
                    help="Déjalo activo para evitar que la misma compra aumente el stock dos veces.",
                )
                observaciones = st.text_area("Observaciones")
                ok = st.form_submit_button("Registrar lote vinculado", type="primary")
            if ok:
                try:
                    lote_id = registrar_lote_con_factura(
                        item_id,
                        factura_id=factura_id,
                        codigo_lote=codigo,
                        cantidad=cantidad,
                        costo_unitario_usd=costo,
                        fecha_entrada=fecha_entrada.isoformat(),
                        fecha_vencimiento=None if sin_vencimiento else fecha_vencimiento.isoformat(),
                        proveedor=proveedor,
                        ubicacion=ubicacion,
                        observaciones=observaciones,
                        usuario=usuario,
                        stock_ya_contabilizado=stock_ya_contabilizado,
                    )
                    st.success(f"Lote #{lote_id} registrado y vinculado a la factura.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        lotes = listar_lotes()
        if lotes.empty:
            st.info("Todavía no hay lotes registrados.")
        else:
            st.dataframe(lotes, use_container_width=True, hide_index=True)
            st.caption("Orden FEFO: primero debe consumirse lo que vence primero.")

    with tabs[2]:
        st.markdown("### Registro del día")
        st.info(
            "Al procesar automáticamente, el sistema descuenta los materiales de la receta, "
            "consume primero los lotes próximos a vencer y agrega al stock únicamente la cantidad buena."
        )
        recetas = listar_recetas()
        receta_ids = [None] + ([int(x) for x in recetas["id"].tolist()] if not recetas.empty else [])
        receta_nombre = {None: "Producción manual / sin receta"}
        if not recetas.empty:
            receta_nombre.update({int(r["id"]): str(r["nombre"]) for _, r in recetas.iterrows()})
        producto_ids = [None] + ([int(x) for x in articulos["id"].tolist()] if not articulos.empty else [])
        producto_nombre = {None: "Servicio sin producto terminado"}
        if not articulos.empty:
            producto_nombre.update({int(r["id"]): str(r["nombre"]) for _, r in articulos.iterrows()})

        with st.form("produccion_diaria_panaderia"):
            procesar_inventario = st.checkbox(
                "Descontar materiales y aumentar producto terminado automáticamente",
                value=True,
            )
            c1, c2 = st.columns(2)
            receta_id = c1.selectbox("Receta o ficha", receta_ids, format_func=lambda value: receta_nombre[value])
            producto_id = c2.selectbox("Producto terminado", producto_ids, format_func=lambda value: producto_nombre[value])
            c3, c4 = st.columns(2)
            codigo_lote = c3.text_input("Lote de producción", placeholder="PROD-2026-001")
            referencia = c4.text_input("Pedido o referencia")
            c5, c6, c7 = st.columns(3)
            planificada = c5.number_input("Cantidad planificada", min_value=0.0, step=1.0)
            producida = c6.number_input("Cantidad procesada", min_value=0.0001, step=1.0)
            buena = c7.number_input("Cantidad buena", min_value=0.0, step=1.0)
            costo_total = st.number_input(
                "Costo total manual USD",
                min_value=0.0,
                step=0.01,
                disabled=procesar_inventario,
                help="Cuando el procesamiento automático está activo, el costo se calcula desde los materiales consumidos.",
            )
            ok = st.form_submit_button("Procesar producción del día", type="primary")
        if ok:
            try:
                registro_id = registrar_produccion_diaria(
                    receta_id=receta_id,
                    producto_id=producto_id,
                    codigo_lote=codigo_lote,
                    cantidad_planificada=planificada,
                    cantidad_producida=producida,
                    cantidad_buena=buena,
                    costo_total_usd=costo_total,
                    referencia=referencia,
                    usuario=usuario,
                    procesar_inventario=procesar_inventario,
                )
                st.success(
                    f"Producción #{registro_id} procesada. Materiales, lotes, costo y producto terminado quedaron actualizados."
                    if procesar_inventario else f"Producción diaria #{registro_id} registrada sin modificar existencias."
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        produccion = listar_produccion_diaria()
        if produccion.empty:
            st.info("No hay producción diaria registrada.")
        else:
            st.dataframe(produccion, use_container_width=True, hide_index=True)

    with tabs[3]:
        produccion = listar_produccion_diaria()
        if produccion.empty:
            st.info("Registra producción para medir rendimiento.")
        else:
            st.markdown("### Rendimiento y pérdida real")
            st.dataframe(
                produccion[[
                    "fecha", "receta", "producto", "codigo_lote",
                    "cantidad_planificada", "cantidad_producida", "cantidad_buena",
                    "cantidad_merma", "rendimiento_pct", "costo_total_usd",
                ]],
                use_container_width=True,
                hide_index=True,
            )
            total_procesado = float(produccion["cantidad_producida"].sum())
            total_bueno = float(produccion["cantidad_buena"].sum())
            rendimiento = total_bueno / total_procesado * 100 if total_procesado else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("Procesado", f"{total_procesado:,.2f}")
            c2.metric("Producto bueno", f"{total_bueno:,.2f}")
            c3.metric("Rendimiento global", f"{rendimiento:,.2f}%")
