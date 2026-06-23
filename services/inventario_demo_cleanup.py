from __future__ import annotations

from typing import Any

from database.connection import db_transaction

DEMO_SKUS = ("PRUEBA-001", "PAP-BOND-CARTA-75G")


def _table_exists(conn: Any, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(conn: Any, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def eliminar_articulos_demo() -> int:
    """Elimina definitivamente los dos artículos de demostración y sus relaciones técnicas."""
    with db_transaction() as conn:
        if not _table_exists(conn, "inventario"):
            return 0

        placeholders = ",".join("?" for _ in DEMO_SKUS)
        rows = conn.execute(
            f"SELECT id FROM inventario WHERE sku IN ({placeholders})",
            DEMO_SKUS,
        ).fetchall()
        ids = [int(row[0]) for row in rows]
        if not ids:
            return 0

        relaciones = [
            ("inventario_usos", "inventario_id"),
            ("reservas_inventario", "inventario_id"),
            ("mermas_inventario", "inventario_id"),
            ("conteos_inventario", "inventario_id"),
            ("movimientos_inventario", "inventario_id"),
            ("recetas_inventario_detalle", "insumo_id"),
            ("recetas_inventario", "producto_inventario_id"),
            ("ventas_detalle", "inventario_id"),
        ]

        id_marks = ",".join("?" for _ in ids)
        for table, column in relaciones:
            if column in _columns(conn, table):
                conn.execute(
                    f"DELETE FROM {table} WHERE {column} IN ({id_marks})",
                    ids,
                )

        conn.execute(
            f"DELETE FROM inventario WHERE id IN ({id_marks})",
            ids,
        )
        return len(ids)
