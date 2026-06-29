from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from uuid import uuid4

from database.connection import db_transaction
from legal.application.commands import CreateLegalMatterCommand
from legal.audit.events import AuditEvent
from legal.domain.entities import LegalMatter
from legal.infrastructure.sqlite.queries import legal_dashboard_metrics, list_legal_matter_summary, list_recent_audit
from legal.infrastructure.sqlite.repositories import SQLiteAuditRepository, SQLiteLegalMatterRepository
from legal.migrations import migrate_all
from legal.security.rbac import LegalPermission, SecurityContext, require_permission


class LegalEnterpriseFacade:
    """Application facade consumed by Streamlit without exposing SQL to the UI."""

    def __init__(self) -> None:
        migrate_all()

    def dashboard(self, context: SecurityContext) -> dict[str, int]:
        require_permission(context, LegalPermission.VIEW)
        return legal_dashboard_metrics()

    def matters(self, context: SecurityContext) -> list[dict]:
        require_permission(context, LegalPermission.VIEW)
        return list_legal_matter_summary()

    def audit(self, context: SecurityContext) -> list[dict]:
        require_permission(context, LegalPermission.AUDIT_VIEW)
        return list_recent_audit()

    def create_matter(self, command: CreateLegalMatterCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        matter = LegalMatter(**asdict(command))
        matter.validate()
        with db_transaction() as conn:
            matters = SQLiteLegalMatterRepository(conn)
            audit = SQLiteAuditRepository(conn)
            if not matter.code.strip():
                matter.code = matters.next_code(matter.matter_type)
            matter_id = matters.add(matter)
            event = AuditEvent(
                actor=context.user,
                action="LEGAL_ENTERPRISE_MATTER_CREATED",
                entity_type="legal_matter",
                entity_id=matter_id,
                before={},
                after=asdict(matter),
                context=_audit_context(context, permission=LegalPermission.CREATE.value),
                previous_hash=audit.last_hash(),
            ).seal()
            audit.add(event)
            return matter_id


def _audit_context(context: SecurityContext, *, permission: str) -> dict:
    """Build a normalized audit context with placeholders for future request metadata."""
    return {
        "session_id": context.session_id,
        "correlation_id": context.correlation_id or str(uuid4()),
        "roles": list(context.roles),
        "permission": permission,
        "ip": "pending-streamlit-adapter",
        "device": "pending-streamlit-adapter",
        "browser": "pending-streamlit-adapter",
        "recorded_at": datetime.utcnow().isoformat(),
    }


def serialize_for_export(rows: list[dict]) -> str:
    """Serialize rows as readable JSON for controlled exports."""
    return json.dumps(rows, ensure_ascii=False, indent=2, default=str)
