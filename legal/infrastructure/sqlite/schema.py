from __future__ import annotations

from database.connection import db_transaction

ENTERPRISE_SCHEMA_VERSION = 101


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

            CREATE TABLE IF NOT EXISTS legal_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL UNIQUE,
                contract_type TEXT NOT NULL,
                counterparty_id INTEGER,
                start_date TEXT,
                end_date TEXT,
                renewal_notice_days INTEGER NOT NULL DEFAULT 30,
                amount NUMERIC NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                auto_renew INTEGER NOT NULL DEFAULT 0 CHECK (auto_renew IN (0,1)),
                termination_terms TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE,
                FOREIGN KEY (counterparty_id) REFERENCES legal_parties(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_privacy_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                record_type TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                legal_basis TEXT NOT NULL DEFAULT '',
                data_categories TEXT NOT NULL DEFAULT '',
                retention_rule TEXT NOT NULL DEFAULT '',
                published_version TEXT,
                published_at TEXT,
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                subject_name TEXT NOT NULL,
                subject_contact TEXT,
                purpose TEXT NOT NULL,
                legal_basis TEXT NOT NULL,
                consent_text TEXT NOT NULL,
                granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT,
                source TEXT,
                evidence_document_id INTEGER,
                FOREIGN KEY (evidence_document_id) REFERENCES legal_documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_litigation_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL UNIQUE,
                court_or_authority TEXT,
                external_counsel TEXT,
                case_number TEXT,
                claim_amount NUMERIC NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                procedural_stage TEXT NOT NULL DEFAULT 'Inicial',
                next_hearing TEXT,
                strategy_summary TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legal_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                document_id INTEGER,
                evidence_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                custody_owner TEXT NOT NULL,
                collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                chain_of_custody TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES legal_documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_compliance_obligations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                obligation_type TEXT NOT NULL,
                title TEXT NOT NULL,
                authority TEXT,
                frequency TEXT NOT NULL DEFAULT 'Unica',
                due_date TEXT,
                owner TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pendiente',
                evidence_required INTEGER NOT NULL DEFAULT 1 CHECK (evidence_required IN (0,1)),
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_risks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER,
                risk_title TEXT NOT NULL,
                category TEXT NOT NULL,
                probability INTEGER NOT NULL CHECK (probability BETWEEN 1 AND 5),
                impact INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
                treatment TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL,
                accepted INTEGER NOT NULL DEFAULT 0 CHECK (accepted IN (0,1)),
                FOREIGN KEY (matter_id) REFERENCES legal_matters(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS legal_governance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matter_id INTEGER NOT NULL,
                body_name TEXT NOT NULL,
                record_type TEXT NOT NULL,
                meeting_date TEXT,
                quorum TEXT,
                resolution TEXT NOT NULL DEFAULT '',
                follow_up_owner TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_legal_contracts_dates ON legal_contracts(start_date, end_date);
            CREATE INDEX IF NOT EXISTS idx_legal_compliance_due ON legal_compliance_obligations(status, due_date);
            CREATE INDEX IF NOT EXISTS idx_legal_risks_score ON legal_risks(probability, impact);
            CREATE INDEX IF NOT EXISTS idx_legal_audit_entity ON legal_audit_events(entity_type, entity_id);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (100, "enterprise_legal_foundation"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (101, "enterprise_legal_domains"),
        )
