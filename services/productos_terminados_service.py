from __future__ import annotations

import json
from typing import Any

import pandas as pd

from database.connection import db_transaction


def ensure_productos_terminados_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS productos_terminados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                codigo TEXT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                categoria TEXT NOT NULL DEFAULT 'Producto terminado',
                unidad_venta TEXT NOT NULL DEFAULT 'unidad',
                costo_materiales_usd REAL NOT NULL DEFAULT 0,
                costo_operativo_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                margen_pct REAL NOT NULL DEFAULT 0,
                precio_sugerido_usd REAL NOT NULL DEFAULT 0,
                stock_actual REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'activo',
                detalle_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS productos_terminados_bom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_terminado_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                insumo_nombre TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 0,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                notas TEXT,
                FOREIGN KEY(producto_terminado_id) REFERENCES productos_terminados(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_productos_terminados_estado ON productos_terminados(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_productos_terminados_bom_producto ON productos_terminados_bom(producto_terminado_id)")


def listar_inventario_para_bom() -> pd.DataFrame:
    ensure_productos_terminados_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, sku, nombre, unidad, stock_actual, costo_unitario_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY nombre
            """,
            conn,
        )


def crear_producto_terminado(
    *,
    usuario: str,
    codigo: str,
    nombre: str,
    descripcion: str,
    unidad_venta: str,
    insumos: list[dict[str, Any]],
    costo_operativo_usd: float = 0.0,
    margen_pct: float = 40.0,
    stock_actual: float = 0.0,
) -> int:
    ensure_productos_terminados_tables()
    nombre_clean = str(nombre or '').strip()
    if not nombre_clean:
        raise ValueError('El nombre del producto terminado es obligatorio.')
    if not insumos:
        raise ValueError('Agrega al menos una materia prima o insumo.')

    costo_materiales = sum(float(item.get('costo_total_usd') or 0.0) for item in insumos)
    costo_operativo = max(0.0, float(costo_operativo_usd or 0.0))
    costo_total = costo_materiales + costo_operativo
    margen = max(0.0, float(margen_pct or 0.0)) / 100.0
    if margen >= 0.95:
        margen = 0.95
    precio_sugerido = costo_total / max(1.0 - margen, 0.05)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO productos_terminados
            (
                usuario, codigo, nombre, descripcion, unidad_venta,
                costo_materiales_usd, costo_operativo_usd, costo_total_usd,
                margen_pct, precio_sugerido_usd, stock_actual, detalle_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or 'Sistema'),
                str(codigo or '').strip(),
                nombre_clean,
                str(descripcion or '').strip(),
                str(unidad_venta or 'unidad').strip() or 'unidad',
                round(costo_materiales, 6),
                round(costo_operativo, 6),
                round(costo_total, 6),
                float(margen_pct or 0.0),
                round(precio_sugerido, 6),
                max(0.0, float(stock_actual or 0.0)),
                json.dumps(insumos, ensure_ascii=False),
            ),
        )
        producto_id = int(cur.lastrowid)
        for item in insumos:
            conn.execute(
                """
                INSERT INTO productos_terminados_bom
                (
                    producto_terminado_id, inventario_id, insumo_nombre,
                    cantidad, unidad, costo_unitario_usd, costo_total_usd, notas
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    producto_id,
                    int(item['inventario_id']),
                    str(item.get('insumo_nombre') or ''),
                    float(item.get('cantidad') or 0.0),
                    str(item.get('unidad') or 'unidad'),
                    float(item.get('costo_unitario_usd') or 0.0),
                    float(item.get('costo_total_usd') or 0.0),
                    str(item.get('notas') or ''),
                ),
            )
        return producto_id


def listar_productos_terminados(limit: int = 100) -> pd.DataFrame:
    ensure_productos_terminados_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, fecha_creacion, codigo, nombre, unidad_venta,
                costo_materiales_usd, costo_operativo_usd, costo_total_usd,
                margen_pct, precio_sugerido_usd, stock_actual, estado
            FROM productos_terminados
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )
