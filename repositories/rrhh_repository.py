from __future__ import annotations

from datetime import date
from typing import Any

from database.connection import db_transaction


class RRHHRepository:
    def ensure_schema(self) -> None:
        with db_transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS rrhh_empleados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    puesto TEXT NOT NULL,
                    fecha_ingreso TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS rrhh_asistencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    hora_entrada TEXT,
                    hora_salida TEXT,
                    usuario TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (empleado_id, fecha),
                    FOREIGN KEY (empleado_id) REFERENCES rrhh_empleados(id)
                );

                CREATE TABLE IF NOT EXISTS rrhh_solicitudes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL CHECK (tipo IN ('vacaciones', 'permiso')),
                    motivo TEXT,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
                    comentario_admin TEXT,
                    created_by TEXT,
                    resuelto_por TEXT,
                    resuelto_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empleado_id) REFERENCES rrhh_empleados(id)
                );

                CREATE INDEX IF NOT EXISTS idx_rrhh_asistencias_fecha ON rrhh_asistencias(fecha);
                CREATE INDEX IF NOT EXISTS idx_rrhh_solicitudes_estado ON rrhh_solicitudes(estado);
                CREATE INDEX IF NOT EXISTS idx_rrhh_solicitudes_fechas ON rrhh_solicitudes(fecha_inicio, fecha_fin);
                """
            )

    def create_employee(self, *, nombre: str, puesto: str, fecha_ingreso: str, created_by: str) -> int:
        with db_transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO rrhh_empleados (nombre, puesto, fecha_ingreso, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (nombre, puesto, fecha_ingreso, created_by),
            )
            return int(cur.lastrowid)

    def list_employees(self, estado: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT id, nombre, puesto, fecha_ingreso, estado, created_at, updated_at
            FROM rrhh_empleados
        """
        params: tuple[Any, ...] = ()
        if estado in {"activo", "inactivo"}:
            query += " WHERE estado = ?"
            params = (estado,)
        query += " ORDER BY estado ASC, nombre ASC, id DESC"

        with db_transaction() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def update_employee_status(self, empleado_id: int, estado: str) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE rrhh_empleados
                SET estado = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (estado, int(empleado_id)),
            )

    def upsert_attendance(
        self,
        *,
        empleado_id: int,
        fecha: str,
        hora_entrada: str | None,
        hora_salida: str | None,
        usuario: str,
    ) -> int:
        with db_transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM rrhh_asistencias WHERE empleado_id = ? AND fecha = ?",
                (int(empleado_id), fecha),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE rrhh_asistencias
                    SET hora_entrada = COALESCE(?, hora_entrada),
                        hora_salida = COALESCE(?, hora_salida),
                        usuario = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (hora_entrada, hora_salida, usuario, int(existing["id"])),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO rrhh_asistencias (empleado_id, fecha, hora_entrada, hora_salida, usuario)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(empleado_id), fecha, hora_entrada, hora_salida, usuario),
            )
            return int(cur.lastrowid)

    def list_attendance(self, *, fecha_desde: str, fecha_hasta: str) -> list[dict[str, Any]]:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.fecha,
                    a.hora_entrada,
                    a.hora_salida,
                    e.id AS empleado_id,
                    e.nombre AS empleado,
                    e.estado AS empleado_estado
                FROM rrhh_asistencias a
                INNER JOIN rrhh_empleados e ON e.id = a.empleado_id
                WHERE a.fecha BETWEEN ? AND ?
                ORDER BY a.fecha DESC, e.nombre ASC
                """,
                (fecha_desde, fecha_hasta),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_request(
        self,
        *,
        empleado_id: int,
        tipo: str,
        motivo: str,
        fecha_inicio: str,
        fecha_fin: str,
        created_by: str,
    ) -> int:
        with db_transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO rrhh_solicitudes (
                    empleado_id, tipo, motivo, fecha_inicio, fecha_fin, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(empleado_id), tipo, motivo, fecha_inicio, fecha_fin, created_by),
            )
            return int(cur.lastrowid)

    def list_requests(
        self,
        *,
        estado: str | None = None,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                s.id,
                s.tipo,
                s.motivo,
                s.fecha_inicio,
                s.fecha_fin,
                s.estado,
                s.comentario_admin,
                s.created_by,
                s.resuelto_por,
                s.resuelto_at,
                s.created_at,
                e.id AS empleado_id,
                e.nombre AS empleado
            FROM rrhh_solicitudes s
            INNER JOIN rrhh_empleados e ON e.id = s.empleado_id
            WHERE 1=1
        """
        params: list[Any] = []
        if estado in {"pendiente", "aprobado", "rechazado"}:
            query += " AND s.estado = ?"
            params.append(estado)
        if fecha_desde:
            query += " AND s.fecha_inicio >= ?"
            params.append(fecha_desde)
        if fecha_hasta:
            query += " AND s.fecha_fin <= ?"
            params.append(fecha_hasta)
        query += " ORDER BY s.created_at DESC, s.id DESC"

        with db_transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def resolve_request(self, *, solicitud_id: int, estado: str, comentario: str, admin_usuario: str) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE rrhh_solicitudes
                SET estado = ?,
                    comentario_admin = ?,
                    resuelto_por = ?,
                    resuelto_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (estado, comentario, admin_usuario, int(solicitud_id)),
            )

    def get_dashboard_metrics(self) -> dict[str, int]:
        today = date.today().isoformat()
        with db_transaction() as conn:
            total_empleados = conn.execute("SELECT COUNT(*) AS total FROM rrhh_empleados").fetchone()["total"]
            asistencias_hoy = conn.execute(
                "SELECT COUNT(*) AS total FROM rrhh_asistencias WHERE fecha = ?",
                (today,),
            ).fetchone()["total"]
            pendientes = conn.execute(
                "SELECT COUNT(*) AS total FROM rrhh_solicitudes WHERE estado = 'pendiente'"
            ).fetchone()["total"]

        return {
            "total_empleados": int(total_empleados or 0),
            "asistencias_hoy": int(asistencias_hoy or 0),
            "solicitudes_pendientes": int(pendientes or 0),
        }
