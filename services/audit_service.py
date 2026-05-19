from __future__ import annotations

import json
from typing import Any

from database.connection import db_transaction


def ensure_audit_log_table() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                modulo TEXT NOT NULL,
                accion TEXT NOT NULL,
                entidad TEXT,
                entidad_id TEXT,
                detalle TEXT,
                metadata TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_fecha ON audit_log(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_modulo ON audit_log(modulo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_usuario ON audit_log(usuario)")


def log_audit_event(
    *,
    usuario: str,
    modulo: str,
    accion: str,
    entidad: str | None = None,
    entidad_id: Any | None = None,
    detalle: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Registra una acción operativa. Nunca debe romper la acción principal."""
    try:
        ensure_audit_log_table()
        metadata_text = json.dumps(metadata or {}, ensure_ascii=False, default=str)
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO audit_log(usuario, modulo, accion, entidad, entidad_id, detalle, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario or "Sistema",
                    modulo,
                    accion,
                    entidad,
                    str(entidad_id) if entidad_id is not None else None,
                    detalle,
                    metadata_text,
                ),
            )
    except Exception:
        # La auditoría no debe impedir cierres, ventas o registros críticos.
        return
