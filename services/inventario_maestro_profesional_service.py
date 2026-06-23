from __future__ import annotations

from typing import Any
import pandas as pd

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_profesional_service import ensure_schema as ensure_profesional_schema

UNIDADES_CONTROL = ["unidad", "hoja", "pliego", "cm", "m", "cm²", "m²", "ml", "L", "g", "kg"]


def _cols(conn: Any, table: str = "inventario") -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    ensure_profesional_schema()
    with db_transaction() as conn:
        cols = _cols(conn)
        extras = {
            "unidad_compra_profesional": "TEXT",
            "factor_compra_base": "REAL NOT NULL DEFAULT 1",
            "bloquear_si_critico": "INTEGER NOT NULL DEFAULT 1",
            "consumo_lote_estandar": "REAL NOT NULL DEFAULT 0",
            "lote_estandar_nombre": "TEXT",
        }
        for name, ddl in extras.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {name} {ddl}")


def _expr(cols: set[str], name: str, default: str, alias: str | None = None) -> str:
    out = alias or name
    return f"COALESCE(i.{name}, {default}) AS {out}" if name in cols else f"{default} AS {out}"


def listar_maestro() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        cols = _cols(conn)
        reservas_existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reservas_inventario'"
        ).fetchone() is not None

        unidad_base = (
            "COALESCE(NULLIF(i.unidad_base,''), NULLIF(i.unidad,''), 'unidad') AS unidad_base"
            if "unidad_base" in cols and "unidad" in cols
            else _expr(cols, "unidad_base", "'unidad'") if "unidad_base" in cols
            else _expr(cols, "unidad", "'unidad'", "unidad_base")
        )
        unidad_control = (
            "COALESCE(NULLIF(i.unidad_control,''), NULLIF(i.unidad_base,''), NULLIF(i.unidad,''), 'unidad') AS unidad_control"
            if {"unidad_control", "unidad_base", "unidad"}.issubset(cols)
            else "'unidad' AS unidad_control"
        )
        unidad_compra = (
            "COALESCE(NULLIF(i.unidad_compra_profesional,''), NULLIF(i.unidad_compra,''), 'unidad') AS unidad_compra"
            if {"unidad_compra_profesional", "unidad_compra"}.issubset(cols)
            else _expr(cols, "unidad_compra_profesional", "'unidad'", "unidad_compra")
        )
        factor_compra = (
            "COALESCE(NULLIF(i.factor_compra_base,0), NULLIF(i.contenido_compra,0), 1) AS factor_compra_base"
            if {"factor_compra_base", "contenido_compra"}.issubset(cols)
            else _expr(cols, "factor_compra_base", "1", "factor_compra_base")
        )
        reservado = (
            "COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id=i.id AND r.estado='activa'),0) AS reservado"
            if reservas_existe else "0 AS reservado"
        )
        proveedor = _expr(cols, "proveedor_principal", "''", "proveedor")

        selected = [
            _expr(cols, "id", "0"),
            _expr(cols, "sku", "''"),
            _expr(cols, "nombre", "''"),
            _expr(cols, "categoria", "''"),
            _expr(cols, "tipo_fisico", "'unidad'"),
            unidad_base,
            unidad_control,
            unidad_compra,
            factor_compra,
            _expr(cols, "stock_actual", "0"),
            reservado,
            _expr(cols, "stock_minimo_operativo", "0", "minimo_operativo"),
            _expr(cols, "stock_seguridad", "0"),
            _expr(cols, "punto_reorden", "0"),
            _expr(cols, "stock_ideal", "0"),
            _expr(cols, "stock_maximo", "0"),
            _expr(cols, "consumo_promedio_diario", "0", "consumo_diario"),
            _expr(cols, "dias_reposicion", "0"),
            _expr(cols, "ancho_cm", "0"),
            _expr(cols, "alto_cm", "0"),
            _expr(cols, "gramaje", "''"),
            _expr(cols, "merma_base_pct", "0", "merma_pct"),
            _expr(cols, "bloquear_si_critico", "1"),
            _expr(cols, "costo_unitario_usd", "0"),
            proveedor,
        ]
        where = "WHERE lower(COALESCE(i.estado,'activo'))='activo'" if "estado" in cols else ""
        order = "ORDER BY i.nombre COLLATE NOCASE" if "nombre" in cols else "ORDER BY i.id"
        sql = f"SELECT {', '.join(selected)} FROM inventario i {where} {order}"
        return pd.read_sql_query(sql, conn)


def guardar_ficha(
    inventario_id: int,
    *, unidad_control: str, unidad_compra: str, factor_compra_base: float,
    minimo_operativo: float, stock_seguridad: float, consumo_diario: float,
    dias_reposicion: float, stock_ideal: float, stock_maximo: float,
    bloquear_si_critico: bool,
) -> None:
    ensure_schema()
    if factor_compra_base <= 0:
        raise ValueError("El factor de compra debe ser mayor que cero.")
    punto = float(consumo_diario or 0) * float(dias_reposicion or 0) + float(stock_seguridad or 0)
    with db_transaction() as conn:
        conn.execute("""
            UPDATE inventario SET unidad_control=?,unidad_compra_profesional=?,factor_compra_base=?,
                stock_minimo_operativo=?,stock_seguridad=?,consumo_promedio_diario=?,dias_reposicion=?,
                punto_reorden=?,stock_ideal=?,stock_maximo=?,bloquear_si_critico=? WHERE id=?
        """, (
            unidad_control, unidad_compra, float(factor_compra_base), float(minimo_operativo or 0),
            float(stock_seguridad or 0), float(consumo_diario or 0), float(dias_reposicion or 0),
            punto, float(stock_ideal or 0), float(stock_maximo or 0), 1 if bloquear_si_critico else 0,
            int(inventario_id),
        ))


def registrar_compra(
    inventario_id: int, *, cantidad_comprada: float, costo_total_usd: float,
    referencia: str, usuario: str,
) -> tuple[float, float]:
    ensure_schema()
    if cantidad_comprada <= 0:
        raise ValueError("La cantidad comprada debe ser mayor que cero.")
    with db_transaction() as conn:
        row = conn.execute("SELECT factor_compra_base,nombre FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        if not row:
            raise ValueError("Artículo no encontrado.")
        factor = float(row["factor_compra_base"] or 1)
        cantidad_base = float(cantidad_comprada) * factor
        costo_unitario = float(costo_total_usd or 0) / cantidad_base if cantidad_base > 0 else 0
        ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(inventario_id), tipo="COMPRA", cantidad=cantidad_base,
            costo_unitario=costo_unitario, motivo=referencia or "Compra", usuario=usuario,
        ))
        if not ok:
            raise ValueError(msg)
        return cantidad_base, costo_unitario


def resumen_alertas() -> pd.DataFrame:
    df = listar_maestro()
    if df.empty:
        return df
    df["disponible"] = df["stock_actual"] - df["reservado"]

    def estado(r: pd.Series) -> str:
        if r["disponible"] <= 0:
            return "AGOTADO"
        if r["minimo_operativo"] > 0 and r["disponible"] <= r["minimo_operativo"]:
            return "CRITICO"
        if r["punto_reorden"] > 0 and r["disponible"] <= r["punto_reorden"]:
            return "REORDEN"
        if r["reservado"] > 0 and r["stock_actual"] > 0 and r["reservado"] >= r["stock_actual"] * 0.5:
            return "COMPROMETIDO"
        return "SUFICIENTE"

    df["estado"] = df.apply(estado, axis=1)
    df["compra_sugerida"] = (df["stock_ideal"] - df["disponible"]).clip(lower=0)
    return df
