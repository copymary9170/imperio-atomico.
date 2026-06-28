from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission

RELEASE = "2026.06.28 · Legal Enterprise V3"
STORAGE_ROOT = Path("data/legal_files_v3")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "webp", "txt", "eml", "msg", "mp3", "wav", "mp4"}
MAX_FILE_MB = 20

WORKFLOWS = {
    "documento": ["Borrador", "En revisión", "Cambios solicitados", "Aprobado", "Publicado", "Vigente", "Archivado"],
    "contrato": ["Borrador", "En negociación", "En revisión", "Aprobado", "Pendiente de firma", "Firmado", "Vigente", "Suspendido", "Vencido", "Terminado", "Archivado"],
    "caso": ["Registrado", "En análisis", "En proceso", "Escalado", "Resuelto", "Cerrado", "Archivado"],
    "riesgo": ["Identificado", "Evaluado", "Tratamiento", "Monitoreo", "Aceptado", "Cerrado"],
    "registro": ["Borrador", "Presentado", "En trámite", "Observado", "Concedido", "Vigente", "Vencido", "Archivado"],
}

MODULE_SPECS = {
    "AVISO_LEGAL": {"name": "Aviso Legal", "workflow": "documento", "docs": ["Borrador editable", "PDF aprobado"]},
    "TERMINOS": {"name": "Términos y Condiciones", "workflow": "documento", "docs": ["Borrador editable", "PDF aprobado", "Evidencia de publicación"]},
    "PRIVACIDAD": {"name": "Política de Privacidad", "workflow": "documento", "docs": ["Inventario de tratamientos", "Borrador editable", "PDF aprobado", "Evidencia de publicación"]},
    "COOKIES": {"name": "Política de Cookies", "workflow": "documento", "docs": ["Inventario de cookies", "Borrador editable", "PDF aprobado"]},
    "CONSENTIMIENTOS": {"name": "Consentimientos", "workflow": "documento", "docs": ["Texto de consentimiento", "Evidencia de aceptación"]},
    "PROPIEDAD_INTELECTUAL": {"name": "Propiedad Intelectual", "workflow": "registro", "docs": ["Documento de titularidad", "Evidencia de creación"]},
    "MARCAS": {"name": "Marcas", "workflow": "registro", "docs": ["Logo o signo", "Solicitud", "Comprobante", "Certificado"]},
    "DERECHOS_AUTOR": {"name": "Derechos de Autor", "workflow": "registro", "docs": ["Obra o muestra", "Declaración de autoría", "Certificado"]},
    "GESTION_CONTRACTUAL": {"name": "Gestión Contractual", "workflow": "contrato", "docs": ["Solicitud contractual", "Borrador editable", "Contrato firmado"]},
    "CONTRATOS_CLIENTES": {"name": "Contratos con Clientes", "workflow": "contrato", "docs": ["Identificación o registro mercantil", "RIF", "Borrador editable", "Contrato firmado"]},
    "CONTRATOS_PROVEEDORES": {"name": "Contratos con Proveedores", "workflow": "contrato", "docs": ["Registro mercantil", "RIF", "Datos bancarios", "Borrador editable", "Contrato firmado"]},
    "CONTRATOS_LABORALES": {"name": "Contratos Laborales", "workflow": "contrato", "docs": ["Documento de identidad", "Datos laborales", "Contrato firmado"]},
    "GARANTIAS": {"name": "Garantías", "workflow": "caso", "docs": ["Factura", "Serial o lote", "Evidencia fotográfica", "Diagnóstico"]},
    "DEVOLUCIONES": {"name": "Devoluciones", "workflow": "caso", "docs": ["Factura", "Solicitud del cliente", "Evidencia", "Acta de devolución"]},
    "RECLAMOS": {"name": "Reclamos", "workflow": "caso", "docs": ["Reclamo original", "Factura", "Evidencias", "Respuesta final"]},
    "LITIGIOS": {"name": "Litigios", "workflow": "caso", "docs": ["Demanda o escrito", "Poder", "Evidencias", "Actuaciones judiciales"]},
    "RIESGOS": {"name": "Gestión de Riesgos", "workflow": "riesgo", "docs": ["Matriz de riesgo", "Plan de tratamiento"]},
    "DEMANDAS": {"name": "Gestión de Demandas", "workflow": "caso", "docs": ["Demanda", "Poder", "Evidencias", "Decisiones"]},
    "EVIDENCIAS": {"name": "Evidencias", "workflow": "caso", "docs": ["Archivo original", "Acta de cadena de custodia"]},
    "DOCUMENTACION": {"name": "Documentación Legal", "workflow": "documento", "docs": ["Documento fuente"]},
    "LICENCIAS": {"name": "Licencias", "workflow": "registro", "docs": ["Solicitud", "Comprobante", "Licencia emitida"]},
    "PERMISOS": {"name": "Permisos", "workflow": "registro", "docs": ["Solicitud", "Comprobante", "Permiso emitido"]},
    "NORMATIVAS": {"name": "Normativas", "workflow": "documento", "docs": ["Fuente normativa", "Análisis de impacto"]},
    "CUMPLIMIENTO": {"name": "Cumplimiento", "workflow": "riesgo", "docs": ["Lista de verificación", "Evidencias", "Plan de acción"]},
    "AUDITORIA": {"name": "Auditoría", "workflow": "caso", "docs": ["Plan de auditoría", "Papeles de trabajo", "Informe final"]},
    "FIRMA_DIGITAL": {"name": "Firma Digital", "workflow": "documento", "docs": ["Documento a firmar", "Evidencia de firma"]},
    "CAMBIOS": {"name": "Registro de Cambios", "workflow": "documento", "docs": ["Solicitud de cambio", "Aprobación"]},
    "VERSIONES": {"name": "Control de Versiones", "workflow": "documento", "docs": ["Documento versionado"]},
    "ARCHIVO": {"name": "Archivo Jurídico", "workflow": "documento", "docs": ["Índice documental"]},
    "CALENDARIO": {"name": "Calendario Legal", "workflow": "caso", "docs": []},
    "NOTIFICACIONES": {"name": "Notificaciones", "workflow": "caso", "docs": ["Constancia de envío"]},
    "CONFIGURACION": {"name": "Configuración Jurídica", "workflow": "documento", "docs": ["Solicitud de configuración", "Aprobación"]},
}

TRANSITION_PERMISSION = {
    "En revisión": "legal.review",
    "Aprobado": "legal.approve",
    "Publicado": "legal.publish",
    "Pendiente de firma": "legal.sign",
    "Firmado": "legal.sign",
    "Vigente": "legal.approve",
    "Aceptado": "legal.approve",
    "Concedido": "legal.approve",
}


def _ensure_schema() -> None:
    with db_transaction() as conn:
        conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS legal_v3_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT NOT NULL UNIQUE, code TEXT NOT NULL UNIQUE,
            module_code TEXT NOT NULL, module_name TEXT NOT NULL, workflow_type TEXT NOT NULL,
            title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, risk_level TEXT NOT NULL DEFAULT 'Medio',
            confidentiality TEXT NOT NULL DEFAULT 'Interno', owner_user TEXT NOT NULL, reviewer_user TEXT, approver_user TEXT,
            counterparty TEXT, counterparty_tax_id TEXT, jurisdiction TEXT DEFAULT 'Venezuela', start_date TEXT, due_date TEXT,
            expiration_date TEXT, amount REAL DEFAULT 0, currency TEXT DEFAULT 'USD', legal_basis TEXT, tags TEXT,
            retention_years INTEGER DEFAULT 5, legal_hold INTEGER DEFAULT 0, current_version INTEGER DEFAULT 1,
            created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_by TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_v3_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL, version_number INTEGER NOT NULL,
            version_label TEXT NOT NULL, status TEXT NOT NULL, content TEXT, change_reason TEXT NOT NULL,
            author TEXT NOT NULL, reviewer TEXT, approver TEXT, effective_date TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_current INTEGER DEFAULT 1, restored_from INTEGER, FOREIGN KEY(record_id) REFERENCES legal_v3_records(id),
            UNIQUE(record_id, version_number)
        );
        CREATE TABLE IF NOT EXISTS legal_v3_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL, version_id INTEGER, document_type TEXT NOT NULL,
            original_name TEXT NOT NULL, stored_name TEXT NOT NULL, extension TEXT NOT NULL, mime_type TEXT,
            size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, storage_path TEXT NOT NULL, mandatory INTEGER DEFAULT 0,
            signed INTEGER DEFAULT 0, signature_provider TEXT, uploaded_by TEXT NOT NULL, uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1, FOREIGN KEY(record_id) REFERENCES legal_v3_records(id),
            FOREIGN KEY(version_id) REFERENCES legal_v3_versions(id)
        );
        CREATE TABLE IF NOT EXISTS legal_v3_obligations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL, title TEXT NOT NULL, obligated_party TEXT,
            due_date TEXT, amount REAL DEFAULT 0, currency TEXT DEFAULT 'USD', status TEXT DEFAULT 'Pendiente',
            evidence_required INTEGER DEFAULT 0, owner_user TEXT, created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT, FOREIGN KEY(record_id) REFERENCES legal_v3_records(id)
        );
        CREATE TABLE IF NOT EXISTS legal_v3_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER, task_type TEXT NOT NULL, title TEXT NOT NULL,
            assigned_to TEXT, due_date TEXT, status TEXT DEFAULT 'Pendiente', priority TEXT DEFAULT 'Media', source_key TEXT UNIQUE,
            created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
            FOREIGN KEY(record_id) REFERENCES legal_v3_records(id)
        );
        CREATE TABLE IF NOT EXISTS legal_v3_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_uuid TEXT NOT NULL UNIQUE, event_time TEXT DEFAULT CURRENT_TIMESTAMP,
            user TEXT NOT NULL, ip_address TEXT, device TEXT, browser TEXT, session_id TEXT, action TEXT NOT NULL,
            entity TEXT NOT NULL, entity_id INTEGER, record_id INTEGER, module_code TEXT, before_json TEXT, after_json TEXT,
            comments TEXT, result TEXT NOT NULL DEFAULT 'Exitoso', prev_hash TEXT, event_hash TEXT NOT NULL
        );
        """)


def _context() -> dict:
    ctx = getattr(st, "context", None)
    headers = getattr(ctx, "headers", {}) if ctx else {}
    return {
        "ip": str(headers.get("X-Forwarded-For") or headers.get("X-Real-Ip") or ""),
        "device": str(headers.get("Sec-Ch-Ua-Platform") or ""),
        "browser": str(headers.get("User-Agent") or ""),
        "session": str(st.session_state.get("session_id") or ""),
    }


def _audit(user: str, action: str, entity: str, entity_id: int | None, record_id: int | None, module_code: str | None,
           before: dict | None = None, after: dict | None = None, comments: str = "", result: str = "Exitoso") -> None:
    context = _context()
    with db_transaction() as conn:
        previous = conn.execute("SELECT event_hash FROM legal_v3_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = str(previous["event_hash"]) if previous else "GENESIS"
        payload = json.dumps({"user": user, "action": action, "entity": entity, "entity_id": entity_id,
                              "record_id": record_id, "before": before or {}, "after": after or {},
                              "comments": comments, "prev_hash": prev_hash}, ensure_ascii=False, sort_keys=True, default=str)
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        conn.execute("""INSERT INTO legal_v3_audit(event_uuid,user,ip_address,device,browser,session_id,action,entity,entity_id,
                     record_id,module_code,before_json,after_json,comments,result,prev_hash,event_hash)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (str(uuid4()), user, context["ip"], context["device"], context["browser"], context["session"], action,
                      entity, entity_id, record_id, module_code, json.dumps(before or {}, ensure_ascii=False, default=str),
                      json.dumps(after or {}, ensure_ascii=False, default=str), comments, result, prev_hash, event_hash))


def _read(sql: str, params: tuple = ()) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _can_view_record(row: pd.Series | dict, user: str) -> bool:
    confidentiality = str(row.get("confidentiality") or "Interno")
    if confidentiality == "Restringido" and not (has_permission("legal.restricted.view") or has_permission("legal.admin")):
        return str(row.get("owner_user")) == user or str(row.get("reviewer_user")) == user or str(row.get("approver_user")) == user
    if confidentiality == "Confidencial" and not (has_permission("legal.confidential.view") or has_permission("legal.admin")):
        return str(row.get("owner_user")) == user or str(row.get("reviewer_user")) == user or str(row.get("approver_user")) == user
    return True


def _next_code(module_code: str) -> str:
    prefix = module_code[:4].replace("_", "")
    with db_transaction() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id),0)+1 n FROM legal_v3_records").fetchone()
    return f"{prefix}-{date.today().year}-{int(row['n']):06d}"


def _validate_people(user: str, reviewer: str, approver: str) -> None:
    people = [p.strip().casefold() for p in (user, reviewer, approver) if p and p.strip()]
    if len(people) != len(set(people)):
        raise ValueError("Creador, revisor y aprobador deben ser usuarios distintos.")


def _required_documents(record_id: int, module_code: str) -> pd.DataFrame:
    expected = MODULE_SPECS[module_code]["docs"]
    loaded = _read("SELECT document_type,mandatory,signed FROM legal_v3_files WHERE record_id=? AND active=1", (record_id,))
    present = set(loaded["document_type"].astype(str).tolist()) if not loaded.empty else set()
    return pd.DataFrame([{"Documento": name, "Obligatorio": True, "Cargado": name in present} for name in expected])


def _change_status(record_id: int, target: str, comment: str, user: str) -> None:
    permission = TRANSITION_PERMISSION.get(target, "legal.edit")
    if not (has_permission(permission) or has_permission("legal.admin")):
        raise PermissionError(f"La transición a {target} requiere el permiso {permission}.")
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM legal_v3_records WHERE id=?", (record_id,)).fetchone()
        if not row:
            raise ValueError("Expediente no encontrado.")
        before = dict(row)
        states = WORKFLOWS[before["workflow_type"]]
        current = before["status"]
        allowed = target == current or (current in states and target in states and states.index(target) == states.index(current) + 1) or target in {"Archivado", "Suspendido", "Cambios solicitados", "Escalado"}
        if not allowed:
            raise ValueError(f"Transición no permitida: {current} → {target}.")
        if target in {"Aprobado", "Publicado", "Firmado", "Vigente", "Aceptado", "Concedido"}:
            if not before.get("approver_user"):
                raise ValueError("Debe asignarse un aprobador.")
            if str(before.get("approver_user")).casefold() != user.casefold() and not has_permission("legal.admin"):
                raise PermissionError("Solo el aprobador asignado puede ejecutar esta transición.")
        if target in {"Publicado", "Firmado", "Vigente", "Concedido"}:
            matrix = _required_documents(record_id, before["module_code"])
            if not matrix.empty and not bool(matrix["Cargado"].all()):
                missing = ", ".join(matrix.loc[~matrix["Cargado"], "Documento"].tolist())
                raise ValueError(f"Faltan documentos obligatorios: {missing}.")
        if target in {"Archivado", "Suspendido", "Vencido", "Terminado", "Cerrado"} and not comment.strip():
            raise ValueError("El motivo es obligatorio para esta transición.")
        conn.execute("UPDATE legal_v3_records SET status=?,updated_by=?,updated_at=? WHERE id=?",
                     (target, user, pd.Timestamp.now().isoformat(), record_id))
    after = dict(before); after["status"] = target
    _audit(user, "STATUS_CHANGE", "record", record_id, record_id, before["module_code"], before, after, comment)


def _create_record(data: dict, user: str) -> int:
    if not (has_permission("legal.create") or has_permission("legal.admin")):
        raise PermissionError("No tienes permiso para crear expedientes.")
    _validate_people(user, data.get("reviewer_user", ""), data.get("approver_user", ""))
    payload = dict(data)
    payload.update({"uuid": str(uuid4()), "created_by": user, "updated_by": user, "updated_at": pd.Timestamp.now().isoformat()})
    with db_transaction() as conn:
        keys = list(payload)
        cur = conn.execute(f"INSERT INTO legal_v3_records ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [payload[k] for k in keys])
        record_id = int(cur.lastrowid)
        conn.execute("""INSERT INTO legal_v3_versions(record_id,version_number,version_label,status,content,change_reason,author,reviewer,approver,is_current)
                     VALUES(?,?,?,?,?,?,?,?,?,1)""", (record_id, 1, "1.0", payload["status"], payload["description"], "Versión inicial",
                     user, payload.get("reviewer_user"), payload.get("approver_user")))
    _audit(user, "CREATE", "record", record_id, record_id, payload["module_code"], after=payload)
    return record_id


def _save_file(record_id: int, uploaded, document_type: str, signed: bool, provider: str, user: str) -> int:
    if not (has_permission("legal.files.upload") or has_permission("legal.admin")):
        raise PermissionError("No tienes permiso para cargar archivos.")
    raw = uploaded.getvalue()
    if not raw or len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"Archivo vacío o mayor de {MAX_FILE_MB} MB.")
    extension = Path(uploaded.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato no permitido.")
    sha256 = hashlib.sha256(raw).hexdigest()
    with db_transaction() as conn:
        record = conn.execute("SELECT module_code FROM legal_v3_records WHERE id=?", (record_id,)).fetchone()
        version = conn.execute("SELECT id FROM legal_v3_versions WHERE record_id=? AND is_current=1", (record_id,)).fetchone()
        if not record:
            raise ValueError("Expediente no encontrado.")
        if conn.execute("SELECT 1 FROM legal_v3_files WHERE sha256=? AND active=1", (sha256,)).fetchone():
            raise ValueError("El archivo ya existe en el repositorio jurídico.")
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.{extension}"
    destination = STORAGE_ROOT / stored_name
    destination.write_bytes(raw)
    mime = mimetypes.guess_type(uploaded.name)[0] or "application/octet-stream"
    with db_transaction() as conn:
        cur = conn.execute("""INSERT INTO legal_v3_files(record_id,version_id,document_type,original_name,stored_name,extension,mime_type,size_bytes,
                     sha256,storage_path,mandatory,signed,signature_provider,uploaded_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (record_id, int(version["id"]) if version else None, document_type, uploaded.name, stored_name, extension, mime,
                      len(raw), sha256, str(destination), 1, int(signed), provider.strip(), user))
        file_id = int(cur.lastrowid)
    _audit(user, "UPLOAD_FILE", "file", file_id, record_id, record["module_code"], after={"name": uploaded.name, "sha256": sha256})
    return file_id


def _new_version(record_id: int, content: str, reason: str, user: str, restored_from: int | None = None) -> int:
    if not (has_permission("legal.edit") or has_permission("legal.admin")):
        raise PermissionError("No tienes permiso para crear versiones.")
    if not reason.strip():
        raise ValueError("El motivo del cambio es obligatorio.")
    with db_transaction() as conn:
        record = conn.execute("SELECT * FROM legal_v3_records WHERE id=?", (record_id,)).fetchone()
        if not record:
            raise ValueError("Expediente no encontrado.")
        next_version = int(record["current_version"]) + 1
        conn.execute("UPDATE legal_v3_versions SET is_current=0 WHERE record_id=?", (record_id,))
        cur = conn.execute("""INSERT INTO legal_v3_versions(record_id,version_number,version_label,status,content,change_reason,author,reviewer,approver,is_current,restored_from)
                     VALUES(?,?,?,?,?,?,?,?,?,1,?)""", (record_id, next_version, f"{next_version}.0", "Borrador", content, reason, user,
                     record["reviewer_user"], record["approver_user"], restored_from))
        version_id = int(cur.lastrowid)
        conn.execute("UPDATE legal_v3_records SET current_version=?,status='Borrador',description=?,updated_by=?,updated_at=? WHERE id=?",
                     (next_version, content, user, pd.Timestamp.now().isoformat(), record_id))
    _audit(user, "CREATE_VERSION", "version", version_id, record_id, record["module_code"], after={"version": next_version, "reason": reason})
    return version_id


def _run_automations(user: str) -> int:
    today = pd.Timestamp.today().normalize()
    records = _read("SELECT * FROM legal_v3_records")
    created = 0
    if records.empty:
        return 0
    for row in records.to_dict("records"):
        raw_date = row.get("expiration_date") or row.get("due_date")
        due = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(due) or row["status"] in {"Archivado", "Cerrado", "Terminado"}:
            continue
        days = int((due.normalize() - today).days)
        if days <= 30:
            priority = "Crítica" if days < 0 else "Alta" if days <= 7 else "Media"
            source = f"expiry:{row['id']}:{due.date().isoformat()}"
            with db_transaction() as conn:
                cur = conn.execute("""INSERT OR IGNORE INTO legal_v3_tasks(record_id,task_type,title,assigned_to,due_date,priority,source_key,created_by)
                           VALUES(?,?,?,?,?,?,?,?)""", (row["id"], "Vencimiento", f"Revisar {row['code']} · {row['title']}", row["owner_user"],
                           due.date().isoformat(), priority, source, user))
                created += int(cur.rowcount or 0)
    if created:
        _audit(user, "RUN_AUTOMATIONS", "task", None, None, None, after={"tasks_created": created})
    return created


def _to_excel(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Legal")
    return output.getvalue()


def _dashboard(user: str) -> None:
    records = _read("SELECT * FROM legal_v3_records")
    if not records.empty:
        records = records[records.apply(lambda r: _can_view_record(r, user), axis=1)]
    tasks = _read("SELECT * FROM legal_v3_tasks WHERE status<>'Completada'")
    today = pd.Timestamp.today().normalize()
    dates = pd.to_datetime(records["expiration_date"].fillna(records["due_date"]), errors="coerce") if not records.empty else pd.Series(dtype="datetime64[ns]")
    open_mask = ~records["status"].isin(["Archivado", "Cerrado", "Terminado"]) if not records.empty else pd.Series(dtype=bool)
    expiring = int((dates.notna() & (dates >= today) & (dates <= today + pd.Timedelta(days=30)) & open_mask).sum()) if not records.empty else 0
    overdue = int((dates.notna() & (dates < today) & open_mask).sum()) if not records.empty else 0
    cols = st.columns(6)
    cols[0].metric("Expedientes", len(records)); cols[1].metric("Vigentes", int(records["status"].isin(["Vigente", "Firmado", "Publicado", "Concedido"]).sum()) if not records.empty else 0)
    cols[2].metric("Riesgo alto/crítico", int(records["risk_level"].isin(["Alto", "Crítico"]).sum()) if not records.empty else 0)
    cols[3].metric("Vencen ≤30 días", expiring); cols[4].metric("Vencidos", overdue); cols[5].metric("Tareas", len(tasks))
    if overdue: st.error(f"🔴 {overdue} expediente(s) vencido(s).")
    elif expiring: st.warning(f"🟡 {expiring} expediente(s) próximos a vencer.")
    else: st.success("🟢 Sin vencimientos críticos.")
    if not records.empty:
        st.bar_chart(records.groupby("module_name").size())
        st.dataframe(records.groupby(["risk_level", "status"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)


def _records_ui(user: str) -> None:
    with st.expander("Nuevo expediente", expanded=False):
        with st.form("legal_v3_new"):
            a, b = st.columns(2)
            module_code = a.selectbox("Módulo *", list(MODULE_SPECS), format_func=lambda c: MODULE_SPECS[c]["name"])
            title = b.text_input("Título *", max_chars=180)
            description = st.text_area("Descripción / objeto / alcance *", max_chars=8000)
            c, d, e = st.columns(3)
            owner = c.text_input("Responsable *", value=user, max_chars=120)
            reviewer = d.text_input("Revisor", max_chars=120)
            approver = e.text_input("Aprobador", max_chars=120)
            f, g, h = st.columns(3)
            risk = f.selectbox("Riesgo", ["Bajo", "Medio", "Alto", "Crítico"], index=1)
            confidentiality = g.selectbox("Confidencialidad", ["Público", "Interno", "Confidencial", "Restringido"], index=1)
            jurisdiction = h.text_input("Jurisdicción", value="Venezuela", max_chars=120)
            i, j, k = st.columns(3)
            start = i.date_input("Inicio", value=date.today()); due = j.date_input("Fecha límite", value=date.today()+timedelta(days=30)); expiration = k.date_input("Vencimiento", value=date.today()+timedelta(days=365))
            l, m, n = st.columns(3)
            counterparty = l.text_input("Contraparte", max_chars=180); tax_id = m.text_input("Identificación fiscal", max_chars=40); amount = n.number_input("Monto", min_value=0.0)
            currency = st.selectbox("Moneda", ["USD", "EUR", "VES"])
            legal_basis = st.text_area("Base legal / normativa aplicable", max_chars=4000)
            tags = st.text_input("Etiquetas", max_chars=500)
            retention = st.number_input("Conservación (años)", min_value=1, max_value=50, value=5)
            submit = st.form_submit_button("Crear expediente", type="primary")
        if submit:
            try:
                if not title.strip() or not description.strip() or not owner.strip(): raise ValueError("Título, descripción y responsable son obligatorios.")
                if start > due or due > expiration: raise ValueError("Las fechas deben cumplir Inicio ≤ Límite ≤ Vencimiento.")
                spec = MODULE_SPECS[module_code]
                rid = _create_record({"code": _next_code(module_code), "module_code": module_code, "module_name": spec["name"],
                    "workflow_type": spec["workflow"], "title": title.strip(), "description": description.strip(),
                    "status": WORKFLOWS[spec["workflow"]][0], "risk_level": risk, "confidentiality": confidentiality,
                    "owner_user": owner.strip(), "reviewer_user": reviewer.strip(), "approver_user": approver.strip(),
                    "counterparty": counterparty.strip(), "counterparty_tax_id": tax_id.strip(), "jurisdiction": jurisdiction.strip(),
                    "start_date": start.isoformat(), "due_date": due.isoformat(), "expiration_date": expiration.isoformat(),
                    "amount": float(amount), "currency": currency, "legal_basis": legal_basis.strip(), "tags": tags.strip(),
                    "retention_years": int(retention)}, user)
                st.success(f"Expediente #{rid} creado."); st.rerun()
            except (ValueError, PermissionError) as exc: st.error(str(exc))
    records = _read("SELECT * FROM legal_v3_records ORDER BY id DESC")
    if records.empty: st.info("No hay expedientes."); return
    visible = records[records.apply(lambda r: _can_view_record(r, user), axis=1)]
    st.dataframe(visible[["id","code","module_name","title","status","risk_level","confidentiality","owner_user","reviewer_user","approver_user","expiration_date","current_version"]], use_container_width=True, hide_index=True)
    if visible.empty: return
    with st.expander("Gestionar expediente", expanded=False):
        record_id = st.selectbox("Expediente", visible["id"].astype(int).tolist(), format_func=lambda v: f"{visible[visible['id']==v].iloc[0]['code']} · {visible[visible['id']==v].iloc[0]['title']}")
        selected = visible[visible["id"] == record_id].iloc[0]
        tabs = st.tabs(["Estado", "Documentos", "Versiones", "Obligaciones", "Auditoría"])
        with tabs[0]:
            target = st.selectbox("Nuevo estado", WORKFLOWS[selected["workflow_type"]], index=WORKFLOWS[selected["workflow_type"]].index(selected["status"]))
            comment = st.text_area("Comentario / motivo")
            if st.button("Aplicar transición", type="primary"):
                try: _change_status(int(record_id), target, comment, user); st.success("Estado actualizado."); st.rerun()
                except (ValueError, PermissionError) as exc: st.error(str(exc))
        with tabs[1]:
            matrix = _required_documents(int(record_id), selected["module_code"])
            st.markdown("#### Matriz documental obligatoria")
            st.dataframe(matrix, use_container_width=True, hide_index=True)
            options = MODULE_SPECS[selected["module_code"]]["docs"] or ["Documento general"]
            doc_type = st.selectbox("Tipo documental", options)
            uploaded = st.file_uploader("Archivo", type=sorted(ALLOWED_EXTENSIONS), key=f"v3_file_{record_id}")
            x, y = st.columns(2); signed = x.checkbox("Firmado"); provider = y.text_input("Proveedor / método de firma", disabled=not signed)
            if st.button("Cargar archivo", disabled=uploaded is None):
                try: _save_file(int(record_id), uploaded, doc_type, signed, provider, user); st.success("Archivo cargado."); st.rerun()
                except (ValueError, PermissionError, OSError) as exc: st.error(str(exc))
            files = _read("SELECT id,document_type,original_name,extension,size_bytes,sha256,signed,signature_provider,uploaded_by,uploaded_at FROM legal_v3_files WHERE record_id=? AND active=1", (int(record_id),))
            st.dataframe(files, use_container_width=True, hide_index=True)
        with tabs[2]:
            versions = _read("SELECT * FROM legal_v3_versions WHERE record_id=? ORDER BY version_number DESC", (int(record_id),))
            st.dataframe(versions[["id","version_label","status","change_reason","author","reviewer","approver","created_at","is_current","restored_from"]], use_container_width=True, hide_index=True)
            content = st.text_area("Contenido de nueva versión", value=str(selected["description"]), height=180)
            reason = st.text_area("Motivo del cambio")
            if st.button("Crear nueva versión"):
                try: _new_version(int(record_id), content, reason, user); st.success("Versión creada."); st.rerun()
                except (ValueError, PermissionError) as exc: st.error(str(exc))
            if len(versions) >= 2:
                ids = versions["id"].astype(int).tolist(); c1, c2 = st.columns(2)
                v1 = c1.selectbox("Versión A", ids, key="v3_a"); v2 = c2.selectbox("Versión B", ids, index=1, key="v3_b")
                if st.button("Comparar versiones"):
                    a = str(versions[versions["id"]==v1].iloc[0]["content"] or "").splitlines(); b = str(versions[versions["id"]==v2].iloc[0]["content"] or "").splitlines()
                    diff = pd.DataFrame({"Línea": range(1, max(len(a),len(b))+1), "Versión A": a+[""]*(max(len(a),len(b))-len(a)), "Versión B": b+[""]*(max(len(a),len(b))-len(b))})
                    st.dataframe(diff[diff["Versión A"] != diff["Versión B"]], use_container_width=True, hide_index=True)
                restore_id = st.selectbox("Restaurar desde", ids, key="v3_restore")
                restore_reason = st.text_input("Motivo de restauración")
                if st.button("Restaurar como nueva versión"):
                    row = versions[versions["id"]==restore_id].iloc[0]
                    try: _new_version(int(record_id), str(row["content"] or ""), restore_reason, user, int(restore_id)); st.success("Versión restaurada como nueva versión."); st.rerun()
                    except (ValueError, PermissionError) as exc: st.error(str(exc))
        with tabs[3]:
            with st.form(f"obligation_{record_id}"):
                title_o = st.text_input("Obligación *"); party_o = st.text_input("Parte obligada"); due_o = st.date_input("Fecha de cumplimiento", value=date.today()+timedelta(days=30)); evidence = st.checkbox("Requiere evidencia"); submit_o = st.form_submit_button("Crear obligación")
            if submit_o and title_o.strip():
                with db_transaction() as conn:
                    cur = conn.execute("INSERT INTO legal_v3_obligations(record_id,title,obligated_party,due_date,evidence_required,owner_user,created_by) VALUES(?,?,?,?,?,?,?)", (int(record_id), title_o.strip(), party_o.strip(), due_o.isoformat(), int(evidence), selected["owner_user"], user)); oid = int(cur.lastrowid)
                _audit(user, "CREATE_OBLIGATION", "obligation", oid, int(record_id), selected["module_code"], after={"title": title_o, "due_date": due_o.isoformat()}); st.rerun()
            obligations = _read("SELECT * FROM legal_v3_obligations WHERE record_id=? ORDER BY due_date", (int(record_id),))
            st.dataframe(obligations, use_container_width=True, hide_index=True)
        with tabs[4]:
            if has_permission("legal.audit.view") or has_permission("legal.admin"):
                st.dataframe(_read("SELECT event_time,user,action,entity,comments,result,prev_hash,event_hash FROM legal_v3_audit WHERE record_id=? ORDER BY id DESC LIMIT 300", (int(record_id),)), use_container_width=True, hide_index=True)
            else: st.warning("No tienes permiso para consultar auditoría.")


def _reports(user: str) -> None:
    records = _read("SELECT * FROM legal_v3_records")
    if records.empty: st.info("No hay datos."); return
    records = records[records.apply(lambda r: _can_view_record(r, user), axis=1)]
    report = st.selectbox("Reporte", ["Portafolio jurídico", "Contratos próximos a vencer", "Documentos pendientes", "Riesgos altos y críticos", "Licencias y permisos", "Obligaciones pendientes", "Auditoría"])
    today = pd.Timestamp.today().normalize()
    if report == "Contratos próximos a vencer":
        dates = pd.to_datetime(records["expiration_date"], errors="coerce"); result = records[records["workflow_type"].eq("contrato") & dates.notna() & (dates >= today) & (dates <= today+pd.Timedelta(days=90))]
    elif report == "Documentos pendientes": result = records[~records["status"].isin(["Publicado","Vigente","Archivado","Cerrado","Concedido"])]
    elif report == "Riesgos altos y críticos": result = records[records["risk_level"].isin(["Alto","Crítico"])]
    elif report == "Licencias y permisos": result = records[records["module_code"].isin(["LICENCIAS","PERMISOS"])]
    elif report == "Obligaciones pendientes": result = _read("SELECT o.*,r.code,r.title record_title FROM legal_v3_obligations o JOIN legal_v3_records r ON r.id=o.record_id WHERE o.status<>'Completada'")
    elif report == "Auditoría":
        if not (has_permission("legal.audit.view") or has_permission("legal.admin")): st.error("Sin permiso."); return
        result = _read("SELECT * FROM legal_v3_audit ORDER BY id DESC LIMIT 5000")
    else: result = records
    st.dataframe(result, use_container_width=True, hide_index=True)
    if has_permission("legal.export") or has_permission("legal.admin"):
        st.download_button("Exportar Excel", _to_excel(result), file_name="reporte_legal.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("Exportar CSV", result.to_csv(index=False).encode("utf-8-sig"), file_name="reporte_legal.csv", mime="text/csv")


def render_legal_enterprise_v3(user: str = "Sistema") -> None:
    _ensure_schema()
    st.title("🏛️ Departamento Jurídico Enterprise V3")
    st.caption("Expedientes especializados, segregación de funciones, matriz documental, obligaciones, versiones, automatizaciones y auditoría encadenada.")
    st.success(f"✅ {RELEASE}")
    section = st.radio("Área", ["Dashboard", "Expedientes", "Automatizaciones", "Reportes"], horizontal=True, key="legal_v3_section")
    st.divider()
    if section == "Dashboard": _dashboard(user)
    elif section == "Expedientes": _records_ui(user)
    elif section == "Automatizaciones":
        st.subheader("Automatizaciones jurídicas")
        st.write("Genera tareas por vencimientos vencidos o dentro de 30 días, sin duplicarlas.")
        if st.button("Ejecutar revisión de vencimientos", type="primary"):
            created = _run_automations(user); st.success(f"Automatización ejecutada. Tareas nuevas: {created}.")
        st.dataframe(_read("SELECT * FROM legal_v3_tasks ORDER BY id DESC"), use_container_width=True, hide_index=True)
    else: _reports(user)
