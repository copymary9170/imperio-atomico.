from __future__ import annotations

from database.connection import db_transaction

MIGRATION_VERSION = 102
MIGRATION_NAME = "legacy_v4_import"


def apply() -> None:
    """Import compatible Legal V4 matters into the enterprise schema.

    The import is idempotent and keeps the original V4 records untouched. It only
    maps fields that exist in both models and records provenance through
    ``legacy_source`` and ``legacy_record_id``.
    """

    with db_transaction() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='legal_v4_matters'"
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
                (MIGRATION_VERSION, MIGRATION_NAME),
            )
            return

        conn.execute(
            """
            INSERT OR IGNORE INTO legal_matters(
                uuid, code, legacy_source, legacy_record_id, area, matter_type, title,
                description, status, risk_level, confidentiality, owner, reviewer,
                approver, counterparty, jurisdiction, due_date, expiration_date,
                legal_basis, tags, legal_hold, retention_years, created_by, created_at,
                updated_by, updated_at
            )
            SELECT
                'legacy-v4-' || id,
                code,
                'legal_v4_matters',
                id,
                matter_type,
                matter_type,
                title,
                description,
                status,
                risk_level,
                confidentiality,
                owner,
                reviewer,
                approver,
                counterparty,
                jurisdiction,
                due_date,
                expiration_date,
                legal_basis,
                tags,
                legal_hold,
                retention_years,
                created_by,
                created_at,
                updated_by,
                updated_at
              FROM legal_v4_matters
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (MIGRATION_VERSION, MIGRATION_NAME),
        )
