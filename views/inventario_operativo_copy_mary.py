from __future__ import annotations

import streamlit as st

from services.inventario_operativo_service import (
    TIPOS_MOVIMIENTO, agregar_insumo_receta, consumir_reserva, crear_receta,
    liberar_reserva, listar_articulos, listar_mermas, listar_recetas, listar_reservas,
    producir, registrar_conteo, registrar_merma, registrar_movimiento, reservar,
)


def _selector_articulo(label: str, key: str) -> int | None:
    df = listar_articulos()
    if df.empty:
        st.info("No hay artículos activos. Créalo primero en la pestaña Maestro.")
        return None
    ids = [int(x) for x in df["id"].tolist()]
    mapa = {
        int(r["id"]): f"{r['nombre']} · {r['stock_disponible']:.2f} {r['unidad']} disponibles"
        for _, r in df.iterrows()
    }
    return st.selectbox(label, ids, format_func=lambda x: mapa[x], key=key)


def render_inventario_operativo_copy_mary(usuario: str) -> None:
    st.subheader("🏭 Control operativo de inventario")
    st.caption("Compras, salidas, reservas, producción, mermas y conteos físicos conectados al stock real.")
    tabs = st.tabs(["Existencias", "Movimientos", "Reservas", "Recetas", "Producción", "Mermas", "Conteo físico"])

    with tabs[0]:
        df = listar_articulos()
        if df.empty:
            st.info("Todavía no hay artículos. Ve a Maestro para crear el primero.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[1]:
        item_id = _selector_articulo("Artículo", "mov_item")
        if item_id is not None:
            with st.form("movimiento_operativo"):
                c1, c2, c3 = st.columns(3)
                tipo = c1.selectbox("Tipo", TIPOS_MOVIMIENTO)
                cantidad = c2.number_input("Cantidad", min_value=0.0001, step=1.0)
                costo = c3.number_input("Costo por unidad base", min_value=0.0, step=0.01)
                motivo = st.text_input("Motivo o documento", placeholder="Compra #25, venta #103, ajuste...")
                ok = st.form_submit_button("Registrar movimiento", type="primary")
            if ok:
                try:
                    registrar_movimiento(
                        inventario_id=item_id, tipo=tipo, cantidad=cantidad,
                        costo_unitario=costo, motivo=motivo, usuario=usuario,
                    )
                    st.success("Movimiento registrado y stock actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tabs[2]:
        item_id = _selector_articulo("Artículo a reservar", "res_item")
        if item_id is not None:
            with st.form("crear_reserva"):
                c1, c2 = st.columns(2)
                cantidad = c1.number_input("Cantidad reservada", min_value=0.0001, step=1.0)
                referencia = c2.text_input("Pedido o referencia *", placeholder="Pedido CM-104")
                ok = st.form_submit_button("Reservar", type="primary")
            if ok:
                try:
                    rid = reservar(inventario_id=item_id, cantidad=cantidad, referencia=referencia, usuario=usuario)
                    st.success(f"Reserva #{rid} creada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        reservas = listar_reservas()
        if reservas.empty:
            st.info("No hay reservas registradas.")
        else:
            st.dataframe(reservas, use_container_width=True, hide_index=True)
            activas = reservas[reservas["estado"] == "activa"]
            if not activas.empty:
                rid = st.selectbox("Reserva activa", [int(x) for x in activas["id"]])
                c1, c2 = st.columns(2)
                if c1.button("Consumir reserva", use_container_width=True):
                    try:
                        consumir_reserva(rid, usuario)
                        st.success("Reserva consumida y descontada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                if c2.button("Liberar reserva", use_container_width=True):
                    liberar_reserva(rid)
                    st.success("Reserva liberada.")
                    st.rerun()

    with tabs[3]:
        st.markdown("#### Crear receta o ficha de materiales")
        articulos = listar_articulos()
        ids = [None] + [int(x) for x in articulos["id"].tolist()]
        nombres = {None: "Servicio sin producto terminado"}
        nombres.update({int(r["id"]): str(r["nombre"]) for _, r in articulos.iterrows()})
        with st.form("crear_receta"):
            nombre = st.text_input("Nombre de la receta *", placeholder="4 fotos tipo carnet")
            producto = st.selectbox("Producto terminado opcional", ids, format_func=lambda x: nombres[x])
            c1, c2 = st.columns(2)
            rendimiento = c1.number_input("Rendimiento", min_value=0.0001, value=1.0)
            unidad = c2.text_input("Unidad del rendimiento", value="servicio")
            obs = st.text_area("Observaciones")
            ok = st.form_submit_button("Crear receta", type="primary")
        if ok:
            try:
                receta_id = crear_receta(
                    nombre=nombre, producto_id=producto, rendimiento=rendimiento,
                    unidad=unidad, observaciones=obs, usuario=usuario,
                )
                st.success(f"Receta #{receta_id} creada.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        recetas = listar_recetas()
        if recetas.empty:
            st.info("Todavía no hay recetas.")
        else:
            st.dataframe(recetas, use_container_width=True, hide_index=True)
            st.markdown("#### Agregar material a receta")
            insumo_id = _selector_articulo("Insumo", "rec_insumo")
            if insumo_id is not None:
                with st.form("agregar_insumo"):
                    receta_id = st.selectbox(
                        "Receta", [int(x) for x in recetas["id"]],
                        format_func=lambda x: str(recetas.loc[recetas["id"] == x, "nombre"].iloc[0]),
                    )
                    c1, c2 = st.columns(2)
                    cantidad = c1.number_input("Cantidad por rendimiento", min_value=0.0001, step=0.1)
                    merma = c2.number_input("Merma prevista (%)", min_value=0.0, max_value=100.0)
                    ok = st.form_submit_button("Agregar material")
                if ok:
                    try:
                        agregar_insumo_receta(
                            receta_id=receta_id, insumo_id=insumo_id,
                            cantidad=cantidad, merma_pct=merma,
                        )
                        st.success("Material agregado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    with tabs[4]:
        recetas = listar_recetas()
        if recetas.empty:
            st.info("Primero crea una receta y agrega sus materiales.")
        else:
            with st.form("producir_receta"):
                receta_id = st.selectbox(
                    "Receta", [int(x) for x in recetas["id"]],
                    format_func=lambda x: str(recetas.loc[recetas["id"] == x, "nombre"].iloc[0]),
                )
                c1, c2 = st.columns(2)
                cantidad = c1.number_input("Cantidad a producir", min_value=0.0001, step=1.0)
                referencia = c2.text_input("Pedido o lote", placeholder="Pedido CM-104")
                ok = st.form_submit_button("Procesar producción", type="primary")
            if ok:
                try:
                    producir(
                        receta_id=receta_id, cantidad_producir=cantidad,
                        usuario=usuario, referencia=referencia,
                    )
                    st.success("Producción procesada y materiales descontados.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tabs[5]:
        item_id = _selector_articulo("Artículo perdido", "merma_item")
        if item_id is not None:
            with st.form("registrar_merma"):
                c1, c2 = st.columns(2)
                cantidad = c1.number_input("Cantidad perdida", min_value=0.0001, step=1.0)
                motivo = c2.selectbox(
                    "Motivo",
                    ["Impresión incorrecta", "Corte incorrecto", "Atasco", "Sublimación dañada", "Material manchado", "Prueba", "Humedad", "Vencimiento", "Otro"],
                )
                referencia = st.text_input("Pedido o detalle")
                ok = st.form_submit_button("Registrar merma", type="primary")
            if ok:
                try:
                    registrar_merma(
                        inventario_id=item_id, cantidad=cantidad, motivo=motivo,
                        referencia=referencia, usuario=usuario,
                    )
                    st.success("Merma registrada y valorizada.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        mermas = listar_mermas()
        if mermas.empty:
            st.info("No hay mermas registradas.")
        else:
            st.dataframe(mermas, use_container_width=True, hide_index=True)

    with tabs[6]:
        item_id = _selector_articulo("Artículo contado", "conteo_item")
        if item_id is not None:
            with st.form("conteo_fisico"):
                stock_fisico = st.number_input("Cantidad física encontrada", min_value=0.0, step=1.0)
                motivo = st.text_input("Observación", value="Conteo periódico")
                ok = st.form_submit_button("Guardar conteo y ajustar", type="primary")
            if ok:
                try:
                    diferencia = registrar_conteo(
                        inventario_id=item_id, stock_fisico=stock_fisico,
                        motivo=motivo, usuario=usuario,
                    )
                    st.success(f"Conteo registrado. Diferencia aplicada: {diferencia:+.2f}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
