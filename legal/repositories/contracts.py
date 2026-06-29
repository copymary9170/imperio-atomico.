from __future__ import annotations

from typing import Protocol

from legal.audit.events import AuditEvent
from legal.domain.entities import LegalMatter


class LegalMatterRepository(Protocol):
    def next_code(self, matter_type: str) -> str:
        """Return the next enterprise legal code for the matter type."""

    def add(self, matter: LegalMatter) -> int:
        """Persist a legal matter and return its database id."""

    def get(self, matter_id: int) -> LegalMatter | None:
        """Fetch a matter aggregate by id."""

    def update(self, matter_id: int, matter: LegalMatter) -> None:
        """Persist aggregate changes."""


class AuditRepository(Protocol):
    def last_hash(self) -> str:
        """Return the last audit hash in the chain."""

    def add(self, event: AuditEvent) -> int:
        """Persist an audit event and return its database id."""


class UnitOfWork(Protocol):
    matters: LegalMatterRepository
    audit: AuditRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
