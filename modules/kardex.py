from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text


CSV_COLUMNS = [
    "fecha",
    "tipo",
    "cantidad",
    "saldo",
    "usuario",
    "sku",
    "nombre",
    "costo_unitario_usd",
    "costo_total_usd",
    "referencia",
]


def _slugify_filename(value: str) -> str:
    safe_value = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "kardex").strip())
    return safe_value.strip("_") or "kardex"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def add_inventory_movement_shared(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float = 0.0,
    referencia: str = "",
) -> int:
    tipo_normalizado = clean_text(tipo).lower() or "ajuste"
    if tipo_normalizado not in {"entrada", "salida", "ajuste"}:
        raise ValueError("Tipo de movimiento inválido. Usa: entrada, salida o ajuste.")

    qty = float(cantidad or 0.0)
    if tipo_normalizado == "entrada":
        qty = abs(qty)
    elif tipo_normalizado == "salida":
        qty = -abs(qty)

    if qty == 0:
        raise ValueError("La cantidad del movimiento debe ser distinta de cero.")

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT stock_actual, costo_unitario_usd FROM inventario WHERE id=?",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("El ítem de inventario no existe.")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nuevo_stock = stock_actual + qty
        if nuevo_stock < 0:
            raise ValueError("El ajuste deja el inventario en negativo.")

        costo_mov = float(costo_unitario_usd if costo_unitario_usd is not None else costo_actual)

        conn.execute(
            """
            INSERT INTO movimientos_inventario(
                usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema").strip() or "Sistema",
                int(inventario_id),
                tipo_normalizado,
                float(qty),
                max(0.0, float(costo_mov or 0.0)),
                str(referencia or "").strip(),
            ),
        )

        conn.execute(
            "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
            (float(qty), int(inventario_id)),
        )

        mov_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return int(mov_id)


def render_kardex(usuario: str) -> None:
    st.title("📊 Kardex Profesional")
    st.caption("Trazabilidad cronológica de entradas, salidas y ajustes con analítica operativa.")

    try:
        with db_transaction() as conn:
            productos = conn.execute(
                """
                SELECT id, sku, nombre, stock_actual, costo_unitario_usd
                FROM inventario
                WHERE COALESCE(estado, 'activo')='activo'
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
                FROM movimientos_inventario m
                LEFT JOIN inventario i ON i.id = m.inventario_id
                WHERE COALESCE(m.estado, 'activo')='activo'
                ORDER BY m.fecha DESC
                LIMIT 5000
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
    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0.0)
    df["costo_unitario_usd"] = pd.to_numeric(df["costo_unitario_usd"], errors="coerce").fillna(0.0)
    df["costo_total_usd"] = pd.to_numeric(df["costo_total_usd"], errors="coerce").fillna(0.0)
    df["cantidad_abs"] = df["cantidad"].abs()

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
        key="kdx_producto",
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
        key="kdx_tipo",
    )

    if fecha_inicio > fecha_fin:
        st.error("La fecha inicial no puede ser mayor a la fecha final.")
        return

    producto_df = df[df["inventario_id"] == int(selected_label)].copy()
    producto_df = producto_df.sort_values("fecha")
    buscar = st.text_input("🔎 Buscar", placeholder="usuario o referencia", key="kdx_buscar")

    fecha_inicio_ts = pd.Timestamp(fecha_inicio)
    fecha_fin_ts = pd.Timestamp(fecha_fin) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

    view = producto_df[
        producto_df["fecha"].between(fecha_inicio_ts, fecha_fin_ts)
    ].copy()
    if tipo_filtro:
        view = view[view["tipo"].isin(tipo_filtro)]

    if buscar:
        view = view[
            view.astype(str)
            .apply(lambda x: x.str.contains(buscar, case=False, na=False))
            .any(axis=1)
        ]

    stock_actual = float(item_row["stock_actual"] or 0.0)
    costo_ref = float(item_row["costo_unitario_usd"] or 0.0)

    movimientos_despues_fin = producto_df[producto_df["fecha"] > fecha_fin_ts].copy()
    stock_cierre_periodo = float(stock_actual - movimientos_despues_fin["cantidad"].sum())

    movimientos_desde_inicio = producto_df[producto_df["fecha"] >= fecha_inicio_ts].copy()
    stock_inicial_periodo = float(stock_actual - movimientos_desde_inicio["cantidad"].sum())

    if not view.empty:
        saldo = stock_inicial_periodo + view["cantidad"].cumsum()
        view = view.assign(saldo=saldo)
    else:
        view = view.assign(saldo=pd.Series(dtype=float))

    entradas_periodo = float(view[view["cantidad"] > 0]["cantidad"].sum()) if not view.empty else 0.0
    salidas_periodo = float(view[view["cantidad"] < 0]["cantidad"].abs().sum()) if not view.empty else 0.0
    neto_periodo = entradas_periodo - salidas_periodo
    costo_promedio = float(view["costo_unitario_usd"].mean()) if not view.empty else costo_ref
    total_invertido = float(view[view["cantidad"] > 0]["costo_total_usd"].sum()) if not view.empty else 0.0
    valor_total_actual = stock_actual * costo_promedio

    stock_base_rotacion = (stock_inicial_periodo + stock_actual) / 2 if (stock_inicial_periodo + stock_actual) > 0 else 0.0
    rotacion = (salidas_periodo / stock_base_rotacion) if stock_base_rotacion > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Stock inicial período", f"{stock_inicial_periodo:,.2f}")
    k2.metric("Entradas", f"{entradas_periodo:,.2f}")
    k3.metric("Salidas", f"{salidas_periodo:,.2f}")
    k4.metric("Neto período", f"{neto_periodo:,.2f}")
    k5.metric("Stock actual", f"{stock_actual:,.2f}")

    k6, k7, k8, k9 = st.columns(4)
    k6.metric("Costo promedio", f"$ {costo_promedio:,.4f}")
    k7.metric("Total invertido", f"$ {total_invertido:,.2f}")
    k8.metric("Valor total actual", f"$ {valor_total_actual:,.2f}")
    k9.metric("Rotación inventario", f"{rotacion:,.2f}")

    st.caption(
        f"Cierre calculado del período: {stock_cierre_periodo:,.2f} unidades. "
        f"Movimientos analizados: {len(view)}"
    )

    if view.empty:
        st.info("Sin movimientos para los filtros seleccionados.")
    else:
        table_view = view.sort_values("fecha", ascending=False).copy()
        table_view["cantidad"] = table_view["cantidad"].map(lambda value: float(value))
        table_view["saldo"] = table_view["saldo"].map(lambda value: float(value))

        st.dataframe(
            table_view[
                [
                    "fecha",
                    "tipo",
                    "cantidad",
                    "saldo",
                    "usuario",
                    "sku",
                    "nombre",
                    "costo_unitario_usd",
                    "costo_total_usd",
                    "referencia",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "fecha": st.column_config.DatetimeColumn("Fecha", format="YYYY-MM-DD HH:mm:ss"),
                "tipo": "Tipo",
                "cantidad": st.column_config.NumberColumn("Movimiento", format="%.3f"),
                "saldo": st.column_config.NumberColumn("Saldo", format="%.3f"),
                "usuario": "Usuario",
                "sku": "SKU",
                "nombre": "Producto",
                "costo_unitario_usd": st.column_config.NumberColumn("Costo unit", format="%.4f"),
                "costo_total_usd": st.column_config.NumberColumn("Costo total", format="%.2f"),
                "referencia": "Referencia",
            },
        )

        csv_data = table_view[CSV_COLUMNS].to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Exportar CSV",
            data=csv_data,
            file_name=f"kardex_{_slugify_filename(item_row['nombre'])}_{fecha_inicio}_{fecha_fin}.csv",
            mime="text/csv",
        )

    st.divider()
    st.subheader("🔧 Ajuste manual")

    a1, a2, a3, a4 = st.columns([1, 1, 1, 2])
    accion_ajuste = a1.selectbox("Acción", ["Sumar stock", "Restar stock"], key="kdx_accion")
    cantidad_ajuste = a2.number_input("Cantidad", min_value=0.0, value=0.0, key="kdx_cantidad")
    usuario_ajuste = a3.text_input("Usuario", value=usuario or "Sistema", key="kdx_usuario")
    motivo_ajuste = a4.text_input("Motivo", value="Ajuste manual desde Kardex", key="kdx_motivo")

    if st.button("💾 Aplicar ajuste manual", use_container_width=True, key="kdx_guardar_ajuste"):
        if cantidad_ajuste <= 0:
            st.warning("La cantidad debe ser mayor a 0 para aplicar el ajuste.")
            return

        delta = float(cantidad_ajuste) if accion_ajuste == "Sumar stock" else -float(cantidad_ajuste)

        try:
            add_inventory_movement_shared(
                usuario=usuario_ajuste,
                inventario_id=int(selected_label),
                tipo="ajuste",
                cantidad=delta,
                costo_unitario_usd=costo_ref,
                referencia=motivo_ajuste,
            )
        except Exception as e:
            st.error("No se pudo aplicar el ajuste manual.")
            st.exception(e)
            return

        st.success("✅ Ajuste manual aplicado correctamente.")
        st.rerun()
