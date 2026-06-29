from __future__ import annotations

from legal.infrastructure.sqlite.schema import migrate_enterprise_legal


def bootstrap_enterprise_legal() -> None:
    """Apply enterprise legal migrations without touching legacy V4 tables."""

    migrate_enterprise_legal()
