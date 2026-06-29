"""SQLite adapters for the enterprise legal module."""

from legal.infrastructure.sqlite.audit_repository import SQLiteAuditRepository
from legal.infrastructure.sqlite.matter_repository import SQLiteLegalMatterRepository
from legal.infrastructure.sqlite.schema import migrate_enterprise_legal
from legal.infrastructure.sqlite.uow import SQLiteLegalUnitOfWork

__all__ = [
    "SQLiteAuditRepository",
    "SQLiteLegalMatterRepository",
    "SQLiteLegalUnitOfWork",
    "migrate_enterprise_legal",
]
