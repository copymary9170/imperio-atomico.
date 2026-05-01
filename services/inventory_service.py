from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InventoryMovement:
    item_id: int
    tipo: str
    cantidad: float
    costo_unitario: float
    motivo: str
    usuario: str


class InventoryService:
    """
    Motor central de inventario compatible con schema actual.

    Usa:
    - inventario.stock_actual
    - inventario.costo_unitario_usd
    - movimientos_inventario
    """

    TIPOS_ENTRADA = {"ENTRADA", "COMPRA", "AJUSTE_ENTRADA"}
    TIPOS_SALIDA = {"SALIDA", "VENTA", "MERMA", "AJUSTE_SALIDA"}

    def procesar_movimiento(self, conn: Any, movement: InventoryMovement) -> tuple[bool, str]:
        try:
            item_id = int(movement.item_id)
            tipo = str(movement.tipo or "").upper().strip()
            cantidad = float(movement.cantidad or 0)
            costo_mov = float(movement.costo_unitario or 0)
            motivo = str(movement.motivo or "").strip()
            usuario = str(movement.usuario or "Sistema").strip()

            if cantidad <= 0:
                return False, "La cantidad debe ser mayor a cero"

            if tipo not in self.TIPOS_ENTRADA and tipo not in self.TIPOS_SALIDA:
                return False, f"Tipo de movimiento inválido: {tipo}"

            row = conn.execute(
                """
                SELECT id, nombre, stock_actual, costo_unitario_usd
                FROM inventario
                WHERE id = ?
                  AND COALESCE(estado, 'activo') = 'activo'
                """,
                (item_id,),
            ).fetchone()

            if not row:
                return False, "Producto no encontrado o inactivo"

            stock_anterior = float(row["stock_actual"] or 0)
            costo_actual = float(row["costo_unitario_usd"] or 0)

            if tipo in self.TIPOS_ENTRADA:
                nuevo_stock = stock_anterior + cantidad

                if costo_mov > 0:
                    nuevo_costo = self._costo_promedio(
                        stock_actual=stock_anterior,
                        costo_actual=costo_actual,
                        cantidad_entrada=cantidad,
                        costo_entrada=costo_mov,
                    )
                else:
                    nuevo_costo = costo_actual

                cantidad_registro = abs(cantidad)
                tipo_registro = "entrada"

            else:
                if cantidad > stock_anterior:
                    return False, f"Stock insuficiente para {row['nombre']}"

                nuevo_stock = stock_anterior - cantidad
                nuevo_costo = costo_actual
                cantidad_registro = -abs(cantidad)
                tipo_registro = "salida"

            conn.execute(
                """
                UPDATE inventario
                SET stock_actual = ?,
                    costo_unitario_usd = ?
                WHERE id = ?
                """,
                (
                    round(float(nuevo_stock), 6),
                    round(float(nuevo_costo), 6),
                    item_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO movimientos_inventario
                (
                    usuario,
                    inventario_id,
                    tipo,
                    cantidad,
                    costo_unitario_usd,
                    referencia
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    item_id,
                    tipo_registro,
                    round(float(cantidad_registro), 6),
                    round(float(costo_mov if costo_mov > 0 else nuevo_costo), 6),
                    motivo or tipo,
                ),
            )

            return True, "Movimiento procesado correctamente"

        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _costo_promedio(
        *,
        stock_actual: float,
        costo_actual: float,
        cantidad_entrada: float,
        costo_entrada: float,
    ) -> float:
        nuevo_stock = float(stock_actual) + float(cantidad_entrada)
        if nuevo_stock <= 0:
            return float(costo_entrada)

        valor_actual = float(stock_actual) * float(costo_actual)
        valor_entrada = float(cantidad_entrada) * float(costo_entrada)

        return (valor_actual + valor_entrada) / nuevo_stock
