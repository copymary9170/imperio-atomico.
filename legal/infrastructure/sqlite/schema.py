from __future__ import annotations

from database.connection import db_transaction

ENTERPRISE_SCHEMA_VERSION = 100


def migrate_enterprise_legal() -> None:
    """Create the enterprise legal schema in parallel to legacy V4 tables."""

    with db_transaction() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS legal_enterprise_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS legal_matters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                legacy_source TEXT,
                legacy_record_id INTEGER,
                area TEXT NOT NULL,
                matter_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
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
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT,
                updated_at TEXT,
                CHECK (status IN ('Borrador','En revision','Cambios solicitados','Aprobado','Pendiente de firma','Vigente','Suspendido','Cerrado','Archivado')),
                CHECK (risk_level IN ('Bajo','Medio','Alto','Critico')),
                CHECK (confidentiality IN ('Publico','Interno','Confidencial','Restringido')),
                UNIQUE (legacy_source, legacy_record_id)
            );

            CREATE TABLE IF NOT EXISTS legal_parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                party_type TEXT NOT NULL,
                name TEXT NOT NULL,
                tax_id TEXT,
                email TEXT,
                phone TEXT,
                address TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS legal_matter_parties (
                matter_id INTEGER NOT NULL,
                party_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (matter_id, party_id, role),
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES legal_parties(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS legal_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                matter_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                title TEXT NOT NULL,
                original_name TEXT,
                storage_path TEXT,
                sha256 TEXT,
                classification TEXT NOT NULL DEFAULT 'Interno',
                version_number INTEGER NOT NULL DEFAULT 1,
                is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
                signed INTEGER NOT NULL DEFAULT 0 CHECK (signed IN (0,1)),
                legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0,1)),
                retention_until TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE RESTRICT,
                UNIQUE (matter_id, title, version_number)
            );

            CREATE TABLE IF NOT EXISTS legal_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'matter',
                entity_id INTEGER,
                comment TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uuid TEXT NOT NULL UNIQUE,
                event_time TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                before_json TEXT NOT NULL DEFAULT '{}',
                after_json TEXT NOT NULL DEFAULT '{}',
                context_json TEXT NOT NULL DEFAULT '{}',
                previous_hash TEXT,
                event_hash TEXT NOT NULL UNIQUE
            );

            CREATE INDEX IF NOT EXISTS idx_legal_matters_area_status ON legal_matters(area, status);
            CREATE INDEX IF NOT EXISTS idx_legal_matters_due ON legal_matters(due_date, expiration_date);
            CREATE INDEX IF NOT EXISTS idx_legal_documents_matter ON legal_documents(matter_id, is_current);
            CREATE INDEX IF NOT EXISTS idx_legal_audit_entity ON legal_audit_events(entity_type, entity_id);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (ENTERPRISE_SCHEMA_VERSION, "enterprise_legal_foundation"),
        )
