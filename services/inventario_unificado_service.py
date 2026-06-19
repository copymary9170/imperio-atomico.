from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text

TIPOS_USO = ["Insumo", "Reventa", "Ambos"]
UNIDADES_BASE = [
    "unidad", "hoja", "pliego", "resma", "paquete", "caja", "rollo",
    "g", "kg", "mg", "ml", "L", "cm", "m", "cm²", "m²", "cm³", "m³",
]


def ensure_inventario_unificado_schema() -> None:
    with db_transaction() as conn:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}
        migrations = {
            "tipo_uso": "TEXT NOT NULL DEFAULT 'Ambos'",
            "unidad_base": "TEXT",
            "permite_fraccionamiento": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, ddl in migrations.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {name} {ddl}")
                cols.add(name)

        conn.execute(
            """
            UPDATE inventario
            SET tipo_uso = CASE
                WHEN lower(COALESCE(tipo_uso, '')) IN ('insumo','reventa','ambos')
                    THEN upper(substr(tipo_uso,1,1)) || lower(substr(tipo_uso,2))
                WHEN lower(COALESCE(categoria,'')) LIKE '%tinta%'
                  OR lower(COALESCE(categoria,'')) LIKE '%consumible%'
                  OR lower(COALESCE(nombre,'')) LIKE '%tinta%'
                  OR lower(COALESCE(nombre,'')) LIKE '%cabezal%'
                    THEN 'Insumo'
                ELSE 'Ambos'
            END,
            unidad_base = COALESCE(NULLIF(unidad_base,''), NULLIF(unidad,''), 'unidad'),
            permite_fraccionamiento = COALESCE(permite_fraccionamiento, 1)
            """
        )


def listar_inventario_unificado(activos_only: bool = True) -> pd.DataFrame:
    ensure_inventario_unificado_schema()
    where = "WHERE lower(COALESCE(estado,'activo'))='activo'" if activos_only else ""
    with db_transaction() as conn:
        return pd.read_sql_query(
            f"""
            SELECT id, sku, nombre, categoria,
                   COALESCE(NULLIF(unidad_base,''), unidad, 'unidad') AS unidad_base,
                   unidad,
                   COALESCE(tipo_uso,'Ambos') AS tipo_uso,
                   COALESCE(permite_fraccionamiento,1) AS permite_fraccionamiento,
                   COALESCE(stock_actual,0) AS stock_actual,
                   COALESCE(stock_minimo,0) AS stock_minimo,
                   COALESCE(costo_unitario_usd,0) AS costo_unitario_usd,
                   COALESCE(precio_venta_usd,0) AS precio_venta_usd,
                   COALESCE(estado,'activo') AS estado
            FROM inventario
            {where}
            ORDER BY nombre COLLATE NOCASE
            """,
            conn,
        )


def guardar_clasificacion_inventario(
    inventario_id: int,
    *,
    tipo_uso: str,
    unidad_base: str,
    permite_fraccionamiento: bool,
) -> None:
    ensure_inventario_unificado_schema()
    tipo = clean_text(tipo_uso).title()
    if tipo not in TIPOS_USO:
        raise ValueError("Tipo de uso inválido.")
    unidad = clean_text(unidad_base) or "unidad"
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE inventario
            SET tipo_uso=?, unidad_base=?, unidad=?, permite_fraccionamiento=?
            WHERE id=?
            """,
            (tipo, unidad, unidad, 1 if permite_fraccionamiento else 0, int(inventario_id)),
        )


def crear_item_unificado(data: dict[str, Any], usuario: str) -> int:
    ensure_inventario_unificado_schema()
    nombre = clean_text(data.get("nombre"))
    sku = clean_text(data.get("sku"))
    if not nombre or not sku:
        raise ValueError("Nombre y SKU son obligatorios.")
    tipo_uso = clean_text(data.get("tipo_uso") or "Ambos").title()
    if tipo_uso not in TIPOS_USO:
        raise ValueError("Tipo de uso inválido.")
    unidad = clean_text(data.get("unidad_base") or "unidad")
    with db_transaction() as conn:
        existe = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?)", (sku,)).fetchone()
        if existe:
            raise ValueError("Ya existe un producto con ese SKU.")
        cur = conn.execute(
            """
            INSERT INTO inventario(
                usuario, sku, nombre, categoria, unidad, unidad_base, tipo_uso,
                permite_fraccionamiento, stock_actual, stock_minimo,
                costo_unitario_usd, precio_venta_usd, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo')
            """,
            (
                usuario, sku, nombre, clean_text(data.get("categoria") or "General"),
                unidad, unidad, tipo_uso, 1 if data.get("permite_fraccionamiento", True) else 0,
                float(data.get("stock_actual") or 0), float(data.get("stock_minimo") or 0),
                float(data.get("costo_unitario_usd") or 0), float(data.get("precio_venta_usd") or 0),
            ),
        )
        return int(cur.lastrowid)
