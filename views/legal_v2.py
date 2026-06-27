from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction

MODULES = [
    ("AVISO_LEGAL", "Aviso Legal", "Identificación legal, canales y publicación oficial", "Normativo"),
    ("TERMINOS", "Términos y Condiciones", "Condiciones comerciales, servicios, pagos y uso", "Normativo"),
    ("PRIVACIDAD", "Política de Privacidad", "Tratamiento de datos personales y derechos", "Datos"),
    ("COOKIES", "Política de Cookies", "Cookies, analítica y consentimiento web", "Datos"),
    ("CONSENTIMIENTOS", "Consentimientos", "Autorizaciones, evidencias y revocaciones", "Datos"),
    ("PROPIEDAD_INTELECTUAL", "Propiedad Intelectual", "Marca, diseños, plantillas, fotos y contenido", "PI"),
    ("MARCAS", "Marcas", "Registro, uso, licencias y protección de marca", "PI"),
    ("DERECHOS_AUTOR", "Derechos de Autor", "Obras, diseños, archivos y creaciones", "PI"),
    ("CONTRATOS", "Gestión Contractual", "Ciclo de vida contractual completo", "Contratos"),
    ("CONTRATOS_CLIENTES", "Contratos con Clientes", "Clientes particulares, empresas y gobierno", "Contratos"),
    ("CONTRATOS_PROVEEDORES", "Contratos con Proveedores", "Compras, suministros, tecnología e insumos", "Contratos"),
    ("CONTRATOS_LABORALES", "Contratos Laborales", "Trabajadores, confidencialidad y funciones", "Laboral"),
    ("GARANTIAS", "Garantías", "Garantías de productos, impresoras y consumibles", "Operativo"),
    ("DEVOLUCIONES", "Devoluciones", "Cambios, devoluciones, notas de crédito y reposiciones", "Operativo"),
    ("RECLAMOS", "Reclamos", "Reclamos de clientes, seguimiento y solución", "Operativo"),
    ("LITIGIOS", "Litigios", "Conflictos, abogados, juzgados y actuaciones", "Riesgo"),
    ("RIESGOS", "Gestión de Riesgos", "Mapa de riesgos legales y controles", "Riesgo"),
    ("DEMANDAS", "Gestión de Demandas", "Demandas, expedientes y etapas procesales", "Riesgo"),
    ("EVIDENCIAS", "Evidencias", "Capturas, correos, audios, videos y pruebas", "Documental"),
    ("DOCUMENTACION", "Documentación Legal", "Repositorio documental jurídico", "Documental"),
    ("LICENCIAS", "Licencias", "Licencias comerciales, software y permisos", "Cumplimiento"),
    ("PERMISOS", "Permisos", "Permisos administrativos y operativos", "Cumplimiento"),
    ("NORMATIVAS", "Normativas", "Leyes, reglamentos y obligaciones aplicables", "Cumplimiento"),
    ("CUMPLIMIENTO", "Cumplimiento", "Checklist, controles y obligaciones", "Cumplimiento"),
    ("AUDITORIA", "Auditoría", "Trazabilidad de eventos y controles", "Gobierno"),
    ("FIRMA_DIGITAL", "Firma Digital", "Firmas, sellos y aprobaciones", "Gobierno"),
    ("CAMBIOS", "Registro de Cambios", "Cambios legales y versionado funcional", "Gobierno"),
    ("VERSIONES", "Control de Versiones", "Versiones, comparación y vigencia", "Gobierno"),
    ("ARCHIVO", "Archivo Jurídico", "Conservación, retención y archivo", "Documental"),
    ("CALENDARIO", "Calendario Legal", "Vencimientos, renovaciones y audiencias", "Calendario"),
    ("NOTIFICACIONES", "Notificaciones", "Alertas, aprobaciones y recordatorios", "Automatización"),
    ("CONFIG", "Configuración Jurídica", "Roles, plantillas, canales y reglas", "Configuración"),
]

STATES = ["Borrador", "En revisión", "Cambios solicitados", "Aprobado", "Vigente", "Pendiente", "En proceso", "Cerrado", "Suspendido", "Archivado", "Vencido", "Cancelado"]
RISK_LEVELS = ["Bajo", "Medio", "Alto", "Crítico"]
CONFIDENTIALITY = ["Público", "Interno", "Confidencial", "Restringido"]
FILE_EXTENSIONS = {"pdf", "docx", "xlsx", "png", "jpg", "jpeg", "eml", "msg", "mp3", "mp4", "wav"}


def _ensure_schema() -> None:
    with db_transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS legal_v2_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            modulo_codigo TEXT NOT NULL,
            modulo_nombre TEXT NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            contraparte TEXT,
            cliente_proveedor TEXT,
            responsable TEXT NOT NULL,
            revisor TEXT,
            aprobador TEXT,
            estado TEXT NOT NULL DEFAULT 'Borrador',
            prioridad TEXT NOT NULL DEFAULT 'Media',
            riesgo TEXT NOT NULL DEFAULT 'Medio',
            confidencialidad TEXT NOT NULL DEFAULT 'Interno',
            fecha_inicio TEXT,
            fecha_limite TEXT,
            fecha_vencimiento TEXT,
            version_actual TEXT NOT NULL DEFAULT '1.0',
            canal TEXT,
            jurisdiccion TEXT DEFAULT 'Venezuela',
            monto_usd REAL DEFAULT 0,
            etiquetas TEXT,
            datos_json TEXT,
            creado_por TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_por TEXT,
            actualizado_en TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_v2_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            estado TEXT NOT NULL,
            contenido_json TEXT NOT NULL,
            hash_contenido TEXT NOT NULL,
            autor TEXT NOT NULL,
            revisor TEXT,
            aprobador TEXT,
            comentario TEXT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            vigente INTEGER NOT NULL DEFAULT 0,
            UNIQUE(case_id, version)
        );
        CREATE TABLE IF NOT EXISTS legal_v2_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            version_id INTEGER,
            nombre_archivo TEXT NOT NULL,
            extension TEXT NOT NULL,
            tamano_bytes INTEGER NOT NULL,
            hash_sha256 TEXT NOT NULL,
            ruta TEXT NOT NULL,
            tipo_documento TEXT NOT NULL,
            firmado INTEGER NOT NULL DEFAULT 0,
            obligatorio INTEGER NOT NULL DEFAULT 0,
            cargado_por TEXT NOT NULL,
            fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS legal_v2_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            entidad TEXT NOT NULL,
            entidad_id INTEGER,
            modulo_codigo TEXT,
            antes_json TEXT,
            despues_json TEXT,
            comentario TEXT,
            resultado TEXT NOT NULL DEFAULT 'Exitoso',
            ip TEXT,
            equipo TEXT,
            navegador TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_v2_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            modulo_codigo TEXT,
            titulo TEXT NOT NULL,
            tipo_evento TEXT NOT NULL,
            fecha_evento TEXT NOT NULL,
            responsable TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            alerta_dias INTEGER NOT NULL DEFAULT 7,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS legal_v2_checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            obligatorio INTEGER NOT NULL DEFAULT 1,
            responsable TEXT,
            comentario TEXT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)


def _audit(user: str, action: str, entity: str, entity_id: int | None, module_code: str = "", before: dict | None = None, after: dict | None = None, comment: str = "") -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO legal_v2_audit (usuario, accion, entidad, entidad_id, modulo_codigo, antes_json, despues_json, comentario) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user, action, entity, entity_id, module_code, json.dumps(before or {}, ensure_ascii=False, default=str), json.dumps(after or {}, ensure_ascii=False, default=str), comment),
        )


def _module_name(code: str) -> str:
    return dict((m[0], m[1]) for m in MODULES).get(code, code)


def _next_code(module_code: str) -> str:
    prefix = module_code[:4].replace("_", "")
    year = date.today().year
    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) total FROM legal_v2_cases WHERE codigo LIKE ?", (f"{prefix}-{year}-%",)).fetchone()
    return f"{prefix}-{year}-{int(row['total'] or 0) + 1:04d}"


def _hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _read_cases(where: str = "", params: tuple = ()) -> pd.DataFrame:
    _ensure_schema()
    sql = "SELECT * FROM legal_v2_cases"
    if where:
        sql += " WHERE " + where
    sql += " ORDER BY id DESC"
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _create_case(payload: dict, user: str) -> int:
    payload = dict(payload)
    payload["codigo"] = _next_code(payload["modulo_codigo"])
    payload["modulo_nombre"] = _module_name(payload["modulo_codigo"])
    payload["creado_por"] = user
    payload["actualizado_por"] = user
    payload["actualizado_en"] = pd.Timestamp.now().isoformat()
    with db_transaction() as conn:
        allowed = {str(r[1]) for r in conn.execute("PRAGMA table_info(legal_v2_cases)")}
        data = {k: v for k, v in payload.items() if k in allowed}
        keys = list(data)
        cur = conn.execute(f"INSERT INTO legal_v2_cases ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [data[k] for k in keys])
        case_id = int(cur.lastrowid)
        digest = _hash(data)
        vcur = conn.execute("INSERT INTO legal_v2_versions (case_id, version, estado, contenido_json, hash_contenido, autor, comentario, vigente) VALUES (?, '1.0', ?, ?, ?, ?, 'Creación inicial', 1)", (case_id, data.get("estado", "Borrador"), json.dumps(data, ensure_ascii=False, default=str), digest, user))
        version_id = int(vcur.lastrowid)
        checklist = ["Datos generales completos", "Responsable asignado", "Riesgo clasificado", "Fecha límite o revisión definida", "Documentos/evidencias cargados", "Aprobación registrada si aplica"]
        for item in checklist:
            conn.execute("INSERT INTO legal_v2_checklist (case_id, item, responsable) VALUES (?, ?, ?)", (case_id, item, user))
    _audit(user, "Crear expediente legal", "legal_v2_cases", case_id, payload["modulo_codigo"], after=data)
    return case_id


def _update_state(case_id: int, state: str, user: str, comment: str) -> None:
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM legal_v2_cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise ValueError("Expediente no encontrado")
        before = dict(row)
        conn.execute("UPDATE legal_v2_cases SET estado=?, actualizado_por=?, actualizado_en=? WHERE id=?", (state, user, pd.Timestamp.now().isoformat(), case_id))
        data = dict(before)
        data["estado"] = state
        digest = _hash(data)
        current_version = str(before.get("version_actual") or "1.0")
        conn.execute("UPDATE legal_v2_versions SET vigente=0 WHERE case_id=?", (case_id,))
        cur = conn.execute("INSERT INTO legal_v2_versions (case_id, version, estado, contenido_json, hash_contenido, autor, comentario, vigente) VALUES (?, ?, ?, ?, ?, ?, ?, 1)", (case_id, current_version, state, json.dumps(data, ensure_ascii=False, default=str), digest, user, comment or f"Cambio de estado a {state}"))
        version_id = int(cur.lastrowid)
    _audit(user, f"Cambiar estado a {state}", "legal_v2_cases", case_id, before.get("modulo_codigo", ""), before=before, after={"estado": state}, comment=comment)


def _save_file(case_id: int, files, kind: str, signed: bool, required: bool, user: str) -> int:
    root = Path("data/legal_v2_files") / str(case_id)
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    with db_transaction() as conn:
        version = conn.execute("SELECT id FROM legal_v2_versions WHERE case_id=? AND vigente=1 ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
        version_id = int(version["id"]) if version else None
    for uploaded in files or []:
        ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        if ext not in FILE_EXTENSIONS:
            raise ValueError(f"Formato no permitido: {uploaded.name}")
        content = uploaded.getvalue()
        if len(content) > 25 * 1024 * 1024:
            raise ValueError(f"Archivo supera 25 MB: {uploaded.name}")
        digest = hashlib.sha256(content).hexdigest()
        path = root / f"{digest[:12]}_{Path(uploaded.name).name}"
        with db_transaction() as conn:
            duplicate = conn.execute("SELECT id FROM legal_v2_files WHERE case_id=? AND hash_sha256=?", (case_id, digest)).fetchone()
            if duplicate:
                continue
            path.write_bytes(content)
            conn.execute("INSERT INTO legal_v2_files (case_id, version_id, nombre_archivo, extension, tamano_bytes, hash_sha256, ruta, tipo_documento, firmado, obligatorio, cargado_por) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (case_id, version_id, uploaded.name, ext, len(content), digest, str(path), kind, int(signed), int(required), user))
        count += 1
        _audit(user, "Cargar documento", "legal_v2_files", case_id, after={"archivo": uploaded.name, "hash": digest, "tipo": kind})
    return count


def _dashboard() -> None:
    df = _read_cases()
    today = pd.Timestamp.today().normalize()
    due_count = 0
    if not df.empty:
        dates = pd.to_datetime(df["fecha_vencimiento"].fillna(df["fecha_limite"]), errors="coerce")
        due_count = int((dates.notna() & (dates <= today + pd.Timedelta(days=30)) & ~df["estado"].isin(["Cerrado", "Archivado", "Cancelado"])).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expedientes", len(df))
    c2.metric("Riesgo alto/crítico", int(df["riesgo"].isin(["Alto", "Crítico"]).sum()) if not df.empty else 0)
    c3.metric("Vencen ≤ 30 días", due_count)
    c4.metric("Activos", int(~df["estado"].isin(["Cerrado", "Archivado", "Cancelado"]).sum()) if not df.empty else 0)
    if df.empty:
        st.info("No hay expedientes legales en Legal V2.")
        return
    by_module = df.groupby("modulo_nombre").size().reset_index(name="cantidad").sort_values("cantidad", ascending=False)
    st.markdown("### Expedientes por módulo")
    st.dataframe(by_module, use_container_width=True, hide_index=True)
    st.markdown("### Expedientes recientes")
    st.dataframe(df[["id", "codigo", "modulo_nombre", "titulo", "estado", "riesgo", "responsable", "fecha_limite", "fecha_vencimiento"]].head(30), use_container_width=True, hide_index=True)


def _new_case(user: str) -> None:
    st.subheader("Nuevo expediente legal")
    with st.form("legal_v2_new_case"):
        col1, col2 = st.columns(2)
        module_code = col1.selectbox("Módulo legal", [m[0] for m in MODULES], format_func=_module_name)
        title = col2.text_input("Título / asunto *")
        description = st.text_area("Descripción")
        c1, c2, c3 = st.columns(3)
        responsible = c1.text_input("Responsable *", value=user)
        reviewer = c2.text_input("Revisor")
        approver = c3.text_input("Aprobador")
        c4, c5, c6 = st.columns(3)
        state = c4.selectbox("Estado", STATES)
        risk = c5.selectbox("Riesgo", RISK_LEVELS, index=1)
        confidentiality = c6.selectbox("Confidencialidad", CONFIDENTIALITY, index=1)
        c7, c8, c9 = st.columns(3)
        start = c7.date_input("Fecha inicio", value=date.today())
        limit = c8.date_input("Fecha límite", value=date.today() + timedelta(days=30))
        expiration = c9.date_input("Fecha vencimiento/revisión", value=date.today() + timedelta(days=365))
        c10, c11 = st.columns(2)
        party = c10.text_input("Contraparte")
        client_supplier = c11.text_input("Cliente / proveedor relacionado")
        channel = st.selectbox("Canal", ["Presencial", "WhatsApp", "Instagram", "Web", "Correo", "Contrato", "Factura", "Otro"])
        jurisdiction = st.text_input("Jurisdicción", value="Venezuela")
        amount = st.number_input("Monto USD relacionado", min_value=0.0, step=1.0)
        tags = st.text_input("Etiquetas", help="Separadas por coma")
        extra = st.text_area("Campos específicos / notas JSON", help="Puedes registrar datos especiales del módulo en texto o JSON.")
        submit = st.form_submit_button("Crear expediente", type="primary")
    if submit:
        if not title.strip() or not responsible.strip():
            st.error("Título y responsable son obligatorios.")
            return
        payload = {
            "modulo_codigo": module_code, "titulo": title, "descripcion": description,
            "responsable": responsible, "revisor": reviewer, "aprobador": approver,
            "estado": state, "riesgo": risk, "prioridad": "Alta" if risk in {"Alto", "Crítico"} else "Media",
            "confidencialidad": confidentiality, "fecha_inicio": start.isoformat(),
            "fecha_limite": limit.isoformat(), "fecha_vencimiento": expiration.isoformat(),
            "contraparte": party, "cliente_proveedor": client_supplier, "canal": channel,
            "jurisdiccion": jurisdiction, "monto_usd": float(amount), "etiquetas": tags,
            "datos_json": extra,
        }
        case_id = _create_case(payload, user)
        st.success(f"Expediente legal #{case_id} creado.")
        st.rerun()


def _case_detail(user: str) -> None:
    df = _read_cases()
    if df.empty:
        st.info("No hay expedientes. Crea uno primero.")
        return
    labels = {int(r.id): f"{r.codigo} · {r.modulo_nombre} · {r.titulo} · {r.estado}" for _, r in df.iterrows()}
    case_id = st.selectbox("Expediente", list(labels), format_func=lambda x: labels[x])
    row = df[df["id"] == case_id].iloc[0]
    tabs = st.tabs(["Ficha", "Flujo", "Documentos", "Versiones", "Checklist", "Calendario", "Auditoría"])
    with tabs[0]:
        st.json({"Código": row["codigo"], "Módulo": row["modulo_nombre"], "Estado": row["estado"], "Riesgo": row["riesgo"], "Responsable": row["responsable"], "Revisor": row["revisor"], "Aprobador": row["aprobador"], "Contraparte": row["contraparte"], "Jurisdicción": row["jurisdiccion"], "Confidencialidad": row["confidencialidad"]})
        st.markdown("### Descripción")
        st.write(row["descripcion"] or "Sin descripción")
        st.markdown("### Datos específicos")
        st.code(row["datos_json"] or "Sin datos específicos")
    with tabs[1]:
        new_state = st.selectbox("Nuevo estado", STATES, index=STATES.index(row["estado"]) if row["estado"] in STATES else 0)
        comment = st.text_area("Comentario obligatorio para cambios sensibles")
        if st.button("Actualizar estado", type="primary"):
            _update_state(case_id, new_state, user, comment)
            st.success("Estado actualizado con auditoría y nueva versión.")
            st.rerun()
    with tabs[2]:
        kind = st.selectbox("Tipo documental", ["Contrato", "PDF legal", "Word editable", "Excel", "Factura", "Correo", "Captura", "Acta", "Autorización", "Registro mercantil", "Licencia", "Audio", "Video", "Otro"])
        signed = st.checkbox("Firmado")
        required = st.checkbox("Obligatorio")
        files = st.file_uploader("Cargar documentos", accept_multiple_files=True, type=sorted(FILE_EXTENSIONS))
        if st.button("Guardar documentos"):
            try:
                count = _save_file(case_id, files, kind, signed, required, user)
                st.success(f"{count} documento(s) guardado(s).")
            except Exception as exc:
                st.error(str(exc))
        with db_transaction() as conn:
            fdf = pd.read_sql_query("SELECT id,nombre_archivo,extension,tamano_bytes,hash_sha256,tipo_documento,firmado,obligatorio,cargado_por,fecha_carga FROM legal_v2_files WHERE case_id=? ORDER BY id DESC", conn, params=(case_id,))
        st.dataframe(fdf, use_container_width=True, hide_index=True) if not fdf.empty else st.info("Sin documentos.")
    with tabs[3]:
        with db_transaction() as conn:
            vdf = pd.read_sql_query("SELECT id,version,estado,hash_contenido,autor,revisor,aprobador,comentario,fecha,vigente FROM legal_v2_versions WHERE case_id=? ORDER BY id DESC", conn, params=(case_id,))
        st.dataframe(vdf, use_container_width=True, hide_index=True) if not vdf.empty else st.info("Sin versiones.")
    with tabs[4]:
        with db_transaction() as conn:
            cdf = pd.read_sql_query("SELECT * FROM legal_v2_checklist WHERE case_id=? ORDER BY id", conn, params=(case_id,))
        st.dataframe(cdf, use_container_width=True, hide_index=True) if not cdf.empty else st.info("Sin checklist.")
    with tabs[5]:
        with st.form("calendar_event"):
            title = st.text_input("Evento")
            event_type = st.selectbox("Tipo", ["Vencimiento", "Renovación", "Audiencia", "Revisión", "Aprobación", "Recordatorio"])
            event_date = st.date_input("Fecha", value=date.today() + timedelta(days=7))
            alert_days = st.number_input("Alertar días antes", min_value=0, value=7, step=1)
            save_event = st.form_submit_button("Guardar evento")
        if save_event and title.strip():
            with db_transaction() as conn:
                conn.execute("INSERT INTO legal_v2_calendar (case_id, modulo_codigo, titulo, tipo_evento, fecha_evento, responsable, alerta_dias) VALUES (?, ?, ?, ?, ?, ?, ?)", (case_id, row["modulo_codigo"], title, event_type, event_date.isoformat(), user, int(alert_days)))
            _audit(user, "Crear evento legal", "legal_v2_calendar", case_id, row["modulo_codigo"], after={"titulo": title, "fecha": event_date.isoformat()})
            st.success("Evento guardado.")
        with db_transaction() as conn:
            edf = pd.read_sql_query("SELECT * FROM legal_v2_calendar WHERE case_id=? ORDER BY fecha_evento", conn, params=(case_id,))
        st.dataframe(edf, use_container_width=True, hide_index=True) if not edf.empty else st.info("Sin eventos.")
    with tabs[6]:
        with db_transaction() as conn:
            adf = pd.read_sql_query("SELECT * FROM legal_v2_audit WHERE entidad_id=? OR (entidad='legal_v2_cases' AND entidad_id=?) ORDER BY id DESC", conn, params=(case_id, case_id))
        st.dataframe(adf, use_container_width=True, hide_index=True) if not adf.empty else st.info("Sin auditoría.")


def _modules_catalog() -> None:
    st.subheader("Catálogo del departamento jurídico")
    df = pd.DataFrame(MODULES, columns=["Código", "Módulo", "Objetivo", "Categoría"])
    st.dataframe(df, use_container_width=True, hide_index=True)
    with st.expander("Reglas empresariales base"):
        st.markdown("""
- Ningún documento vigente se edita directamente; se crea una nueva versión.
- Ningún documento firmado o aprobado se elimina físicamente.
- Todo archivo carga hash SHA-256 y auditoría.
- Los módulos de datos personales deben vincular consentimiento, privacidad y evidencia.
- Contratos, licencias, garantías y permisos requieren fecha de vencimiento o revisión.
- Estados sensibles como Rechazado, Suspendido, Archivado o Cancelado requieren comentario.
- Roles recomendados: Legal Admin, Legal Reviewer, Compliance Officer, Dirección, Marketing lectura, Ventas lectura y Soporte limitado.
""")


def _reports() -> None:
    df = _read_cases()
    st.subheader("Reportes jurídicos")
    if df.empty:
        st.info("Sin información para reportes.")
        return
    report = st.selectbox("Reporte", ["Contratos y documentos próximos a vencer", "Riesgos altos y críticos", "Pendientes por responsable", "Expedientes por estado", "Auditoría general"])
    if report == "Contratos y documentos próximos a vencer":
        dates = pd.to_datetime(df["fecha_vencimiento"].fillna(df["fecha_limite"]), errors="coerce")
        out = df[dates.notna() & (dates <= pd.Timestamp.today().normalize() + pd.Timedelta(days=60))]
        st.dataframe(out, use_container_width=True, hide_index=True)
    elif report == "Riesgos altos y críticos":
        st.dataframe(df[df["riesgo"].isin(["Alto", "Crítico"])], use_container_width=True, hide_index=True)
    elif report == "Pendientes por responsable":
        out = df[~df["estado"].isin(["Cerrado", "Archivado", "Cancelado"])].groupby(["responsable", "estado"]).size().reset_index(name="cantidad")
        st.dataframe(out, use_container_width=True, hide_index=True)
    elif report == "Expedientes por estado":
        st.dataframe(df.groupby(["modulo_nombre", "estado"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)
    else:
        with db_transaction() as conn:
            adf = pd.read_sql_query("SELECT * FROM legal_v2_audit ORDER BY id DESC LIMIT 500", conn)
        st.dataframe(adf, use_container_width=True, hide_index=True)


def render_legal_v2(user: str = "Sistema") -> None:
    _ensure_schema()
    st.title("⚖️ Legal V2 — Departamento Jurídico Digital")
    st.caption("Sub-ERP jurídico empresarial: expedientes, documentos, versiones, auditoría, riesgos, calendario, cumplimiento y reportes.")
    view = st.radio("Vista", ["Dashboard", "Nuevo expediente", "Expediente", "Catálogo legal", "Reportes"], horizontal=True, key="legal_v2_view")
    st.divider()
    if view == "Dashboard":
        _dashboard()
    elif view == "Nuevo expediente":
        _new_case(user)
    elif view == "Expediente":
        _case_detail(user)
    elif view == "Catálogo legal":
        _modules_catalog()
    else:
        _reports()
