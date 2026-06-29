from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from sqlite3 import Connection
from typing import Any

from legal.audit.events import AuditEvent
from legal.domain.entities import LegalMatter
from legal.domain.enums import Confidentiality, MatterStatus, RiskLevel


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteLegalMatterRepository:
    """SQLite implementation of the LegalMatterRepository contract."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def next_code(self, matter_type: str) -> str:
        year = datetime.utcnow().year
        prefix = "LEG"
        row = self.conn.execute("SELECT COALESCE(MAX(id),0)+1 AS n FROM legal_matters").fetchone()
        return f"{prefix}-{year}-{int(row['n']):06d}"

    def add(self, matter: LegalMatter) -> int:
        area = _area_for_type(matter.matter_type)
        cur = self.conn.execute(
            """
            INSERT INTO legal_matters(
                uuid, code, area, matter_type, title, description, status, risk_level,
                confidentiality, owner, reviewer, approver, counterparty, jurisdiction,
                due_date, expiration_date, legal_basis, tags, legal_hold, retention_years,
                created_by, created_at, updated_by, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                matter.uuid,
                matter.code,
                area,
                matter.matter_type,
                matter.title.strip(),
                matter.description.strip(),
                _enum_value(matter.status),
                _enum_value(matter.risk_level),
                _enum_value(matter.confidentiality),
                matter.owner.strip(),
                matter.reviewer.strip(),
                matter.approver.strip(),
                matter.counterparty.strip(),
                matter.jurisdiction.strip() or "Venezuela",
                _iso(matter.due_date),
                _iso(matter.expiration_date),
                matter.legal_basis.strip(),
                matter.tags.strip(),
                int(matter.legal_hold),
                matter.retention_years,
                matter.created_by.strip(),
                _iso(matter.created_at),
                None,
                None,
            ),
        )
        matter_id = int(cur.lastrowid)
        self.conn.execute(
            "INSERT INTO legal_timeline_events(matter_id,event_type,title,description,actor) VALUES(?,?,?,?,?)",
            (matter_id, "CREACION", "Expediente creado", matter.description.strip(), matter.created_by.strip()),
        )
        return matter_id

    def get(self, matter_id: int) -> LegalMatter | None:
        row = self.conn.execute("SELECT * FROM legal_matters WHERE id=? AND active=1", (matter_id,)).fetchone()
        if row is None:
            return None
        return LegalMatter(
            code=row["code"],
            matter_type=row["matter_type"],
            title=row["title"],
            description=row["description"] or "",
            owner=row["owner"],
            created_by=row["created_by"],
            reviewer=row["reviewer"] or "",
            approver=row["approver"] or "",
            status=MatterStatus(row["status"]),
            risk_level=RiskLevel(row["risk_level"]),
            confidentiality=Confidentiality(row["confidentiality"]),
            counterparty=row["counterparty"] or "",
            jurisdiction=row["jurisdiction"] or "Venezuela",
            due_date=_parse_date(row["due_date"]),
            expiration_date=_parse_date(row["expiration_date"]),
            legal_basis=row["legal_basis"] or "",
            tags=row["tags"] or "",
            legal_hold=bool(row["legal_hold"]),
            retention_years=int(row["retention_years"]),
            uuid=row["uuid"],
            created_at=_parse_datetime(row["created_at"]) or datetime.utcnow(),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    def update(self, matter_id: int, matter: LegalMatter) -> None:
        self.conn.execute(
            """
            UPDATE legal_matters
               SET title=?, description=?, status=?, risk_level=?, confidentiality=?, owner=?,
                   reviewer=?, approver=?, counterparty=?, jurisdiction=?, due_date=?,
                   expiration_date=?, legal_basis=?, tags=?, legal_hold=?, retention_years=?,
                   updated_by=?, updated_at=?
             WHERE id=?
            """,
            (
                matter.title.strip(),
                matter.description.strip(),
                _enum_value(matter.status),
                _enum_value(matter.risk_level),
                _enum_value(matter.confidentiality),
                matter.owner.strip(),
                matter.reviewer.strip(),
                matter.approver.strip(),
                matter.counterparty.strip(),
                matter.jurisdiction.strip() or "Venezuela",
                _iso(matter.due_date),
                _iso(matter.expiration_date),
                matter.legal_basis.strip(),
                matter.tags.strip(),
                int(matter.legal_hold),
                matter.retention_years,
                matter.created_by.strip(),
                datetime.utcnow().isoformat(),
                matter_id,
            ),
        )
        self.conn.execute(
            "INSERT INTO legal_timeline_events(matter_id,event_type,title,description,actor) VALUES(?,?,?,?,?)",
            (matter_id, "ACTUALIZACION", "Expediente actualizado", f"Estado: {_enum_value(matter.status)}", matter.created_by.strip()),
        )

    def list_summary(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, code, area, matter_type, title, status, risk_level, confidentiality,
                   owner, counterparty, due_date, expiration_date, created_at
              FROM legal_matters
             WHERE active=1
             ORDER BY id DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


class SQLiteAuditRepository:
    """SQLite audit event writer with hash-chain continuity."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def last_hash(self) -> str:
        row = self.conn.execute("SELECT event_hash FROM legal_audit_events ORDER BY id DESC LIMIT 1").fetchone()
        return row["event_hash"] if row else ""

    def add(self, event: AuditEvent) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO legal_audit_events(
                event_uuid, event_time, actor, action, entity_type, entity_id,
                before_json, after_json, context_json, previous_hash, event_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.event_uuid,
                event.event_time,
                event.actor,
                event.action,
                event.entity_type,
                str(event.entity_id or ""),
                _json(event.before),
                _json(event.after),
                _json(event.context),
                event.previous_hash,
                event.event_hash,
            ),
        )
        return int(cur.lastrowid)

    def list_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM legal_audit_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def _json(value: Any) -> str:
    import json

    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


def _area_for_type(matter_type: str) -> str:
    normalized = matter_type.strip().casefold()
    if "contrato" in normalized:
        return "Contratos"
    if "privacidad" in normalized or "cookie" in normalized or "consent" in normalized or "termin" in normalized or "aviso" in normalized:
        return "Privacidad"
    if "litig" in normalized or "demanda" in normalized:
        return "Litigios"
    if "marca" in normalized or "autor" in normalized or "propiedad" in normalized:
        return "Propiedad intelectual"
    if "riesgo" in normalized:
        return "Riesgos"
    if "cumpl" in normalized or "auditor" in normalized:
        return "Cumplimiento"
    if "licencia" in normalized or "permiso" in normalized:
        return "Licencias y permisos"
    if "gobierno" in normalized or "acta" in normalized:
        return "Gobierno corporativo"
    if "reclamo" in normalized or "garantia" in normalized or "devol" in normalized:
        return "Reclamos y garantias"
    return "Documentos publicos"
