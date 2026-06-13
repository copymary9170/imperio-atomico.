import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text
from modules.integration_hub import dispatch_to_module, render_send_buttons
from services.contabilidad_service import contabilizar_venta
from services.conciliacion_service import periodo_esta_cerrado
from services.costeo_service import actualizar_vinculos_costeo
from services.cxc_cobranza_service import CobranzaInput, registrar_abono_cuenta_por_cobrar
from services.cuentas_por_cobrar_service import ensure_cuentas_por_cobrar_tables
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
# AUXILIARES
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_text(value: Any, default: str = "") -> str:
    txt = clean_text(value)
    return txt if txt else default


def _safe_date_text(value: Any) -> str:
    txt = clean_text(value)
    if not txt:
        return ""
    try:
        return pd.to_datetime(txt).date().isoformat()
    except Exception:
        return ""


def _normalize_currency(moneda: str) -> str:
    txt = clean_text(moneda).upper()
    if txt in {"BS", "VES", "BOLIVARES", "BOLÍVARES"}:
        return "BS"
    if txt in {"USDT"}:
        return "USDT"
    if txt in {"KONTIGO"}:
        return "KONTIGO"
    return "USD"


def _ensure_sales_state() -> None:
    if "ventas_items" not in st.session_state:
        st.session_state.ventas_items = []


def _clear_sales_state() -> None:
    st.session_state.ventas_items = []


def _infer_fiscal_type(iva_pct: float) -> str:
    return "gravada" if float(iva_pct or 0.0) > 0 else "exenta"


def _get_price_for_item(producto_row: dict[str, Any], override_price: float | None = None) -> float:
    if override_price is not None and float(override_price) > 0:
        return float(override_price)
    return float(producto_row.get("precio_venta_usd") or 0.0)


def _calcular_totales_items(
    items: list[dict[str, Any]],
    descuento_global_usd: float = 0.0,
    iva_pct: float = 16.0,
) -> dict[str, float]:
    subtotal = 0.0
    costo_total = 0.0

    for item in items:
        cantidad = as_positive(item.get("cantidad", 0), "Cantidad", allow_zero=False)
        precio = as_positive(item.get("precio_unitario_usd", 0), "Precio unitario")
        costo = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario")
        descuento_item = max(0.0, float(item.get("descuento_usd", 0.0) or 0.0))

        subtotal_linea = max((cantidad * precio) - descuento_item, 0.0)
        subtotal += subtotal_linea
        costo_total += cantidad * costo

    descuento_global_usd = max(0.0, float(descuento_global_usd or 0.0))
    subtotal_neto = max(subtotal - descuento_global_usd, 0.0)

    iva_pct = max(0.0, float(iva_pct or 0.0))
    impuesto = round(subtotal_neto * (iva_pct / 100.0), 2)
    total = round(subtotal_neto + impuesto, 2)
    utilidad = round(subtotal_neto - costo_total, 2)

    return {
        "subtotal_bruto_usd": round(subtotal, 2),
        "descuento_global_usd": round(descuento_global_usd, 2),
        "subtotal_usd": round(subtotal_neto, 2),
        "impuesto_usd": round(impuesto, 2),
        "total_usd": round(total, 2),
        "costo_total_usd": round(costo_total, 2),
        "utilidad_estimada_usd": round(utilidad, 2),
    }


def _load_clientes() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT id, nombre
                FROM clientes
                WHERE COALESCE(estado, 'activo') = 'activo'
                ORDER BY nombre
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(columns=["id", "nombre"])
    return df


def _load_productos() -> pd.DataFrame:
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                sku,
                nombre,
                categoria,
                unidad,
                COALESCE(stock_actual, 0) AS stock_actual,
                COALESCE(costo_unitario_usd, 0) AS costo_unitario_usd,
                COALESCE(precio_venta_usd, 0) AS precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY nombre
            """,
            conn,
        )

    if df.empty:
        return df

    df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce").fillna(0.0)
    df["costo_unitario_usd"] = pd.to_numeric(df["costo_unitario_usd"], errors="coerce").fillna(0.0)
    df["precio_venta_usd"] = pd.to_numeric(df["precio_venta_usd"], errors="coerce").fillna(0.0)
    return df


def _load_historial_ventas() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT
                    v.id,
                    v.fecha,
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    COALESCE(vd.descripcion, 'Sin detalle') AS detalle,
                    COALESCE(vd.cantidad, 0) AS cantidad,
                    COALESCE(vd.precio_unitario_usd, 0) AS precio_unitario_usd,
                    COALESCE(vd.costo_unitario_usd, 0) AS costo_unitario_usd,
                    COALESCE(vd.subtotal_usd, 0) AS subtotal_linea_usd,
                    COALESCE(v.moneda, 'USD') AS moneda,
                    COALESCE(v.tasa_cambio, 1) AS tasa_cambio,
                    COALESCE(v.metodo_pago, 'efectivo') AS metodo_pago,
                    COALESCE(v.subtotal_usd, 0) AS subtotal_usd,
                    COALESCE(v.impuesto_usd, 0) AS impuesto_usd,
                    COALESCE(v.total_usd, 0) AS total_usd,
                    COALESCE(v.total_bs, 0) AS total_bs,
                    COALESCE(v.estado, 'registrado') AS estado
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
                WHERE COALESCE(v.estado, 'registrado') = 'registrado'
                ORDER BY v.fecha DESC, v.id DESC
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(
                columns=[
                    "id",
                    "fecha",
                    "cliente",
                    "detalle",
                    "cantidad",
                    "precio_unitario_usd",
                    "costo_unitario_usd",
                    "subtotal_linea_usd",
                    "moneda",
                    "tasa_cambio",
                    "metodo_pago",
                    "subtotal_usd",
                    "impuesto_usd",
                    "total_usd",
                    "total_bs",
                    "estado",
                ]
            )

    if df.empty:
        return df

    numeric_cols = [
        "cantidad",
        "precio_unitario_usd",
        "costo_unitario_usd",
        "subtotal_linea_usd",
        "tasa_cambio",
        "subtotal_usd",
        "impuesto_usd",
        "total_usd",
        "total_bs",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["utilidad_estimada"] = df["subtotal_linea_usd"] - (df["cantidad"] * df["costo_unitario_usd"])
    return df


def _load_cuentas_por_cobrar_df() -> pd.DataFrame:
    ensure_cuentas_por_cobrar_tables()
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT
                    cxc.id,
                    COALESCE(cxc.fecha, cxc.fecha_creacion) AS fecha,
                    cxc.venta_id,
                    COALESCE(cl.nombre, cxc.cliente, 'Sin cliente') AS cliente,
                    COALESCE(cxc.tipo_documento, 'venta') AS tipo_documento,
                    COALESCE(cxc.monto_original_usd, cxc.total_usd, 0) AS monto_original_usd,
                    COALESCE(cxc.monto_cobrado_usd, cxc.pagado_usd, 0) AS monto_cobrado_usd,
                    COALESCE(cxc.saldo_usd, cxc.pendiente_usd, 0) AS saldo_usd,
                    COALESCE(cxc.estado, 'pendiente') AS estado,
                    COALESCE(cxc.dias_vencimiento, 0) AS dias_vencimiento,
                    COALESCE(cxc.notas, '') AS notas
                FROM cuentas_por_cobrar cxc
                LEFT JOIN ventas v ON v.id = cxc.venta_id
                LEFT JOIN clientes cl ON cl.id = cxc.cliente_id
                ORDER BY COALESCE(cxc.fecha, cxc.fecha_creacion) DESC, cxc.id DESC
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(
                columns=[
                    "id",
                    "fecha",
                    "venta_id",
                    "cliente",
                    "tipo_documento",
                    "monto_original_usd",
                    "monto_cobrado_usd",
                    "saldo_usd",
                    "estado",
                    "dias_vencimiento",
                    "notas",
                ]
            )

    if df.empty:
        return df

    for col in ["monto_original_usd", "monto_cobrado_usd", "saldo_usd", "dias_vencimiento"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


# ============================================================
# REGISTRO DE VENTA
# ============================================================

def registrar_venta(
    usuario: str,
    cliente_id: int | None,
    moneda: str,
    tasa_cambio: float,
    metodo_pago: str,
    items: list[dict[str, Any]],
    descuento_global_usd: float = 0.0,
    iva_pct: float = 16.0,
    dias_credito: int = 30,
    observacion: str = "",
    costeo_orden_id: int | None = None,
) -> int:
    if not items:
        raise ValueError("Debe agregar al menos un ítem.")

    metodo_pago = clean_text(metodo_pago).lower()
    moneda = _normalize_currency(moneda)
    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    dias_credito = max(0, int(dias_credito or 0))

    totales = _calcular_totales_items(
        items=items,
        descuento_global_usd=float(descuento_global_usd or 0.0),
        iva_pct=float(iva_pct or 0.0),
    )

    subtotal = float(totales["subtotal_usd"])
    impuesto = float(totales["impuesto_usd"])
    total = float(totales["total_usd"])
    total_bs = round(convert_to_bs(total, tasa_cambio), 2)

    if total <= 0:
        raise ValueError("El total de la venta debe ser mayor a cero.")

    with db_transaction() as conn:
        if periodo_esta_cerrado(conn, fecha_movimiento=date.today().isoformat(), tipo_cierre="mensual"):
            raise ValueError("Periodo mensual cerrado: no se permiten nuevas ventas en esta fecha.")

        cur = conn.execute(
            """
            INSERT INTO ventas
            (
                usuario,
                cliente_id,
                moneda,
                tasa_cambio,
                metodo_pago,
                subtotal_usd,
                impuesto_usd,
                fiscal_tipo,
                fiscal_tasa_iva,
                fiscal_iva_debito_usd,
                total_usd,
                total_bs,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'registrado')
            """,
            (
                usuario,
                cliente_id,
                moneda,
                float(tasa_cambio),
                metodo_pago,
                money(subtotal),
                money(impuesto),
                _infer_fiscal_type(iva_pct),
                float(iva_pct or 0.0) / 100.0,
                money(impuesto),
                money(total),
                money(total_bs),
            ),
        )
        venta_id = int(cur.lastrowid)

        for item in items:
            inventario_id = item.get("inventario_id")
            descripcion = require_text(item.get("descripcion") or "Ítem", "Descripción")
            cantidad = as_positive(item.get("cantidad", 0), "Cantidad", allow_zero=False)
            precio_u = as_positive(item.get("precio_unitario_usd", 0), "Precio unitario")
            costo_u = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario")
            descuento_item = max(0.0, float(item.get("descuento_usd", 0.0) or 0.0))
            subtotal_linea = round(max((cantidad * precio_u) - descuento_item, 0.0), 2)

            conn.execute(
                """
                INSERT INTO ventas_detalle
                (
                    usuario,
                    venta_id,
                    inventario_id,
                    descripcion,
                    cantidad,
                    precio_unitario_usd,
                    costo_unitario_usd,
                    subtotal_usd
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    int(venta_id),
                    int(inventario_id) if inventario_id else None,
                    descripcion,
                    float(cantidad),
                    money(precio_u),
                    money(costo_u),
                    money(subtotal_linea),
                ),
            )

            if inventario_id:
                current = conn.execute(
                    """
                    SELECT id, nombre, stock_actual
                    FROM inventario
                    WHERE id=? AND COALESCE(estado, 'activo')='activo'
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

                conn.execute(
                    """
                    INSERT INTO movimientos_inventario
                    (
                        usuario,
                        inventario_id,
                        tipo,
                        cantidad,
                        costo_unitario_usd,
                        referencia
                    )
                    VALUES (?, ?, 'salida', ?, ?, ?)
                    """,
                    (
                        usuario,
                        int(inventario_id),
                        -abs(float(cantidad)),
                        money(costo_u),
                        f"Venta #{venta_id}",
                    ),
                )

        if metodo_pago == "credito":
            if not cliente_id:
                raise ValueError("Para una venta a crédito debes seleccionar un cliente.")

            ensure_cuentas_por_cobrar_tables()
            cliente_row = conn.execute("SELECT nombre FROM clientes WHERE id=?", (int(cliente_id),)).fetchone()
            cliente_nombre = str(cliente_row["nombre"] if cliente_row else "Cliente")
            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar
                (
                    usuario,
                    cliente_id,
                    venta_id,
                    cliente,
                    concepto,
                    referencia,
                    tipo_documento,
                    monto_original_usd,
                    monto_cobrado_usd,
                    saldo_usd,
                    total_usd,
                    pagado_usd,
                    pendiente_usd,
                    estado,
                    dias_vencimiento,
                    notas
                )
                VALUES (?, ?, ?, ?, ?, ?, 'venta', ?, 0, ?, ?, 0, ?, 'pendiente', ?, ?)
                """,
                (
                    usuario,
                    int(cliente_id),
                    int(venta_id),
                    cliente_nombre,
                    f"Venta #{venta_id}",
                    f"VENTA-{venta_id}",
                    money(total),
                    money(total),
                    money(total),
                    money(total),
                    int(dias_credito),
                    clean_text(observacion) or "Generada desde ventas",
                ),
            )

            conn.execute(
                """
                UPDATE clientes
                SET saldo_por_cobrar_usd = COALESCE(saldo_por_cobrar_usd, 0) + ?
                WHERE id = ?
                """,
                (money(total), int(cliente_id)),
            )
        else:
            registrar_ingreso(
                conn,
                origen="venta",
                referencia_id=int(venta_id),
                descripcion=f"Venta #{venta_id}",
                monto_usd=float(total),
                moneda=str(moneda),
                monto_moneda=float(total if moneda in {"USD", "USDT", "KONTIGO"} else total_bs),
                tasa_cambio=float(tasa_cambio),
                metodo_pago=metodo_pago,
                usuario=usuario,
                metadata={
                    "cliente_id": int(cliente_id) if cliente_id is not None else None,
                    "metodo_pago": metodo_pago,
                    "observacion": clean_text(observacion),
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
