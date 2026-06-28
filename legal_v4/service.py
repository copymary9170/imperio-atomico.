from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import uuid4

import pandas as pd

from database.connection import db_transaction
from legal_v4.domain import CreateMatterCommand
from legal_v4.schema import migrate


class LegalService:
    def __init__(self) -> None:
        migrate()

    def _audit(self, actor: str, action: str, entity_type: str, entity_id: int | None, before: dict | None = None, after: dict | None = None, context: dict | None = None) -> None:
        before_json = json.dumps(before or {}, ensure_ascii=False, sort_keys=True, default=str)
        after_json = json.dumps(after or {}, ensure_ascii=False, sort_keys=True, default=str)
        context_json = json.dumps(context or {}, ensure_ascii=False, sort_keys=True, default=str)
        with db_transaction() as conn:
            row = conn.execute("SELECT event_hash FROM legal_v4_audit ORDER BY id DESC LIMIT 1").fetchone()
            previous_hash = row["event_hash"] if row else ""
            event_uuid = str(uuid4())
            payload = "|".join([event_uuid, actor, action, entity_type, str(entity_id or ""), before_json, after_json, context_json, previous_hash])
            event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            conn.execute(
                """INSERT INTO legal_v4_audit(event_uuid,actor,action,entity_type,entity_id,before_json,after_json,context_json,previous_hash,event_hash)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (event_uuid, actor, action, entity_type, entity_id, before_json, after_json, context_json, previous_hash, event_hash),
            )

    def create_matter(self, command: CreateMatterCommand, actor: str) -> int:
        command.validate()
        now = datetime.now().isoformat()
        with db_transaction() as conn:
            next_id = int(conn.execute("SELECT COALESCE(MAX(id),0)+1 AS n FROM legal_v4_matters").fetchone()["n"])
            code = f"LEG-{datetime.now().year}-{next_id:06d}"
            matter_uuid = str(uuid4())
            cur = conn.execute(
                """INSERT INTO legal_v4_matters(uuid,code,matter_type,title,description,owner,reviewer,approver,created_by,updated_by,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (matter_uuid, code, command.matter_type, command.title.strip(), command.description.strip(), command.owner.strip(), command.reviewer.strip(), command.approver.strip(), actor, actor, now),
            )
            matter_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO legal_v4_versions(matter_id,version_number,content,change_reason,author) VALUES(?,?,?,?,?)",
                (matter_id, 1, command.description.strip(), "Version inicial", actor),
            )
        self._audit(actor, "CREATE", "legal_matter", matter_id, after={"code": code, "title": command.title, "type": command.matter_type})
        return matter_id

    def list_matters(self) -> pd.DataFrame:
        with db_transaction() as conn:
            return pd.read_sql_query("SELECT * FROM legal_v4_matters ORDER BY id DESC", conn)

    def dashboard(self) -> dict:
        matters = self.list_matters()
        if matters.empty:
            return {"total": 0, "active": 0, "critical": 0, "overdue": 0}
        today = pd.Timestamp.today().normalize()
        due = pd.to_datetime(matters["expiration_date"].fillna(matters["due_date"]), errors="coerce")
        open_mask = ~matters["status"].isin(["Cerrado", "Archivado"])
        return {
            "total": len(matters),
            "active": int(matters["status"].isin(["Vigente", "Aprobado"]).sum()),
            "critical": int(matters["risk_level"].isin(["Alto", "Critico"]).sum()),
            "overdue": int((due.notna() & (due < today) & open_mask).sum()),
        }

    def migrate_legacy(self, actor: str) -> int:
        imported = 0
        with db_transaction() as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legal_enterprise_records'").fetchone()
            if not exists:
                return 0
            rows = conn.execute("SELECT * FROM legal_enterprise_records ORDER BY id").fetchall()
            for row in rows:
                present = conn.execute("SELECT id FROM legal_v4_matters WHERE legacy_record_id=?", (row["id"],)).fetchone()
                if present:
                    continue
                cur = conn.execute(
                    """INSERT INTO legal_v4_matters(uuid,code,legacy_record_id,matter_type,title,description,status,risk_level,confidentiality,owner,reviewer,approver,counterparty,jurisdiction,due_date,expiration_date,legal_basis,tags,legal_hold,retention_years,created_by,created_at,updated_by,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["uuid"], row["code"], row["id"], row["module_name"], row["title"], row["description"] or "Sin descripcion", row["status"], "Critico" if row["risk_level"] == "Crítico" else row["risk_level"], "Publico" if row["confidentiality"] == "Público" else row["confidentiality"], row["owner"], row["reviewer"], row["approver"], row["counterparty"], row["jurisdiction"] or "Venezuela", row["due_date"], row["expiration_date"], row["legal_basis"], row["tags"], row["legal_hold"], row["retention_years"], row["created_by"], row["created_at"], row["updated_by"], row["updated_at"]),
                )
                conn.execute("INSERT INTO legal_v4_versions(matter_id,version_number,content,change_reason,author) VALUES(?,?,?,?,?)", (int(cur.lastrowid), 1, row["description"] or "", "Importado desde Legal V2", actor))
                imported += 1
        if imported:
            self._audit(actor, "MIGRATE_LEGACY", "legal_matter", None, after={"imported": imported})
        return imported
