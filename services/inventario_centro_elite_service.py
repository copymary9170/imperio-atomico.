from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventario_calidad_service import ensure_schema as ensure_calidad_schema
from services.inventario_factura_lote_service import ensure_factura_lote_schema


def _table_exists(conn: Any, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def ensure_schema() -> None:
    ensure_calidad_schema()
    ensure_factura_lote_schema()


def resumen_centro() -> dict[str, float]:
    ensure_schema()
    with db_transaction() as conn:
        lotes = _table_exists(conn, "inventario_lotes")
        reservas = _table_exists(conn, "reservas_inventario")
        facturas = _table_exists(conn, "facturas_compra")
        recetas = _table_exists(conn, "recetas_inventario")

        articulos = conn.execute(
            "SELECT COUNT(*) n FROM inventario WHERE lower(COALESCE(estado,'activo'))='activo'"
        ).fetchone()["n"]
        valor = conn.execute(
            """SELECT COALESCE(SUM(COALESCE(stock_actual,0)*COALESCE(costo_unitario_usd,0)),0) v
               FROM inventario WHERE lower(COALESCE(estado,'activo'))='activo'"""
        ).fetchone()["v"]
        criticos = conn.execute(
            """SELECT COUNT(*) n FROM inventario
               WHERE lower(COALESCE(estado,'activo'))='activo'
                 AND COALESCE(stock_minimo_operativo,0)>0
                 AND COALESCE(stock_actual,0)<=COALESCE(stock_minimo_operativo,0)"""
        ).fetchone()["n"]

        reservados = 0.0
        if reservas:
            reservados = conn.execute(
                "SELECT COALESCE(SUM(cantidad),0) v FROM reservas_inventario WHERE estado='activa'"
            ).fetchone()["v"]

        por_vencer = 0
        if lotes:
            por_vencer = conn.execute(
                """SELECT COUNT(*) n FROM inventario_lotes
                   WHERE cantidad_disponible>0 AND fecha_vencimiento IS NOT NULL
                     AND date(fecha_vencimiento)<=date('now','+30 day')"""
            ).fetchone()["n"]

        cxp = 0.0
        if facturas:
            cxp = conn.execute(
                "SELECT COALESCE(SUM(pendiente_usd),0) v FROM facturas_compra WHERE pendiente_usd>0"
            ).fetchone()["v"]

        recetas_activas = 0
        if recetas:
            recetas_activas = conn.execute(
                "SELECT COUNT(*) n FROM recetas_inventario WHERE activo=1"
            ).fetchone()["n"]

        return {
            "articulos": float(articulos or 0),
            "valor_inventario": float(valor or 0),
            "criticos": float(criticos or 0),
            "reservados": float(reservados or 0),
            "lotes_por_vencer": float(por_vencer or 0),
            "cuentas_por_pagar": float(cxp or 0),
            "recetas_activas": float(recetas_activas or 0),
        }


def conciliacion_stock_lotes() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        if not _table_exists(conn, "inventario_lotes"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT i.id, i.sku, i.nombre,
                   COALESCE(i.stock_actual,0) AS stock_sistema,
                   COALESCE(SUM(CASE WHEN l.estado!='agotado' THEN l.cantidad_disponible ELSE 0 END),0) AS stock_lotes,
                   ROUND(COALESCE(i.stock_actual,0)-COALESCE(SUM(CASE WHEN l.estado!='agotado' THEN l.cantidad_disponible ELSE 0 END),0),6) AS diferencia
            FROM inventario i
            LEFT JOIN inventario_lotes l ON l.inventario_id=i.id
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            GROUP BY i.id,i.sku,i.nombre,i.stock_actual
            HAVING ABS(diferencia)>0.000001
            ORDER BY ABS(diferencia) DESC, i.nombre
            """,
            conn,
        )


def alertas_operativas() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT i.id, i.sku, i.nombre,
                   COALESCE(i.stock_actual,0) AS stock_actual,
                   COALESCE(i.stock_minimo_operativo,0) AS stock_minimo,
                   COALESCE(i.punto_reorden,0) AS punto_reorden,
                   COALESCE(i.stock_ideal,0) AS stock_ideal,
                   CASE
                     WHEN COALESCE(i.stock_actual,0)<=0 THEN 'AGOTADO'
                     WHEN COALESCE(i.stock_minimo_operativo,0)>0 AND COALESCE(i.stock_actual,0)<=COALESCE(i.stock_minimo_operativo,0) THEN 'CRÍTICO'
                     WHEN COALESCE(i.punto_reorden,0)>0 AND COALESCE(i.stock_actual,0)<=COALESCE(i.punto_reorden,0) THEN 'REORDEN'
                     ELSE 'NORMAL'
                   END AS estado,
                   MAX(COALESCE(i.stock_ideal,0)-COALESCE(i.stock_actual,0),0) AS compra_sugerida
            FROM inventario i
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY CASE estado WHEN 'AGOTADO' THEN 1 WHEN 'CRÍTICO' THEN 2 WHEN 'REORDEN' THEN 3 ELSE 4 END,
                     i.nombre
            """,
            conn,
        )


def ultimos_movimientos(limit: int = 50) -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        if not _table_exists(conn, "movimientos_inventario"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT m.id, m.fecha, i.sku, i.nombre, m.tipo, m.cantidad,
                   m.costo_unitario_usd, m.referencia, m.usuario
            FROM movimientos_inventario m
            JOIN inventario i ON i.id=m.inventario_id
            ORDER BY m.id DESC LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )
