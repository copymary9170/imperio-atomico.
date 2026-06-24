from __future__ import annotations

from typing import Any
import pandas as pd

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService

TIPOS_MOVIMIENTO = ["COMPRA", "ENTRADA", "SALIDA", "VENTA", "MERMA", "AJUSTE_ENTRADA", "AJUSTE_SALIDA"]


def ensure_schema() -> None:
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recetas_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                producto_inventario_id INTEGER,
                rendimiento REAL NOT NULL DEFAULT 1,
                unidad_rendimiento TEXT NOT NULL DEFAULT 'unidad',
                activo INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(producto_inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recetas_inventario_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receta_id INTEGER NOT NULL,
                insumo_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                merma_pct REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(receta_id) REFERENCES recetas_inventario(id),
                FOREIGN KEY(insumo_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservas_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                referencia TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activa',
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                liberada_at TEXT,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mermas_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                motivo TEXT NOT NULL,
                referencia TEXT,
                costo_perdido_usd REAL NOT NULL DEFAULT 0,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conteos_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                stock_sistema REAL NOT NULL,
                stock_fisico REAL NOT NULL,
                diferencia REAL NOT NULL,
                motivo TEXT,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reservas_item_estado ON reservas_inventario(inventario_id, estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_receta_detalle_receta ON recetas_inventario_detalle(receta_id)")


def listar_articulos() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT i.id, i.sku, i.nombre, COALESCE(i.unidad_base,i.unidad,'unidad') unidad,
                   COALESCE(i.stock_actual,0) stock_fisico,
                   COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id=i.id AND r.estado='activa'),0) stock_reservado,
                   COALESCE(i.stock_actual,0)-COALESCE((SELECT SUM(r.cantidad) FROM reservas_inventario r WHERE r.inventario_id=i.id AND r.estado='activa'),0) stock_disponible,
                   COALESCE(i.costo_unitario_usd,0) costo_unitario_usd
            FROM inventario i WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY i.nombre COLLATE NOCASE
        """, conn)


def registrar_movimiento(*, inventario_id: int, tipo: str, cantidad: float, costo_unitario: float, motivo: str, usuario: str) -> int | None:
    ensure_schema()
    tipo = str(tipo).upper().strip()
    if tipo not in TIPOS_MOVIMIENTO:
        raise ValueError("Tipo de movimiento inválido.")
    if tipo in {"AJUSTE_ENTRADA", "AJUSTE_SALIDA"}:
        from services.inventario_gobernanza_service import solicitar_ajuste
        return solicitar_ajuste(
            inventario_id=int(inventario_id), tipo=tipo, cantidad=float(cantidad),
            motivo=str(motivo or tipo), usuario=usuario,
        )
    with db_transaction() as conn:
        ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(inventario_id), tipo=tipo, cantidad=float(cantidad),
            costo_unitario=float(costo_unitario or 0), motivo=str(motivo or tipo), usuario=usuario,
        ))
        if not ok:
            raise ValueError(msg)
    return None


def reservar(*, inventario_id: int, cantidad: float, referencia: str, usuario: str) -> int:
    ensure_schema()
    if cantidad <= 0 or not str(referencia).strip():
        raise ValueError("Cantidad y referencia son obligatorias.")
    with db_transaction() as conn:
        row = conn.execute("""
            SELECT COALESCE(i.stock_actual,0)-COALESCE((SELECT SUM(cantidad) FROM reservas_inventario WHERE inventario_id=i.id AND estado='activa'),0) disponible
            FROM inventario i WHERE i.id=?
        """, (int(inventario_id),)).fetchone()
        if not row or float(row["disponible"] or 0) < float(cantidad):
            raise ValueError("Stock disponible insuficiente para reservar.")
        cur = conn.execute("INSERT INTO reservas_inventario(inventario_id,cantidad,referencia,usuario) VALUES(?,?,?,?)",
                           (int(inventario_id), float(cantidad), referencia.strip(), usuario))
        return int(cur.lastrowid)


def liberar_reserva(reserva_id: int) -> None:
    ensure_schema()
    with db_transaction() as conn:
        conn.execute("UPDATE reservas_inventario SET estado='liberada', liberada_at=CURRENT_TIMESTAMP WHERE id=? AND estado='activa'", (int(reserva_id),))


def consumir_reserva(reserva_id: int, usuario: str) -> None:
    ensure_schema()
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM reservas_inventario WHERE id=? AND estado='activa'", (int(reserva_id),)).fetchone()
        if not row:
            raise ValueError("Reserva no encontrada o ya cerrada.")
        ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(row["inventario_id"]), tipo="SALIDA", cantidad=float(row["cantidad"]), costo_unitario=0,
            motivo=f"Consumo de reserva: {row['referencia']}", usuario=usuario,
        ))
        if not ok:
            raise ValueError(msg)
        conn.execute("UPDATE reservas_inventario SET estado='consumida', liberada_at=CURRENT_TIMESTAMP WHERE id=?", (int(reserva_id),))


def registrar_merma(*, inventario_id: int, cantidad: float, motivo: str, referencia: str, usuario: str) -> None:
    ensure_schema()
    with db_transaction() as conn:
        item = conn.execute("SELECT costo_unitario_usd FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        if not item:
            raise ValueError("Artículo no encontrado.")
        costo = float(item["costo_unitario_usd"] or 0)
        ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(inventario_id), tipo="MERMA", cantidad=float(cantidad), costo_unitario=costo,
            motivo=f"Merma: {motivo}. {referencia}".strip(), usuario=usuario,
        ))
        if not ok:
            raise ValueError(msg)
        conn.execute("INSERT INTO mermas_inventario(inventario_id,cantidad,motivo,referencia,costo_perdido_usd,usuario) VALUES(?,?,?,?,?,?)",
                     (int(inventario_id), float(cantidad), motivo.strip(), referencia.strip(), round(float(cantidad)*costo,6), usuario))


def registrar_conteo(*, inventario_id: int, stock_fisico: float, motivo: str, usuario: str) -> float:
    ensure_schema()
    with db_transaction() as conn:
        row = conn.execute("SELECT stock_actual,costo_unitario_usd FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        if not row:
            raise ValueError("Artículo no encontrado.")
        sistema = float(row["stock_actual"] or 0)
    diferencia = float(stock_fisico)-sistema
    with db_transaction() as conn:
        conn.execute("INSERT INTO conteos_inventario(inventario_id,stock_sistema,stock_fisico,diferencia,motivo,usuario) VALUES(?,?,?,?,?,?)",
                     (int(inventario_id), sistema, float(stock_fisico), diferencia, motivo.strip(), usuario))
    if diferencia:
        from services.inventario_gobernanza_service import solicitar_ajuste
        solicitar_ajuste(
            inventario_id=int(inventario_id),
            tipo="AJUSTE_ENTRADA" if diferencia > 0 else "AJUSTE_SALIDA",
            cantidad=abs(diferencia), motivo=f"Conteo físico: {motivo}",
            usuario=usuario, stock_fisico=float(stock_fisico),
        )
    return diferencia


def crear_receta(*, nombre: str, producto_id: int | None, rendimiento: float, unidad: str, observaciones: str, usuario: str) -> int:
    ensure_schema()
    if not nombre.strip() or rendimiento <= 0:
        raise ValueError("Nombre y rendimiento válido son obligatorios.")
    with db_transaction() as conn:
        cur = conn.execute("INSERT INTO recetas_inventario(nombre,producto_inventario_id,rendimiento,unidad_rendimiento,observaciones) VALUES(?,?,?,?,?)",
                           (nombre.strip(), int(producto_id) if producto_id else None, float(rendimiento), unidad.strip() or "unidad", observaciones.strip()))
        return int(cur.lastrowid)


def agregar_insumo_receta(*, receta_id: int, insumo_id: int, cantidad: float, merma_pct: float) -> None:
    ensure_schema()
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    with db_transaction() as conn:
        conn.execute("INSERT INTO recetas_inventario_detalle(receta_id,insumo_id,cantidad,merma_pct) VALUES(?,?,?,?)",
                     (int(receta_id), int(insumo_id), float(cantidad), float(merma_pct or 0)))


def producir(*, receta_id: int, cantidad_producir: float, usuario: str, referencia: str) -> None:
    ensure_schema()
    if cantidad_producir <= 0:
        raise ValueError("Cantidad inválida.")
    with db_transaction() as conn:
        receta = conn.execute("SELECT * FROM recetas_inventario WHERE id=? AND activo=1", (int(receta_id),)).fetchone()
        if not receta:
            raise ValueError("Receta no encontrada.")
        factor = float(cantidad_producir) / float(receta["rendimiento"] or 1)
        detalles = conn.execute("""
            SELECT d.*, i.nombre, COALESCE(i.stock_actual,0) stock, COALESCE(i.costo_unitario_usd,0) costo
            FROM recetas_inventario_detalle d JOIN inventario i ON i.id=d.insumo_id WHERE d.receta_id=?
        """, (int(receta_id),)).fetchall()
        if not detalles:
            raise ValueError("La receta no tiene insumos.")
        requeridos=[]
        for d in detalles:
            qty=float(d["cantidad"])*factor*(1+float(d["merma_pct"] or 0)/100)
            if qty>float(d["stock"] or 0): raise ValueError(f"Stock insuficiente de {d['nombre']}.")
            requeridos.append((d,qty))
        costo_total=0.0
        for d,qty in requeridos:
            ok,msg=InventoryService().procesar_movimiento(conn,InventoryMovement(item_id=int(d["insumo_id"]),tipo="SALIDA",cantidad=qty,costo_unitario=float(d["costo"] or 0),motivo=f"Producción {referencia or receta['nombre']}",usuario=usuario))
            if not ok: raise ValueError(msg)
            costo_total += qty*float(d["costo"] or 0)
        if receta["producto_inventario_id"]:
            costo_unitario=costo_total/float(cantidad_producir)
            ok,msg=InventoryService().procesar_movimiento(conn,InventoryMovement(item_id=int(receta["producto_inventario_id"]),tipo="ENTRADA",cantidad=float(cantidad_producir),costo_unitario=costo_unitario,motivo=f"Producción {referencia or receta['nombre']}",usuario=usuario))
            if not ok: raise ValueError(msg)


def listar_reservas() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT r.id,i.nombre,r.cantidad,r.referencia,r.estado,r.created_at FROM reservas_inventario r JOIN inventario i ON i.id=r.inventario_id ORDER BY r.id DESC",conn)


def listar_recetas() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT r.id,r.nombre,r.rendimiento,r.unidad_rendimiento,COALESCE(i.nombre,'Servicio') producto FROM recetas_inventario r LEFT JOIN inventario i ON i.id=r.producto_inventario_id WHERE r.activo=1 ORDER BY r.nombre",conn)


def listar_mermas() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT m.id,i.nombre,m.cantidad,m.motivo,m.referencia,m.costo_perdido_usd,m.created_at FROM mermas_inventario m JOIN inventario i ON i.id=m.inventario_id ORDER BY m.id DESC",conn)
