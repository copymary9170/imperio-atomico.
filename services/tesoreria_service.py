from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from modules.common import as_positive, clean_text, money, require_text


TIPOS_TESORERIA = ("ingreso", "egreso")
ORIGENES_TESORERIA = (
    "venta",
    "cobro_cliente",
    "gasto",
    "gasto_manual",
    "factura_compra_pagada",
    "pago_proveedor",
    "compra_inicial_pagada",
    "ajuste_manual",
    "cierre_caja",
)
ESTADOS_TESORERIA = ("confirmado", "cancelado")


def _normalize_tipo(tipo: str) -> str:
    value = clean_text(tipo).lower()
    if value not in TIPOS_TESORERIA:
        raise ValueError("Tipo de tesorería inválido")
    return value


def _normalize_origen(origen: str) -> str:
    value = clean_text(origen).lower()
    if value not in ORIGENES_TESORERIA:
        raise ValueError("Origen de tesorería inválido")
    return value


def _normalize_estado(estado: str) -> str:
    value = clean_text(estado).lower() or "confirmado"
    if value not in ESTADOS_TESORERIA:
        raise ValueError("Estado de tesorería inválido")
    return value


def _serialize_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return bool(row)


def _get_table_columns(conn: Any, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}
    except Exception:
        return set()


def _pick_first_existing(columns: set[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _safe_read_sql(query: str, conn: Any, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    try:
        return pd.read_sql_query(query, conn, params=params or [])
    except Exception:
        return pd.DataFrame()


def registrar_movimiento_tesoreria(
    conn: Any,
    *,
    tipo: str,
    origen: str,
    descripcion: str,
    monto_usd: float,
    usuario: str,
    referencia_id: int | None = None,
    fecha: str | None = None,
    moneda: str = "USD",
    monto_moneda: float | None = None,
    tasa_cambio: float = 1.0,
    metodo_pago: str = "efectivo",
    estado: str = "confirmado",
    metadata: dict[str, Any] | None = None,
    allow_duplicate: bool = False,
) -> int:
    tipo_normalizado = _normalize_tipo(tipo)
    origen_normalizado = _normalize_origen(origen)
    estado_normalizado = _normalize_estado(estado)
    descripcion_normalizada = require_text(descripcion, "Descripción")
    usuario_normalizado = require_text(usuario, "Usuario")
    monto = money(as_positive(monto_usd, "Monto tesorería", allow_zero=False))
    tasa = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    moneda_normalizada = clean_text(moneda).upper() or "USD"
    monto_moneda_normalizado = money(
        monto if monto_moneda is None else as_positive(monto_moneda, "Monto en moneda", allow_zero=True)
    )
    metodo_pago_normalizado = clean_text(metodo_pago).lower() or "efectivo"
    fecha_normalizada = clean_text(fecha) or None
    fecha_control = fecha_normalizada or datetime.now().date().isoformat()

    from services.conciliacion_service import periodo_esta_cerrado

    if periodo_esta_cerrado(conn, fecha_movimiento=fecha_control, tipo_cierre="mensual"):
        raise ValueError(f"El período mensual de la fecha {fecha_control} está cerrado")

    if referencia_id is not None and not allow_duplicate:
        existing = conn.execute(
            """
            SELECT id
            FROM movimientos_tesoreria
            WHERE origen=? AND referencia_id=? AND tipo=? AND estado='confirmado'
            LIMIT 1
            """,
            (origen_normalizado, int(referencia_id), tipo_normalizado),
        ).fetchone()
        if existing:
            return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO movimientos_tesoreria
        (
            fecha,
            tipo,
            origen,
            referencia_id,
            descripcion,
            monto_usd,
            moneda,
            monto_moneda,
            tasa_cambio,
            metodo_pago,
            usuario,
            estado,
            metadata
        )
        VALUES (COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha_normalizada,
            tipo_normalizado,
            origen_normalizado,
            int(referencia_id) if referencia_id is not None else None,
            descripcion_normalizada,
            monto,
            moneda_normalizada,
            monto_moneda_normalizado,
            float(tasa),
            metodo_pago_normalizado,
            usuario_normalizado,
            estado_normalizado,
            _serialize_metadata(metadata),
        ),
    )
    return int(cur.lastrowid)


def registrar_ingreso(conn: Any, **kwargs: Any) -> int:
    return registrar_movimiento_tesoreria(conn, tipo="ingreso", **kwargs)


def registrar_egreso(conn: Any, **kwargs: Any) -> int:
    return registrar_movimiento_tesoreria(conn, tipo="egreso", **kwargs)


def listar_movimientos_tesoreria(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    tipo: str | None = None,
    origen: str | None = None,
    metodo_pago: str | None = None,
    estado: str = "confirmado",
) -> pd.DataFrame:
    filters: list[str] = ["estado = ?"]
    params: list[Any] = [_normalize_estado(estado)]

    if clean_text(fecha_desde):
        filters.append("date(fecha) >= date(?)")
        params.append(clean_text(fecha_desde))
    if clean_text(fecha_hasta):
        filters.append("date(fecha) <= date(?)")
        params.append(clean_text(fecha_hasta))
    if clean_text(tipo):
        filters.append("tipo = ?")
        params.append(_normalize_tipo(tipo))
    if clean_text(origen):
        filters.append("origen = ?")
        params.append(_normalize_origen(origen))
    if clean_text(metodo_pago):
        filters.append("metodo_pago = ?")
        params.append(clean_text(metodo_pago).lower())

    query = f"""
        SELECT
            id,
            fecha,
            tipo,
            origen,
            referencia_id,
            descripcion,
            monto_usd,
            moneda,
            monto_moneda,
            tasa_cambio,
            metodo_pago,
            usuario,
            estado,
            metadata
        FROM movimientos_tesoreria
        WHERE {' AND '.join(filters)}
        ORDER BY fecha DESC, id DESC
    """
    return _safe_read_sql(query, conn, tuple(params))
