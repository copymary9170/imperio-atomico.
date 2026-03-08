from __future__ import annotations

from contextlib import contextmanager
from typing import Generator


def _safe(value: float | int | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@contextmanager
def savepoint(conn, name: str) -> Generator[None, None, None]:
    """
    Helper para crear sub-transacciones en SQLite.
    Permite rollback parcial dentro de una transacción mayor.
    """

    name = str(name or "sp").replace(" ", "_")

    conn.execute(f"SAVEPOINT {name}")

    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {name}")

    except Exception:

        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        conn.execute(f"RELEASE SAVEPOINT {name}")

        raise


def obtener_stock_disponible(conn, inventario_id: int) -> float:
    """
    Obtiene el stock disponible de un producto activo.
    """

    row = conn.execute(
        """
        SELECT COALESCE(cantidad, stock_actual, 0)
        FROM inventario
        WHERE id = ?
        AND COALESCE(activo, 1) = 1
        AND COALESCE(estado, 'activo') <> 'inactivo'
        """,
        (inventario_id,),
    ).fetchone()

    return _safe(row[0] if row else 0)


def validar_stock_para_salida(conn, inventario_id: int, cantidad: float) -> None:
    """
    Verifica que haya stock suficiente antes de permitir una salida.
    """

    cantidad = _safe(cantidad)

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero")

    disponible = obtener_stock_disponible(conn, inventario_id)

    if disponible < cantidad:

        raise ValueError(
            f"Stock insuficiente para item {inventario_id}. "
            f"Disponible={disponible}, requerido={cantidad}"
        )
