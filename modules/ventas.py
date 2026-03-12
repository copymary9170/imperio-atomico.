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

    tasa_cambio = as_positive(
        tasa_cambio,
        "Tasa de cambio",
        allow_zero=False
    )

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
                total_bs
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
            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar
                (usuario, cliente_id, venta_id, saldo_usd, estado)
                VALUES (?, ?, ?, ?, 'pendiente')
                """,
                (usuario, cliente_id, venta_id, total),
            )

        return venta_id


def _load_clientes() -> list[dict]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, nombre
            FROM clientes
            WHERE estado='activo'
            ORDER BY nombre
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _load_productos() -> list[dict]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, nombre, precio_venta_usd, costo_unitario_usd, stock_actual
            FROM inventario
            WHERE estado='activo'
            ORDER BY nombre
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _render_tab_registro(usuario: str) -> None:
    clientes = _load_clientes()
    productos = _load_productos()

    if not productos:
        st.warning("⚠️ No hay productos activos en inventario para vender.")
        return

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
        c7.metric("Total estimado (Bs)", f"{convert_to_bs(monto_prev_usd, float(tasa)):,.2f}")

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

    c1, c2, c3 = st.columns([1, 1, 2])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="ventas_desde")
    hasta = c2.date_input("Hasta", date.today(), key="ventas_hasta")
    buscador = c3.text_input("Buscar por cliente o detalle")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if buscador:
        df_fil = df_fil[
            df_fil["cliente"].str.contains(buscador, case=False, na=False)
            | df_fil["detalle"].str.contains(buscador, case=False, na=False)
        ]

    st.dataframe(df_fil, use_container_width=True, hide_index=True)
    st.metric("Total del periodo", f"$ {float(df_fil['total_usd'].sum()):,.2f}")

    st.subheader("Gestión de pendientes")
    pendientes = df_fil[df_fil["metodo_pago"].str.lower() == "credito"]

    if pendientes.empty:
        st.info("No hay ventas a crédito en el filtro actual.")
    else:
        for _, row in pendientes.iterrows():
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
    st.subheader("Resumen comercial")

    try:
        with db_transaction() as conn:
            df = pd.read_sql_query(
                """
                SELECT
                    id,
                    fecha,
                    metodo_pago,
                    total_usd,
                    cliente_id
                FROM ventas
                WHERE estado='registrada'
                """,
                conn,
            )
            top = pd.read_sql_query(
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
    except Exception as e:
        st.error("Error cargando resumen")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay ventas para analizar.")
        return

    total = float(df["total_usd"].sum())
    por_cobrar = float(df[df["metodo_pago"].str.lower() == "credito"]["total_usd"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas totales", f"$ {total:,.2f}")
    c2.metric("Por cobrar", f"$ {por_cobrar:,.2f}")

    if top.empty:
        c3.metric("Mejor cliente", "N/A")
    else:
        c3.metric("Mejor cliente", str(top.iloc[0]["cliente"]))

    st.subheader("Ventas por cliente")
    st.bar_chart(top.set_index("cliente")["total"])


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
