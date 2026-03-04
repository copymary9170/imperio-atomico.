from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class InventoryMovement:
    item_id: int
    tipo: str
    cantidad: float
    costo_unitario: float
    motivo: str
    usuario: str


class InventoryService:
    def __init__(self, money_fn, audit_fn):
        self.money = money_fn
        self.audit = audit_fn

    def registrar_kardex(
        self,
        conn,
        item_id: int,
        item: str,
        tipo: str,
        cantidad: float,
        stock_anterior: float,
        stock_nuevo: float,
        costo_unit: float,
        usuario: str,
    ) -> bool:
        cantidad = float(cantidad or 0.0)
        costo_unit = float(costo_unit or 0.0)
        costo_total = float(self.money(cantidad * costo_unit))
        conn.execute(
            """
            INSERT INTO kardex
            (item_id, item, tipo, cantidad, stock_anterior, stock_nuevo, costo_unit, costo_total, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(item_id),
                str(item),
                str(tipo),
                cantidad,
                float(stock_anterior or 0.0),
                float(stock_nuevo or 0.0),
                costo_unit,
                costo_total,
                str(usuario or "Sistema"),
            ),
        )
        return True

    def procesar_movimiento(self, conn, movement: InventoryMovement) -> Tuple[bool, str]:
        try:
            item_id = int(movement.item_id)
            tipo_txt = str(movement.tipo or "").upper().strip()
            cantidad = float(movement.cantidad or 0.0)
            costo_unitario = float(movement.costo_unitario or 0.0)
            motivo_txt = str(movement.motivo or "")
            usuario_txt = str(movement.usuario or "Sistema")
        except (TypeError, ValueError):
            return False, "Parámetros inválidos para procesar movimiento"

        if tipo_txt not in {"ENTRADA", "SALIDA", "AJUSTE", "COMPRA", "MERMA", "VENTA"}:
            return False, "Tipo de movimiento no válido"
        if tipo_txt in {"ENTRADA", "SALIDA", "COMPRA", "MERMA", "VENTA"} and cantidad <= 0:
            return False, "La cantidad debe ser mayor a 0"
        if tipo_txt == "AJUSTE" and cantidad == 0:
            return False, "El ajuste no puede ser 0"

        inicio_explicito = False
        savepoint_name: Optional[str] = None
        try:
            if conn.in_transaction:
                savepoint_name = f"sp_inv_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
                conn.execute(f"SAVEPOINT {savepoint_name}")
            else:
                conn.execute("BEGIN IMMEDIATE")
                inicio_explicito = True

            row = conn.execute(
                """
                SELECT item, COALESCE(cantidad,0), COALESCE(costo_promedio,COALESCE(precio_usd,0)),
                       COALESCE(valor_total, COALESCE(cantidad,0)*COALESCE(costo_promedio,COALESCE(precio_usd,0)))
                FROM inventario
                WHERE id=? AND COALESCE(activo,1)=1
                """,
                (item_id,),
            ).fetchone()
            if not row:
                raise ValueError("Ítem no encontrado o inactivo")

            item_nombre = str(row[0])
            saldo_antes = float(row[1] or 0.0)
            costo_prom_actual = float(row[2] or 0.0)
            valor_total_actual = float(row[3] or 0.0)

            tipo_registro = tipo_txt
            base_tipo = "ENTRADA" if tipo_txt == "COMPRA" else "SALIDA" if tipo_txt in {"MERMA", "VENTA"} else tipo_txt

            if base_tipo == "ENTRADA":
                valor_nuevo = float(cantidad) * float(costo_unitario)
                saldo_despues = saldo_antes + float(cantidad)
                valor_total_nuevo = valor_total_actual + valor_nuevo
                costo_prom_nuevo = (valor_total_nuevo / saldo_despues) if saldo_despues > 0 else 0.0
                costo_unit_mov = float(costo_unitario)
                costo_total_mov = valor_nuevo
            elif base_tipo == "SALIDA":
                if float(cantidad) > saldo_antes:
                    raise ValueError("Stock insuficiente para salida")
                saldo_despues = saldo_antes - float(cantidad)
                costo_unit_mov = float(costo_prom_actual)
                costo_total_mov = float(cantidad) * costo_unit_mov
                valor_total_nuevo = max(0.0, valor_total_actual - costo_total_mov)
                costo_prom_nuevo = (valor_total_nuevo / saldo_despues) if saldo_despues > 0 else 0.0
            else:
                es_resta = float(cantidad) < 0 or any(k in motivo_txt.lower() for k in ["rest", "salida", "rebaja"])
                delta = abs(float(cantidad))
                if es_resta:
                    if delta > saldo_antes:
                        raise ValueError("Stock insuficiente para ajuste negativo")
                    saldo_despues = saldo_antes - delta
                    costo_unit_mov = float(costo_prom_actual)
                    costo_total_mov = delta * costo_unit_mov
                    valor_total_nuevo = max(0.0, valor_total_actual - costo_total_mov)
                    cantidad = delta
                else:
                    costo_base_ajuste = float(costo_unitario) if float(costo_unitario) > 0 else float(costo_prom_actual)
                    saldo_despues = saldo_antes + delta
                    costo_unit_mov = costo_base_ajuste
                    costo_total_mov = delta * costo_unit_mov
                    valor_total_nuevo = valor_total_actual + costo_total_mov
                    cantidad = delta
                costo_prom_nuevo = (valor_total_nuevo / saldo_despues) if saldo_despues > 0 else 0.0

            if saldo_despues < 0:
                raise ValueError("Stock negativo no permitido")

            conn.execute(
                """
                UPDATE inventario
                SET cantidad=?, costo_promedio=?, valor_total=?, precio_usd=?, ultima_actualizacion=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (float(saldo_despues), float(costo_prom_nuevo), float(valor_total_nuevo), float(costo_prom_nuevo), int(item_id)),
            )

            conn.execute(
                """
                INSERT INTO inventario_movs
                (item_id, tipo, cantidad, saldo_antes, saldo_despues, costo_unitario, costo_total, motivo, usuario)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(item_id),
                    str(tipo_registro),
                    float(cantidad),
                    float(saldo_antes),
                    float(saldo_despues),
                    float(costo_unit_mov),
                    float(costo_total_mov),
                    motivo_txt,
                    usuario_txt,
                ),
            )

            self.audit(
                conn,
                accion=f"MOV_INVENTARIO_{tipo_registro}",
                valor_anterior=f"item={item_nombre}; saldo={saldo_antes:.6f}; costo_prom={costo_prom_actual:.6f}",
                valor_nuevo=f"item={item_nombre}; saldo={saldo_despues:.6f}; costo_prom={costo_prom_nuevo:.6f}; motivo={motivo_txt}",
                usuario=usuario_txt,
            )

            self.registrar_kardex(
                conn=conn,
                item_id=int(item_id),
                item=item_nombre,
                tipo=str(tipo_registro),
                cantidad=float(cantidad),
                stock_anterior=float(saldo_antes),
                stock_nuevo=float(saldo_despues),
                costo_unit=float(costo_unit_mov),
                usuario=usuario_txt,
            )

            if savepoint_name:
                conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            elif inicio_explicito:
                conn.commit()
            return True, "Movimiento procesado correctamente"

        except Exception as e:  # noqa: BLE001
            try:
                if savepoint_name:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                elif inicio_explicito:
                    conn.rollback()
            except Exception:
                pass
            return False, str(e)
