from __future__ import annotations

from database.connection import get_connection
from legal.infrastructure.sqlite.audit_repository import SQLiteAuditRepository
from legal.infrastructure.sqlite.matter_repository import SQLiteLegalMatterRepository
from legal.infrastructure.sqlite.schema import migrate_enterprise_legal


class SQLiteLegalUnitOfWork:
    """Transaction boundary for enterprise legal use cases."""

    def __init__(self) -> None:
        self.conn = None
        self.matters = None
        self.audit = None

    def __enter__(self) -> "SQLiteLegalUnitOfWork":
        migrate_enterprise_legal()
        self.conn = get_connection()
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.execute('BEGIN')
        self.matters = SQLiteLegalMatterRepository(self.conn)
        self.audit = SQLiteAuditRepository(self.conn)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            self.rollback()
        if self.conn is not None:
            self.conn.close()

    def commit(self) -> None:
        if self.conn is not None:
            self.conn.commit()

    def rollback(self) -> None:
        if self.conn is not None:
            self.conn.rollback()
