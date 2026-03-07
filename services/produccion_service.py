from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from utils.helpers import validar_stock_para_salida


@dataclass(frozen=True)
class ConsumoInsumo:
    inventario_id: int
    cantidad: float
    costo_unitario: float


class ProduccionService:
    def __init__(self, inventory_service: InventoryService):
        self.inventory_service = inventory_service

    def registrar_orden(
        self,
        usuario: str,
        tipo_produccion: str,
        referencia: str,
        costo_estimado: float,
        insumos: Sequence[ConsumoInsumo],
    ) -> int:
        with db_transaction() as conn:
            for insumo in insumos:
                validar_stock_para_salida(conn, insumo.inventario_id, insumo.cantidad)

            cur = conn.execute(
                """
                INSERT INTO ordenes_produccion (usuario, tipo, referencia, costo_estimado, estado)
                VALUES (?, ?, ?, ?, 'Pendiente')
                """,
                (usuario, tipo_produccion, referencia, float(costo_estimado)),
            )
            orden_id = int(cur.lastrowid)

            for insumo in insumos:
                ok, msg = self.inventory_service.procesar_movimiento(
                    conn,
                    InventoryMovement(
                        item_id=insumo.inventario_id,
                        tipo="SALIDA",
                        cantidad=insumo.cantidad,
                        costo_unitario=insumo.costo_unitario,
                        motivo=f"Producción #{orden_id} ({tipo_produccion})",
                        usuario=usuario,
                    ),
                )
                if not ok:
                    raise ValueError(msg)

            conn.execute(
                "INSERT INTO produccion_auditoria (usuario, modulo, accion, detalle) VALUES (?, 'produccion', 'crear_orden', ?)",
                (usuario, f"Orden #{orden_id} tipo={tipo_produccion} referencia={referencia}"),
            )

        return orden_id
