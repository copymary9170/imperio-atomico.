from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from modules.common import clean_text, require_text
from services.conciliacion_service import periodo_esta_cerrado


def _periodo_a_rango(periodo: str) -> tuple[str, str]:
    periodo_norm = require_text(periodo, "Periodo (YYYY-MM)")
    try:
        year, month = periodo_norm.split("-", 1)
        inicio = date(int(year), int(month), 1)
    except Exception as exc:
        raise ValueError("Periodo inválido. Usa formato YYYY-MM") from exc

    siguiente_mes = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    fin = siguiente_mes - timedelta(days=1)
    return inicio.isoformat(), fin.isoformat()


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_column(conn: Any, table_name: str, column_name: str, ddl: str) -> None:
    columns = _table_columns(conn, table_name)
    if columns and column_name not in columns:
        conn.execute(ddl)


def _ensure_fiscal_columns(conn: Any) -> None:
    """Add missing fiscal columns to older SQLite databases.

    Streamlit Cloud can keep an existing database created before the tax module
    existed. This migration is intentionally local and idempotent: it only adds
    missing columns and does not delete or rewrite user data.
    """
    if _table_exists(conn, "ventas"):
        _ensure_column(conn, "ventas", "fiscal_tipo", "ALTER TABLE ventas ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
        _ensure_column(conn, "ventas", "fiscal_iva_debito_usd", "ALTER TABLE ventas ADD COLUMN fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0")
        conn.execute(
            """
            UPDATE ventas
            SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                fiscal_iva_debito_usd = CASE
                    WHEN COALESCE(fiscal_iva_debito_usd, 0) <= 0 THEN COALESCE(impuesto_usd, 0)
                    ELSE fiscal_iva_debito_usd
                END
            """
        )

    if _table_exists(conn, "gastos"):
        _ensure_column(conn, "gastos", "fiscal_tipo", "ALTER TABLE gastos ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
        _ensure_column(conn, "gastos", "fiscal_iva_credito_usd", "ALTER TABLE gastos ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "gastos", "fiscal_credito_iva_deducible", "ALTER TABLE gastos ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            UPDATE gastos
            SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                fiscal_credito_iva_deducible = COALESCE(fiscal_credito_iva_deducible, 1),
                fiscal_iva_credito_usd = CASE
                    WHEN COALESCE(fiscal_iva_credito_usd, 0) <= 0 THEN COALESCE(impuesto_usd, 0)
                    ELSE fiscal_iva_credito_usd
                END
            """
        )

    if _table_exists(conn, "historial_compras"):
        _ensure_column(conn, "historial_compras", "fiscal_tipo", "ALTER TABLE historial_compras ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
        _ensure_column(conn, "historial_compras", "fiscal_iva_credito_usd", "ALTER TABLE historial_compras ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "historial_compras", "fiscal_credito_iva_deducible", "ALTER TABLE historial_compras ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            UPDATE historial_compras
            SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                fiscal_credito_iva_deducible = COALESCE(fiscal_credito_iva_deducible, 1),
                fiscal_iva_credito_usd = CASE
                    WHEN COALESCE(fiscal_iva_credito_usd, 0) <= 0 THEN COALESCE(impuestos, 0)
                    ELSE fiscal_iva_credito_usd
                END
            """
        )


def obtener_resumen_fiscal_periodo(conn: Any, *, periodo: str) -> dict[str, float | int | str | bool]:
    _ensure_fiscal_columns(conn)
    fecha_desde, fecha_hasta = _periodo_a_rango(periodo)

    ventas = conn.execute(
        """
        SELECT COUNT(*) AS documentos,
               COALESCE(SUM(subtotal_usd), 0) AS base,
               COALESCE(SUM(fiscal_iva_debito_usd), 0) AS iva
        FROM ventas
        WHERE date(fecha) BETWEEN date(?) AND date(?)
          AND estado != 'anulada'
          AND COALESCE(fiscal_tipo, 'gravada') = 'gravada'
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()

    compras = None
    if _table_exists(conn, "historial_compras"):
        compras = conn.execute(
            """
            SELECT COUNT(*) AS documentos,
                   COALESCE(SUM(costo_total_usd), 0) AS base,
                   COALESCE(SUM(fiscal_iva_credito_usd), 0) AS iva
            FROM historial_compras
            WHERE date(fecha) BETWEEN date(?) AND date(?)
              AND COALESCE(activo, 1) = 1
              AND COALESCE(fiscal_tipo, 'gravada') = 'gravada'
              AND COALESCE(fiscal_credito_iva_deducible, 1) = 1
            """,
            (fecha_desde, fecha_hasta),
        ).fetchone()

    gastos = conn.execute(
        """
        SELECT COUNT(*) AS documentos,
               COALESCE(SUM(subtotal_usd), 0) AS base,
               COALESCE(SUM(fiscal_iva_credito_usd), 0) AS iva
        FROM gastos
        WHERE date(fecha) BETWEEN date(?) AND date(?)
          AND estado NOT IN ('anulado','cancelado')
          AND COALESCE(fiscal_tipo, 'gravada') = 'gravada'
          AND COALESCE(fiscal_credito_iva_deducible, 1) = 1
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()

    iva_debito = float(ventas["iva"] if ventas else 0.0)
    iva_credito_compras = float(compras["iva"] if compras else 0.0)
    iva_credito_gastos = float(gastos["iva"] if gastos else 0.0)
    iva_credito_total = iva_credito_compras + iva_credito_gastos

    return {
        "periodo": clean_text(periodo),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "ventas_documentos": int(ventas["documentos"] if ventas else 0),
        "ventas_base_usd": float(ventas["base"] if ventas else 0.0),
        "iva_debito_usd": round(iva_debito, 2),
        "compras_documentos": int(compras["documentos"] if compras else 0),
        "compras_base_usd": float(compras["base"] if compras else 0.0),
        "iva_credito_compras_usd": round(iva_credito_compras, 2),
        "gastos_documentos": int(gastos["documentos"] if gastos else 0),
        "gastos_base_usd": float(gastos["base"] if gastos else 0.0),
        "iva_credito_gastos_usd": round(iva_credito_gastos, 2),
        "iva_credito_usd": round(iva_credito_total, 2),
        "iva_neto_periodo_usd": round(iva_debito - iva_credito_total, 2),
        "periodo_cerrado": bool(periodo_esta_cerrado(conn, fecha_movimiento=fecha_hasta, tipo_cierre="mensual")),
    }


def obtener_detalle_fiscal_periodo(conn: Any, *, periodo: str) -> pd.DataFrame:
    r = obtener_resumen_fiscal_periodo(conn, periodo=periodo)
    return pd.DataFrame(
        [
            {"Concepto": "IVA débito fiscal (ventas)", "Documentos": r["ventas_documentos"], "Base USD": r["ventas_base_usd"], "IVA USD": r["iva_debito_usd"]},
            {"Concepto": "IVA crédito fiscal (compras)", "Documentos": r["compras_documentos"], "Base USD": r["compras_base_usd"], "IVA USD": r["iva_credito_compras_usd"]},
            {"Concepto": "IVA crédito fiscal (gastos)", "Documentos": r["gastos_documentos"], "Base USD": r["gastos_base_usd"], "IVA USD": r["iva_credito_gastos_usd"]},
            {"Concepto": "IVA neto del período", "Documentos": None, "Base USD": None, "IVA USD": r["iva_neto_periodo_usd"]},
        ]
    )


def exportar_resumen_fiscal_csv(conn: Any, *, periodo: str) -> bytes:
    return obtener_detalle_fiscal_periodo(conn, periodo=periodo).to_csv(index=False).encode("utf-8")
