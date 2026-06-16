from __future__ import annotations

import json
from typing import Any

from database.connection import db_transaction


def _to_json(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def record_domain_event(
    *,
    tipo_evento: str,
    modulo_origen: str,
    usuario: str = "Sistema",
    referencia_tabla: str | None = None,
    referencia_id: int | None = None,
    payload: dict[str, Any] | None = None,
    severidad: str = "normal",
) -> int:
    """Register an ERP business event for audit, dashboards and async processing."""
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO eventos_transaccionales (
                tipo_evento,
                modulo_origen,
                referencia_tabla,
                referencia_id,
                usuario,
                severidad,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tipo_evento,
                modulo_origen,
                referencia_tabla,
                referencia_id,
                usuario,
                severidad,
                _to_json(payload),
            ),
        )
        return int(cur.lastrowid)


def mark_domain_event_processed(event_id: int, resultado: dict[str, Any] | None = None) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE eventos_transaccionales
            SET estado = 'procesado', resultado_json = ?, procesado_en = CURRENT_TIMESTAMP, error = NULL
            WHERE id = ?
            """,
            (_to_json(resultado), event_id),
        )


def mark_domain_event_failed(event_id: int, error: str, resultado: dict[str, Any] | None = None) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE eventos_transaccionales
            SET estado = 'fallido', resultado_json = ?, error = ?, procesado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (_to_json(resultado), str(error), event_id),
        )


def fetch_pending_domain_events(limit: int = 50) -> list[dict[str, Any]]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM eventos_transaccionales
            WHERE estado = 'pendiente'
            ORDER BY fecha ASC, id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]
