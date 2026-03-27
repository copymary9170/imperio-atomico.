from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from database.connection import db_transaction
from models.operacion_industrial import MaintenanceOrderInput, TraceabilityEvent




def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None

class OperacionIndustrialRepository:
    def ensure_schema(self) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS industrial_maintenance_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activo_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL CHECK (tipo IN ('preventivo', 'correctivo')),
                    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'programado', 'en_ejecucion', 'completado', 'cancelado')),
                    fecha_programada TEXT NOT NULL,
                    tecnico_responsable TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    costo_estimado REAL NOT NULL DEFAULT 0,
                    costo_real REAL,
                    notas TEXT,
                    evidencia_url TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (activo_id) REFERENCES activos(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS industrial_traceability_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activo_id INTEGER,
                    accion TEXT NOT NULL,
                    detalle TEXT,
                    usuario TEXT,
                    costo REAL NOT NULL DEFAULT 0,
                    evidencia_ref TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (activo_id) REFERENCES activos(id)
                )
                """
            )

    def create_maintenance_order(self, payload: MaintenanceOrderInput, usuario: str) -> int:
        with db_transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO industrial_maintenance_orders (
                    activo_id, tipo, estado, fecha_programada, tecnico_responsable,
                    descripcion, costo_estimado, notas, evidencia_url, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.activo_id,
                    payload.tipo.value,
                    payload.estado.value,
                    payload.fecha_programada.isoformat(),
                    payload.tecnico_responsable,
                    payload.descripcion,
                    payload.costo_estimado,
                    payload.notas,
                    payload.evidencia_url,
                    usuario,
                ),
            )
            order_id = int(cur.lastrowid)
        return order_id

    def log_traceability(self, event: TraceabilityEvent) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO industrial_traceability_events (
                    activo_id, accion, detalle, usuario, costo, evidencia_ref, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.activo_id,
                    event.accion,
                    event.detalle,
                    event.usuario,
                    event.costo,
                    event.evidencia_ref,
                    json.dumps(event.metadata, ensure_ascii=False),
                    (event.created_at or datetime.utcnow()).isoformat(timespec="seconds"),
                ),
            )

    def list_assets_catalog(self) -> list[dict[str, Any]]:
        with db_transaction() as conn:
            if not _table_exists(conn, "activos"):
                return []
            rows = conn.execute(
                """
                SELECT
                    id,
                    equipo,
                    modelo,
                    unidad,
                    COALESCE(tipo_detalle, tipo_impresora) AS tipo_detalle,
                    COALESCE(clase_registro, 'equipo_principal') AS clase_registro,
                    activo_padre_id,
                    COALESCE(estado, 'activo') AS estado,
                    COALESCE(inversion, 0) AS inversion,
                    COALESCE(uso_acumulado, 0) AS uso_acumulado,
                    COALESCE(vida_util_valor, 0) AS vida_util_valor,
                    COALESCE(vida_util_unidad, 'usos') AS vida_util_unidad,
                    CASE
                        WHEN COALESCE(vida_util_valor, 0) <= 0 THEN NULL
                        ELSE ROUND(MAX(0, (1 - COALESCE(uso_acumulado, 0) / vida_util_valor)) * 100, 2)
                    END AS vida_restante_pct,
                    fecha
                FROM activos
                WHERE COALESCE(activo, 1) = 1
                ORDER BY id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_open_maintenance_orders(self) -> list[dict[str, Any]]:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT mo.*, a.equipo, a.modelo, a.unidad
                FROM industrial_maintenance_orders mo
                LEFT JOIN activos a ON a.id = mo.activo_id
                WHERE mo.estado IN ('pendiente', 'programado', 'en_ejecucion')
                ORDER BY mo.fecha_programada ASC, mo.id ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_recent_diagnostics(self, limit: int = 50) -> list[dict[str, Any]]:
        with db_transaction() as conn:
            if not _table_exists(conn, "printer_diagnostics"):
                return []
            rows = conn.execute(
                """
                SELECT
                    pd.id,
                    pd.printer_id AS activo_id,
                    a.equipo,
                    a.modelo,
                    pd.diagnostic_date,
                    pd.estimation_mode,
                    pd.confidence_level,
                    pd.diagnostic_accuracy,
                    pd.notes
                FROM printer_diagnostics pd
                LEFT JOIN activos a ON a.id = pd.printer_id
                ORDER BY pd.diagnostic_date DESC, pd.id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_overview_metrics(self) -> dict[str, Any]:
        with db_transaction() as conn:
            if not _table_exists(conn, "activos"):
                return {
                    "total_activos": 0,
                    "inversion_instalada": 0.0,
                    "equipos_principales": 0,
                    "componentes": 0,
                    "herramientas": 0,
                    "backlog_abierto": 0,
                    "top_costos": [],
                }

            assets = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(inversion), 0) AS inversion,
                    SUM(CASE WHEN clase_registro = 'equipo_principal' THEN 1 ELSE 0 END) AS equipos,
                    SUM(CASE WHEN clase_registro = 'componente' THEN 1 ELSE 0 END) AS componentes,
                    SUM(CASE WHEN clase_registro = 'herramienta' THEN 1 ELSE 0 END) AS herramientas
                FROM activos
                WHERE COALESCE(activo, 1) = 1
                """
            ).fetchone()
            if _table_exists(conn, "industrial_maintenance_orders"):
                backlog = conn.execute(
                    """
                    SELECT COUNT(*) AS pendientes
                    FROM industrial_maintenance_orders
                    WHERE estado IN ('pendiente', 'programado', 'en_ejecucion')
                    """
                ).fetchone()
            else:
                backlog = {"pendientes": 0}
            costs = conn.execute(
                """
                SELECT a.id, a.equipo, a.modelo, COALESCE(SUM(mo.costo_estimado), 0) AS costo
                FROM activos a
                LEFT JOIN industrial_maintenance_orders mo ON mo.activo_id = a.id
                GROUP BY a.id
                ORDER BY costo DESC, a.id ASC
                LIMIT 5
                """
            ).fetchall()

        return {
            "total_activos": int(assets["total"] or 0),
            "inversion_instalada": float(assets["inversion"] or 0.0),
            "equipos_principales": int(assets["equipos"] or 0),
            "componentes": int(assets["componentes"] or 0),
            "herramientas": int(assets["herramientas"] or 0),
            "backlog_abierto": int(backlog["pendientes"] or 0),
            "top_costos": [dict(row) for row in costs],
        }

    def list_unified_history(self, limit: int = 200) -> list[dict[str, Any]]:
        cap = max(1, int(limit))
        with db_transaction() as conn:
            queries: list[str] = []
            if _table_exists(conn, "activos_historial"):
                queries.append(
                    """
                    SELECT ah.fecha AS fecha, NULL AS activo_id, ah.activo AS activo,
                           'activo_historial' AS origen, ah.accion AS accion, ah.detalle AS detalle,
                           ah.usuario AS usuario, COALESCE(ah.costo, 0) AS costo
                    FROM activos_historial ah
                    """
                )
            if _table_exists(conn, "asset_diagnostics") and _table_exists(conn, "activos"):
                queries.append(
                    """
                    SELECT ad.created_at AS fecha, ad.activo_id AS activo_id, a.equipo AS activo,
                           'diagnostico_visual' AS origen, ad.severity AS accion, ad.recommendation AS detalle,
                           ad.created_by AS usuario, 0 AS costo
                    FROM asset_diagnostics ad
                    LEFT JOIN activos a ON a.id = ad.activo_id
                    """
                )
            if _table_exists(conn, "printer_maintenance_logs") and _table_exists(conn, "activos"):
                queries.append(
                    """
                    SELECT pm.maintenance_date AS fecha, pm.printer_id AS activo_id, a.equipo AS activo,
                           'diagnostico_mantenimiento' AS origen, pm.maintenance_type AS accion, pm.notes AS detalle,
                           pm.created_by AS usuario, COALESCE(pm.cost, 0) AS costo
                    FROM printer_maintenance_logs pm
                    LEFT JOIN activos a ON a.id = pm.printer_id
                    """
                )
            if _table_exists(conn, "industrial_maintenance_orders") and _table_exists(conn, "activos"):
                queries.append(
                    """
                    SELECT mo.created_at AS fecha, mo.activo_id, a.equipo AS activo,
                           'mantenimiento_industrial' AS origen, mo.tipo || ':' || mo.estado AS accion,
                           mo.descripcion AS detalle, mo.created_by AS usuario, COALESCE(mo.costo_estimado, 0) AS costo
                    FROM industrial_maintenance_orders mo
                    LEFT JOIN activos a ON a.id = mo.activo_id
                    """
                )
            if _table_exists(conn, "industrial_traceability_events") and _table_exists(conn, "activos"):
                queries.append(
                    """
                    SELECT te.created_at AS fecha, te.activo_id, a.equipo AS activo,
                           'trazabilidad' AS origen, te.accion, te.detalle, te.usuario, COALESCE(te.costo, 0) AS costo
                    FROM industrial_traceability_events te
                    LEFT JOIN activos a ON a.id = te.activo_id
                    """
                )

            if not queries:
                return []

            union_sql = " UNION ALL ".join(queries)
            rows = conn.execute(
                f"SELECT * FROM ({union_sql}) timeline ORDER BY datetime(fecha) DESC LIMIT ?",
                (cap,),
            ).fetchall()
        return [dict(row) for row in rows]
