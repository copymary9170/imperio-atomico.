from __future__ import annotations

from database.connection import db_transaction

SCHEMA_VERSION = 1


def migrate() -> None:
    with db_transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS legal_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS legal_v4_matters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                legacy_record_id INTEGER UNIQUE,
                matter_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Borrador',
                risk_level TEXT NOT NULL DEFAULT 'Medio',
                confidentiality TEXT NOT NULL DEFAULT 'Interno',
                owner TEXT NOT NULL,
                reviewer TEXT,
                approver TEXT,
                counterparty TEXT,
                jurisdiction TEXT NOT NULL DEFAULT 'Venezuela',
                due_date TEXT,
                expiration_date TEXT,
                legal_basis TEXT,
                tags TEXT,
                legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0,1)),
                retention_years INTEGER NOT NULL DEFAULT 5 CHECK (retention_years BETWEEN 1 AND 100),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT,
                updated_at TEXT,
                CHECK (risk_level IN ('Bajo','Medio','Alto','Critico')),
                CHECK (confidentiality IN ('Publico','Interno','Confidencial','Restringido'))
            );

            CREATE TABLE IF NOT EXISTS legal_v4_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                change_reason TEXT NOT NULL,
                author TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE RESTRICT,
                UNIQUE (matter_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS legal_v4_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uuid TEXT NOT NULL UNIQUE,
                event_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                before_json TEXT NOT NULL DEFAULT '{}',
                after_json TEXT NOT NULL DEFAULT '{}',
                context_json TEXT NOT NULL DEFAULT '{}',
                previous_hash TEXT,
                event_hash TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS legal_v4_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                title TEXT NOT NULL,
                assigned_to TEXT,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'Media',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_status ON legal_v4_matters(status);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_type ON legal_v4_matters(matter_type);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_due ON legal_v4_matters(due_date, expiration_date);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_audit_entity ON legal_v4_audit(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_tasks_due ON legal_v4_tasks(status, due_date);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_schema_migrations(version,name) VALUES(?,?)",
            (SCHEMA_VERSION, "legal_v4_initial"),
        )
