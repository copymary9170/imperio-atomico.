from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text


CATEGORIAS_REVENTA = [
    "Papeleria",
    "Utiles escolares",
    "Consumibles",
    "Accesorios",
    "Mercancia general",
]

UNIDADES_REVENTA = ["unidad", "paquete", "caja", "docena", "resma", "rollo", "kit"]


def ensure_reventa_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mercancia_reventa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                sku TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'Mercancia general',
                marca TEXT,
                proveedor_principal TEXT,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                stock_actual REAL NOT NULL DEFAULT 0,
                stock_minimo REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                precio_venta_usd REAL NOT NULL DEFAULT 0,
                margen_pct REAL NOT NULL DEFAULT 0,
                ubicacion TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS compras_reventa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                mercancia_id INTEGER NOT NULL,
                proveedor TEXT,
                factura TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                precio_venta_usd REAL NOT NULL DEFAULT 0,
                referencia TEXT,
                FOREIGN KEY(mercancia_id) REFERENCES mercancia_reventa(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reventa_estado ON mercancia_reventa(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_compras_reventa_item ON compras_reventa(mercancia_id)")


def crear_mercancia_reventa(*, usuario: str, sku: str, nombre: str, categoria: str, unidad: str, precio_venta_usd: float = 0.0, stock_minimo: float = 0.0, marca: str = "", proveedor_principal: str = "", ubicacion: str = "") -> int:
    ensure_reventa_tables()
    sku_ok = require_text(sku, "SKU")
    nombre_ok = require_text(nombre, "Nombre")
    with db_transaction() as conn:
        existe = conn.execute("SELECT id FROM mercancia_reventa WHERE lower(sku)=lower(?)", (sku_ok,)).fetchone()
        if existe:
            raise ValueError(f"Ya existe mercancía con SKU {sku_ok}.")
        cur = conn.execute(
            """
            INSERT INTO mercancia_reventa
            (usuario, sku, nombre, categoria, marca, proveedor_principal, unidad, stock_minimo, precio_venta_usd, ubicacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"), sku_ok, nombre_ok, clean_text(categoria) or "Mercancia general",
                clean_text(marca), clean_text(proveedor_principal), clean_text(unidad) or "unidad",
                max(0.0, float(stock_minimo or 0.0)), max(0.0, float(precio_venta_usd or 0.0)), clean_text(ubicacion)
            ),
        )
        return int(cur.lastrowid)


def registrar_compra_reventa(*, usuario: str, mercancia_id: int, cantidad: float, costo_total_usd: float, precio_venta_usd: float | None = None, proveedor: str = "", factura: str = "", referencia: str = "") -> dict[str, Any]:
    ensure_reventa_tables()
    cantidad_ok = float(cantidad or 0.0)
    total_ok = float(costo_total_usd or 0.0)
    if cantidad_ok <= 0 or total_ok <= 0:
        raise ValueError("Cantidad y costo total deben ser mayores a cero.")
    costo_unit = total_ok / cantidad_ok
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM mercancia_reventa WHERE id=? AND estado='activo'", (int(mercancia_id),)).fetchone()
        if not row:
            raise ValueError("Mercancía no encontrada o inactiva.")
        stock_anterior = float(row["stock_actual"] or 0.0)
        costo_anterior = float(row["costo_unitario_usd"] or 0.0)
        stock_nuevo = stock_anterior + cantidad_ok
        costo_promedio = ((stock_anterior * costo_anterior) + total_ok) / stock_nuevo if stock_nuevo else costo_unit
        precio = float(precio_venta_usd) if precio_venta_usd is not None and float(precio_venta_usd) > 0 else float(row["precio_venta_usd"] or 0.0)
        margen = ((precio - costo_promedio) / precio * 100.0) if precio > 0 else 0.0
        conn.execute(
            "UPDATE mercancia_reventa SET stock_actual=?, costo_unitario_usd=?, precio_venta_usd=?, margen_pct=?, proveedor_principal=COALESCE(NULLIF(?, ''), proveedor_principal) WHERE id=?",
            (round(stock_nuevo, 4), round(costo_promedio, 6), round(precio, 4), round(margen, 4), clean_text(proveedor), int(mercancia_id)),
        )
        cur = conn.execute(
            """
            INSERT INTO compras_reventa
            (usuario, mercancia_id, proveedor, factura, cantidad, costo_total_usd, costo_unitario_usd, precio_venta_usd, referencia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(usuario or "Sistema"), int(mercancia_id), clean_text(proveedor), clean_text(factura), cantidad_ok, round(total_ok, 4), round(costo_unit, 6), round(precio, 4), clean_text(referencia)),
        )
        return {"compra_id": int(cur.lastrowid), "stock_anterior": stock_anterior, "stock_nuevo": stock_nuevo, "costo_unitario_usd": costo_unit, "costo_promedio_usd": costo_promedio, "margen_pct": margen}


def listar_mercancia_reventa() -> pd.DataFrame:
    ensure_reventa_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, sku, nombre, categoria, marca, proveedor_principal, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd, margen_pct, ubicacion, estado
            FROM mercancia_reventa
            WHERE estado='activo'
            ORDER BY categoria, nombre
            """,
            conn,
        )


def listar_compras_reventa(limit: int = 100) -> pd.DataFrame:
    ensure_reventa_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT cr.id, cr.fecha, mr.nombre, cr.proveedor, cr.factura, cr.cantidad, cr.costo_total_usd, cr.costo_unitario_usd, cr.precio_venta_usd, cr.referencia
            FROM compras_reventa cr
            JOIN mercancia_reventa mr ON mr.id = cr.mercancia_id
            ORDER BY cr.id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )
