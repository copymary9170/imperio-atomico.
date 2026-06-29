from __future__ import annotations

from database.connection import db_transaction

MIGRATION_VERSION = 101
MIGRATION_NAME = "legal_operational_domains"


def apply() -> None:
    """Create normalized operational aggregates for Legal Enterprise.

    The migration is idempotent and runs in parallel with legacy Legal V2/V4
    tables. It does not delete or rewrite historical records.
    """
    with db_transaction() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS legal_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL UNIQUE,
                contract_type TEXT NOT NULL,
                effective_date TEXT,
                end_date TEXT,
                renewal_type TEXT NOT NULL DEFAULT 'No renovable',
                notice_days INTEGER NOT NULL DEFAULT 30 CHECK (notice_days >= 0),
                amount REAL CHECK (amount IS NULL OR amount >= 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                governing_law TEXT,
                signature_status TEXT NOT NULL DEFAULT 'Pendiente',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS legal_contract_obligations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                responsible_party TEXT NOT NULL,
                due_date TEXT,
                frequency TEXT NOT NULL DEFAULT 'Unica',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                evidence_required INTEGER NOT NULL DEFAULT 1 CHECK (evidence_required IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contract_id) REFERENCES legal_contracts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_privacy_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                notice_type TEXT NOT NULL,
                version TEXT NOT NULL,
                legal_basis TEXT NOT NULL,
                purposes TEXT NOT NULL,
                data_categories TEXT NOT NULL,
                recipients TEXT,
                retention_policy TEXT,
                published_at TEXT,
                active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE RESTRICT,
                UNIQUE (notice_type, version)
            );

            CREATE TABLE IF NOT EXISTS legal_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                subject_reference TEXT NOT NULL,
                purpose TEXT NOT NULL,
                granted INTEGER NOT NULL CHECK (granted IN (0,1)),
                evidence_reference TEXT,
                source TEXT,
                granted_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (notice_id) REFERENCES legal_privacy_notices(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS legal_litigation_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL UNIQUE,
                proceeding_type TEXT NOT NULL,
                authority TEXT,
                case_number TEXT,
                external_counsel TEXT,
                claim_amount REAL CHECK (claim_amount IS NULL OR claim_amount >= 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                probability TEXT NOT NULL DEFAULT 'Posible',
                provision_amount REAL CHECK (provision_amount IS NULL OR provision_amount >= 0),
                next_hearing_at TEXT,
                strategy TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS legal_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                document_id INTEGER,
                evidence_type TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT,
                collected_by TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                custody_status TEXT NOT NULL DEFAULT 'Custodiada',
                integrity_hash TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE RESTRICT,
                FOREIGN KEY (document_id) REFERENCES legal_documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_risks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                likelihood INTEGER NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
                impact INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
                inherent_score INTEGER NOT NULL CHECK (inherent_score BETWEEN 1 AND 25),
                controls TEXT,
                residual_score INTEGER CHECK (residual_score BETWEEN 1 AND 25),
                owner TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Abierto',
                review_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_compliance_obligations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                regulation TEXT NOT NULL,
                obligation TEXT NOT NULL,
                authority TEXT,
                owner TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'Unica',
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'Pendiente',
                control_reference TEXT,
                evidence_reference TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                license_type TEXT NOT NULL,
                authority TEXT NOT NULL,
                license_number TEXT,
                issue_date TEXT,
                expiration_date TEXT,
                renewal_lead_days INTEGER NOT NULL DEFAULT 60 CHECK (renewal_lead_days >= 0),
                status TEXT NOT NULL DEFAULT 'Vigente',
                owner TEXT NOT NULL,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_governance_meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                body_name TEXT NOT NULL,
                meeting_type TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                quorum_required REAL CHECK (quorum_required IS NULL OR quorum_required BETWEEN 0 AND 100),
                quorum_achieved REAL CHECK (quorum_achieved IS NULL OR quorum_achieved BETWEEN 0 AND 100),
                status TEXT NOT NULL DEFAULT 'Programada',
                minutes_document_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL,
                FOREIGN KEY (minutes_document_id) REFERENCES legal_documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                title TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'Media',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                escalation_level INTEGER NOT NULL DEFAULT 0 CHECK (escalation_level >= 0),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT,
                reminder_days INTEGER NOT NULL DEFAULT 7 CHECK (reminder_days >= 0),
                owner TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Programado',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_legal_contracts_dates ON legal_contracts(effective_date, end_date);
            CREATE INDEX IF NOT EXISTS idx_legal_contract_obligations_due ON legal_contract_obligations(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_legal_consents_subject ON legal_consents(subject_reference, purpose);
            CREATE INDEX IF NOT EXISTS idx_legal_litigation_hearing ON legal_litigation_cases(next_hearing_at);
            CREATE INDEX IF NOT EXISTS idx_legal_risks_status_score ON legal_risks(status, residual_score);
            CREATE INDEX IF NOT EXISTS idx_legal_compliance_due ON legal_compliance_obligations(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_legal_licenses_expiration ON legal_licenses(status, expiration_date);
            CREATE INDEX IF NOT EXISTS idx_legal_tasks_due ON legal_tasks(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_legal_calendar_starts ON legal_calendar_events(status, starts_at);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (MIGRATION_VERSION, MIGRATION_NAME),
        )
