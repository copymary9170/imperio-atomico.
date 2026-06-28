from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from database.connection import db_transaction
from legal_v4.domain import CreateMatterCommand, ensure_can_attach_document, validate_transition
from legal_v4.schema import migrate

DOCUMENT_ROOT = Path("data/legal_v4_documents")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "webp", "txt", "eml", "msg"}
MAX_DOCUMENT_MB = 25


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

    def list_documents(self, matter_id: int | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM legal_v4_documents WHERE active=1"
        params: tuple = ()
        if matter_id:
            sql += " AND matter_id=?"
            params = (matter_id,)
        sql += " ORDER BY id DESC"
        with db_transaction() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def list_obligations(self) -> pd.DataFrame:
        with db_transaction() as conn:
            return pd.read_sql_query("SELECT * FROM legal_v4_obligations ORDER BY id DESC", conn)

    def list_audit(self, limit: int = 200) -> pd.DataFrame:
        with db_transaction() as conn:
            return pd.read_sql_query("SELECT * FROM legal_v4_audit ORDER BY id DESC LIMIT ?", conn, params=(limit,))

    def change_status(self, matter_id: int, target_status: str, comment: str, actor: str) -> None:
        with db_transaction() as conn:
            row = conn.execute("SELECT * FROM legal_v4_matters WHERE id=?", (matter_id,)).fetchone()
            if not row:
                raise ValueError("Expediente no encontrado.")
            before = dict(row)
            validate_transition(before["status"], target_status, before.get("approver") or "", comment)
            conn.execute("UPDATE legal_v4_matters SET status=?,updated_by=?,updated_at=? WHERE id=?", (target_status, actor, datetime.now().isoformat(), matter_id))
            conn.execute("INSERT INTO legal_v4_workflow_events(matter_id,from_status,to_status,comment,actor) VALUES(?,?,?,?,?)", (matter_id, before["status"], target_status, comment.strip(), actor))
        after = dict(before)
        after["status"] = target_status
        self._audit(actor, "STATUS_CHANGE", "legal_matter", matter_id, before=before, after=after, context={"comment": comment})

    def attach_document(self, matter_id: int, uploaded, document_type: str, signed: bool, actor: str, signature_provider: str = "", signature_reference: str = "") -> int:
        raw = uploaded.getvalue()
        if len(raw) > MAX_DOCUMENT_MB * 1024 * 1024:
            raise ValueError(f"El archivo supera {MAX_DOCUMENT_MB} MB.")
        extension = Path(uploaded.name).suffix.lower().lstrip(".")
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Formato documental no permitido.")
        sha256 = hashlib.sha256(raw).hexdigest()
        with db_transaction() as conn:
            matter = conn.execute("SELECT * FROM legal_v4_matters WHERE id=?", (matter_id,)).fetchone()
            if not matter:
                raise ValueError("Expediente no encontrado.")
            ensure_can_attach_document(matter["status"], signed)
            duplicate = conn.execute("SELECT id FROM legal_v4_documents WHERE matter_id=? AND sha256=? AND active=1", (matter_id, sha256)).fetchone()
            if duplicate:
                raise ValueError("El documento ya existe en el expediente.")
            current_version = conn.execute("SELECT id FROM legal_v4_versions WHERE matter_id=? AND is_current=1", (matter_id,)).fetchone()
        DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}.{extension}"
        destination = DOCUMENT_ROOT / stored_name
        destination.write_bytes(raw)
        mime_type = mimetypes.guess_type(uploaded.name)[0] or "application/octet-stream"
        with db_transaction() as conn:
            cur = conn.execute(
                """INSERT INTO legal_v4_documents(matter_id,version_id,uuid,document_type,original_name,stored_name,extension,mime_type,size_bytes,sha256,storage_path,signed,signature_provider,signature_reference,legal_hold,uploaded_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (matter_id, int(current_version["id"]) if current_version else None, str(uuid4()), document_type, uploaded.name, stored_name, extension, mime_type, len(raw), sha256, str(destination), int(signed), signature_provider.strip(), signature_reference.strip(), int(signed), actor),
            )
            document_id = int(cur.lastrowid)
        self._audit(actor, "ATTACH_DOCUMENT", "legal_document", document_id, after={"matter_id": matter_id, "name": uploaded.name, "sha256": sha256, "signed": signed})
        return document_id

    def create_obligation(self, matter_id: int | None, title: str, owner: str, actor: str, obligation_type: str = "Cumplimiento", due_date: str | None = None, description: str = "") -> int:
        if not title.strip() or not owner.strip():
            raise ValueError("Titulo y responsable de la obligacion son obligatorios.")
        with db_transaction() as conn:
            cur = conn.execute(
                """INSERT INTO legal_v4_obligations(matter_id,obligation_type,title,description,owner,due_date,created_by)
                   VALUES(?,?,?,?,?,?,?)""",
                (matter_id, obligation_type, title.strip(), description.strip(), owner.strip(), due_date, actor),
            )
            obligation_id = int(cur.lastrowid)
        self._audit(actor, "CREATE_OBLIGATION", "legal_obligation", obligation_id, after={"matter_id": matter_id, "title": title, "owner": owner})
        return obligation_id

    def dashboard(self) -> dict:
        matters = self.list_matters()
        documents = self.list_documents()
        obligations = self.list_obligations()
        if matters.empty:
            return {"total": 0, "active": 0, "critical": 0, "overdue": 0, "documents": len(documents), "obligations": len(obligations)}
        today = pd.Timestamp.today().normalize()
        due = pd.to_datetime(matters["expiration_date"].fillna(matters["due_date"]), errors="coerce")
        open_mask = ~matters["status"].isin(["Cerrado", "Archivado"])
        return {
            "total": len(matters),
            "active": int(matters["status"].isin(["Vigente", "Aprobado"]).sum()),
            "critical": int(matters["risk_level"].isin(["Alto", "Critico"]).sum()),
            "overdue": int((due.notna() & (due < today) & open_mask).sum()),
            "documents": len(documents),
            "obligations": len(obligations),
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
