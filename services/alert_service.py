from __future__ import annotations

from dataclasses import dataclass

from database.connection import db_transaction


@dataclass(frozen=True)
class AlertSummary:
    criticas: int = 0
    medias: int = 0
    informativas: int = 0

    @property
    def total(self) -> int:
        return self.criticas + self.medias + self.informativas


def _table_exists(conn, table_name: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None
    except Exception:
        return False


def _columns(conn, table_name: str) -> set[str]:
    try:
        if not _table_exists(conn, table_name):
            return set()
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except Exception:
        return set()


def _count(conn, table_name: str, where: str | None = None, needed_columns: set[str] | None = None) -> int:
    try:
        if not _table_exists(conn, table_name):
            return 0
        existing = _columns(conn, table_name)
        if needed_columns and not needed_columns.issubset(existing):
            return 0
        sql = f"SELECT COUNT(*) AS total FROM {table_name}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql).fetchone()
        return int(row["total"] if row and "total" in row.keys() else (row[0] if row else 0))
    except Exception:
        return 0


def get_alert_summary() -> AlertSummary:
    """Resumen liviano para sidebar. Nunca debe romper la app."""
    try:
        with db_transaction() as conn:
            criticas = 0
            medias = 0
            informativas = 0

            if _count(conn, "disenos_aprobaciones", "bloqueo_produccion=1", {"bloqueo_produccion"}):
                criticas += 1
            if _count(conn, "cierres_caja_turnos", "estado='Con diferencia'", {"estado"}):
                criticas += 1
            if _count(conn, "migration_errors"):
                criticas += 1

            if _count(conn, "despachos_entregas", "estado NOT IN ('Entregado', 'Devuelto')", {"estado"}):
                medias += 1
            if _count(conn, "cola_impresion", "estado NOT IN ('Completado', 'Cancelado', 'Entregado')", {"estado"}):
                medias += 1
            if _count(conn, "contadores_impresion", "estado NOT IN ('Cuadrado', 'Cerrado')", {"estado"}):
                medias += 1
            if _count(conn, "ordenes_compra", "estado NOT IN ('Recibida', 'Cerrada', 'Cancelada')", {"estado"}):
                medias += 1

            if _count(conn, "fichas_tecnicas_bom", "estado IN ('Borrador', 'En revisión')", {"estado"}):
                informativas += 1
            if _count(conn, "proveedores", "COALESCE(rif, '')='' OR COALESCE(telefono, '')=''", {"rif", "telefono"}):
                informativas += 1

            return AlertSummary(criticas=criticas, medias=medias, informativas=informativas)
    except Exception:
        return AlertSummary()
