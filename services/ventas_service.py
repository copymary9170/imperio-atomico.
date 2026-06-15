from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from services.recetas_consumo_service import consumir_receta_por_venta, validar_stock_receta
from services.tesoreria_service import registrar_ingreso
from services.contabilidad_service import contabilizar_venta
from utils.helpers import validar_stock_para_salida


@dataclass(frozen=True)
class VentaItem:
    inventario_id: int
    descripcion: str
    cantidad: float
    precio_unitario_usd: float
    costo_unitario_usd: float


def _es_servicio(conn: Any, inventario_id: int) -> bool:
    row = conn.execute(
        """
        SELECT COALESCE(tipo_item, 'producto_venta') AS tipo_item
        FROM inventario
        WHERE id = ?
        """,
        (int(inventario_id),),
    ).fetchone()
    tipo_item = str(row["tipo_item"] if row else "producto_venta").strip().lower()
    return tipo_item == "servicio"


class VentasService:
    """Servicio transaccional para registrar ventas COMPLETAS (inventario + tesorería + contabilidad)."""

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

        metodo_pago = str(metodo_pago or "").lower().strip()

        subtotal = round(sum(float(i.cantidad) * float(i.precio_unitario_usd) for i in items), 2)
        total = round(subtotal + float(impuesto_usd), 2)
        total_bs = round(total * float(tasa_cambio), 2)

        if total <= 0:
            raise ValueError("El total de la venta debe ser mayor a cero")

        with db_transaction() as conn:

            # 1. VALIDAR STOCK DEL PRODUCTO VENDIDO Y DE SUS INSUMOS DE RECETA
            for item in items:
                if not _es_servicio(conn, item.inventario_id):
                    validar_stock_para_salida(conn, item.inventario_id, float(item.cantidad))
                validar_stock_receta(conn, item.inventario_id, float(item.cantidad))

            # 2. CREAR VENTA
            cur = conn.execute(
                """
                INSERT INTO ventas
                (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal_usd, impuesto_usd, total_usd, total_bs, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'registrado')
                """,
                (
                    usuario,
                    cliente_id,
                    moneda,
                    tasa_cambio,
                    metodo_pago,
                    subtotal,
                    impuesto_usd,
                    total,
                    total_bs,
                ),
            )

            venta_id = int(cur.lastrowid)

            # 3. DETALLE + INVENTARIO + CONSUMO DE RECETAS
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

                if not _es_servicio(conn, item.inventario_id):
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

                consumir_receta_por_venta(
                    conn,
                    inventory_service=self.inventory_service,
                    usuario=usuario,
                    venta_id=venta_id,
                    producto_id=item.inventario_id,
                    cantidad_producto=float(item.cantidad),
                )

            # 4. TESORERÍA
            if metodo_pago != "credito":
                registrar_ingreso(
                    conn,
                    origen="venta",
                    referencia_id=venta_id,
                    descripcion=f"Venta #{venta_id}",
                    monto_usd=total,
                    moneda=moneda,
                    monto_moneda=total if moneda == "USD" else total_bs,
                    tasa_cambio=tasa_cambio,
                    metodo_pago=metodo_pago,
                    usuario=usuario,
                )

            # 5. CUENTAS POR COBRAR
            else:
                if not cliente_id:
                    raise ValueError("Venta a crédito requiere cliente")

                conn.execute(
                    """
                    INSERT INTO cuentas_por_cobrar
                    (usuario, cliente_id, venta_id, tipo_documento, monto_original_usd, monto_cobrado_usd, saldo_usd, estado, dias_vencimiento)
                    VALUES (?, ?, ?, 'venta', ?, 0, ?, 'pendiente', 30)
                    """,
                    (
                        usuario,
                        cliente_id,
                        venta_id,
                        total,
                        total,
                    ),
                )

            # 6. CONTABILIDAD
            contabilizar_venta(conn, venta_id=venta_id, usuario=usuario)

        return venta_id
