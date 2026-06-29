from __future__ import annotations

import json

from legal.audit.events import AuditEvent


class SQLiteAuditRepository:
    """SQLite repository for sealed legal audit events."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def last_hash(self) -> str:
        row = self.conn.execute('SELECT event_hash FROM legal_audit_events ORDER BY id DESC LIMIT 1').fetchone()
        return row['event_hash'] if row else ''

    def add(self, event: AuditEvent) -> int:
        self.conn.execute(
            '''
            INSERT INTO legal_audit_events(
                event_uuid, event_time, actor, action, entity_type, entity_id,
                before_json, after_json, context_json, previous_hash, event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                event.event_uuid,
                event.event_time,
                event.actor,
                event.action,
                event.entity_type,
                str(event.entity_id) if event.entity_id is not None else None,
                json.dumps(event.before or {}, ensure_ascii=False, default=str),
                json.dumps(event.after or {}, ensure_ascii=False, default=str),
                json.dumps(event.context or {}, ensure_ascii=False, default=str),
                event.previous_hash,
                event.event_hash,
            ),
        )
        return int(self.conn.execute('SELECT last_insert_rowid()').fetchone()[0])
