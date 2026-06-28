from __future__ import annotations

from database.connection import db_transaction

SCHEMA_VERSION = 2


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

            CREATE TABLE IF NOT EXISTS legal_v4_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                version_id INTEGER,
                uuid TEXT NOT NULL UNIQUE,
                document_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                signed INTEGER NOT NULL DEFAULT 0 CHECK (signed IN (0,1)),
                signature_provider TEXT,
                signature_reference TEXT,
                retention_until TEXT,
                legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0,1)),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE RESTRICT,
                FOREIGN KEY (version_id) REFERENCES legal_v4_versions(id) ON DELETE SET NULL,
                UNIQUE (matter_id, sha256, active)
            );

            CREATE TABLE IF NOT EXISTS legal_v4_workflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                from_status TEXT NOT NULL,
                to_status TEXT NOT NULL,
                comment TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_v4_obligations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                obligation_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL,
                due_date TEXT,
                frequency TEXT NOT NULL DEFAULT 'Unica',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                evidence_required INTEGER NOT NULL DEFAULT 1 CHECK (evidence_required IN (0,1)),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE SET NULL
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
            CREATE INDEX IF NOT EXISTS idx_legal_v4_documents_matter ON legal_v4_documents(matter_id, active);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_documents_hash ON legal_v4_documents(sha256);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_obligations_due ON legal_v4_obligations(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_workflow_matter ON legal_v4_workflow_events(matter_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_audit_entity ON legal_v4_audit(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_tasks_due ON legal_v4_tasks(status, due_date);
            """
        )
        conn.execute("INSERT OR IGNORE INTO legal_schema_migrations(version,name) VALUES(?,?)", (1, "legal_v4_initial"))
        conn.execute("INSERT OR IGNORE INTO legal_schema_migrations(version,name) VALUES(?,?)", (2, "legal_v4_documents_workflows"))
