from __future__ import annotations

from typing import Any
import pandas as pd

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_profesional_service import ensure_schema as ensure_profesional_schema

UNIDADES_CONTROL = ["unidad", "hoja", "pliego", "cm", "m", "cm²", "m²", "ml", "L", "g", "kg"]


def _cols(conn: Any) -> set[str]:
    return {str(r[1]) for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}


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


def listar_maestro() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT i.id,i.sku,i.nombre,i.categoria,COALESCE(i.tipo_fisico,'unidad') tipo_fisico,
                   COALESCE(i.unidad_base,i.unidad,'unidad') unidad_base,
                   COALESCE(i.unidad_control,i.unidad_base,i.unidad,'unidad') unidad_control,
                   COALESCE(i.unidad_compra_profesional,i.unidad_compra,'unidad') unidad_compra,
                   COALESCE(i.factor_compra_base,CASE WHEN COALESCE(i.contenido_compra,0)>0 THEN i.contenido_compra ELSE 1 END) factor_compra_base,
                   COALESCE(i.stock_actual,0) stock_actual,
                   COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id=i.id AND r.estado='activa'),0) reservado,
                   COALESCE(i.stock_minimo_operativo,0) minimo_operativo,
                   COALESCE(i.stock_seguridad,0) stock_seguridad,
                   COALESCE(i.punto_reorden,0) punto_reorden,
                   COALESCE(i.stock_ideal,0) stock_ideal,
                   COALESCE(i.stock_maximo,0) stock_maximo,
                   COALESCE(i.consumo_promedio_diario,0) consumo_diario,
                   COALESCE(i.dias_reposicion,0) dias_reposicion,
                   COALESCE(i.ancho_cm,0) ancho_cm,COALESCE(i.alto_cm,0) alto_cm,
                   COALESCE(i.gramaje,'') gramaje,COALESCE(i.merma_base_pct,0) merma_pct,
                   COALESCE(i.bloquear_si_critico,1) bloquear_si_critico,
                   COALESCE(i.costo_unitario_usd,0) costo_unitario_usd,
                   COALESCE(p.nombre,i.proveedor_principal,'') proveedor
            FROM inventario i
            LEFT JOIN proveedores p ON p.id=i.proveedor_principal_id
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY i.nombre COLLATE NOCASE
        """, conn)


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
        if r["disponible"] <= 0: return "AGOTADO"
        if r["minimo_operativo"] > 0 and r["disponible"] <= r["minimo_operativo"]: return "CRITICO"
        if r["punto_reorden"] > 0 and r["disponible"] <= r["punto_reorden"]: return "REORDEN"
        if r["reservado"] > 0 and r["reservado"] >= r["stock_actual"] * 0.5: return "COMPROMETIDO"
        return "SUFICIENTE"
    df["estado"] = df.apply(estado, axis=1)
    df["compra_sugerida"] = (df["stock_ideal"] - df["disponible"]).clip(lower=0)
    return df
