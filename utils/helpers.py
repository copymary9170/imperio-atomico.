from __future__ import annotations

from contextlib import contextmanager
from typing import Generator


@contextmanager
def savepoint(conn, name: str) -> Generator[None, None, None]:
    """Nested transaction helper for SQLite operations inside existing flows."""
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {name}")
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        conn.execute(f"RELEASE SAVEPOINT {name}")
        raise


def obtener_stock_disponible(conn, inventario_id: int) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(cantidad, stock_actual, 0)
        FROM inventario
        WHERE id = ? AND COALESCE(activo, 1) = 1 AND COALESCE(estado, 'activo') <> 'inactivo'
        """,
        (inventario_id,),
    ).fetchone()
    return float(row[0] if row else 0.0)


def validar_stock_para_salida(conn, inventario_id: int, cantidad: float) -> None:
    disponible = obtener_stock_disponible(conn, inventario_id)
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")
    if disponible < cantidad:
        raise ValueError(
            f"Stock insuficiente para item {inventario_id}: disponible={disponible}, requerido={cantidad}"
        )
