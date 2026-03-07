from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from utils.helpers import validar_stock_para_salida


@dataclass(frozen=True)
class VentaItem:
    inventario_id: int
    descripcion: str
    cantidad: float
    precio_unitario_usd: float
    costo_unitario_usd: float


class VentasService:
    """Servicio transaccional para registrar ventas sin romper integridad de inventario."""

    def __init__(self, inventory_service: InventoryService):
        self.inventory_service = inventory_service

    def registrar_venta_atomica(
        self,
        usuario: str,
        cliente_id: int | None,
        metodo_pago: str,
        moneda: str,
        tasa_cambio: float,
        items: Sequence[VentaItem],
        impuesto_usd: float = 0.0,
    ) -> int:
        if not items:
            raise ValueError("La venta debe tener al menos un item")

        subtotal = round(sum(float(i.cantidad) * float(i.precio_unitario_usd) for i in items), 2)
        total = round(subtotal + float(impuesto_usd), 2)
        total_bs = round(total * float(tasa_cambio), 2)

        with db_transaction() as conn:
            for item in items:
                validar_stock_para_salida(conn, item.inventario_id, float(item.cantidad))

            cur = conn.execute(
                """
                INSERT INTO ventas (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal_usd, impuesto_usd, total_usd, total_bs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal, impuesto_usd, total, total_bs),
            )
            venta_id = int(cur.lastrowid)

            for item in items:
                conn.execute(
                    """
                    INSERT INTO ventas_detalle
                    (usuario, venta_id, inventario_id, descripcion, cantidad, precio_unitario_usd, costo_unitario_usd, subtotal_usd)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usuario,
                        venta_id,
                        item.inventario_id,
                        item.descripcion,
                        item.cantidad,
                        item.precio_unitario_usd,
                        item.costo_unitario_usd,
                        round(float(item.cantidad) * float(item.precio_unitario_usd), 2),
                    ),
                )
                ok, msg = self.inventory_service.procesar_movimiento(
                    conn,
                    InventoryMovement(
                        item_id=item.inventario_id,
                        tipo="VENTA",
                        cantidad=float(item.cantidad),
                        costo_unitario=float(item.costo_unitario_usd),
                        motivo=f"Venta #{venta_id}",
                        usuario=usuario,
                    ),
                )
                if not ok:
                    raise ValueError(msg)

            if metodo_pago.lower() == "credito" and cliente_id:
                conn.execute(
                    """
                    INSERT INTO cuentas_por_cobrar (usuario, cliente_id, venta_id, saldo_usd, estado)
                    VALUES (?, ?, ?, ?, 'pendiente')
                    """,
                    (usuario, cliente_id, venta_id, total),
                )

        return venta_id
