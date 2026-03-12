import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.inventario import add_inventory_movement


def render_kardex(usuario: str):

    st.title("📊 Kardex Profesional")
    st.caption("Trazabilidad cronológica de entradas, salidas y ajustes con analítica operativa.")

    try:

        with db_transaction() as conn:

            productos = conn.execute(
                """
                SELECT id, sku, nombre, stock_actual, costo_unitario_usd
                FROM inventario
                WHERE estado='activo'
                ORDER BY nombre ASC
                """
            ).fetchall()

            rows = conn.execute(
                """
                SELECT
                    m.id,
                    m.fecha AS fecha,
                    m.usuario,
                    m.inventario_id,
                    i.sku,
                    i.nombre,
                    UPPER(m.tipo) AS tipo,
                    m.cantidad,
                    m.costo_unitario_usd,
                    (ABS(m.cantidad) * m.costo_unitario_usd) AS costo_total_usd,
                    m.referencia
                FROM movimientos_inventario
                m LEFT JOIN inventario i ON i.id = m.inventario_id
                ORDER BY m.fecha DESC
                LIMIT 2500
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando kardex")
        st.exception(e)
        return

    if not productos:
        st.info("No hay productos activos en inventario.")
        return

   movement_columns = [
        "id",
        "fecha",
        "usuario",
        "inventario_id",
        "sku",
        "nombre",
        "tipo",
        "cantidad",
        "costo_unitario_usd",
        "costo_total_usd",
        "referencia",
    ]

    if not rows:

        st.info("No hay movimientos registrados.")

        df = pd.DataFrame(columns=movement_columns)
    else:
        df = pd.DataFrame(rows, columns=movement_columns)

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["tipo"] = df["tipo"].fillna("AJUSTE").astype(str).str.upper()

    df_items = pd.DataFrame(
        productos,
        columns=["id", "sku", "nombre", "stock_actual", "costo_unitario_usd"],
    )

    selected_label = st.selectbox(
        "Producto",
        options=df_items["id"].tolist(),
        format_func=lambda item_id: (
            f"{df_items.loc[df_items['id'] == item_id, 'nombre'].iloc[0]}"
            f" ({df_items.loc[df_items['id'] == item_id, 'sku'].iloc[0]})"
        ),
    )

    item_row = df_items[df_items["id"] == selected_label].iloc[0]

    f1, f2, f3 = st.columns(3)
    fecha_inicio = f1.date_input(
        "Desde",
        value=(pd.Timestamp.now() - pd.Timedelta(days=30)).date(),
        key="kdx_desde",
    )
    fecha_fin = f2.date_input(
        "Hasta",
        value=pd.Timestamp.now().date(),
        key="kdx_hasta",
    )
    tipo_filtro = f3.multiselect(
        "Tipo",

        ["ENTRADA", "SALIDA", "AJUSTE"],
        default=["ENTRADA", "SALIDA", "AJUSTE"],
    )

    if fecha_inicio > fecha_fin:
        st.error("La fecha inicial no puede ser mayor a la fecha final.")
        return

    view = df[df["inventario_id"] == int(selected_label)].copy()
    view = view[
        view["fecha"].dt.date.between(fecha_inicio, fecha_fin)
    ]
    if tipo_filtro:
        view = view[view["tipo"].isin(tipo_filtro)]

    buscar = st.text_input("🔎 Buscar", placeholder="usuario o referencia")

    if buscar:
        view = view[
            view.astype(str)
            .apply(lambda x: x.str.contains(buscar, case=False))
            .any(axis=1)
        ]

    stock_actual = float(item_row["stock_actual"] or 0.0)
    costo_ref = float(item_row["costo_unitario_usd"] or 0.0)

    costo_promedio = float(view["costo_unitario_usd"].mean()) if not view.empty else costo_ref
    total_invertido = float(view[view["tipo"] == "ENTRADA"]["costo_total_usd"].sum()) if not view.empty else 0.0
    valor_total_actual = stock_actual * costo_promedio
    salidas_periodo = float(view[view["tipo"] == "SALIDA"]["cantidad"].abs().sum()) if not view.empty else 0.0

    if not view.empty:
        stock_eje = float((view["cantidad"].cumsum() + stock_actual - view["cantidad"].sum()).mean())
        rotacion = (salidas_periodo / stock_eje) if stock_eje > 0 else 0.0
    else:
        rotacion = 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Stock actual", f"{stock_actual:,.2f}")
    k2.metric("Costo promedio", f"$ {costo_promedio:,.4f}")
    k3.metric("Total invertido", f"$ {total_invertido:,.2f}")
    k4.metric("Valor total actual", f"$ {valor_total_actual:,.2f}")
    k5.metric("Rotación inventario", f"{rotacion:,.2f}")

    if view.empty:
        st.info("Sin movimientos para los filtros seleccionados.")
    else:
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "fecha": st.column_config.DatetimeColumn("Fecha", format="YYYY-MM-DD HH:mm:ss"),
                "usuario": "Usuario",
                "inventario_id": "ID Inventario",
                "sku": "SKU",
                "nombre": "Producto",
                "tipo": "Tipo",
                "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
                "costo_unitario_usd": st.column_config.NumberColumn("Costo unit", format="%.4f"),
                "costo_total_usd": st.column_config.NumberColumn("Costo total", format="%.2f"),
                "referencia": "Referencia",
            },
        )

        csv_data = view.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar CSV",
            data=csv_data,
            file_name=f"kardex_{item_row['nombre']}_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )

    st.divider()
    st.subheader("🔧 Ajuste manual")

    a1, a2, a3, a4 = st.columns([1, 1, 1, 2])
    accion_ajuste = a1.selectbox("Acción", ["Sumar stock", "Restar stock"], key="kdx_accion")
    cantidad_ajuste = a2.number_input("Cantidad", min_value=0.0, value=0.0, key="kdx_cantidad")
    usuario_ajuste = a3.text_input("Usuario", value=usuario or "Sistema", key="kdx_usuario")
    motivo_ajuste = a4.text_input("Motivo", value="Ajuste manual desde Kardex", key="kdx_motivo")

    if st.button("💾 Aplicar ajuste manual", use_container_width=True):
        if cantidad_ajuste <= 0:
            st.warning("La cantidad debe ser mayor a 0 para aplicar el ajuste.")
            return

        delta = float(cantidad_ajuste) if accion_ajuste == "Sumar stock" else -float(cantidad_ajuste)

        try:
            add_inventory_movement(
                usuario=usuario_ajuste,
                inventario_id=int(selected_label),
                tipo="ajuste",
                cantidad=delta,
                costo_unitario_usd=float(costo_ref),
                referencia=f"{motivo_ajuste} | {'Ajuste entrada' if delta > 0 else 'Ajuste salida'}",
            )
            st.success("Ajuste aplicado y registrado en Kardex.")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo aplicar el ajuste: {e}")
