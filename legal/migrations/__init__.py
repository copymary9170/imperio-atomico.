from __future__ import annotations

from legal.infrastructure.sqlite.schema import migrate_enterprise_legal
from legal.migrations.v101_operational_domains import apply as apply_v101
from legal.migrations.v102_legacy_v4_import import apply as apply_v102


def migrate_all() -> None:
    """Apply all Legal Enterprise migrations in deterministic order."""

    migrate_enterprise_legal()
    apply_v101()
    apply_v102()


__all__ = ["migrate_all"]
