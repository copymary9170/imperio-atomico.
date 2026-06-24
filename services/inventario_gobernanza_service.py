from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.facturas_compra_service import ensure_facturas_compra_tables
from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_control_contable_service import ensure_schema as ensure_control_schema
from services.inventario_factura_lote_service import ensure_factura_lote_schema


def ensure_schema() -> None:
    ensure_control_schema()
    ensure_facturas_compra_tables()
    ensure_factura_lote_schema()
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_solicitudes_ajuste (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario_solicita TEXT NOT NULL,
                inventario_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                cantidad REAL NOT NULL,
                stock_sistema REAL NOT NULL,
                stock_fisico REAL,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                motivo TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                usuario_aprueba TEXT,
                fecha_decision TEXT,
                observacion_decision TEXT,
                movimiento_id INTEGER,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devoluciones_proveedor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                factura_id INTEGER NOT NULL,
                factura_linea_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                cantidad REAL NOT NULL,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                motivo TEXT NOT NULL,
                nota_credito TEXT,
                credito_proveedor_usd REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(factura_id) REFERENCES facturas_compra(id),
                FOREIGN KEY(factura_linea_id) REFERENCES facturas_compra_lineas(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ajustes_estado ON inventario_solicitudes_ajuste(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devoluciones_factura ON devoluciones_proveedor(factura_id)")


def periodo_cerrado(fecha_operacion: str | None = None) -> bool:
    ensure_schema()
    fecha_valor = str(fecha_operacion or date.today().isoformat())[:10]
    periodo = fecha_valor[:7]
    with db_transaction() as conn:
        return conn.execute(
            "SELECT 1 FROM inventario_cierres WHERE periodo=? LIMIT 1",
            (periodo,),
        ).fetchone() is not None


def exigir_periodo_abierto(fecha_operacion: str | None = None) -> None:
    fecha_valor = str(fecha_operacion or date.today().isoformat())[:10]
    if periodo_cerrado(fecha_valor):
        raise ValueError(
            f"El período {fecha_valor[:7]} está cerrado. No se permiten operaciones retroactivas sin reapertura administrativa."
        )


def solicitar_ajuste(
    *,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    motivo: str,
    usuario: str,
    stock_fisico: float | None = None,
) -> int:
    ensure_schema()
    exigir_periodo_abierto()
    tipo_ok = str(tipo or "").upper().strip()
    if tipo_ok not in {"AJUSTE_ENTRADA", "AJUSTE_SALIDA"}:
        raise ValueError("Tipo de ajuste inválido.")
    if float(cantidad or 0) <= 0 or not str(motivo or "").strip():
        raise ValueError("Cantidad y motivo son obligatorios.")
    with db_transaction() as conn:
        item = conn.execute(
            "SELECT stock_actual,costo_unitario_usd FROM inventario WHERE id=? AND lower(COALESCE(estado,'activo'))='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not item:
            raise ValueError("Artículo no encontrado.")
        if tipo_ok == "AJUSTE_SALIDA" and float(cantidad) > float(item["stock_actual"] or 0):
            raise ValueError("El ajuste solicitado supera el stock disponible.")
        cur = conn.execute("""
            INSERT INTO inventario_solicitudes_ajuste(
                usuario_solicita,inventario_id,tipo,cantidad,stock_sistema,stock_fisico,
                costo_unitario_usd,motivo
            ) VALUES(?,?,?,?,?,?,?,?)
        """, (
            str(usuario or "Sistema"), int(inventario_id), tipo_ok, float(cantidad),
            float(item["stock_actual"] or 0), float(stock_fisico) if stock_fisico is not None else None,
            float(item["costo_unitario_usd"] or 0), str(motivo).strip(),
        ))
        return int(cur.lastrowid)


def decidir_ajuste(solicitud_id: int, *, aprobar: bool, usuario: str, observacion: str = "") -> None:
    ensure_schema()
    exigir_periodo_abierto()
    with db_transaction() as conn:
        solicitud = conn.execute(
            "SELECT * FROM inventario_solicitudes_ajuste WHERE id=? AND estado='pendiente'",
            (int(solicitud_id),),
        ).fetchone()
        if not solicitud:
            raise ValueError("La solicitud no existe o ya fue decidida.")
        if str(solicitud["usuario_solicita"] or "") == str(usuario or ""):
            raise ValueError("Quien solicita el ajuste no puede aprobarlo.")
        movimiento_id = None
        estado = "rechazada"
        if aprobar:
            ok, mensaje = InventoryService().procesar_movimiento(conn, InventoryMovement(
                item_id=int(solicitud["inventario_id"]),
                tipo=str(solicitud["tipo"]),
                cantidad=float(solicitud["cantidad"]),
                costo_unitario=float(solicitud["costo_unitario_usd"] or 0),
                motivo=f"Ajuste aprobado #{solicitud_id}: {solicitud['motivo']}",
                usuario=str(usuario or "Sistema"),
            ))
            if not ok:
                raise ValueError(mensaje)
            movimiento_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            estado = "aprobada"
        conn.execute("""
            UPDATE inventario_solicitudes_ajuste
               SET estado=?,usuario_aprueba=?,fecha_decision=CURRENT_TIMESTAMP,
                   observacion_decision=?,movimiento_id=?
             WHERE id=?
        """, (estado, str(usuario or "Sistema"), str(observacion or "").strip(), movimiento_id, int(solicitud_id)))


def listar_solicitudes_ajuste(estado: str | None = None) -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        filtro = "WHERE s.estado=?" if estado else ""
        params = (str(estado),) if estado else ()
        return pd.read_sql_query(f"""
            SELECT s.id,s.fecha,s.usuario_solicita,i.sku,i.nombre,s.tipo,s.cantidad,
                   s.stock_sistema,s.stock_fisico,s.motivo,s.estado,s.usuario_aprueba,
                   s.fecha_decision,s.observacion_decision
            FROM inventario_solicitudes_ajuste s
            JOIN inventario i ON i.id=s.inventario_id
            {filtro}
            ORDER BY CASE s.estado WHEN 'pendiente' THEN 1 ELSE 2 END,s.id DESC
        """, conn, params=params)


def registrar_devolucion_proveedor(
    *,
    factura_linea_id: int,
    cantidad: float,
    motivo: str,
    nota_credito: str,
    usuario: str,
) -> int:
    ensure_schema()
    exigir_periodo_abierto()
    if float(cantidad or 0) <= 0 or not str(motivo or "").strip():
        raise ValueError("Cantidad y motivo son obligatorios.")
    with db_transaction() as conn:
        linea = conn.execute("""
            SELECT l.*,f.estado estado_factura,f.pagado_usd,f.pendiente_usd
            FROM facturas_compra_lineas l
            JOIN facturas_compra f ON f.id=l.factura_id
            WHERE l.id=? AND l.inventario_id IS NOT NULL
        """, (int(factura_linea_id),)).fetchone()
        if not linea:
            raise ValueError("La línea no corresponde a un artículo de inventario.")
        if str(linea["estado_factura"] or "").lower() == "anulada":
            raise ValueError("La factura está anulada.")
        devuelto = conn.execute(
            "SELECT COALESCE(SUM(cantidad),0) total FROM devoluciones_proveedor WHERE factura_linea_id=?",
            (int(factura_linea_id),),
        ).fetchone()["total"]
        disponible_devolver = float(linea["cantidad"] or 0) - float(devuelto or 0)
        if float(cantidad) > disponible_devolver + 0.000001:
            raise ValueError(f"Solo quedan {max(disponible_devolver,0):.4f} unidades por devolver.")
        item = conn.execute("SELECT stock_actual FROM inventario WHERE id=?", (int(linea["inventario_id"]),)).fetchone()
        if not item or float(item["stock_actual"] or 0) < float(cantidad):
            raise ValueError("No existe stock suficiente; parte del material ya fue consumida o vendida.")
        costo = float(linea["costo_unitario_real_usd"] or 0)
        total = float(cantidad) * costo
        ok, mensaje = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(linea["inventario_id"]), tipo="SALIDA", cantidad=float(cantidad),
            costo_unitario=costo, motivo=f"Devolución proveedor factura #{linea['factura_id']}",
            usuario=str(usuario or "Sistema"),
        ))
        if not ok:
            raise ValueError(mensaje)
        pendiente_anterior = float(linea["pendiente_usd"] or 0)
        reduccion_pendiente = min(total, pendiente_anterior)
        credito = max(total - reduccion_pendiente, 0)
        conn.execute("""
            UPDATE facturas_compra
               SET total_usd=MAX(total_usd-?,0),pendiente_usd=MAX(pendiente_usd-?,0),
                   estado=CASE WHEN MAX(pendiente_usd-?,0)=0 THEN 'pagada' ELSE estado END
             WHERE id=?
        """, (total, reduccion_pendiente, reduccion_pendiente, int(linea["factura_id"])))
        cur = conn.execute("""
            INSERT INTO devoluciones_proveedor(
                usuario,factura_id,factura_linea_id,inventario_id,cantidad,
                costo_unitario_usd,total_usd,motivo,nota_credito,credito_proveedor_usd
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            str(usuario or "Sistema"), int(linea["factura_id"]), int(factura_linea_id),
            int(linea["inventario_id"]), float(cantidad), costo, total,
            str(motivo).strip(), str(nota_credito or "").strip(), credito,
        ))
        return int(cur.lastrowid)


def anular_factura_compra(factura_id: int, *, usuario: str, motivo: str) -> None:
    ensure_schema()
    exigir_periodo_abierto()
    if not str(motivo or "").strip():
        raise ValueError("Debes indicar el motivo de anulación.")
    with db_transaction() as conn:
        factura = conn.execute("SELECT * FROM facturas_compra WHERE id=?", (int(factura_id),)).fetchone()
        if not factura:
            raise ValueError("Factura no encontrada.")
        if str(factura["estado"] or "").lower() == "anulada":
            raise ValueError("La factura ya está anulada.")
        if float(factura["pagado_usd"] or 0) > 0:
            raise ValueError("La factura tiene pagos. Registra una devolución o nota de crédito en lugar de anularla.")
        lineas = conn.execute(
            "SELECT * FROM facturas_compra_lineas WHERE factura_id=?",
            (int(factura_id),),
        ).fetchall()
        if any(row["inventario_id"] is None for row in lineas):
            raise ValueError("La factura contiene activos, gastos o servicios y requiere reversión administrativa especializada.")
        for linea in lineas:
            item = conn.execute("SELECT stock_actual FROM inventario WHERE id=?", (int(linea["inventario_id"]),)).fetchone()
            if not item or float(item["stock_actual"] or 0) < float(linea["cantidad"] or 0):
                raise ValueError(f"No se puede anular: el artículo '{linea['descripcion']}' ya fue consumido o vendido.")
            lotes = conn.execute("""
                SELECT cantidad_inicial,cantidad_disponible FROM inventario_lotes
                WHERE factura_compra_id=? AND inventario_id=?
            """, (int(factura_id), int(linea["inventario_id"]))).fetchall()
            if any(abs(float(l["cantidad_inicial"] or 0)-float(l["cantidad_disponible"] or 0))>0.000001 for l in lotes):
                raise ValueError(f"No se puede anular: existe consumo del lote de '{linea['descripcion']}'.")
        for linea in lineas:
            ok, mensaje = InventoryService().procesar_movimiento(conn, InventoryMovement(
                item_id=int(linea["inventario_id"]), tipo="SALIDA", cantidad=float(linea["cantidad"]),
                costo_unitario=float(linea["costo_unitario_real_usd"] or 0),
                motivo=f"Anulación factura compra #{factura_id}: {motivo}", usuario=str(usuario or "Sistema"),
            ))
            if not ok:
                raise ValueError(mensaje)
        conn.execute("""
            UPDATE inventario_lotes SET cantidad_disponible=0,estado='anulado'
            WHERE factura_compra_id=?
        """, (int(factura_id),))
        conn.execute("""
            UPDATE facturas_compra
               SET estado='anulada',pendiente_usd=0,
                   observaciones=trim(COALESCE(observaciones,'') || ' | ANULADA: ' || ?)
             WHERE id=?
        """, (str(motivo).strip(), int(factura_id)))


def listar_lineas_devolvibles() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT l.id linea_id,f.id factura_id,f.numero_factura,f.proveedor,l.inventario_id,
                   i.sku,i.nombre,l.cantidad,
                   COALESCE((SELECT SUM(d.cantidad) FROM devoluciones_proveedor d WHERE d.factura_linea_id=l.id),0) devuelto,
                   l.cantidad-COALESCE((SELECT SUM(d.cantidad) FROM devoluciones_proveedor d WHERE d.factura_linea_id=l.id),0) disponible_devolver,
                   l.costo_unitario_real_usd
            FROM facturas_compra_lineas l
            JOIN facturas_compra f ON f.id=l.factura_id
            JOIN inventario i ON i.id=l.inventario_id
            WHERE lower(COALESCE(f.estado,''))!='anulada'
            ORDER BY f.id DESC,l.id DESC
        """, conn)
