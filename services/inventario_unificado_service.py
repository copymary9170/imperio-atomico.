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

CAMPOS_FICHA_AVANZADA: dict[str, str] = {
    "marca": "TEXT",
    "color": "TEXT",
    "tamano": "TEXT",
    "gramaje": "TEXT",
    "acabado": "TEXT",
    "ancho_cm": "REAL NOT NULL DEFAULT 0",
    "alto_cm": "REAL NOT NULL DEFAULT 0",
    "margen_izquierdo_cm": "REAL NOT NULL DEFAULT 0",
    "margen_derecho_cm": "REAL NOT NULL DEFAULT 0",
    "margen_superior_cm": "REAL NOT NULL DEFAULT 0",
    "margen_inferior_cm": "REAL NOT NULL DEFAULT 0",
    "separacion_cm": "REAL NOT NULL DEFAULT 0",
    "sangrado_cm": "REAL NOT NULL DEFAULT 0",
    "merma_base_pct": "REAL NOT NULL DEFAULT 0",
    "unidad_compra": "TEXT",
    "contenido_compra": "REAL NOT NULL DEFAULT 0",
    "proveedor_principal": "TEXT",
    "ubicacion": "TEXT",
    "stock_ideal": "REAL NOT NULL DEFAULT 0",
    "stock_maximo": "REAL NOT NULL DEFAULT 0",
    "punto_reorden": "REAL NOT NULL DEFAULT 0",
    "observaciones": "TEXT",
}


def _table_columns(conn: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_inventario_unificado_schema() -> None:
    with db_transaction() as conn:
        cols = _table_columns(conn, "inventario")
        migrations = {
            "tipo_uso": "TEXT NOT NULL DEFAULT 'Ambos'",
            "unidad_base": "TEXT",
            "permite_fraccionamiento": "INTEGER NOT NULL DEFAULT 1",
            **CAMPOS_FICHA_AVANZADA,
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


def _query_inventario(activos_only: bool = True) -> pd.DataFrame:
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
                   COALESCE(marca,'') AS marca,
                   COALESCE(color,'') AS color,
                   COALESCE(tamano,'') AS tamano,
                   COALESCE(gramaje,'') AS gramaje,
                   COALESCE(acabado,'') AS acabado,
                   COALESCE(ancho_cm,0) AS ancho_cm,
                   COALESCE(alto_cm,0) AS alto_cm,
                   COALESCE(margen_izquierdo_cm,0) AS margen_izquierdo_cm,
                   COALESCE(margen_derecho_cm,0) AS margen_derecho_cm,
                   COALESCE(margen_superior_cm,0) AS margen_superior_cm,
                   COALESCE(margen_inferior_cm,0) AS margen_inferior_cm,
                   COALESCE(separacion_cm,0) AS separacion_cm,
                   COALESCE(sangrado_cm,0) AS sangrado_cm,
                   COALESCE(merma_base_pct,0) AS merma_base_pct,
                   ROUND(COALESCE(ancho_cm,0) * COALESCE(alto_cm,0), 4) AS area_total_cm2,
                   ROUND(MAX(COALESCE(ancho_cm,0)-COALESCE(margen_izquierdo_cm,0)-COALESCE(margen_derecho_cm,0),0)
                         * MAX(COALESCE(alto_cm,0)-COALESCE(margen_superior_cm,0)-COALESCE(margen_inferior_cm,0),0), 4) AS area_util_cm2,
                   CASE WHEN COALESCE(ancho_cm,0) * COALESCE(alto_cm,0) > 0 THEN
                       ROUND(100 - ((MAX(COALESCE(ancho_cm,0)-COALESCE(margen_izquierdo_cm,0)-COALESCE(margen_derecho_cm,0),0)
                         * MAX(COALESCE(alto_cm,0)-COALESCE(margen_superior_cm,0)-COALESCE(margen_inferior_cm,0),0))
                         / (COALESCE(ancho_cm,0) * COALESCE(alto_cm,0)) * 100), 2)
                   ELSE 0 END AS merma_dimensional_pct,
                   COALESCE(unidad_compra,'') AS unidad_compra,
                   COALESCE(contenido_compra,0) AS contenido_compra,
                   COALESCE(proveedor_principal,'') AS proveedor_principal,
                   COALESCE(ubicacion,'') AS ubicacion,
                   COALESCE(stock_ideal,0) AS stock_ideal,
                   COALESCE(stock_maximo,0) AS stock_maximo,
                   COALESCE(punto_reorden,0) AS punto_reorden,
                   COALESCE(observaciones,'') AS observaciones,
                   COALESCE(estado,'activo') AS estado
            FROM inventario
            {where}
            ORDER BY nombre COLLATE NOCASE
            """,
            conn,
        )


def _try_restore_inventory_json() -> None:
    try:
        from services.inventario_cloud_sync import restore_inventario_from_github_if_empty

        restore_inventario_from_github_if_empty("Sistema")
    except Exception:
        pass


def _try_export_inventory_json() -> None:
    try:
        from services.inventario_cloud_sync import export_inventario_to_github

        export_inventario_to_github()
    except Exception:
        pass


def listar_inventario_unificado(activos_only: bool = True) -> pd.DataFrame:
    ensure_inventario_unificado_schema()
    df = _query_inventario(activos_only)
    if df.empty:
        _try_restore_inventory_json()
        df = _query_inventario(activos_only)
    return df


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
    _try_export_inventory_json()


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
    item_id = 0
    with db_transaction() as conn:
        existe = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?)", (sku,)).fetchone()
        if existe:
            raise ValueError("Ya existe un producto con ese SKU.")
        cur = conn.execute(
            """
            INSERT INTO inventario(
                usuario, sku, nombre, categoria, unidad, unidad_base, tipo_uso,
                permite_fraccionamiento, stock_actual, stock_minimo,
                costo_unitario_usd, precio_venta_usd, marca, color, tamano,
                gramaje, acabado, ancho_cm, alto_cm, margen_izquierdo_cm,
                margen_derecho_cm, margen_superior_cm, margen_inferior_cm,
                separacion_cm, sangrado_cm, merma_base_pct,
                unidad_compra, contenido_compra, proveedor_principal, ubicacion,
                stock_ideal, stock_maximo, punto_reorden, observaciones, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo')
            """,
            (
                usuario, sku, nombre, clean_text(data.get("categoria") or "General"),
                unidad, unidad, tipo_uso, 1 if data.get("permite_fraccionamiento", True) else 0,
                float(data.get("stock_actual") or 0), float(data.get("stock_minimo") or 0),
                float(data.get("costo_unitario_usd") or 0), float(data.get("precio_venta_usd") or 0),
                clean_text(data.get("marca")), clean_text(data.get("color")), clean_text(data.get("tamano")),
                clean_text(data.get("gramaje")), clean_text(data.get("acabado")),
                float(data.get("ancho_cm") or 0), float(data.get("alto_cm") or 0),
                float(data.get("margen_izquierdo_cm") or 0), float(data.get("margen_derecho_cm") or 0),
                float(data.get("margen_superior_cm") or 0), float(data.get("margen_inferior_cm") or 0),
                float(data.get("separacion_cm") or 0), float(data.get("sangrado_cm") or 0),
                float(data.get("merma_base_pct") or 0), clean_text(data.get("unidad_compra")),
                float(data.get("contenido_compra") or 0), clean_text(data.get("proveedor_principal")),
                clean_text(data.get("ubicacion")), float(data.get("stock_ideal") or 0),
                float(data.get("stock_maximo") or 0), float(data.get("punto_reorden") or 0),
                clean_text(data.get("observaciones")),
            ),
        )
        item_id = int(cur.lastrowid)
    _try_export_inventory_json()
    return item_id
