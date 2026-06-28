from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission

LEGAL_MODULES = {
    "AVISO_LEGAL": "Aviso Legal",
    "TERMINOS": "Términos y Condiciones",
    "PRIVACIDAD": "Política de Privacidad",
    "COOKIES": "Política de Cookies",
    "CONSENTIMIENTOS": "Consentimientos",
    "PROPIEDAD_INTELECTUAL": "Propiedad Intelectual",
    "MARCAS": "Marcas",
    "DERECHOS_AUTOR": "Derechos de Autor",
    "CONTRATOS_CLIENTES": "Contratos con Clientes",
    "CONTRATOS_PROVEEDORES": "Contratos con Proveedores",
    "CONTRATOS_LABORALES": "Contratos Laborales",
    "GARANTIAS": "Garantías",
    "DEVOLUCIONES": "Devoluciones",
    "RECLAMOS": "Reclamos",
    "LITIGIOS": "Litigios",
    "RIESGOS": "Gestión de Riesgos",
    "DEMANDAS": "Gestión de Demandas",
    "EVIDENCIAS": "Evidencias",
    "DOCUMENTACION": "Documentación Legal",
    "LICENCIAS": "Licencias",
    "PERMISOS": "Permisos",
    "NORMATIVAS": "Normativas",
    "CUMPLIMIENTO": "Cumplimiento",
    "AUDITORIA": "Auditoría",
    "FIRMA_DIGITAL": "Firma Digital",
    "CAMBIOS": "Registro de Cambios",
    "VERSIONES": "Control de Versiones",
    "ARCHIVO": "Archivo Jurídico",
    "CALENDARIO": "Calendario Legal",
    "NOTIFICACIONES": "Notificaciones",
    "CONFIGURACION": "Configuración Jurídica",
}

WORKFLOWS = {
    "documento": ["Borrador", "En revisión", "Cambios solicitados", "Aprobado", "Publicado", "Vigente", "Archivado"],
    "contrato": ["Borrador", "En negociación", "En revisión", "Aprobado", "Pendiente de firma", "Firmado", "Vigente", "Suspendido", "Vencido", "Terminado", "Archivado"],
    "caso": ["Registrado", "En análisis", "En proceso", "Escalado", "Resuelto", "Cerrado", "Archivado"],
    "riesgo": ["Identificado", "Evaluado", "Tratamiento", "Monitoreo", "Aceptado", "Cerrado"],
}

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "webp", "txt", "eml", "msg", "mp3", "wav", "mp4"}
MAX_FILE_MB = 20
STORAGE_ROOT = Path("data/legal_files")


def _workflow_for(module_code: str) -> str:
    if module_code.startswith("CONTRATOS"):
        return "contrato"
    if module_code in {"RECLAMOS", "GARANTIAS", "DEVOLUCIONES", "LITIGIOS", "DEMANDAS", "EVIDENCIAS"}:
        return "caso"
    if module_code == "RIESGOS":
        return "riesgo"
    return "documento"


def _ensure_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS legal_enterprise_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                module_code TEXT NOT NULL,
                module_name TEXT NOT NULL,
                workflow_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL DEFAULT 'Medio',
                confidentiality TEXT NOT NULL DEFAULT 'Interno',
                owner TEXT NOT NULL,
                reviewer TEXT,
                approver TEXT,
                counterparty TEXT,
                jurisdiction TEXT DEFAULT 'Venezuela',
                start_date TEXT,
                due_date TEXT,
                expiration_date TEXT,
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                tags TEXT,
                legal_basis TEXT,
                retention_years INTEGER DEFAULT 5,
                legal_hold INTEGER DEFAULT 0,
                current_version INTEGER DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                version_label TEXT NOT NULL,
                status TEXT NOT NULL,
                content TEXT,
                change_reason TEXT NOT NULL,
                author TEXT NOT NULL,
                reviewer TEXT,
                approver TEXT,
                effective_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_current INTEGER DEFAULT 1,
                FOREIGN KEY(record_id) REFERENCES legal_enterprise_records(id),
                UNIQUE(record_id, version_number)
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL,
                version_id INTEGER,
                document_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                extension TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                mandatory INTEGER DEFAULT 0,
                signed INTEGER DEFAULT 0,
                signature_provider TEXT,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1,
                FOREIGN KEY(record_id) REFERENCES legal_enterprise_records(id),
                FOREIGN KEY(version_id) REFERENCES legal_enterprise_versions(id)
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uuid TEXT NOT NULL UNIQUE,
                event_time TEXT DEFAULT CURRENT_TIMESTAMP,
                user TEXT NOT NULL,
                ip_address TEXT,
                device TEXT,
                browser TEXT,
                session_id TEXT,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                module_code TEXT,
                before_json TEXT,
                after_json TEXT,
                comments TEXT,
                result TEXT NOT NULL DEFAULT 'Exitoso'
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER,
                task_type TEXT NOT NULL,
                title TEXT NOT NULL,
                assigned_to TEXT,
                due_date TEXT,
                status TEXT DEFAULT 'Pendiente',
                priority TEXT DEFAULT 'Media',
                created_by TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY(record_id) REFERENCES legal_enterprise_records(id)
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                alert_days INTEGER DEFAULT 7,
                owner TEXT,
                status TEXT DEFAULT 'Pendiente',
                created_by TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(record_id) REFERENCES legal_enterprise_records(id)
            );
            CREATE TABLE IF NOT EXISTS legal_enterprise_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_code TEXT NOT NULL UNIQUE,
                module_code TEXT,
                trigger_event TEXT NOT NULL,
                condition_json TEXT,
                action_code TEXT NOT NULL,
                severity TEXT DEFAULT 'Alta',
                blocking INTEGER DEFAULT 1,
                active INTEGER DEFAULT 1,
                description TEXT NOT NULL
            );
            """
        )
        rules = [
            ("DOC_SIGNED_NO_DELETE", None, "DELETE_FILE", "{\"signed\": true}", "BLOCK", "Crítica", 1, 1, "No permitir eliminar documentos firmados."),
            ("APPROVED_NO_EDIT", None, "EDIT_RECORD", "{\"status_in\": [\"Aprobado\", \"Publicado\", \"Firmado\", \"Vigente\"]}", "CREATE_VERSION", "Crítica", 1, 1, "Los registros aprobados o vigentes solo cambian mediante nueva versión."),
            ("PUBLISH_REQUIRES_APPROVAL", None, "STATUS_CHANGE", "{\"target\": \"Publicado\"}", "REQUIRE_APPROVER", "Crítica", 1, 1, "Publicar requiere aprobación y aprobador distinto del autor."),
            ("CRITICAL_RISK_APPROVAL", None, "STATUS_CHANGE", "{\"risk_level\": \"Crítico\"}", "REQUIRE_APPROVER", "Crítica", 1, 1, "Riesgos críticos requieren aprobación."),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO legal_enterprise_rules(rule_code,module_code,trigger_event,condition_json,action_code,severity,blocking,active,description) VALUES(?,?,?,?,?,?,?,?,?)",
            rules,
        )


def _read(sql: str, params: tuple = ()) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _request_context() -> dict:
    headers = getattr(st, "context", None)
    header_map = getattr(headers, "headers", {}) if headers else {}
    return {
        "ip_address": str(header_map.get("X-Forwarded-For") or header_map.get("X-Real-Ip") or ""),
        "device": str(header_map.get("Sec-Ch-Ua-Platform") or ""),
        "browser": str(header_map.get("User-Agent") or ""),
        "session_id": str(st.session_state.get("session_id") or ""),
    }


def _audit(user: str, action: str, entity: str, entity_id: int | None, module_code: str | None, before: dict | None = None, after: dict | None = None, comments: str = "", result: str = "Exitoso") -> None:
    context = _request_context()
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO legal_enterprise_audit(event_uuid,user,ip_address,device,browser,session_id,action,entity,entity_id,module_code,before_json,after_json,comments,result)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()), user, context["ip_address"], context["device"], context["browser"], context["session_id"],
                action, entity, entity_id, module_code,
                json.dumps(before or {}, ensure_ascii=False, default=str),
                json.dumps(after or {}, ensure_ascii=False, default=str), comments, result,
            ),
        )


def _next_code(module_code: str) -> str:
    prefix = module_code[:4].replace("_", "")
    year = date.today().year
    with db_transaction() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id),0)+1 AS n FROM legal_enterprise_records").fetchone()
    return f"{prefix}-{year}-{int(row['n']):06d}"


def _validate_people(user: str, reviewer: str, approver: str) -> None:
    people = [str(user).strip().casefold(), str(reviewer).strip().casefold(), str(approver).strip().casefold()]
    populated = [p for p in people if p]
    if len(populated) != len(set(populated)):
        raise ValueError("Creador, revisor y aprobador deben ser personas diferentes.")


def _create_record(data: dict, user: str) -> int:
    if not has_permission("legal.create") and not has_permission("legal.admin"):
        raise PermissionError("No tienes permiso para crear expedientes jurídicos.")
    _validate_people(user, data.get("reviewer", ""), data.get("approver", ""))
    payload = dict(data)
    payload.update({"uuid": str(uuid4()), "created_by": user, "updated_by": user, "updated_at": pd.Timestamp.now().isoformat()})
    with db_transaction() as conn:
        keys = list(payload)
        cur = conn.execute(
            f"INSERT INTO legal_enterprise_records ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            [payload[k] for k in keys],
        )
        record_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO legal_enterprise_versions(record_id,version_number,version_label,status,content,change_reason,author,reviewer,approver,is_current) VALUES(?,?,?,?,?,?,?,?,?,1)",
            (record_id, 1, "1.0", payload["status"], payload.get("description", ""), "Versión inicial", user, payload.get("reviewer"), payload.get("approver")),
        )
    _audit(user, "CREATE", "legal_record", record_id, payload["module_code"], after=payload)
    return record_id


def _allowed_transition(workflow_type: str, current: str, target: str) -> bool:
    states = WORKFLOWS[workflow_type]
    if current == target:
        return True
    try:
        return states.index(target) == states.index(current) + 1 or target in {"Archivado", "Suspendido", "Cambios solicitados", "Escalado"}
    except ValueError:
        return False


def _change_status(record_id: int, target: str, comment: str, user: str) -> None:
    if not has_permission("legal.edit") and not has_permission("legal.admin"):
        raise PermissionError("No tienes permiso para modificar expedientes.")
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM legal_enterprise_records WHERE id=?", (record_id,)).fetchone()
        if not row:
            raise ValueError("Expediente no encontrado.")
        before = dict(row)
        if not _allowed_transition(before["workflow_type"], before["status"], target):
            raise ValueError(f"Transición no permitida: {before['status']} → {target}.")
        if target in {"Aprobado", "Publicado", "Firmado", "Vigente"} and not before.get("approver"):
            raise ValueError("Debe asignarse un aprobador antes de completar esta transición.")
        if target in {"Archivado", "Suspendido", "Vencido", "Terminado", "Cerrado"} and not comment.strip():
            raise ValueError("El comentario o motivo es obligatorio para este estado.")
        conn.execute("UPDATE legal_enterprise_records SET status=?,updated_by=?,updated_at=? WHERE id=?", (target, user, pd.Timestamp.now().isoformat(), record_id))
    after = dict(before)
    after["status"] = target
    _audit(user, "STATUS_CHANGE", "legal_record", record_id, before["module_code"], before, after, comment)


def _new_version(record_id: int, content: str, reason: str, user: str) -> int:
    if not has_permission("legal.edit") and not has_permission("legal.admin"):
        raise PermissionError("No tienes permiso para crear versiones.")
    if not reason.strip():
        raise ValueError("El motivo del cambio es obligatorio.")
    with db_transaction() as conn:
        record = conn.execute("SELECT * FROM legal_enterprise_records WHERE id=?", (record_id,)).fetchone()
        if not record:
            raise ValueError("Expediente no encontrado.")
        next_version = int(record["current_version"] or 1) + 1
        conn.execute("UPDATE legal_enterprise_versions SET is_current=0 WHERE record_id=?", (record_id,))
        cur = conn.execute(
            "INSERT INTO legal_enterprise_versions(record_id,version_number,version_label,status,content,change_reason,author,reviewer,approver,is_current) VALUES(?,?,?,?,?,?,?,?,?,1)",
            (record_id, next_version, f"{next_version}.0", "Borrador", content, reason, user, record["reviewer"], record["approver"]),
        )
        version_id = int(cur.lastrowid)
        conn.execute("UPDATE legal_enterprise_records SET current_version=?,status='Borrador',updated_by=?,updated_at=? WHERE id=?", (next_version, user, pd.Timestamp.now().isoformat(), record_id))
    _audit(user, "CREATE_VERSION", "legal_version", version_id, record["module_code"], after={"record_id": record_id, "version": next_version, "reason": reason})
    return version_id


def _save_file(record_id: int, uploaded, document_type: str, mandatory: bool, signed: bool, user: str) -> int:
    if not has_permission("legal.files.upload") and not has_permission("legal.admin"):
        raise PermissionError("No tienes permiso para cargar archivos jurídicos.")
    raw = uploaded.getvalue()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"El archivo supera el máximo de {MAX_FILE_MB} MB.")
    extension = Path(uploaded.name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formato no permitido.")
    sha256 = hashlib.sha256(raw).hexdigest()
    with db_transaction() as conn:
        duplicate = conn.execute("SELECT id FROM legal_enterprise_files WHERE record_id=? AND sha256=? AND active=1", (record_id, sha256)).fetchone()
        if duplicate:
            raise ValueError("Este archivo ya está cargado en el expediente.")
        record = conn.execute("SELECT module_code,current_version FROM legal_enterprise_records WHERE id=?", (record_id,)).fetchone()
        version = conn.execute("SELECT id FROM legal_enterprise_versions WHERE record_id=? AND is_current=1", (record_id,)).fetchone()
        if not record:
            raise ValueError("Expediente no encontrado.")
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.{extension}"
    destination = STORAGE_ROOT / stored_name
    destination.write_bytes(raw)
    mime = mimetypes.guess_type(uploaded.name)[0] or "application/octet-stream"
    with db_transaction() as conn:
        cur = conn.execute(
            """INSERT INTO legal_enterprise_files(record_id,version_id,document_type,original_name,stored_name,extension,mime_type,size_bytes,sha256,storage_path,mandatory,signed,uploaded_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record_id, int(version["id"]) if version else None, document_type, uploaded.name, stored_name, extension, mime, len(raw), sha256, str(destination), int(mandatory), int(signed), user),
        )
        file_id = int(cur.lastrowid)
    _audit(user, "UPLOAD_FILE", "legal_file", file_id, record["module_code"], after={"record_id": record_id, "name": uploaded.name, "sha256": sha256, "signed": signed})
    return file_id


def _dashboard() -> None:
    records = _read("SELECT * FROM legal_enterprise_records")
    files = _read("SELECT * FROM legal_enterprise_files WHERE active=1")
    tasks = _read("SELECT * FROM legal_enterprise_tasks")
    today = pd.Timestamp.today().normalize()
    expiring = 0
    overdue = 0
    if not records.empty:
        dates = pd.to_datetime(records["expiration_date"].fillna(records["due_date"]), errors="coerce")
        open_mask = ~records["status"].isin(["Archivado", "Cerrado", "Terminado"])
        expiring = int((dates.notna() & (dates >= today) & (dates <= today + pd.Timedelta(days=30)) & open_mask).sum())
        overdue = int((dates.notna() & (dates < today) & open_mask).sum())
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Expedientes", len(records))
    c2.metric("Vigentes", int(records["status"].isin(["Vigente", "Firmado", "Publicado"]).sum()) if not records.empty else 0)
    c3.metric("Riesgo alto/crítico", int(records["risk_level"].isin(["Alto", "Crítico"]).sum()) if not records.empty else 0)
    c4.metric("Vencen ≤30 días", expiring)
    c5.metric("Vencidos", overdue)
    c6.metric("Archivos", len(files))
    if overdue:
        st.error(f"🔴 {overdue} expediente(s) vencido(s) requieren atención.")
    elif expiring:
        st.warning(f"🟡 {expiring} expediente(s) próximos a vencer.")
    else:
        st.success("🟢 Sin vencimientos críticos registrados.")
    if not records.empty:
        left, right = st.columns(2)
        with left:
            st.markdown("### Cumplimiento por estado")
            st.dataframe(records.groupby(["module_name", "status"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)
        with right:
            st.markdown("### Matriz de riesgo")
            st.dataframe(records.groupby(["risk_level", "status"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)
    if not tasks.empty:
        st.markdown("### Tareas jurídicas")
        st.dataframe(tasks[tasks["status"] != "Completada"], use_container_width=True, hide_index=True)


def _records_ui(user: str) -> None:
    st.subheader("Expedientes jurídicos")
    with st.expander("Nuevo expediente", expanded=False):
        with st.form("legal_enterprise_new_record"):
            a, b = st.columns(2)
            module_code = a.selectbox("Módulo *", list(LEGAL_MODULES), format_func=lambda code: LEGAL_MODULES[code])
            title = b.text_input("Título *", max_chars=180)
            description = st.text_area("Descripción, objeto o alcance *", max_chars=8000)
            c, d, e = st.columns(3)
            owner = c.text_input("Responsable *", value=user, max_chars=120)
            reviewer = d.text_input("Revisor", max_chars=120)
            approver = e.text_input("Aprobador", max_chars=120)
            f, g, h = st.columns(3)
            risk = f.selectbox("Riesgo", ["Bajo", "Medio", "Alto", "Crítico"], index=1)
            confidentiality = g.selectbox("Confidencialidad", ["Público", "Interno", "Confidencial", "Restringido"], index=1)
            jurisdiction = h.text_input("Jurisdicción", value="Venezuela", max_chars=120)
            i, j, k = st.columns(3)
            start = i.date_input("Fecha de inicio", value=date.today())
            due = j.date_input("Fecha límite", value=date.today() + timedelta(days=30))
            expiration = k.date_input("Vencimiento", value=date.today() + timedelta(days=365))
            l, m, n = st.columns(3)
            counterparty = l.text_input("Contraparte", max_chars=180)
            amount = m.number_input("Monto", min_value=0.0)
            currency = n.selectbox("Moneda", ["USD", "EUR", "VES"])
            legal_basis = st.text_area("Base legal / normativa aplicable", max_chars=4000)
            tags = st.text_input("Etiquetas", help="Separadas por comas", max_chars=500)
            retention = st.number_input("Conservación documental (años)", min_value=1, max_value=50, value=5)
            submit = st.form_submit_button("Crear expediente", type="primary")
        if submit:
            try:
                if not title.strip() or not description.strip() or not owner.strip():
                    raise ValueError("Título, descripción y responsable son obligatorios.")
                workflow = _workflow_for(module_code)
                record_id = _create_record({
                    "code": _next_code(module_code), "module_code": module_code, "module_name": LEGAL_MODULES[module_code],
                    "workflow_type": workflow, "title": title.strip(), "description": description.strip(),
                    "status": WORKFLOWS[workflow][0], "risk_level": risk, "confidentiality": confidentiality,
                    "owner": owner.strip(), "reviewer": reviewer.strip(), "approver": approver.strip(),
                    "counterparty": counterparty.strip(), "jurisdiction": jurisdiction.strip(),
                    "start_date": start.isoformat(), "due_date": due.isoformat(), "expiration_date": expiration.isoformat(),
                    "amount": float(amount), "currency": currency, "tags": tags.strip(), "legal_basis": legal_basis.strip(),
                    "retention_years": int(retention),
                }, user)
                st.success(f"Expediente #{record_id} creado con versión 1.0 y auditoría.")
                st.rerun()
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))

    records = _read("SELECT * FROM legal_enterprise_records ORDER BY id DESC")
    if records.empty:
        st.info("No hay expedientes jurídicos.")
        return
    a, b, c = st.columns(3)
    module_filter = a.selectbox("Filtrar módulo", ["Todos"] + sorted(records["module_name"].unique().tolist()))
    status_filter = b.selectbox("Filtrar estado", ["Todos"] + sorted(records["status"].unique().tolist()))
    risk_filter = c.selectbox("Filtrar riesgo", ["Todos", "Bajo", "Medio", "Alto", "Crítico"])
    filtered = records.copy()
    if module_filter != "Todos": filtered = filtered[filtered["module_name"] == module_filter]
    if status_filter != "Todos": filtered = filtered[filtered["status"] == status_filter]
    if risk_filter != "Todos": filtered = filtered[filtered["risk_level"] == risk_filter]
    st.dataframe(filtered[["id", "code", "module_name", "title", "status", "risk_level", "owner", "reviewer", "approver", "expiration_date", "current_version"]], use_container_width=True, hide_index=True)

    with st.expander("Acciones del expediente"):
        record_id = st.selectbox("Expediente", records["id"].astype(int).tolist(), format_func=lambda value: f"{records[records['id']==value].iloc[0]['code']} · {records[records['id']==value].iloc[0]['title']}")
        selected = records[records["id"] == record_id].iloc[0]
        action_tabs = st.tabs(["Estado", "Nueva versión", "Archivo", "Historial"])
        with action_tabs[0]:
            states = WORKFLOWS[selected["workflow_type"]]
            target = st.selectbox("Nuevo estado", states, index=states.index(selected["status"]) if selected["status"] in states else 0)
            comment = st.text_area("Comentario / motivo", key="legal_status_comment")
            if st.button("Aplicar transición", type="primary"):
                try:
                    _change_status(int(record_id), target, comment, user)
                    st.success("Estado actualizado con auditoría.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        with action_tabs[1]:
            content = st.text_area("Contenido o resumen de la nueva versión", value=str(selected.get("description") or ""), height=220)
            reason = st.text_area("Motivo del cambio *", key="legal_version_reason")
            if st.button("Crear nueva versión"):
                try:
                    version_id = _new_version(int(record_id), content, reason, user)
                    st.success(f"Versión creada. ID {version_id}.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
        with action_tabs[2]:
            uploaded = st.file_uploader("Archivo", type=sorted(ALLOWED_EXTENSIONS), key=f"legal_file_{record_id}")
            doc_type = st.selectbox("Tipo documental", ["Contrato", "Identidad", "Registro mercantil", "Licencia", "Permiso", "Factura", "Correo", "Captura", "Acta", "Evidencia", "Anexo", "Otro"])
            x, y = st.columns(2)
            mandatory = x.checkbox("Documento obligatorio")
            signed = y.checkbox("Documento firmado")
            st.caption(f"Formatos permitidos: {', '.join(sorted(ALLOWED_EXTENSIONS))}. Máximo {MAX_FILE_MB} MB por archivo.")
            if st.button("Cargar archivo", disabled=uploaded is None):
                try:
                    file_id = _save_file(int(record_id), uploaded, doc_type, mandatory, signed, user)
                    st.success(f"Archivo #{file_id} cargado y verificado por SHA-256.")
                    st.rerun()
                except (ValueError, PermissionError, OSError) as exc:
                    st.error(str(exc))
            files = _read("SELECT id,document_type,original_name,extension,size_bytes,sha256,mandatory,signed,uploaded_by,uploaded_at FROM legal_enterprise_files WHERE record_id=? AND active=1 ORDER BY id DESC", (int(record_id),))
            if not files.empty:
                st.dataframe(files, use_container_width=True, hide_index=True)
        with action_tabs[3]:
            versions = _read("SELECT version_label,status,change_reason,author,reviewer,approver,created_at,is_current FROM legal_enterprise_versions WHERE record_id=? ORDER BY version_number DESC", (int(record_id),))
            audits = _read("SELECT event_time,user,action,comments,result,before_json,after_json FROM legal_enterprise_audit WHERE entity_id=? ORDER BY id DESC LIMIT 100", (int(record_id),))
            st.markdown("#### Versiones")
            st.dataframe(versions, use_container_width=True, hide_index=True)
            st.markdown("#### Auditoría")
            st.dataframe(audits, use_container_width=True, hide_index=True)


def _calendar_ui(user: str) -> None:
    st.subheader("Calendario y tareas legales")
    records = _read("SELECT id,code,title FROM legal_enterprise_records ORDER BY id DESC")
    with st.form("legal_calendar_form"):
        options = [0] + (records["id"].astype(int).tolist() if not records.empty else [])
        record_id = st.selectbox("Expediente relacionado", options, format_func=lambda value: "General" if value == 0 else f"{records[records['id']==value].iloc[0]['code']} · {records[records['id']==value].iloc[0]['title']}")
        title = st.text_input("Evento *", max_chars=180)
        a, b, c = st.columns(3)
        event_type = a.selectbox("Tipo", ["Vencimiento", "Renovación", "Audiencia", "Revisión", "Aprobación", "Firma", "Publicación", "Recordatorio"])
        event_date = b.date_input("Fecha", value=date.today() + timedelta(days=7))
        alert_days = c.number_input("Alertar días antes", min_value=0, max_value=365, value=7)
        submit = st.form_submit_button("Crear evento")
    if submit:
        if not title.strip():
            st.error("El título es obligatorio.")
        else:
            with db_transaction() as conn:
                cur = conn.execute("INSERT INTO legal_enterprise_calendar(record_id,event_type,title,event_date,alert_days,owner,created_by) VALUES(?,?,?,?,?,?,?)", (int(record_id) or None, event_type, title.strip(), event_date.isoformat(), int(alert_days), user, user))
                event_id = int(cur.lastrowid)
            _audit(user, "CREATE_EVENT", "legal_calendar", event_id, None, after={"title": title, "event_date": event_date.isoformat(), "alert_days": alert_days})
            st.success("Evento creado.")
            st.rerun()
    events = _read("SELECT * FROM legal_enterprise_calendar ORDER BY event_date")
    if not events.empty:
        st.dataframe(events, use_container_width=True, hide_index=True)


def _governance_ui() -> None:
    tabs = st.tabs(["Módulos", "Reglas", "Auditoría", "Reportes"])
    with tabs[0]:
        st.dataframe(pd.DataFrame([{"Código": code, "Módulo": name, "Workflow": _workflow_for(code)} for code, name in LEGAL_MODULES.items()]), use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(_read("SELECT * FROM legal_enterprise_rules ORDER BY severity DESC,rule_code"), use_container_width=True, hide_index=True)
    with tabs[2]:
        if has_permission("legal.audit.view") or has_permission("legal.admin"):
            st.dataframe(_read("SELECT * FROM legal_enterprise_audit ORDER BY id DESC LIMIT 1000"), use_container_width=True, hide_index=True)
        else:
            st.warning("No tienes permiso para consultar la auditoría legal.")
    with tabs[3]:
        records = _read("SELECT * FROM legal_enterprise_records")
        if records.empty:
            st.info("No hay datos para reportar.")
        else:
            report = st.selectbox("Reporte", ["Contratos próximos a vencer", "Documentos pendientes", "Riesgos altos y críticos", "Licencias y permisos", "Historial jurídico"])
            today = pd.Timestamp.today().normalize()
            if report == "Contratos próximos a vencer":
                dates = pd.to_datetime(records["expiration_date"], errors="coerce")
                result = records[records["module_code"].str.startswith("CONTRATOS") & dates.notna() & (dates >= today) & (dates <= today + pd.Timedelta(days=90))]
            elif report == "Documentos pendientes":
                result = records[~records["status"].isin(["Publicado", "Vigente", "Archivado", "Cerrado"])]
            elif report == "Riesgos altos y críticos":
                result = records[records["risk_level"].isin(["Alto", "Crítico"])]
            elif report == "Licencias y permisos":
                result = records[records["module_code"].isin(["LICENCIAS", "PERMISOS"])]
            else:
                result = records
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.download_button("Exportar CSV", result.to_csv(index=False).encode("utf-8-sig"), file_name="reporte_legal.csv", mime="text/csv")


def render_legal_enterprise_core(user: str = "Sistema") -> None:
    _ensure_schema()
    st.title("🏛️ Departamento Jurídico Enterprise")
    st.caption("Expedientes, workflows, documentos, versiones, calendario, riesgos, auditoría y gobierno jurídico.")
    section = st.radio("Área", ["Dashboard", "Expedientes", "Calendario", "Gobierno y reportes"], horizontal=True, key="legal_enterprise_core_section")
    st.divider()
    if section == "Dashboard":
        _dashboard()
    elif section == "Expedientes":
        _records_ui(user)
    elif section == "Calendario":
        _calendar_ui(user)
    else:
        _governance_ui()
