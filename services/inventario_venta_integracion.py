from __future__ import annotations

from typing import Any

from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_operativo_service import ensure_schema


def _receta_producto(conn: Any, producto_id: int):
    ensure_schema()
    return conn.execute(
        "SELECT * FROM recetas_inventario WHERE producto_inventario_id=? AND activo=1 ORDER BY id DESC LIMIT 1",
        (int(producto_id),),
    ).fetchone()


def _receta_por_codigo(conn: Any, codigo: str):
    ensure_schema()
    return conn.execute(
        """
        SELECT r.* FROM recetas_inventario r
        JOIN inventario i ON i.id=r.producto_inventario_id
        WHERE lower(i.sku)=lower(?) AND r.activo=1
        ORDER BY r.id DESC LIMIT 1
        """,
        (str(codigo or "").strip(),),
    ).fetchone()


def _requerimientos(conn: Any, receta_id: int, cantidad_producto: float) -> list[tuple[Any, float]]:
    receta = conn.execute("SELECT rendimiento FROM recetas_inventario WHERE id=?", (int(receta_id),)).fetchone()
    if not receta:
        return []
    factor = float(cantidad_producto) / float(receta["rendimiento"] or 1)
    rows = conn.execute(
        """
        SELECT d.*, i.nombre, COALESCE(i.stock_actual,0) stock,
               COALESCE(i.costo_unitario_usd,0) costo,
               COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r
                         WHERE r.inventario_id=i.id AND r.estado='activa'),0) reservado
        FROM recetas_inventario_detalle d
        JOIN inventario i ON i.id=d.insumo_id
        WHERE d.receta_id=?
        """,
        (int(receta_id),),
    ).fetchall()
    result=[]
    for row in rows:
        qty=float(row["cantidad"] or 0)*factor*(1+float(row["merma_pct"] or 0)/100)
        if qty>0: result.append((row,qty))
    return result


def validar_receta_producto(conn: Any, producto_id: int, cantidad: float) -> bool:
    receta=_receta_producto(conn,producto_id)
    if not receta: return False
    reqs=_requerimientos(conn,int(receta["id"]),cantidad)
    if not reqs: raise ValueError(f"La receta '{receta['nombre']}' no tiene materiales.")
    for row,qty in reqs:
        disponible=float(row["stock"] or 0)-float(row["reservado"] or 0)
        if qty>disponible:
            raise ValueError(f"Stock insuficiente de {row['nombre']}. Requerido {qty:.2f}; disponible {disponible:.2f}.")
    return True


def consumir_receta_producto(conn: Any, *, producto_id: int, cantidad: float, usuario: str, referencia: str) -> bool:
    receta=_receta_producto(conn,producto_id)
    if not receta: return False
    validar_receta_producto(conn,producto_id,cantidad)
    service=InventoryService()
    for row,qty in _requerimientos(conn,int(receta["id"]),cantidad):
        ok,msg=service.procesar_movimiento(conn,InventoryMovement(
            item_id=int(row["insumo_id"]),tipo="SALIDA",cantidad=qty,
            costo_unitario=float(row["costo"] or 0),motivo=f"Consumo receta {referencia}",usuario=usuario,
        ))
        if not ok: raise ValueError(msg)
    return True


def consumir_receta_codigo(conn: Any, *, codigo: str, cantidad: float, usuario: str, referencia: str) -> bool:
    receta=_receta_por_codigo(conn,codigo)
    if not receta: return False
    producto_id=int(receta["producto_inventario_id"])
    return consumir_receta_producto(conn,producto_id=producto_id,cantidad=cantidad,usuario=usuario,referencia=referencia)


def reservar_receta_producto(conn: Any, *, producto_id: int, cantidad: float, referencia: str, usuario: str) -> int:
    receta=_receta_producto(conn,producto_id)
    if not receta: raise ValueError("El producto no tiene receta operativa.")
    validar_receta_producto(conn,producto_id,cantidad)
    creadas=0
    for row,qty in _requerimientos(conn,int(receta["id"]),cantidad):
        conn.execute(
            "INSERT INTO reservas_inventario(inventario_id,cantidad,referencia,usuario) VALUES(?,?,?,?)",
            (int(row["insumo_id"]),qty,referencia,usuario),
        )
        creadas+=1
    return creadas


def cerrar_reservas_referencia(conn: Any, referencia: str) -> int:
    if not str(referencia or "").strip(): return 0
    cur=conn.execute(
        "UPDATE reservas_inventario SET estado='consumida', liberada_at=CURRENT_TIMESTAMP WHERE referencia=? AND estado='activa'",
        (str(referencia).strip(),),
    )
    return int(cur.rowcount or 0)
