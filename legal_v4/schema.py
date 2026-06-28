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
                legacy_version_id INTEGER UNIQUE,
                version_number INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Borrador',
                content TEXT NOT NULL DEFAULT '',
                change_reason TEXT NOT NULL,
                author TEXT NOT NULL,
                reviewer TEXT,
                approver TEXT,
                effective_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE RESTRICT,
                UNIQUE (matter_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS legal_v4_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                matter_id INTEGER NOT NULL,
                version_id INTEGER,
                legacy_file_id INTEGER UNIQUE,
                document_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0 CHECK(size_bytes >= 0),
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                mandatory INTEGER NOT NULL DEFAULT 0 CHECK (mandatory IN (0,1)),
                signed INTEGER NOT NULL DEFAULT 0 CHECK (signed IN (0,1)),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE RESTRICT,
                FOREIGN KEY (version_id) REFERENCES legal_v4_versions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_v4_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                document_id INTEGER NOT NULL,
                signer TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'manual',
                signature_hash TEXT NOT NULL,
                signed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (document_id) REFERENCES legal_v4_documents(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS legal_v4_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                parent_id INTEGER,
                comment_type TEXT NOT NULL DEFAULT 'Nota',
                body TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0,1)),
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES legal_v4_comments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_v4_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                legacy_calendar_id INTEGER UNIQUE,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                alert_days INTEGER NOT NULL DEFAULT 7 CHECK(alert_days >= 0),
                owner TEXT,
                status TEXT NOT NULL DEFAULT 'Pendiente',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_v4_controls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                control_area TEXT NOT NULL,
                control_name TEXT NOT NULL,
                requirement TEXT NOT NULL,
                evidence_required TEXT,
                owner TEXT,
                frequency TEXT NOT NULL DEFAULT 'Evento',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                last_review_date TEXT,
                next_review_date TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_v4_risk_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),
                likelihood INTEGER NOT NULL CHECK(likelihood BETWEEN 1 AND 5),
                score INTEGER GENERATED ALWAYS AS (impact * likelihood) VIRTUAL,
                treatment TEXT NOT NULL,
                owner TEXT,
                accepted_by TEXT,
                review_date TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE
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
                legacy_task_id INTEGER UNIQUE,
                task_type TEXT NOT NULL DEFAULT 'General',
                title TEXT NOT NULL,
                assigned_to TEXT,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'Media',
                status TEXT NOT NULL DEFAULT 'Pendiente',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_v4_matters(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_status ON legal_v4_matters(status);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_type ON legal_v4_matters(matter_type);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_matters_due ON legal_v4_matters(due_date, expiration_date);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_documents_matter ON legal_v4_documents(matter_id, active);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_documents_hash ON legal_v4_documents(sha256);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_calendar_due ON legal_v4_calendar(status, event_date);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_controls_status ON legal_v4_controls(control_area, status);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_audit_entity ON legal_v4_audit(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_legal_v4_tasks_due ON legal_v4_tasks(status, due_date);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_schema_migrations(version,name) VALUES(?,?)",
            (1, "legal_v4_initial"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_schema_migrations(version,name) VALUES(?,?)",
            (SCHEMA_VERSION, "legal_v4_enterprise_operations"),
        )
