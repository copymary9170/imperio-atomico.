from __future__ import annotations

from typing import Any

from services.inventory_service import InventoryMovement, InventoryService


def obtener_consumos_receta(conn: Any, producto_id: int, cantidad_producto: float) -> list[dict[str, float | int | str]]:
    """Devuelve los insumos requeridos por una receta para una cantidad vendida."""
    rows = conn.execute(
        """
        SELECT
            r.insumo_id,
            r.cantidad_insumo,
            COALESCE(r.merma_pct, 0) AS merma_pct,
            COALESCE(i.costo_unitario_usd, 0) AS costo_unitario_usd,
            COALESCE(i.nombre, '') AS insumo_nombre
        FROM recetas_consumo r
        JOIN inventario i ON i.id = r.insumo_id
        WHERE r.producto_id = ?
          AND COALESCE(r.activo, 1) = 1
        """,
        (int(producto_id),),
    ).fetchall()

    consumos: list[dict[str, float | int | str]] = []
    for row in rows:
        cantidad_base = float(row["cantidad_insumo"] or 0) * float(cantidad_producto or 0)
        merma_pct = float(row["merma_pct"] or 0)
        cantidad_total = cantidad_base * (1 + (merma_pct / 100))
        if cantidad_total <= 0:
            continue
        consumos.append(
            {
                "insumo_id": int(row["insumo_id"]),
                "cantidad": round(float(cantidad_total), 6),
                "costo_unitario_usd": float(row["costo_unitario_usd"] or 0),
                "insumo_nombre": str(row["insumo_nombre"] or ""),
            }
        )
    return consumos


def validar_stock_receta(conn: Any, producto_id: int, cantidad_producto: float) -> None:
    """Valida que existan insumos suficientes para consumir una receta."""
    consumos = obtener_consumos_receta(conn, producto_id, cantidad_producto)
    for consumo in consumos:
        row = conn.execute(
            """
            SELECT nombre, COALESCE(stock_actual, 0) AS stock_actual
            FROM inventario
            WHERE id = ?
              AND COALESCE(estado, 'activo') = 'activo'
            """,
            (int(consumo["insumo_id"]),),
        ).fetchone()
        if not row:
            raise ValueError(f"Insumo de receta no encontrado: {consumo['insumo_id']}")
        stock_actual = float(row["stock_actual"] or 0)
        requerido = float(consumo["cantidad"] or 0)
        if requerido > stock_actual:
            raise ValueError(
                f"Stock insuficiente para insumo de receta: {row['nombre']}. "
                f"Requerido: {requerido:.2f}, disponible: {stock_actual:.2f}"
            )


def consumir_receta_por_venta(
    conn: Any,
    *,
    inventory_service: InventoryService,
    usuario: str,
    venta_id: int,
    producto_id: int,
    cantidad_producto: float,
) -> int:
    """Descuenta insumos de una receta y registra salidas en Kardex."""
    consumos = obtener_consumos_receta(conn, producto_id, cantidad_producto)
    movimientos = 0
    for consumo in consumos:
        ok, msg = inventory_service.procesar_movimiento(
            conn,
            InventoryMovement(
                item_id=int(consumo["insumo_id"]),
                tipo="MERMA",
                cantidad=float(consumo["cantidad"]),
                costo_unitario=float(consumo["costo_unitario_usd"]),
                motivo=f"Consumo receta por venta #{venta_id}",
                usuario=usuario,
            ),
        )
        if not ok:
            raise ValueError(msg)
        movimientos += 1
    return movimientos
