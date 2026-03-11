from __future__ import annotations

from contextlib import contextmanager
from typing import Generator


def _safe(value: float | int | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


@contextmanager
def savepoint(conn, name: str) -> Generator[None, None, None]:
    """
    Helper para crear sub-transacciones en SQLite.
    Permite rollback parcial dentro de una transacción mayor.
    """

    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in str(name or "sp"))
    safe_name = safe_name.strip("_") or "sp"

    conn.execute(f"SAVEPOINT {safe_name}")

    try:
        yield
        conn.execute(f"RELEASE SAVEPOINT {safe_name}")

    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
        conn.execute(f"RELEASE SAVEPOINT {safe_name}")
        raise


def obtener_stock_disponible(conn, inventario_id: int) -> float:
    """
    Obtiene el stock disponible de un producto activo.
    Funciona con esquemas legado (`cantidad`) y nuevo (`stock_actual`).
    """

    columns = _table_columns(conn, "inventario")

    stock_expr = "cantidad" if "cantidad" in columns else "stock_actual"

    conditions = ["id = ?"]
    if "activo" in columns:
        conditions.append("COALESCE(activo, 1) = 1")
    if "estado" in columns:
        conditions.append("COALESCE(estado, 'activo') <> 'inactivo'")

    query = f"""
        SELECT COALESCE({stock_expr}, 0)
        FROM inventario
        WHERE {' AND '.join(conditions)}
    """

    row = conn.execute(query, (inventario_id,)).fetchone()
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
