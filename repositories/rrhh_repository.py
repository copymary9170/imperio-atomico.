from __future__ import annotations

from datetime import date
from typing import Any

from database.connection import db_transaction


class RRHHRepository:
    # =========================
    # SCHEMA
    # =========================
    def ensure_schema(self) -> None:
        with db_transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS empleados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    documento TEXT NOT NULL UNIQUE,
                    puesto TEXT NOT NULL,
                    area TEXT NOT NULL,
                    fecha_ingreso TEXT NOT NULL,
                    estado TEXT NOT NULL CHECK (estado IN ('activo', 'inactivo')),
                    created_by TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS asistencias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    hora_entrada TEXT,
                    hora_salida TEXT,
                    usuario TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(empleado_id, fecha),
                    FOREIGN KEY (empleado_id) REFERENCES empleados(id)
                );

                CREATE TABLE IF NOT EXISTS solicitudes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL CHECK (tipo IN ('vacaciones', 'permiso', 'incapacidad')),
                    motivo TEXT,
                    fecha_inicio TEXT NOT NULL,
                    fecha_fin TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente'
                        CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
                    comentario_admin TEXT,
                    created_by TEXT,
                    resuelto_por TEXT,
                    resuelto_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (empleado_id) REFERENCES empleados(id)
                );

                CREATE INDEX IF NOT EXISTS idx_asistencias_fecha ON asistencias(fecha);
                CREATE INDEX IF NOT EXISTS idx_solicitudes_estado ON solicitudes(estado);
                """
            )

    # =========================
    # EMPLEADOS
    # =========================
    def create_employee(
        self,
        *,
        nombre: str,
        documento: str,
        puesto: str,
        area: str,
        fecha_ingreso: str,
        estado: str,
        created_by: str,
    ) -> int:
        with db_transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO empleados (nombre, documento, puesto, area, fecha_ingreso, estado, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (nombre, documento, puesto, area, fecha_ingreso, estado, created_by),
            )
            return int(cur.lastrowid)

    def list_employees(self, estado: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT id, nombre, documento, puesto, area, fecha_ingreso, estado
            FROM empleados
        """
        params: list[Any] = []

        if estado in {"activo", "inactivo"}:
            query += " WHERE estado = ?"
            params.append(estado)

        query += " ORDER BY nombre ASC"

        with db_transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def update_employee_status(self, empleado_id: int, estado: str) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE empleados
                SET estado = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (estado, empleado_id),
            )

    # =========================
    # ASISTENCIA
    # =========================
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
                "SELECT id FROM asistencias WHERE empleado_id = ? AND fecha = ?",
                (empleado_id, fecha),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE asistencias
                    SET hora_entrada = COALESCE(?, hora_entrada),
                        hora_salida = COALESCE(?, hora_salida),
                        usuario = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (hora_entrada, hora_salida, usuario, existing["id"]),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO asistencias (empleado_id, fecha, hora_entrada, hora_salida, usuario)
                VALUES (?, ?, ?, ?, ?)
                """,
                (empleado_id, fecha, hora_entrada, hora_salida, usuario),
            )
            return int(cur.lastrowid)

    def list_attendance(
        self,
        *,
        fecha_desde: str,
        fecha_hasta: str,
        empleado_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                a.id,
                a.fecha,
                a.hora_entrada,
                a.hora_salida,
                e.nombre AS empleado
            FROM asistencias a
            JOIN empleados e ON e.id = a.empleado_id
            WHERE a.fecha BETWEEN ? AND ?
        """
        params: list[Any] = [fecha_desde, fecha_hasta]

        if empleado_id:
            query += " AND e.id = ?"
            params.append(empleado_id)

        query += " ORDER BY a.fecha DESC"

        with db_transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    # =========================
    # SOLICITUDES
    # =========================
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
                INSERT INTO solicitudes (
                    empleado_id, tipo, motivo, fecha_inicio, fecha_fin, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (empleado_id, tipo, motivo, fecha_inicio, fecha_fin, created_by),
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
                e.nombre AS empleado
            FROM solicitudes s
            JOIN empleados e ON e.id = s.empleado_id
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

        query += " ORDER BY s.created_at DESC"

        with db_transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def resolve_request(
        self,
        *,
        solicitud_id: int,
        estado: str,
        comentario: str,
        admin_usuario: str,
    ) -> None:
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE solicitudes
                SET estado = ?,
                    comentario_admin = ?,
                    resuelto_por = ?,
                    resuelto_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (estado, comentario, admin_usuario, solicitud_id),
            )

    # =========================
    # DASHBOARD
    # =========================
    def get_dashboard_metrics(self) -> dict[str, int]:
        today = date.today().isoformat()

        with db_transaction() as conn:
            activos = conn.execute(
                "SELECT COUNT(*) FROM empleados WHERE estado='activo'"
            ).fetchone()[0]

            asistencias = conn.execute(
                "SELECT COUNT(*) FROM asistencias WHERE fecha=?",
                (today,),
            ).fetchone()[0]

            pendientes = conn.execute(
                "SELECT COUNT(*) FROM solicitudes WHERE estado='pendiente'"
            ).fetchone()[0]

            aprobadas = conn.execute(
                "SELECT COUNT(*) FROM solicitudes WHERE estado='aprobado'"
            ).fetchone()[0]

            rechazadas = conn.execute(
                "SELECT COUNT(*) FROM solicitudes WHERE estado='rechazado'"
            ).fetchone()[0]

        return {
            "empleados_activos": int(activos or 0),
            "asistencias_hoy": int(asistencias or 0),
            "solicitudes_pendientes": int(pendientes or 0),
            "solicitudes_aprobadas": int(aprobadas or 0),
            "solicitudes_rechazadas": int(rechazadas or 0),
        }
