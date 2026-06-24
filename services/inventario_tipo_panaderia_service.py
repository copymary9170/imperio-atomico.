from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_operativo_service import ensure_schema as ensure_operativo_schema


CLASES_ARTICULO = ["Materia prima", "Empaque", "Producto terminado", "Mercancía para reventa", "Herramienta"]
ESTADOS_LOTE = ["disponible", "agotado", "bloqueado", "vencido"]


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_schema() -> None:
    ensure_operativo_schema()
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        nuevos = {
            "clase_articulo": "TEXT NOT NULL DEFAULT 'Materia prima'",
            "controla_lotes": "INTEGER NOT NULL DEFAULT 0",
            "controla_vencimiento": "INTEGER NOT NULL DEFAULT 0",
            "dias_vida_util": "INTEGER NOT NULL DEFAULT 0",
        }
        for campo, ddl in nuevos.items():
            if campo not in cols:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {campo} {ddl}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                codigo_lote TEXT NOT NULL,
                fecha_entrada TEXT NOT NULL DEFAULT CURRENT_DATE,
                fecha_vencimiento TEXT,
                cantidad_inicial REAL NOT NULL,
                cantidad_disponible REAL NOT NULL,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                proveedor TEXT,
                ubicacion TEXT,
                estado TEXT NOT NULL DEFAULT 'disponible',
                observaciones TEXT,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(inventario_id, codigo_lote),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_item_estado ON inventario_lotes(inventario_id, estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_vencimiento ON inventario_lotes(fecha_vencimiento)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS produccion_diaria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_DATE,
                receta_id INTEGER,
                producto_inventario_id INTEGER,
                codigo_lote TEXT,
                cantidad_planificada REAL NOT NULL DEFAULT 0,
                cantidad_producida REAL NOT NULL DEFAULT 0,
                cantidad_buena REAL NOT NULL DEFAULT 0,
                cantidad_merma REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                referencia TEXT,
                estado TEXT NOT NULL DEFAULT 'completada',
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(receta_id) REFERENCES recetas_inventario(id),
                FOREIGN KEY(producto_inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_produccion_diaria_fecha ON produccion_diaria(fecha)")


def guardar_clasificacion(
    inventario_id: int,
    *,
    clase_articulo: str,
    controla_lotes: bool,
    controla_vencimiento: bool,
    dias_vida_util: int,
) -> None:
    ensure_schema()
    clase = str(clase_articulo or "").strip()
    if clase not in CLASES_ARTICULO:
        raise ValueError("Clase de artículo inválida.")
    if dias_vida_util < 0:
        raise ValueError("La vida útil no puede ser negativa.")
    with db_transaction() as conn:
        conn.execute(
            """UPDATE inventario
               SET clase_articulo=?, controla_lotes=?, controla_vencimiento=?, dias_vida_util=?
               WHERE id=?""",
            (clase, int(bool(controla_lotes)), int(bool(controla_vencimiento)), int(dias_vida_util), int(inventario_id)),
        )


def listar_articulos_clasificados() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT i.id, i.sku, i.nombre,
                   COALESCE(i.clase_articulo,'Materia prima') AS clase_articulo,
                   COALESCE(i.unidad_base,i.unidad,'unidad') AS unidad,
                   COALESCE(i.stock_actual,0) AS stock_actual,
                   COALESCE(i.stock_minimo,0) AS stock_minimo,
                   COALESCE(i.controla_lotes,0) AS controla_lotes,
                   COALESCE(i.controla_vencimiento,0) AS controla_vencimiento,
                   COALESCE(i.dias_vida_util,0) AS dias_vida_util,
                   COALESCE(i.ubicacion,'') AS ubicacion
            FROM inventario i
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY clase_articulo, i.nombre COLLATE NOCASE
        """, conn)


def registrar_lote(
    inventario_id: int,
    *,
    codigo_lote: str,
    cantidad: float,
    costo_unitario_usd: float,
    fecha_entrada: str,
    fecha_vencimiento: str | None,
    proveedor: str,
    ubicacion: str,
    observaciones: str,
    usuario: str,
) -> int:
    ensure_schema()
    codigo = str(codigo_lote or "").strip()
    if not codigo or cantidad <= 0:
        raise ValueError("Código de lote y cantidad son obligatorios.")
    with db_transaction() as conn:
        item = conn.execute("SELECT id FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        if not item:
            raise ValueError("Artículo no encontrado.")
        cur = conn.execute("""
            INSERT INTO inventario_lotes(
                inventario_id,codigo_lote,fecha_entrada,fecha_vencimiento,
                cantidad_inicial,cantidad_disponible,costo_unitario_usd,
                proveedor,ubicacion,observaciones,usuario
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(inventario_id), codigo, fecha_entrada, fecha_vencimiento or None,
            float(cantidad), float(cantidad), float(costo_unitario_usd or 0),
            str(proveedor or "").strip(), str(ubicacion or "").strip(),
            str(observaciones or "").strip(), usuario,
        ))
        ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
            item_id=int(inventario_id), tipo="ENTRADA", cantidad=float(cantidad),
            costo_unitario=float(costo_unitario_usd or 0), motivo=f"Entrada lote {codigo}", usuario=usuario,
        ))
        if not ok:
            raise ValueError(msg)
        return int(cur.lastrowid)


def listar_lotes() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT l.id, i.sku, i.nombre, l.codigo_lote, l.fecha_entrada,
                   l.fecha_vencimiento, l.cantidad_inicial, l.cantidad_disponible,
                   COALESCE(i.unidad_base,i.unidad,'unidad') AS unidad,
                   l.costo_unitario_usd, l.proveedor, l.ubicacion,
                   CASE
                     WHEN l.fecha_vencimiento IS NOT NULL AND date(l.fecha_vencimiento) < date('now') THEN 'VENCIDO'
                     WHEN l.fecha_vencimiento IS NOT NULL AND date(l.fecha_vencimiento) <= date('now','+30 day') THEN 'POR VENCER'
                     WHEN l.cantidad_disponible <= 0 THEN 'AGOTADO'
                     ELSE upper(l.estado)
                   END AS alerta
            FROM inventario_lotes l
            JOIN inventario i ON i.id=l.inventario_id
            ORDER BY
                CASE WHEN l.fecha_vencimiento IS NULL THEN 1 ELSE 0 END,
                l.fecha_vencimiento, i.nombre
        """, conn)


def _consumir_lotes_fefo(conn: Any, inventario_id: int, cantidad: float) -> None:
    pendiente = float(cantidad)
    lotes = conn.execute("""
        SELECT id, cantidad_disponible
        FROM inventario_lotes
        WHERE inventario_id=? AND cantidad_disponible>0
          AND lower(COALESCE(estado,'disponible'))='disponible'
          AND (fecha_vencimiento IS NULL OR date(fecha_vencimiento)>=date('now'))
        ORDER BY CASE WHEN fecha_vencimiento IS NULL THEN 1 ELSE 0 END,
                 fecha_vencimiento, fecha_entrada, id
    """, (int(inventario_id),)).fetchall()
    for lote in lotes:
        if pendiente <= 0:
            break
        disponible = float(lote["cantidad_disponible"] or 0)
        uso = min(disponible, pendiente)
        nuevo = disponible - uso
        conn.execute(
            "UPDATE inventario_lotes SET cantidad_disponible=?, estado=? WHERE id=?",
            (round(nuevo, 6), "agotado" if nuevo <= 0 else "disponible", int(lote["id"])),
        )
        pendiente -= uso


def registrar_produccion_diaria(
    *,
    receta_id: int | None,
    producto_id: int | None,
    codigo_lote: str,
    cantidad_planificada: float,
    cantidad_producida: float,
    cantidad_buena: float,
    costo_total_usd: float,
    referencia: str,
    usuario: str,
    procesar_inventario: bool = True,
) -> int:
    ensure_schema()
    if cantidad_producida <= 0 or cantidad_buena < 0 or cantidad_buena > cantidad_producida:
        raise ValueError("Las cantidades de producción no son válidas.")
    if procesar_inventario and not receta_id:
        raise ValueError("Selecciona una receta para descontar materiales automáticamente.")

    merma = float(cantidad_producida) - float(cantidad_buena)
    codigo = str(codigo_lote or "").strip()
    referencia_limpia = str(referencia or "").strip()

    with db_transaction() as conn:
        costo_calculado = 0.0
        producto_final_id = int(producto_id) if producto_id else None

        if procesar_inventario:
            receta = conn.execute(
                "SELECT * FROM recetas_inventario WHERE id=? AND activo=1",
                (int(receta_id),),
            ).fetchone()
            if not receta:
                raise ValueError("Receta no encontrada o inactiva.")
            if not producto_final_id and receta["producto_inventario_id"]:
                producto_final_id = int(receta["producto_inventario_id"])

            factor = float(cantidad_producida) / float(receta["rendimiento"] or 1)
            detalles = conn.execute("""
                SELECT d.insumo_id, d.cantidad, d.merma_pct,
                       i.nombre, COALESCE(i.stock_actual,0) AS stock,
                       COALESCE(i.costo_unitario_usd,0) AS costo
                FROM recetas_inventario_detalle d
                JOIN inventario i ON i.id=d.insumo_id
                WHERE d.receta_id=?
            """, (int(receta_id),)).fetchall()
            if not detalles:
                raise ValueError("La receta no tiene materiales configurados.")

            requeridos: list[tuple[Any, float]] = []
            for detalle in detalles:
                requerido = float(detalle["cantidad"] or 0) * factor * (1 + float(detalle["merma_pct"] or 0) / 100)
                if requerido > float(detalle["stock"] or 0):
                    raise ValueError(f"Stock insuficiente de {detalle['nombre']}.")
                requeridos.append((detalle, requerido))

            for detalle, requerido in requeridos:
                ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
                    item_id=int(detalle["insumo_id"]), tipo="SALIDA", cantidad=requerido,
                    costo_unitario=float(detalle["costo"] or 0),
                    motivo=f"Producción {referencia_limpia or codigo or receta['nombre']}", usuario=usuario,
                ))
                if not ok:
                    raise ValueError(msg)
                _consumir_lotes_fefo(conn, int(detalle["insumo_id"]), requerido)
                costo_calculado += requerido * float(detalle["costo"] or 0)

            if producto_final_id and cantidad_buena > 0:
                costo_unitario = costo_calculado / float(cantidad_buena)
                ok, msg = InventoryService().procesar_movimiento(conn, InventoryMovement(
                    item_id=producto_final_id, tipo="ENTRADA", cantidad=float(cantidad_buena),
                    costo_unitario=costo_unitario,
                    motivo=f"Producto terminado {referencia_limpia or codigo or receta['nombre']}", usuario=usuario,
                ))
                if not ok:
                    raise ValueError(msg)
                if codigo:
                    conn.execute("""
                        INSERT INTO inventario_lotes(
                            inventario_id,codigo_lote,fecha_entrada,cantidad_inicial,
                            cantidad_disponible,costo_unitario_usd,estado,observaciones,usuario
                        ) VALUES(?,?,CURRENT_DATE,?,?,?,?,?,?)
                    """, (
                        producto_final_id, codigo, float(cantidad_buena), float(cantidad_buena),
                        costo_unitario, "disponible", f"Producción: {referencia_limpia}", usuario,
                    ))

        costo_final = costo_calculado if procesar_inventario else float(costo_total_usd or 0)
        cur = conn.execute("""
            INSERT INTO produccion_diaria(
                receta_id,producto_inventario_id,codigo_lote,cantidad_planificada,
                cantidad_producida,cantidad_buena,cantidad_merma,costo_total_usd,
                referencia,usuario
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (
            int(receta_id) if receta_id else None,
            producto_final_id,
            codigo, float(cantidad_planificada or 0),
            float(cantidad_producida), float(cantidad_buena), merma,
            round(costo_final, 6), referencia_limpia, usuario,
        ))
        return int(cur.lastrowid)


def resumen_panaderia() -> dict[str, float]:
    ensure_schema()
    with db_transaction() as conn:
        row = conn.execute("""
            SELECT
              (SELECT COUNT(*) FROM inventario WHERE lower(COALESCE(estado,'activo'))='activo') AS articulos,
              (SELECT COUNT(*) FROM inventario WHERE lower(COALESCE(estado,'activo'))='activo' AND COALESCE(stock_actual,0)<=COALESCE(stock_minimo,0)) AS bajo_minimo,
              (SELECT COUNT(*) FROM inventario_lotes WHERE cantidad_disponible>0 AND fecha_vencimiento IS NOT NULL AND date(fecha_vencimiento)<=date('now','+30 day')) AS lotes_por_vencer,
              (SELECT COALESCE(SUM(cantidad_buena),0) FROM produccion_diaria WHERE date(fecha)=date('now')) AS producido_hoy,
              (SELECT COALESCE(SUM(cantidad_merma),0) FROM produccion_diaria WHERE date(fecha)=date('now')) AS merma_hoy
        """).fetchone()
        return {key: float(row[key] or 0) for key in row.keys()}


def listar_produccion_diaria() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT p.id, p.fecha, COALESCE(r.nombre,'Producción manual') AS receta,
                   COALESCE(i.nombre,'Servicio') AS producto, p.codigo_lote,
                   p.cantidad_planificada, p.cantidad_producida, p.cantidad_buena,
                   p.cantidad_merma,
                   CASE WHEN p.cantidad_producida>0 THEN ROUND(p.cantidad_buena/p.cantidad_producida*100,2) ELSE 0 END AS rendimiento_pct,
                   p.costo_total_usd, p.referencia, p.usuario
            FROM produccion_diaria p
            LEFT JOIN recetas_inventario r ON r.id=p.receta_id
            LEFT JOIN inventario i ON i.id=p.producto_inventario_id
            ORDER BY p.id DESC
        """, conn)
