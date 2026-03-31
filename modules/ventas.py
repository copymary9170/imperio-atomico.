from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text
from services.contabilidad_service import contabilizar_venta
from services.conciliacion_service import periodo_esta_cerrado
from services.costeo_service import actualizar_vinculos_costeo
from services.cxc_cobranza_service import CobranzaInput, registrar_abono_cuenta_por_cobrar
from services.tesoreria_service import registrar_ingreso
from utils.currency import convert_to_bs


METODOS_PAGO_VENTA = [
    "efectivo",
    "transferencia",
    "zelle",
    "binance",
    "kontigo",
    "credito",
]

MONEDAS_VENTA = ["USD", "BS", "USDT", "KONTIGO"]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_ventas_schema() -> None:
    with db_transaction() as conn:
        ventas_cols = {r[1] for r in conn.execute("PRAGMA table_info(ventas)").fetchall()}
        if ventas_cols:
            if "delivery_usd" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN delivery_usd REAL DEFAULT 0")
            if "descuento_usd" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN descuento_usd REAL DEFAULT 0")
            if "observaciones" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN observaciones TEXT")
            if "referencia_pago" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN referencia_pago TEXT")
            if "canal_venta" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN canal_venta TEXT DEFAULT 'directa'")
            if "dias_vencimiento" not in ventas_cols:
                conn.execute("ALTER TABLE ventas ADD COLUMN dias_vencimiento INTEGER DEFAULT 30")

        detalle_cols = {r[1] for r in conn.execute("PRAGMA table_info(ventas_detalle)").fetchall()}
        if detalle_cols:
            if "observaciones" not in detalle_cols:
                conn.execute("ALTER TABLE ventas_detalle ADD COLUMN observaciones TEXT")

        mov_cols = {r[1] for r in conn.execute("PRAGMA table_info(movimientos_inventario)").fetchall()}
        if mov_cols and "estado" not in mov_cols:
            try:
                conn.execute("ALTER TABLE movimientos_inventario ADD COLUMN estado TEXT DEFAULT 'activo'")
            except Exception:
                pass


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _get_product_display(producto: Any) -> str:
    nombre = str(producto["nombre"])
    stock = float(producto["stock_actual"] or 0.0)
    precio = float(producto["precio_venta_usd"] or 0.0)
    return f"{nombre} · Stock: {stock:,.2f} · $ {precio:,.2f}"


def _insert_inventory_output_movement(
    conn,
    usuario: str,
    inventario_id: int,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
) -> None:
    conn.execute(
        """
        INSERT INTO movimientos_inventario(
            usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia
        )
        VALUES (?, ?, 'salida', ?, ?, ?)
        """,
        (
            clean_text(usuario) or "Sistema",
            int(inventario_id),
            -abs(float(cantidad)),
            max(0.0, float(costo_unitario_usd or 0.0)),
            clean_text(referencia),
        ),
    )


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
    delivery_usd: float = 0.0,
    descuento_usd: float = 0.0,
    observaciones: str = "",
    referencia_pago: str = "",
    dias_vencimiento: int = 30,
    costeo_orden_id: int | None = None,
) -> int:
    _ensure_ventas_schema()

    if not items:
        raise ValueError("Debe agregar al menos un item.")

    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    delivery_usd = as_positive(delivery_usd, "Delivery")
    descuento_usd = as_positive(descuento_usd, "Descuento")
    dias_vencimiento = int(max(1, int(dias_vencimiento or 30)))

    subtotal = round(
        sum(
            as_positive(item["cantidad"], "Cantidad", allow_zero=False)
            * as_positive(item["precio_unitario_usd"], "Precio unitario")
            for item in items
        ),
        2,
    )

    if descuento_usd > subtotal:
        raise ValueError("El descuento no puede ser mayor al subtotal.")

    base_imponible = round(subtotal - descuento_usd, 2)
    impuesto = round(base_imponible * 0.16, 2)
    total = round(base_imponible + impuesto + delivery_usd, 2)
    total_bs = round(convert_to_bs(total, tasa_cambio), 2)

    with db_transaction() as conn:
        if periodo_esta_cerrado(conn, fecha_movimiento=date.today().isoformat(), tipo_cierre="mensual"):
            raise ValueError("Periodo mensual cerrado: no se permiten nuevas ventas en esta fecha.")

        cur = conn.execute(
            """
            INSERT INTO ventas
            (
                usuario, cliente_id, moneda, tasa_cambio, metodo_pago,
                subtotal_usd, impuesto_usd, fiscal_tipo, fiscal_tasa_iva, fiscal_iva_debito_usd,
                total_usd, total_bs, delivery_usd, descuento_usd, observaciones,
                referencia_pago, canal_venta, dias_vencimiento
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'directa', ?)
            """,
            (
                usuario,
                cliente_id,
                clean_text(moneda).upper(),
                float(tasa_cambio),
                clean_text(metodo_pago).lower(),
                float(subtotal),
                float(impuesto),
                "gravada" if impuesto > 0 else "exenta",
                0.16,
                float(impuesto),
                float(total),
                float(total_bs),
                float(delivery_usd),
                float(descuento_usd),
                clean_text(observaciones),
                clean_text(referencia_pago),
                dias_vencimiento,
            ),
        )
        venta_id = int(cur.lastrowid)

        for item in items:
            cantidad = as_positive(item["cantidad"], "Cantidad", allow_zero=False)
            precio_u = as_positive(item["precio_unitario_usd"], "Precio unitario")
            costo_u = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario")
            descripcion = clean_text(item.get("descripcion")) or "Item"
            inventario_id = item.get("inventario_id")
            observacion_item = clean_text(item.get("observaciones", ""))

            conn.execute(
                """
                INSERT INTO ventas_detalle
                (
                    usuario, venta_id, inventario_id, descripcion,
                    cantidad, precio_unitario_usd, costo_unitario_usd, subtotal_usd, observaciones
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    venta_id,
                    inventario_id,
                    descripcion,
                    float(cantidad),
                    float(precio_u),
                    float(costo_u),
                    round(float(cantidad) * float(precio_u), 2),
                    observacion_item,
                ),
            )

            if inventario_id:
                current = conn.execute(
                    """
                    SELECT stock_actual, nombre
                    FROM inventario
                    WHERE id=? AND COALESCE(estado,'activo')='activo'
                    """,
                    (int(inventario_id),),
                ).fetchone()

                if not current:
                    raise ValueError(f"Inventario #{inventario_id} no existe.")

                stock_actual = float(current["stock_actual"] or 0.0)
                if stock_actual < float(cantidad):
                    raise ValueError(f"Stock insuficiente para {current['nombre']}.")

                conn.execute(
                    """
                    UPDATE inventario
                    SET stock_actual = stock_actual - ?
                    WHERE id = ?
                    """,
                    (float(cantidad), int(inventario_id)),
                )

                _insert_inventory_output_movement(
                    conn=conn,
                    usuario=usuario,
                    inventario_id=int(inventario_id),
                    cantidad=float(cantidad),
                    costo_unitario_usd=float(costo_u),
                    referencia=f"Venta #{venta_id} · {descripcion}",
                )

        if clean_text(metodo_pago).lower() == "credito" and cliente_id:
            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar
                (
                    usuario, cliente_id, venta_id, tipo_documento, monto_original_usd,
                    monto_cobrado_usd, saldo_usd, estado, dias_vencimiento, notas
                )
                VALUES (?, ?, ?, 'venta', ?, 0, ?, 'pendiente', ?, ?)
                """,
                (
                    usuario,
                    int(cliente_id),
                    int(venta_id),
                    float(total),
                    float(total),
                    int(dias_vencimiento),
                    clean_text(observaciones) or "Generada desde venta directa",
                ),
            )
            conn.execute(
                """
                UPDATE clientes
                SET saldo_por_cobrar_usd = COALESCE(saldo_por_cobrar_usd, 0) + ?
                WHERE id = ?
                """,
                (float(total), int(cliente_id)),
            )
        else:
            registrar_ingreso(
                conn,
                origen="venta",
                referencia_id=venta_id,
                descripcion=f"Venta #{venta_id}",
                monto_usd=float(total),
                moneda=str(moneda),
                monto_moneda=float(total if str(moneda).upper() in {"USD", "USDT", "KONTIGO"} else total_bs),
                tasa_cambio=float(tasa_cambio),
                metodo_pago=str(metodo_pago).lower(),
                usuario=usuario,
                metadata={
                    "cliente_id": int(cliente_id) if cliente_id is not None else None,
                    "metodo_pago": str(metodo_pago).lower(),
                    "referencia_pago": clean_text(referencia_pago),
                    "delivery_usd": float(delivery_usd),
                    "descuento_usd": float(descuento_usd),
                },
            )

        contabilizar_venta(conn, venta_id=venta_id, usuario=usuario)

    if costeo_orden_id:
        actualizar_vinculos_costeo(
            orden_id=int(costeo_orden_id),
            venta_id=int(venta_id),
            estado="aprobado",
        )

    return int(venta_id)


# ============================================================
# TAB REGISTRO
# ============================================================

def _render_tab_registro(usuario: str) -> None:
    _ensure_ventas_schema()

    try:
        with db_transaction() as conn:
            clientes = conn.execute(
                "SELECT id, nombre FROM clientes WHERE COALESCE(estado,'activo')='activo' ORDER BY nombre"
            ).fetchall()
            productos = conn.execute(
                """
                SELECT id, nombre, stock_actual, costo_unitario_usd, precio_venta_usd
                FROM inventario
                WHERE COALESCE(estado,'activo')='activo'
                ORDER BY nombre
                """
            ).fetchall()
    except Exception as e:
        st.error("Error cargando datos para venta.")
        st.exception(e)
        return

    if not productos:
        st.warning("No hay productos activos en inventario para vender.")
        return

    with st.form("form_registrar_venta_pro", clear_on_submit=True):
        st.subheader("Datos de la venta")

        c1, c2, c3 = st.columns(3)

        cliente_opciones = {"Sin cliente": None}
        for c in clientes:
            cliente_opciones[str(c["nombre"])] = int(c["id"])

        cliente_nombre = c1.selectbox("Cliente", list(cliente_opciones.keys()))

        producto = c2.selectbox(
            "Producto",
            productos,
            format_func=_get_product_display,
        )

        cantidad = c3.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)

        c4, c5, c6, c7 = st.columns(4)
        metodo_pago = c4.selectbox("Método", METODOS_PAGO_VENTA)
        moneda = c5.selectbox("Moneda", MONEDAS_VENTA)
        tasa = c6.number_input("Tasa de referencia", min_value=0.0001, value=36.5)
        dias_vencimiento = c7.number_input("Días crédito", min_value=1, max_value=365, value=30, step=1)

        precio_manual = st.checkbox("Usar precio manual", key="venta_precio_manual")
        if precio_manual:
            precio_unitario = st.number_input(
                "Precio unitario USD",
                min_value=0.0,
                value=float(producto["precio_venta_usd"] or 0.0),
                step=1.0,
                format="%.4f",
            )
        else:
            precio_unitario = float(producto["precio_venta_usd"] or 0.0)

        c8, c9, c10 = st.columns(3)
        delivery_usd = c8.number_input("Delivery USD", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        descuento_usd = c9.number_input("Descuento USD", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        referencia_pago = c10.text_input("Referencia de pago")

        observaciones = st.text_area("Observaciones")

        subtotal_prev_usd = round(float(cantidad) * float(precio_unitario), 2)
        base_prev = max(0.0, subtotal_prev_usd - float(descuento_usd))
        impuesto_prev = round(base_prev * 0.16, 2)
        total_prev_usd = round(base_prev + impuesto_prev + float(delivery_usd), 2)
        utilidad_prev = round(
            subtotal_prev_usd - (float(cantidad) * float(producto["costo_unitario_usd"] or 0.0)),
            2,
        )

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Subtotal estimado (USD)", f"$ {subtotal_prev_usd:,.2f}")
        p2.metric("IVA estimado (USD)", f"$ {impuesto_prev:,.2f}")
        p3.metric("Total estimado (USD)", f"$ {total_prev_usd:,.2f}")
        p4.metric("Total estimado (Bs)", f"{convert_to_bs(total_prev_usd, float(tasa)):,.2f}")

        p5, p6 = st.columns(2)
        p5.metric("Costo estimado", f"$ {float(cantidad) * float(producto['costo_unitario_usd'] or 0.0):,.2f}")
        p6.metric("Utilidad estimada", f"$ {utilidad_prev:,.2f}")

        submit = st.form_submit_button("🚀 Registrar venta", use_container_width=True)

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
            delivery_usd=float(delivery_usd),
            descuento_usd=float(descuento_usd),
            observaciones=observaciones,
            referencia_pago=referencia_pago,
            dias_vencimiento=int(dias_vencimiento),
            items=[
                {
                    "inventario_id": int(producto["id"]),
                    "descripcion": str(producto["nombre"]),
                    "cantidad": float(cantidad),
                    "precio_unitario_usd": float(precio_unitario),
                    "costo_unitario_usd": float(producto["costo_unitario_usd"] or 0.0),
                    "observaciones": clean_text(observaciones),
                }
            ],
        )

        st.success(f"✅ Venta #{vid} registrada correctamente")
        st.balloons()
        st.rerun()

    except ValueError as exc:
        st.error(str(exc))
    except Exception as e:
        st.error("Error registrando venta.")
        st.exception(e)


# ============================================================
# HISTORIAL
# ============================================================

def _load_historial_ventas() -> pd.DataFrame:
    _ensure_ventas_schema()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                v.id,
                v.fecha,
                COALESCE(c.nombre, 'Sin cliente') AS cliente,
                vd.descripcion AS detalle,
                vd.cantidad,
                vd.precio_unitario_usd,
                vd.costo_unitario_usd,
                v.metodo_pago,
                v.moneda,
                v.tasa_cambio,
                v.subtotal_usd,
                v.impuesto_usd,
                COALESCE(v.delivery_usd, 0) AS delivery_usd,
                COALESCE(v.descuento_usd, 0) AS descuento_usd,
                v.total_usd,
                v.total_bs,
                COALESCE(v.referencia_pago, '') AS referencia_pago,
                COALESCE(v.observaciones, '') AS observaciones,
                v.estado
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
            WHERE COALESCE(v.estado,'registrada')='registrada'
            ORDER BY v.fecha DESC, v.id DESC
            """,
            conn,
        )


def _render_tab_historial() -> None:
    st.subheader("Historial de ventas")

    try:
        df = _load_historial_ventas()
    except Exception as e:
        st.error("Error cargando historial.")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay ventas registradas.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir")
    df["utilidad_estimada"] = (
        (df["cantidad"].fillna(0.0) * df["precio_unitario_usd"].fillna(0.0))
        - (df["cantidad"].fillna(0.0) * df["costo_unitario_usd"].fillna(0.0))
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="ventas_desde")
    hasta = c2.date_input("Hasta", date.today(), key="ventas_hasta")
    metodo = c3.selectbox("Método", ["Todos"] + sorted(df["metodo_pago"].str.title().unique().tolist()))
    buscador = c4.text_input("Buscar por cliente, detalle o referencia")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if metodo != "Todos":
        df_fil = df_fil[df_fil["metodo_pago"].str.lower() == metodo.lower()]

    if buscador:
        df_fil = df_fil[
            df_fil["cliente"].astype(str).str.contains(buscador, case=False, na=False)
            | df_fil["detalle"].astype(str).str.contains(buscador, case=False, na=False)
            | df_fil["referencia_pago"].astype(str).str.contains(buscador, case=False, na=False)
        ]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total filtrado", f"$ {float(df_fil['total_usd'].sum()):,.2f}")
    k2.metric("N° ventas", f"{int(df_fil['id'].nunique())}")
    ticket = float(df_fil["total_usd"].sum()) / max(int(df_fil["id"].nunique()), 1)
    k3.metric("Ticket promedio", f"$ {ticket:,.2f}")
    k4.metric("Delivery total", f"$ {float(df_fil['delivery_usd'].sum()):,.2f}")

    st.dataframe(
        df_fil,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
            "precio_unitario_usd": st.column_config.NumberColumn("Precio unitario", format="%.2f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo unitario", format="%.2f"),
            "subtotal_usd": st.column_config.NumberColumn("Subtotal", format="%.2f"),
            "impuesto_usd": st.column_config.NumberColumn("IVA", format="%.2f"),
            "delivery_usd": st.column_config.NumberColumn("Delivery", format="%.2f"),
            "descuento_usd": st.column_config.NumberColumn("Descuento", format="%.2f"),
            "total_usd": st.column_config.NumberColumn("Total USD", format="%.2f"),
            "total_bs": st.column_config.NumberColumn("Total Bs", format="%.2f"),
            "utilidad_estimada": st.column_config.NumberColumn("Utilidad", format="%.2f"),
        },
    )

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
                st.write(f"Referencia: {row['referencia_pago'] or 'N/A'}")

                if st.button(f"Marcar pagada #{int(row['id'])}", key=f"venta_pagada_{int(row['id'])}"):
                    try:
                        with db_transaction() as conn:
                            cxc = conn.execute(
                                "SELECT id, saldo_usd FROM cuentas_por_cobrar WHERE venta_id=? ORDER BY id DESC LIMIT 1",
                                (int(row["id"]),),
                            ).fetchone()
                            if not cxc:
                                raise ValueError("No existe cuenta por cobrar para esta venta.")

                            registrar_abono_cuenta_por_cobrar(
                                conn,
                                usuario="Sistema",
                                payload=CobranzaInput(
                                    cuenta_por_cobrar_id=int(cxc["id"]),
                                    monto_usd=float(cxc["saldo_usd"] or 0.0),
                                    metodo_pago="efectivo",
                                    observaciones="Pago total desde historial de ventas",
                                ),
                            )
                        st.success("Cuenta actualizada.")
                        st.rerun()
                    except Exception as e:
                        st.error("Error actualizando estado.")
                        st.exception(e)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_fil.to_excel(writer, index=False, sheet_name="Ventas")

    st.download_button(
        "📥 Exportar historial",
        buffer.getvalue(),
        file_name="historial_ventas.xlsx",
        use_container_width=True,
    )


# ============================================================
# RESUMEN
# ============================================================

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
                    COALESCE(delivery_usd, 0) AS delivery_usd,
                    COALESCE(descuento_usd, 0) AS descuento_usd,
                    cliente_id
                FROM ventas
                WHERE COALESCE(estado,'registrada')='registrada'
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
                WHERE COALESCE(v.estado,'registrada')='registrada'
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
                WHERE COALESCE(v.estado,'registrada')='registrada'
                GROUP BY vd.descripcion
                ORDER BY ventas_usd DESC
                LIMIT 10
                """,
                conn,
            )
    except Exception as e:
        st.error("Error cargando resumen.")
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

    c5, c6 = st.columns(2)
    c5.metric("Delivery facturado", f"$ {float(df['delivery_usd'].sum()):,.2f}")
    c6.metric("Descuentos otorgados", f"$ {float(df['descuento_usd'].sum()):,.2f}")

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
        if not top_clientes.empty:
            st.bar_chart(top_clientes.head(8).set_index("cliente")["total"])

    if not top_productos.empty:
        top_productos["margen_usd"] = top_productos["ventas_usd"] - top_productos["costo_usd"].fillna(0.0)
        st.subheader("Productos estrella")
        st.dataframe(
            top_productos,
            use_container_width=True,
            hide_index=True,
            column_config={
                "unidades": st.column_config.NumberColumn("Unidades", format="%.2f"),
                "ventas_usd": st.column_config.NumberColumn("Ventas USD", format="%.2f"),
                "costo_usd": st.column_config.NumberColumn("Costo USD", format="%.2f"),
                "margen_usd": st.column_config.NumberColumn("Margen USD", format="%.2f"),
            },
        )


# ============================================================
# INTERFAZ VENTAS
# ============================================================

def render_ventas(usuario: str) -> None:
    _ensure_ventas_schema()

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
