from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text
from utils.currency import convert_to_bs


METODOS_PAGO_VENTA = [
    "efectivo",
    "transferencia",
    "zelle",
    "binance",
    "kontigo",
    "credito",
]


# ============================================================
# REGISTRAR VENTA
# ============================================================

def registrar_venta(
    usuario: str,
    cliente_id: int | None,
    moneda: str,
    tasa_cambio: float,
    metodo_pago: str,
    items: list[dict],
) -> int:
    if not items:
        raise ValueError("Debe agregar al menos un item")

    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)

    subtotal = round(
        sum(
            as_positive(item["cantidad"], "Cantidad", allow_zero=False)
            * as_positive(item["precio_unitario_usd"], "Precio unitario")
            for item in items
        ),
        2,
    )

    impuesto = round(subtotal * 0.16, 2)
    total = round(subtotal + impuesto, 2)
    total_bs = round(convert_to_bs(total, tasa_cambio), 2)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ventas
            (usuario, cliente_id, moneda, tasa_cambio, metodo_pago,
             subtotal_usd, impuesto_usd, total_usd, total_bs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                cliente_id,
                moneda,
                tasa_cambio,
                metodo_pago,
                subtotal,
                impuesto,
                total,
                total_bs,
            ),
        )

        venta_id = int(cur.lastrowid)

        for item in items:
            cantidad = as_positive(item["cantidad"], "Cantidad", allow_zero=False)
            precio_u = as_positive(item["precio_unitario_usd"], "Precio unitario")
            costo_u = as_positive(item["costo_unitario_usd"], "Costo unitario")
            descripcion = clean_text(item.get("descripcion")) or "Item"
            inventario_id = item.get("inventario_id")

            conn.execute(
                """
                INSERT INTO ventas_detalle
                (usuario, venta_id, inventario_id, descripcion,
                 cantidad, precio_unitario_usd, costo_unitario_usd, subtotal_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    venta_id,
                    inventario_id,
                    descripcion,
                    cantidad,
                    precio_u,
                    costo_u,
                    round(cantidad * precio_u, 2),
                ),
            )

            if inventario_id:
                current = conn.execute(
                    """
                    SELECT stock_actual
                    FROM inventario
                    WHERE id=? AND estado='activo'
                    """,
                    (inventario_id,),
                ).fetchone()

                if not current:
                    raise ValueError(f"Inventario #{inventario_id} no existe")

                if float(current["stock_actual"] or 0.0) < cantidad:
                    raise ValueError("Stock insuficiente")

                conn.execute(
                    """
                    UPDATE inventario
                    SET stock_actual = stock_actual - ?
                    WHERE id = ?
                    """,
                    (cantidad, inventario_id),
                )

        if metodo_pago == "credito" and cliente_id:
@@ -184,245 +175,318 @@ def _render_tab_registro(usuario: str) -> None:
    with st.form("form_registrar_venta_pro", clear_on_submit=True):
        st.subheader("Datos de la venta")

        c1, c2, c3 = st.columns(3)

        cliente_opciones = {"Sin cliente": None}
        for c in clientes:
            cliente_opciones[c["nombre"]] = int(c["id"])

        cliente_nombre = c1.selectbox("Cliente", list(cliente_opciones.keys()))

        producto = c2.selectbox(
            "Producto",
            productos,
            format_func=lambda p: (
                f"{p['nombre']} · Stock: {float(p['stock_actual']):,.2f} · "
                f"$ {float(p['precio_venta_usd']):,.2f}"
            ),
        )

        cantidad = c3.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)

        c4, c5, c6, c7 = st.columns(4)

        metodo_pago = c4.selectbox("Método", METODOS_PAGO_VENTA)
        moneda = c5.selectbox("Moneda", ["USD", "BS", "USDT", "KONTIGO"])
        tasa = c6.number_input("Tasa de referencia", min_value=0.0001, value=36.5)

        monto_prev_usd = float(cantidad) * float(producto["precio_venta_usd"])
        utilidad_prev = monto_prev_usd - (float(cantidad) * float(producto["costo_unitario_usd"] or 0.0))
        c7.metric("Total estimado (Bs)", f"{convert_to_bs(monto_prev_usd, float(tasa)):,.2f}")

        p1, p2 = st.columns(2)
        p1.metric("Subtotal estimado (USD)", f"$ {monto_prev_usd:,.2f}")
        p2.metric("Utilidad estimada", f"$ {utilidad_prev:,.2f}")

        submit = st.form_submit_button("🚀 Registrar venta")

    if not submit:
        return

    try:
        if float(producto["stock_actual"] or 0.0) < float(cantidad):
            st.error("Stock insuficiente para registrar la venta.")
            return

        vid = registrar_venta(
            usuario=usuario,
            cliente_id=cliente_opciones[cliente_nombre],
            moneda=moneda,
            tasa_cambio=float(tasa),
            metodo_pago=metodo_pago,
            items=[
                {
                    "inventario_id": int(producto["id"]),
                    "descripcion": str(producto["nombre"]),
                    "cantidad": float(cantidad),
                    "precio_unitario_usd": float(producto["precio_venta_usd"]),
                    "costo_unitario_usd": float(producto["costo_unitario_usd"]),
                }
            ],
        )

        st.success(f"✅ Venta #{vid} registrada correctamente")
        st.balloons()
        st.rerun()

    except ValueError as exc:
        st.error(str(exc))
    except Exception as e:
        st.error("Error registrando venta")
        st.exception(e)


def _load_historial_ventas() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                v.id,
                v.fecha,
                COALESCE(c.nombre, 'Sin cliente') AS cliente,
                vd.descripcion AS detalle,
                vd.cantidad,
                vd.costo_unitario_usd,
                v.metodo_pago,
                v.moneda,
                v.tasa_cambio,
                v.total_usd,
                v.total_bs,
                v.estado
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
            WHERE v.estado='registrada'
            ORDER BY v.fecha DESC, v.id DESC
            """,
            conn,
        )


def _render_tab_historial() -> None:
    st.subheader("Historial de ventas")

    try:
        df = _load_historial_ventas()
    except Exception as e:
        st.error("Error cargando historial")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay ventas registradas.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir")
    df["utilidad_estimada"] = (
        df["total_usd"].fillna(0.0)
        - (df["cantidad"].fillna(0.0) * df["costo_unitario_usd"].fillna(0.0))
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="ventas_desde")
    hasta = c2.date_input("Hasta", date.today(), key="ventas_hasta")
    metodo = c3.selectbox("Método", ["Todos"] + sorted(df["metodo_pago"].str.title().unique().tolist()))
    buscador = c4.text_input("Buscar por cliente o detalle")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if metodo != "Todos":
        df_fil = df_fil[df_fil["metodo_pago"].str.lower() == metodo.lower()]

    if buscador:
        df_fil = df_fil[
            df_fil["cliente"].str.contains(buscador, case=False, na=False)
            | df_fil["detalle"].str.contains(buscador, case=False, na=False)
        ]

    k1, k2, k3 = st.columns(3)
    k1.metric("Total filtrado", f"$ {float(df_fil['total_usd'].sum()):,.2f}")
    k2.metric("N° ventas", f"{int(df_fil['id'].nunique())}")
    ticket = float(df_fil["total_usd"].sum()) / max(int(df_fil["id"].nunique()), 1)
    k3.metric("Ticket promedio", f"$ {ticket:,.2f}")

    st.dataframe(df_fil, use_container_width=True, hide_index=True)

    if not df_fil.empty:
        tendencia = (
            df_fil.assign(dia=df_fil["fecha"].dt.date)
            .groupby("dia", as_index=False)["total_usd"]
            .sum()
            .sort_values("dia")
        )
        metodos = (
            df_fil.groupby("metodo_pago", as_index=False)["total_usd"]
            .sum()
            .sort_values("total_usd", ascending=False)
        )

        g1, g2 = st.columns(2)
        with g1:
            st.caption("Tendencia de ventas")
            st.line_chart(tendencia.set_index("dia")["total_usd"])
        with g2:
            st.caption("Participación por método")
            st.bar_chart(metodos.set_index("metodo_pago")["total_usd"])

    st.subheader("Gestión de pendientes")
    pendientes = df_fil[df_fil["metodo_pago"].str.lower() == "credito"]

    if pendientes.empty:
        st.info("No hay ventas a crédito en el filtro actual.")
    else:
        for _, row in pendientes.drop_duplicates(subset=["id"]).iterrows():
            with st.container(border=True):
                st.write(f"**Venta #{int(row['id'])} · {row['cliente']}**")
                st.write(f"Total: $ {float(row['total_usd']):,.2f}")
                if st.button(f"Marcar pagada #{int(row['id'])}", key=f"venta_pagada_{int(row['id'])}"):
                    try:
                        with db_transaction() as conn:
                            conn.execute(
                                "UPDATE ventas SET metodo_pago='efectivo' WHERE id=?",
                                (int(row["id"]),),
                            )
                            conn.execute(
                                "UPDATE cuentas_por_cobrar SET estado='pagada', saldo_usd=0 WHERE venta_id=?",
                                (int(row["id"]),),
                            )
                        st.success("Cuenta actualizada")
                        st.rerun()
                    except Exception as e:
                        st.error("Error actualizando estado")
                        st.exception(e)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_fil.to_excel(writer, index=False, sheet_name="Ventas")

    st.download_button(
        "📥 Exportar historial",
        buffer.getvalue(),
        file_name="historial_ventas.xlsx",
    )


def _render_tab_resumen() -> None:
    st.subheader("Resumen comercial avanzado")

    try:
        with db_transaction() as conn:
            df = pd.read_sql_query(
                """
                SELECT
                    id,
                    fecha,
                    metodo_pago,
                    total_usd,
                    subtotal_usd,
                    impuesto_usd,
                    cliente_id
                FROM ventas
                WHERE estado='registrada'
                """,
                conn,
            )
            top_clientes = pd.read_sql_query(
                """
                SELECT
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    SUM(v.total_usd) AS total
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                WHERE v.estado='registrada'
                GROUP BY COALESCE(c.nombre, 'Sin cliente')
                ORDER BY total DESC
                """,
                conn,
            )
            top_productos = pd.read_sql_query(
                """
                SELECT
                    vd.descripcion AS producto,
                    SUM(vd.cantidad) AS unidades,
                    SUM(vd.subtotal_usd) AS ventas_usd,
                    SUM(vd.cantidad * vd.costo_unitario_usd) AS costo_usd
                FROM ventas_detalle vd
                JOIN ventas v ON v.id = vd.venta_id
                WHERE v.estado='registrada'
                GROUP BY vd.descripcion
                ORDER BY ventas_usd DESC
                LIMIT 10
                """,
                conn,
            )
    except Exception as e:
        st.error("Error cargando resumen")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay ventas para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    total = float(df["total_usd"].sum())
    por_cobrar = float(df[df["metodo_pago"].str.lower() == "credito"]["total_usd"].sum())
    ticket_promedio = total / max(int(df["id"].nunique()), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas totales", f"$ {total:,.2f}")
    c2.metric("Por cobrar", f"$ {por_cobrar:,.2f}")
    c3.metric("Ticket promedio", f"$ {ticket_promedio:,.2f}")
    c4.metric("Mejor cliente", "N/A" if top_clientes.empty else str(top_clientes.iloc[0]["cliente"]))

    diaria = (
        df.assign(dia=df["fecha"].dt.date)
        .groupby("dia", as_index=False)["total_usd"]
        .sum()
        .sort_values("dia")
    )

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Evolución diaria")
        st.area_chart(diaria.set_index("dia")["total_usd"])
    with g2:
        st.caption("Top clientes")
        st.bar_chart(top_clientes.head(8).set_index("cliente")["total"])

    if not top_productos.empty:
        top_productos["margen_usd"] = top_productos["ventas_usd"] - top_productos["costo_usd"].fillna(0.0)
        st.subheader("Productos estrella")
        st.dataframe(top_productos, use_container_width=True, hide_index=True)


# ============================================================
# INTERFAZ VENTAS
# ============================================================

def render_ventas(usuario: str) -> None:
    st.subheader("💰 Gestión profesional de ventas")

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar venta",
        "📜 Historial",
        "📊 Resumen",
    ])

    with tab1:
        _render_tab_registro(usuario)

    with tab2:
        _render_tab_historial()

    with tab3:
        _render_tab_resumen()
