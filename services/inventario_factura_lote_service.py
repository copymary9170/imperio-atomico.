from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventario_tipo_panaderia_service import ensure_schema, registrar_lote


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_factura_lote_schema() -> None:
    ensure_schema()
    with db_transaction() as conn:
        cols = _columns(conn, "inventario_lotes")
        migrations = {
            "factura_compra_id": "INTEGER",
            "numero_factura": "TEXT",
            "stock_contabilizado_por_factura": "INTEGER NOT NULL DEFAULT 0",
        }
        for campo, ddl in migrations.items():
            if campo not in cols:
                conn.execute(f"ALTER TABLE inventario_lotes ADD COLUMN {campo} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_factura ON inventario_lotes(factura_compra_id)")


def registrar_lote_con_factura(
    inventario_id: int,
    *,
    factura_id: int | None,
    codigo_lote: str,
    cantidad: float,
    costo_unitario_usd: float,
    fecha_entrada: str,
    fecha_vencimiento: str | None,
    proveedor: str,
    ubicacion: str,
    observaciones: str,
    usuario: str,
    stock_ya_contabilizado: bool,
) -> int:
    ensure_factura_lote_schema()
    codigo = str(codigo_lote or "").strip()
    if not codigo or cantidad <= 0:
        raise ValueError("Código de lote y cantidad son obligatorios.")

    if not factura_id:
        return registrar_lote(
            inventario_id,
            codigo_lote=codigo,
            cantidad=cantidad,
            costo_unitario_usd=costo_unitario_usd,
            fecha_entrada=fecha_entrada,
            fecha_vencimiento=fecha_vencimiento,
            proveedor=proveedor,
            ubicacion=ubicacion,
            observaciones=observaciones,
            usuario=usuario,
        )

    with db_transaction() as conn:
        factura = conn.execute(
            "SELECT id, numero_factura, proveedor FROM facturas_compra WHERE id=?",
            (int(factura_id),),
        ).fetchone()
        if not factura:
            raise ValueError("La factura seleccionada no existe.")

        linea = conn.execute("""
            SELECT id, cantidad, costo_unitario_real_usd
            FROM facturas_compra_lineas
            WHERE factura_id=? AND inventario_id=?
            ORDER BY id DESC LIMIT 1
        """, (int(factura_id), int(inventario_id))).fetchone()
        if not linea:
            raise ValueError("La factura seleccionada no contiene este artículo de inventario.")

        numero = str(factura["numero_factura"] or "").strip()
        proveedor_final = str(proveedor or factura["proveedor"] or "").strip()
        costo_final = float(costo_unitario_usd or linea["costo_unitario_real_usd"] or 0)

        cur = conn.execute("""
            INSERT INTO inventario_lotes(
                inventario_id,codigo_lote,fecha_entrada,fecha_vencimiento,
                cantidad_inicial,cantidad_disponible,costo_unitario_usd,
                proveedor,ubicacion,observaciones,usuario,
                factura_compra_id,numero_factura,stock_contabilizado_por_factura
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(inventario_id), codigo, fecha_entrada, fecha_vencimiento or None,
            float(cantidad), float(cantidad), costo_final, proveedor_final,
            str(ubicacion or "").strip(), str(observaciones or "").strip(), usuario,
            int(factura_id), numero, 1 if stock_ya_contabilizado else 0,
        ))

        if not stock_ya_contabilizado:
            from services.inventory_service import InventoryMovement, InventoryService
            ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
                item_id=int(inventario_id), tipo="ENTRADA", cantidad=float(cantidad),
                costo_unitario=costo_final,
                motivo=f"Entrada lote {codigo} · Factura {numero or factura_id}",
                usuario=usuario,
            ))
            if not ok:
                raise ValueError(msg)

        return int(cur.lastrowid)


def listar_lotes_con_factura() -> pd.DataFrame:
    ensure_factura_lote_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT l.id, i.sku, i.nombre, l.codigo_lote,
                   l.factura_compra_id AS factura_id,
                   COALESCE(NULLIF(l.numero_factura,''),'S/N') AS numero_factura,
                   COALESCE(fc.proveedor,l.proveedor,'') AS proveedor,
                   l.fecha_entrada, l.fecha_vencimiento,
                   l.cantidad_inicial, l.cantidad_disponible,
                   COALESCE(i.unidad_base,i.unidad,'unidad') AS unidad,
                   l.costo_unitario_usd, l.ubicacion,
                   CASE WHEN COALESCE(l.stock_contabilizado_por_factura,0)=1
                        THEN 'Sí' ELSE 'No' END AS stock_desde_factura,
                   CASE
                     WHEN l.fecha_vencimiento IS NOT NULL AND date(l.fecha_vencimiento) < date('now') THEN 'VENCIDO'
                     WHEN l.fecha_vencimiento IS NOT NULL AND date(l.fecha_vencimiento) <= date('now','+30 day') THEN 'POR VENCER'
                     WHEN l.cantidad_disponible <= 0 THEN 'AGOTADO'
                     ELSE upper(l.estado)
                   END AS alerta
            FROM inventario_lotes l
            JOIN inventario i ON i.id=l.inventario_id
            LEFT JOIN facturas_compra fc ON fc.id=l.factura_compra_id
            ORDER BY
                CASE WHEN l.fecha_vencimiento IS NULL THEN 1 ELSE 0 END,
                l.fecha_vencimiento, i.nombre
        """, conn)
