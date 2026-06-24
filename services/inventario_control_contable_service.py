from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventario_centro_elite_service import ensure_schema as ensure_centro_schema


def _table_exists(conn: Any, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def ensure_schema() -> None:
    ensure_centro_schema()
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_cierres (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo TEXT NOT NULL UNIQUE,
                fecha_cierre TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                articulos INTEGER NOT NULL DEFAULT 0,
                cantidad_total REAL NOT NULL DEFAULT 0,
                valor_total_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_cierre_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cierre_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                sku TEXT,
                nombre TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                valor_total_usd REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(cierre_id) REFERENCES inventario_cierres(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierre_detalle_cierre ON inventario_cierre_detalle(cierre_id)")


def auditar_integridad() -> pd.DataFrame:
    ensure_schema()
    hallazgos: list[dict[str, Any]] = []
    with db_transaction() as conn:
        inventario = pd.read_sql_query("""
            SELECT id, sku, nombre, COALESCE(stock_actual,0) stock_actual,
                   COALESCE(costo_unitario_usd,0) costo_unitario_usd,
                   COALESCE(stock_minimo_operativo,0) stock_minimo
            FROM inventario
            WHERE lower(COALESCE(estado,'activo'))='activo'
        """, conn)

        for _, row in inventario.iterrows():
            if float(row["stock_actual"] or 0) < -0.000001:
                hallazgos.append({
                    "severidad": "CRÍTICA", "tipo": "Stock negativo",
                    "articulo": row["nombre"], "referencia": row["sku"],
                    "detalle": f"Existencia: {float(row['stock_actual']):.4f}",
                })
            if float(row["stock_actual"] or 0) > 0 and float(row["costo_unitario_usd"] or 0) <= 0:
                hallazgos.append({
                    "severidad": "ALTA", "tipo": "Inventario sin costo",
                    "articulo": row["nombre"], "referencia": row["sku"],
                    "detalle": "Tiene existencia, pero su costo unitario es cero.",
                })

        if _table_exists(conn, "inventario_lotes"):
            diferencias = pd.read_sql_query("""
                SELECT i.sku, i.nombre, COALESCE(i.stock_actual,0) stock_sistema,
                       COALESCE(SUM(CASE WHEN COALESCE(l.estado,'disponible')!='agotado' THEN l.cantidad_disponible ELSE 0 END),0) stock_lotes
                FROM inventario i
                LEFT JOIN inventario_lotes l ON l.inventario_id=i.id
                WHERE lower(COALESCE(i.estado,'activo'))='activo'
                GROUP BY i.id,i.sku,i.nombre,i.stock_actual
                HAVING ABS(stock_sistema-stock_lotes)>0.000001
            """, conn)
            for _, row in diferencias.iterrows():
                hallazgos.append({
                    "severidad": "ALTA", "tipo": "Diferencia stock-lotes",
                    "articulo": row["nombre"], "referencia": row["sku"],
                    "detalle": f"Sistema {float(row['stock_sistema']):.4f} vs lotes {float(row['stock_lotes']):.4f}",
                })

        if _table_exists(conn, "facturas_compra"):
            duplicadas = pd.read_sql_query("""
                SELECT lower(trim(COALESCE(proveedor,''))) proveedor_normalizado,
                       lower(trim(COALESCE(numero_factura,''))) numero_normalizado,
                       COUNT(*) cantidad, GROUP_CONCAT(id) ids
                FROM facturas_compra
                WHERE trim(COALESCE(numero_factura,''))!='' AND lower(COALESCE(estado,''))!='anulada'
                GROUP BY proveedor_normalizado,numero_normalizado
                HAVING COUNT(*)>1
            """, conn)
            for _, row in duplicadas.iterrows():
                hallazgos.append({
                    "severidad": "CRÍTICA", "tipo": "Factura posiblemente duplicada",
                    "articulo": "—", "referencia": str(row["ids"]),
                    "detalle": f"Proveedor y número repetidos en {int(row['cantidad'])} facturas.",
                })

            descuadres = pd.read_sql_query("""
                SELECT f.id, f.numero_factura, f.total_usd,
                       COALESCE(SUM(l.total_real_linea_usd),0) total_lineas
                FROM facturas_compra f
                LEFT JOIN facturas_compra_lineas l ON l.factura_id=f.id
                WHERE lower(COALESCE(f.estado,''))!='anulada'
                GROUP BY f.id,f.numero_factura,f.total_usd
                HAVING ABS(COALESCE(f.total_usd,0)-COALESCE(SUM(l.total_real_linea_usd),0))>0.01
            """, conn)
            for _, row in descuadres.iterrows():
                hallazgos.append({
                    "severidad": "ALTA", "tipo": "Factura descuadrada",
                    "articulo": "—", "referencia": f"Factura #{int(row['id'])}",
                    "detalle": f"Cabecera ${float(row['total_usd']):.2f} vs líneas ${float(row['total_lineas']):.2f}",
                })

        if _table_exists(conn, "movimientos_inventario"):
            huerfanos = pd.read_sql_query("""
                SELECT m.id,m.inventario_id,m.referencia
                FROM movimientos_inventario m
                LEFT JOIN inventario i ON i.id=m.inventario_id
                WHERE i.id IS NULL
            """, conn)
            for _, row in huerfanos.iterrows():
                hallazgos.append({
                    "severidad": "CRÍTICA", "tipo": "Movimiento huérfano",
                    "articulo": "—", "referencia": f"Movimiento #{int(row['id'])}",
                    "detalle": f"Apunta al artículo inexistente #{int(row['inventario_id'])}.",
                })

    if not hallazgos:
        return pd.DataFrame(columns=["severidad", "tipo", "articulo", "referencia", "detalle"])
    orden = {"CRÍTICA": 1, "ALTA": 2, "MEDIA": 3, "BAJA": 4}
    df = pd.DataFrame(hallazgos)
    df["_orden"] = df["severidad"].map(orden).fillna(9)
    return df.sort_values(["_orden", "tipo", "articulo"]).drop(columns=["_orden"])


def crear_cierre(periodo: str, usuario: str, observaciones: str = "") -> int:
    ensure_schema()
    periodo_limpio = str(periodo or "").strip()
    if len(periodo_limpio) != 7 or periodo_limpio[4] != "-":
        raise ValueError("El período debe tener formato AAAA-MM.")

    hallazgos = auditar_integridad()
    criticos = hallazgos[hallazgos["severidad"] == "CRÍTICA"] if not hallazgos.empty else hallazgos
    if not criticos.empty:
        raise ValueError("No se puede cerrar mientras existan hallazgos críticos de integridad.")

    with db_transaction() as conn:
        existente = conn.execute(
            "SELECT id FROM inventario_cierres WHERE periodo=?",
            (periodo_limpio,),
        ).fetchone()
        if existente:
            raise ValueError("Ese período ya tiene un cierre registrado.")

        filas = conn.execute("""
            SELECT id,sku,nombre,COALESCE(stock_actual,0) cantidad,
                   COALESCE(costo_unitario_usd,0) costo_unitario
            FROM inventario
            WHERE lower(COALESCE(estado,'activo'))='activo'
            ORDER BY nombre
        """).fetchall()
        cantidad_total = sum(float(r["cantidad"] or 0) for r in filas)
        valor_total = sum(float(r["cantidad"] or 0) * float(r["costo_unitario"] or 0) for r in filas)
        cur = conn.execute("""
            INSERT INTO inventario_cierres(periodo,usuario,articulos,cantidad_total,valor_total_usd,observaciones)
            VALUES(?,?,?,?,?,?)
        """, (
            periodo_limpio, str(usuario or "Sistema"), len(filas),
            round(cantidad_total, 6), round(valor_total, 6), str(observaciones or "").strip(),
        ))
        cierre_id = int(cur.lastrowid)
        for r in filas:
            valor = float(r["cantidad"] or 0) * float(r["costo_unitario"] or 0)
            conn.execute("""
                INSERT INTO inventario_cierre_detalle(
                    cierre_id,inventario_id,sku,nombre,cantidad,costo_unitario_usd,valor_total_usd
                ) VALUES(?,?,?,?,?,?,?)
            """, (
                cierre_id, int(r["id"]), r["sku"], r["nombre"],
                round(float(r["cantidad"] or 0), 6),
                round(float(r["costo_unitario"] or 0), 6), round(valor, 6),
            ))
        return cierre_id


def listar_cierres() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT id,periodo,fecha_cierre,usuario,articulos,cantidad_total,valor_total_usd,observaciones
            FROM inventario_cierres ORDER BY periodo DESC
        """, conn)


def detalle_cierre(cierre_id: int) -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("""
            SELECT sku,nombre,cantidad,costo_unitario_usd,valor_total_usd
            FROM inventario_cierre_detalle
            WHERE cierre_id=? ORDER BY nombre
        """, conn, params=(int(cierre_id),))
