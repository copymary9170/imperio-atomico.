from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.kardex import add_inventory_movement_shared


TIPOS_ITEM = {
    "producto_venta": "Producto de venta",
    "servicio": "Servicio",
    "materia_prima": "Materia prima / insumo",
    "producto_terminado": "Producto terminado",
    "empaque": "Empaque",
    "consumible": "Consumible interno",
    "activo_menor": "Activo menor / herramienta",
}


def _safe_read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except Exception as exc:
        st.error("No se pudo leer la información de inventario avanzado.")
        st.exception(exc)
        return pd.DataFrame()


def _load_inventory_options() -> pd.DataFrame:
    return _safe_read_sql(
        """
        SELECT
            id,
            COALESCE(sku, '') AS sku,
            COALESCE(nombre, '') AS nombre,
            COALESCE(categoria, '') AS categoria,
            COALESCE(unidad, '') AS unidad,
            COALESCE(tipo_item, 'producto_venta') AS tipo_item,
            COALESCE(unidad_base, '') AS unidad_base,
            COALESCE(unidad_compra, '') AS unidad_compra,
            COALESCE(stock_actual, 0) AS stock_actual,
            COALESCE(stock_ideal, 0) AS stock_ideal,
            COALESCE(punto_reorden, 0) AS punto_reorden,
            COALESCE(costo_unitario_usd, 0) AS costo_unitario_usd,
            COALESCE(precio_venta_usd, 0) AS precio_venta_usd
        FROM inventario
        ORDER BY nombre COLLATE NOCASE
        """
    )


def _item_label(df: pd.DataFrame, item_id: int) -> str:
    row = df[df["id"] == item_id]
    if row.empty:
        return str(item_id)
    data = row.iloc[0]
    sku = str(data.get("sku") or "").strip()
    nombre = str(data.get("nombre") or "").strip()
    return f"{nombre} ({sku})" if sku else nombre


def _set_receta_activa(receta_id: int, activo: int) -> None:
    with db_transaction() as conn:
        conn.execute("UPDATE recetas_consumo SET activo = ? WHERE id = ?", (int(activo), int(receta_id)))


def _render_clasificacion(usuario: str) -> None:
    st.subheader("🏷️ Clasificación de artículos")
    st.caption("Define si un artículo es producto, servicio, materia prima, empaque o consumible. Esto controla cómo se descuenta en ventas.")

    inv = _load_inventory_options()
    if inv.empty:
        st.info("Primero registra artículos en inventario.")
        return

    item_id = st.selectbox(
        "Artículo",
        inv["id"].tolist(),
        format_func=lambda i: _item_label(inv, i),
        key="clasificacion_item_id",
    )
    row = inv[inv["id"] == item_id].iloc[0]
    tipo_actual = str(row.get("tipo_item") or "producto_venta")
    tipo_keys = list(TIPOS_ITEM.keys())
    tipo_index = tipo_keys.index(tipo_actual) if tipo_actual in tipo_keys else 0

    with st.form("form_clasificacion_articulo"):
        tipo_item = st.selectbox(
            "Tipo de artículo",
            tipo_keys,
            index=tipo_index,
            format_func=lambda value: TIPOS_ITEM.get(value, value),
        )
        c1, c2, c3 = st.columns(3)
        unidad_base = c1.text_input("Unidad base", value=str(row.get("unidad_base") or row.get("unidad") or "unidad"))
        unidad_compra = c2.text_input("Unidad de compra", value=str(row.get("unidad_compra") or ""))
        punto_reorden = c3.number_input("Punto de reorden", min_value=0.0, value=float(row.get("punto_reorden") or 0), step=1.0)
        stock_ideal = st.number_input("Stock ideal", min_value=0.0, value=float(row.get("stock_ideal") or 0), step=1.0)
        guardar = st.form_submit_button("Guardar clasificación")

    if guardar:
        try:
            with db_transaction() as conn:
                conn.execute(
                    """
                    UPDATE inventario
                    SET tipo_item = ?,
                        unidad_base = ?,
                        unidad_compra = ?,
                        punto_reorden = ?,
                        stock_ideal = ?
                    WHERE id = ?
                    """,
                    (
                        tipo_item,
                        unidad_base.strip(),
                        unidad_compra.strip(),
                        float(punto_reorden),
                        float(stock_ideal),
                        int(item_id),
                    ),
                )
            st.success("Clasificación guardada.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo guardar la clasificación.")
            st.exception(exc)

    resumen = inv[["sku", "nombre", "categoria", "tipo_item", "unidad_base", "unidad_compra", "stock_actual", "punto_reorden", "stock_ideal"]].copy()
    resumen["tipo_item"] = resumen["tipo_item"].map(lambda value: TIPOS_ITEM.get(str(value), str(value)))
    st.dataframe(resumen, use_container_width=True, hide_index=True)


def _render_recetas(usuario: str) -> None:
    st.subheader("🧪 Recetas de consumo")
    st.caption("Define qué insumos consume cada producto o servicio vendido.")

    inv = _load_inventory_options()
    if inv.empty:
        st.info("Primero registra productos e insumos en inventario.")
        return

    with st.form("form_receta_consumo"):
        c1, c2 = st.columns(2)
        producto_id = c1.selectbox(
            "Producto / servicio final",
            inv["id"].tolist(),
            format_func=lambda i: _item_label(inv, i),
            key="receta_producto_id",
        )
        insumo_id = c2.selectbox(
            "Insumo consumido",
            inv["id"].tolist(),
            format_func=lambda i: _item_label(inv, i),
            key="receta_insumo_id",
        )
        c3, c4 = st.columns(2)
        cantidad = c3.number_input("Cantidad de insumo por unidad vendida", min_value=0.0, value=1.0, step=0.01)
        unidad = c4.text_input("Unidad", value="unidad")
        merma_pct = st.number_input("Merma estimada (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
        observaciones = st.text_area("Observaciones", value="")
        guardar = st.form_submit_button("Guardar receta")

    if guardar:
        if producto_id == insumo_id:
            st.error("El producto final y el insumo no pueden ser el mismo artículo.")
        elif cantidad <= 0:
            st.error("La cantidad debe ser mayor que cero.")
        else:
            try:
                with db_transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO recetas_consumo(producto_id, insumo_id, cantidad_insumo, unidad, merma_pct, observaciones)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (int(producto_id), int(insumo_id), float(cantidad), unidad.strip(), float(merma_pct), observaciones.strip()),
                    )
                st.success("Receta guardada.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo guardar la receta.")
                st.exception(exc)

    recetas = _safe_read_sql(
        """
        SELECT
            r.id,
            p.nombre AS producto,
            p.sku AS producto_sku,
            i.nombre AS insumo,
            i.sku AS insumo_sku,
            r.cantidad_insumo,
            r.unidad,
            r.merma_pct,
            r.activo,
            r.observaciones
        FROM recetas_consumo r
        JOIN inventario p ON p.id = r.producto_id
        JOIN inventario i ON i.id = r.insumo_id
        ORDER BY p.nombre, i.nombre
        """
    )

    if recetas.empty:
        st.info("Aún no hay recetas creadas.")
        return

    st.dataframe(recetas, use_container_width=True, hide_index=True)
    st.markdown("### Activar / desactivar recetas")
    st.caption("Desactivar una receta evita que ventas consuma sus insumos, pero conserva el registro para historial.")

    for _, receta in recetas.iterrows():
        estado = "Activa" if int(receta["activo"] or 0) == 1 else "Inactiva"
        label = f"#{int(receta['id'])} · {receta['producto']} → {receta['insumo']} · {receta['cantidad_insumo']} {receta['unidad'] or ''} · {estado}"
        col_info, col_accion = st.columns([4, 1])
        col_info.write(label)
        if int(receta["activo"] or 0) == 1:
            if col_accion.button("Desactivar", key=f"desactivar_receta_{int(receta['id'])}"):
                try:
                    _set_receta_activa(int(receta["id"]), 0)
                    st.success("Receta desactivada.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo desactivar la receta.")
                    st.exception(exc)
        else:
            if col_accion.button("Reactivar", key=f"reactivar_receta_{int(receta['id'])}"):
                try:
                    _set_receta_activa(int(receta["id"]), 1)
                    st.success("Receta reactivada.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo reactivar la receta.")
                    st.exception(exc)


def _render_simulador_consumo() -> None:
    st.subheader("🧮 Simulador de consumo")
    st.caption("Vista previa de los insumos que se descontarían al vender un producto o servicio con receta.")

    inv = _load_inventory_options()
    if inv.empty:
        st.info("Primero registra artículos y recetas.")
        return

    c1, c2 = st.columns([3, 1])
    producto_id = c1.selectbox(
        "Producto / servicio a vender",
        inv["id"].tolist(),
        format_func=lambda i: _item_label(inv, i),
        key="simulador_producto_id",
    )
    cantidad = c2.number_input("Cantidad a vender", min_value=0.01, value=1.0, step=1.0, key="simulador_cantidad")

    consumos = _safe_read_sql(
        """
        SELECT
            i.sku,
            i.nombre AS insumo,
            COALESCE(r.cantidad_insumo, 0) AS cantidad_por_unidad,
            COALESCE(r.merma_pct, 0) AS merma_pct,
            COALESCE(r.unidad, i.unidad, '') AS unidad,
            COALESCE(i.stock_actual, 0) AS stock_actual,
            COALESCE(i.costo_unitario_usd, 0) AS costo_unitario_usd,
            COALESCE(r.cantidad_insumo, 0) * ? AS cantidad_base,
            COALESCE(r.cantidad_insumo, 0) * ? * (1 + (COALESCE(r.merma_pct, 0) / 100.0)) AS cantidad_total
        FROM recetas_consumo r
        JOIN inventario i ON i.id = r.insumo_id
        WHERE r.producto_id = ?
          AND COALESCE(r.activo, 1) = 1
        ORDER BY i.nombre COLLATE NOCASE
        """,
        (float(cantidad), float(cantidad), int(producto_id)),
    )

    if consumos.empty:
        st.info("Este producto o servicio no tiene receta activa. No se descontarán insumos por receta.")
        return

    consumos["costo_total_usd"] = consumos["cantidad_total"].astype(float) * consumos["costo_unitario_usd"].astype(float)
    consumos["stock_despues"] = consumos["stock_actual"].astype(float) - consumos["cantidad_total"].astype(float)
    consumos["estado_stock"] = consumos["stock_despues"].apply(lambda value: "OK" if float(value) >= 0 else "Insuficiente")

    c1, c2, c3 = st.columns(3)
    c1.metric("Insumos", len(consumos))
    c2.metric("Costo estimado", f"${float(consumos['costo_total_usd'].sum()):,.2f}")
    c3.metric("Alertas de stock", int((consumos["estado_stock"] == "Insuficiente").sum()))

    st.dataframe(
        consumos[[
            "sku",
            "insumo",
            "cantidad_por_unidad",
            "merma_pct",
            "cantidad_total",
            "unidad",
            "stock_actual",
            "stock_despues",
            "estado_stock",
            "costo_total_usd",
        ]],
        use_container_width=True,
        hide_index=True,
    )

def _render_historial_consumos_receta() -> None:
    st.subheader("📜 Historial de consumos por receta")
    st.caption("Auditoría de insumos descontados automáticamente por ventas con receta.")

    df = _safe_read_sql(
        """
        SELECT
            m.fecha,
            m.usuario,
            REPLACE(COALESCE(m.referencia, ''), 'Consumo receta por venta #', '') AS venta_id,
            i.sku,
            i.nombre AS insumo,
            ABS(COALESCE(m.cantidad, 0)) AS cantidad_consumida,
            COALESCE(m.costo_unitario_usd, 0) AS costo_unitario_usd,
            ABS(COALESCE(m.cantidad, 0)) * COALESCE(m.costo_unitario_usd, 0) AS costo_total_usd,
            m.referencia
        FROM movimientos_inventario m
        JOIN inventario i ON i.id = m.inventario_id
        WHERE COALESCE(m.referencia, '') LIKE 'Consumo receta por venta #%'
        ORDER BY m.fecha DESC, m.id DESC
        LIMIT 1000
        """
    )

    if df.empty:
        st.info("Aún no hay consumos automáticos por receta.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["cantidad_consumida"] = pd.to_numeric(df["cantidad_consumida"], errors="coerce").fillna(0)
    df["costo_total_usd"] = pd.to_numeric(df["costo_total_usd"], errors="coerce").fillna(0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Movimientos", len(df))
    c2.metric("Costo total consumido", f"${float(df['costo_total_usd'].sum()):,.2f}")
    c3.metric("Ventas con receta", df["venta_id"].nunique())

    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_conteo_fisico(usuario: str) -> None:
    st.subheader("📋 Conteo físico")
    st.caption("Registra diferencias entre el stock del sistema y lo contado físicamente.")

    inv = _load_inventory_options()
    if inv.empty:
        st.info("No hay inventario para contar.")
        return

    item_id = st.selectbox(
        "Artículo contado",
        inv["id"].tolist(),
        format_func=lambda i: _item_label(inv, i),
        key="conteo_item_id",
    )
    row = inv[inv["id"] == item_id].iloc[0]
    stock_sistema = float(row.get("stock_actual") or 0)
    costo_unitario = float(row.get("costo_unitario_usd") or 0)
    st.metric("Stock en sistema", f"{stock_sistema:,.2f}")

    with st.form("form_conteo_fisico"):
        stock_contado = st.number_input("Stock contado físicamente", min_value=0.0, value=stock_sistema, step=1.0)
        motivo = st.text_input("Motivo de la diferencia", value="Conteo físico")
        ajustar_stock = st.checkbox("Ajustar stock del sistema con este conteo", value=False)
        observaciones = st.text_area("Observaciones del conteo", value="")
        registrar = st.form_submit_button("Registrar conteo")

    if registrar:
        diferencia = float(stock_contado) - stock_sistema
        try:
            with db_transaction() as conn:
                cur = conn.execute(
                    "INSERT INTO conteos_fisicos(usuario, observaciones) VALUES (?, ?)",
                    (usuario, observaciones.strip()),
                )
                conteo_id = cur.lastrowid
                conn.execute(
                    """
                    INSERT INTO conteos_fisicos_detalle(conteo_id, inventario_id, stock_sistema, stock_contado, diferencia, motivo)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (conteo_id, int(item_id), stock_sistema, float(stock_contado), diferencia, motivo.strip()),
                )
            if ajustar_stock and diferencia != 0:
                add_inventory_movement_shared(
                    usuario=usuario,
                    inventario_id=int(item_id),
                    tipo="ajuste",
                    cantidad=float(diferencia),
                    costo_unitario_usd=costo_unitario,
                    referencia=f"Conteo físico: {motivo.strip() or 'Ajuste por conteo'}",
                )
        except Exception as exc:
            st.error("No se pudo registrar el conteo físico.")
            st.exception(exc)
        else:
            if ajustar_stock and diferencia != 0:
                st.success(f"Conteo registrado y stock ajustado. Diferencia aplicada: {diferencia:,.2f}")
            else:
                st.success(f"Conteo registrado. Diferencia: {diferencia:,.2f}")
            st.rerun()

    historial = _safe_read_sql(
        """
        SELECT
            c.fecha,
            c.usuario,
            i.nombre AS articulo,
            i.sku,
            d.stock_sistema,
            d.stock_contado,
            d.diferencia,
            d.motivo,
            c.observaciones
        FROM conteos_fisicos_detalle d
        JOIN conteos_fisicos c ON c.id = d.conteo_id
        JOIN inventario i ON i.id = d.inventario_id
        ORDER BY c.fecha DESC
        LIMIT 200
        """
    )
    st.dataframe(historial, use_container_width=True, hide_index=True)


def _render_rentabilidad() -> None:
    st.subheader("💰 Rentabilidad por producto")
    st.caption("Calcula margen usando el costo de receta cuando existe; si no hay receta activa, usa el costo unitario del inventario.")

    df = _safe_read_sql(
        """
        SELECT
            i.sku,
            i.nombre,
            i.categoria,
            i.unidad,
            COALESCE(i.tipo_item, 'producto_venta') AS tipo_item,
            COALESCE(i.stock_actual, 0) AS stock_actual,
            COALESCE(i.costo_unitario_usd, 0) AS costo_unitario_usd,
            COALESCE(i.precio_venta_usd, 0) AS precio_venta_usd,
            COALESCE(SUM(
                CASE
                    WHEN COALESCE(r.activo, 1) = 1
                    THEN COALESCE(r.cantidad_insumo, 0) * (1 + (COALESCE(r.merma_pct, 0) / 100.0)) * COALESCE(ins.costo_unitario_usd, 0)
                    ELSE 0
                END
            ), 0) AS costo_receta_usd,
            COUNT(r.id) AS lineas_receta
        FROM inventario i
        LEFT JOIN recetas_consumo r ON r.producto_id = i.id AND COALESCE(r.activo, 1) = 1
        LEFT JOIN inventario ins ON ins.id = r.insumo_id
        GROUP BY i.id
        ORDER BY i.nombre COLLATE NOCASE
        """
    )

    if df.empty:
        st.info("No hay productos para analizar.")
        return

    df["costo_base_usd"] = df.apply(
        lambda row: float(row["costo_receta_usd"] or 0) if float(row["costo_receta_usd"] or 0) > 0 else float(row["costo_unitario_usd"] or 0),
        axis=1,
    )
    df["fuente_costo"] = df.apply(
        lambda row: "Receta" if float(row["costo_receta_usd"] or 0) > 0 else "Inventario",
        axis=1,
    )
    df["ganancia_unitaria_usd"] = df["precio_venta_usd"].astype(float) - df["costo_base_usd"].astype(float)
    df["margen_pct"] = df.apply(
        lambda row: ((float(row["ganancia_unitaria_usd"]) / float(row["precio_venta_usd"])) * 100) if float(row["precio_venta_usd"] or 0) > 0 else 0,
        axis=1,
    )

    bajo_costo = df[df["ganancia_unitaria_usd"] < 0]
    margen_bajo = df[(df["ganancia_unitaria_usd"] >= 0) & (df["margen_pct"] < 30)]
    con_receta = df[df["fuente_costo"] == "Receta"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Artículos", len(df))
    c2.metric("Con costo por receta", len(con_receta))
    c3.metric("Por debajo del costo", len(bajo_costo))
    c4.metric("Margen menor a 30%", len(margen_bajo))

    columnas = [
        "sku",
        "nombre",
        "categoria",
        "tipo_item",
        "precio_venta_usd",
        "costo_base_usd",
        "costo_receta_usd",
        "costo_unitario_usd",
        "fuente_costo",
        "ganancia_unitaria_usd",
        "margen_pct",
        "stock_actual",
    ]
    st.dataframe(df[columnas].sort_values("margen_pct", ascending=True), use_container_width=True, hide_index=True)


def render_inventario_avanzado(usuario: str) -> None:
    st.caption("Inventario avanzado: clasificación, recetas, simulación, conteo físico y rentabilidad.")
    tabs = st.tabs([
    "🏷️ Clasificación",
    "🧪 Recetas",
    "🧮 Simulador",
    "📋 Conteo físico",
    "💰 Rentabilidad",
    "📜 Consumos",
])
        _render_clasificacion(usuario)
    with tabs[1]:
        _render_recetas(usuario)
    with tabs[2]:
        _render_simulador_consumo()
    with tabs[3]:
        _render_conteo_fisico(usuario)
    with tabs[4]:
    _render_rentabilidad()
    with tabs[5]:
    _render_historial_consumos_receta()
