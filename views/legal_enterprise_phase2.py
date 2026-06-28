from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction

STATES = ["Borrador", "En revisión", "Cambios solicitados", "Aprobado", "Vigente", "Pendiente", "En proceso", "Cerrado", "Suspendido", "Archivado", "Vencido", "Cancelado"]
RISKS = ["Bajo", "Medio", "Alto", "Crítico"]
CONTRACT_TYPES = ["Cliente", "Proveedor", "Laboral", "Servicio", "Confidencialidad", "Arrendamiento", "Licencia", "Otro"]
COMPLIANCE_TYPES = ["Aviso Legal", "Términos y Condiciones", "Política de Privacidad", "Política de Cookies", "Consentimiento", "Normativa", "Licencia", "Permiso"]


def _ensure_schema() -> None:
    with db_transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS legal_v2_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            modulo_codigo TEXT NOT NULL,
            modulo_nombre TEXT NOT NULL,
            categoria TEXT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            responsable TEXT NOT NULL,
            revisor TEXT,
            aprobador TEXT,
            estado TEXT NOT NULL DEFAULT 'Borrador',
            riesgo TEXT NOT NULL DEFAULT 'Medio',
            confidencialidad TEXT NOT NULL DEFAULT 'Interno',
            contraparte TEXT,
            canal TEXT,
            jurisdiccion TEXT DEFAULT 'Venezuela',
            fecha_inicio TEXT,
            fecha_limite TEXT,
            fecha_vencimiento TEXT,
            monto_usd REAL DEFAULT 0,
            etiquetas TEXT,
            datos_json TEXT,
            version_actual TEXT NOT NULL DEFAULT '1.0',
            creado_por TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_por TEXT,
            actualizado_en TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_v2_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            extension TEXT,
            tamano_bytes INTEGER DEFAULT 0,
            hash_sha256 TEXT,
            ruta TEXT,
            tipo_documento TEXT,
            firmado INTEGER DEFAULT 0,
            obligatorio INTEGER DEFAULT 0,
            cargado_por TEXT,
            fecha_carga TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS legal_v2_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            entidad TEXT NOT NULL,
            entidad_id INTEGER,
            modulo_codigo TEXT,
            antes_json TEXT,
            despues_json TEXT,
            comentario TEXT,
            resultado TEXT DEFAULT 'Exitoso'
        );
        CREATE TABLE IF NOT EXISTS legal_v2_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            modulo_codigo TEXT,
            titulo TEXT NOT NULL,
            tipo_evento TEXT NOT NULL,
            fecha_evento TEXT NOT NULL,
            responsable TEXT,
            estado TEXT DEFAULT 'Pendiente',
            alerta_dias INTEGER DEFAULT 7
        );
        CREATE TABLE IF NOT EXISTS legal_v2_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rol TEXT NOT NULL,
            permiso TEXT NOT NULL,
            descripcion TEXT,
            UNIQUE(rol, permiso)
        );
        CREATE TABLE IF NOT EXISTS legal_v2_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            area TEXT NOT NULL,
            regla TEXT NOT NULL,
            severidad TEXT NOT NULL DEFAULT 'Media',
            activa INTEGER DEFAULT 1
        );
        """)
        roles = [
            ("Legal Admin", "legal.*", "Control total"),
            ("Legal Reviewer", "legal.review", "Revisión y comentarios"),
            ("Compliance Officer", "legal.audit", "Auditoría y cumplimiento"),
            ("Dirección", "legal.approve", "Aprobación final"),
            ("Ventas Lectura", "legal.read", "Consulta de documentos vigentes"),
        ]
        for role in roles:
            conn.execute("INSERT OR IGNORE INTO legal_v2_roles(rol,permiso,descripcion) VALUES(?,?,?)", role)
        rules = [
            ("Documentos", "No eliminar documentos firmados o publicados", "Crítica"),
            ("Contratos", "No editar contratos aprobados; crear nueva versión", "Crítica"),
            ("Cumplimiento", "No publicar documentos incompletos", "Alta"),
            ("Auditoría", "Registrar usuario, fecha, antes, después y resultado", "Crítica"),
        ]
        for rule in rules:
            conn.execute("INSERT OR IGNORE INTO legal_v2_rules(area,regla,severidad) VALUES(?,?,?)", rule)


def _read(sql: str, params: tuple = ()) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _next_code(prefix: str) -> str:
    year = date.today().year
    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) total FROM legal_v2_cases WHERE codigo LIKE ?", (f"{prefix}-{year}-%",)).fetchone()
    return f"{prefix}-{year}-{int(row['total'] or 0) + 1:04d}"


def _audit(user: str, action: str, entity_id: int, module: str, after: dict, comment: str = "") -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO legal_v2_audit(usuario,accion,entidad,entidad_id,modulo_codigo,despues_json,comentario) VALUES(?,?,?,?,?,?,?)",
            (user, action, "legal_v2_cases", entity_id, module, json.dumps(after, ensure_ascii=False, default=str), comment),
        )


def _create_case(data: dict, user: str) -> int:
    payload = dict(data)
    payload["creado_por"] = user
    payload["actualizado_por"] = user
    payload["actualizado_en"] = pd.Timestamp.now().isoformat()
    with db_transaction() as conn:
        keys = list(payload)
        cur = conn.execute(
            f"INSERT INTO legal_v2_cases ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            [payload[key] for key in keys],
        )
        case_id = int(cur.lastrowid)
    _audit(user, "Crear expediente", case_id, payload["modulo_codigo"], payload)
    return case_id


def _dashboard() -> None:
    cases = _read("SELECT * FROM legal_v2_cases ORDER BY id DESC")
    files = _read("SELECT * FROM legal_v2_files")
    today = pd.Timestamp.today().normalize()
    due = 0
    overdue = 0
    if not cases.empty:
        dates = pd.to_datetime(cases["fecha_vencimiento"].fillna(cases["fecha_limite"]), errors="coerce")
        active_mask = ~cases["estado"].isin(["Cerrado", "Archivado", "Cancelado"])
        due = int((dates.notna() & (dates >= today) & (dates <= today + pd.Timedelta(days=30)) & active_mask).sum())
        overdue = int((dates.notna() & (dates < today) & active_mask).sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Expedientes", len(cases))
    c2.metric("Activos", int((~cases["estado"].isin(["Cerrado", "Archivado", "Cancelado"])).sum()) if not cases.empty else 0)
    c3.metric("Riesgo alto/crítico", int(cases["riesgo"].isin(["Alto", "Crítico"]).sum()) if not cases.empty else 0)
    c4.metric("Vencen ≤ 30 días", due)
    c5.metric("Documentos", len(files))
    if overdue:
        st.error(f"🔴 {overdue} expediente(s) vencido(s).")
    elif due:
        st.warning(f"🟡 {due} expediente(s) próximos a vencer.")
    else:
        st.success("🟢 Sin vencimientos próximos registrados.")
    if not cases.empty:
        left, right = st.columns(2)
        with left:
            st.markdown("### Por área")
            st.dataframe(cases.groupby(["categoria", "estado"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)
        with right:
            st.markdown("### Riesgos")
            st.dataframe(cases.groupby(["riesgo", "estado"]).size().reset_index(name="cantidad"), use_container_width=True, hide_index=True)
        st.markdown("### Atención inmediata")
        urgent = cases[cases["riesgo"].isin(["Alto", "Crítico"]) | cases["estado"].isin(["Vencido", "En revisión"])]
        st.dataframe(urgent[["codigo", "modulo_nombre", "titulo", "estado", "riesgo", "responsable", "fecha_vencimiento"]], use_container_width=True, hide_index=True)


def _portfolio(user: str) -> None:
    cases = _read("SELECT * FROM legal_v2_cases ORDER BY id DESC")
    if cases.empty:
        st.info("No hay expedientes.")
        return
    c1, c2, c3 = st.columns(3)
    category = c1.selectbox("Categoría", ["Todas"] + sorted(cases["categoria"].dropna().unique().tolist()))
    state = c2.selectbox("Estado", ["Todos"] + STATES)
    risk = c3.selectbox("Riesgo", ["Todos"] + RISKS)
    filtered = cases.copy()
    if category != "Todas": filtered = filtered[filtered["categoria"] == category]
    if state != "Todos": filtered = filtered[filtered["estado"] == state]
    if risk != "Todos": filtered = filtered[filtered["riesgo"] == risk]
    st.dataframe(filtered[["id", "codigo", "modulo_nombre", "titulo", "contraparte", "estado", "riesgo", "responsable", "fecha_limite", "fecha_vencimiento"]], use_container_width=True, hide_index=True)
    with st.expander("Actualizar expediente"):
        case_id = st.selectbox("Expediente", cases["id"].astype(int).tolist(), format_func=lambda value: f"#{value} · {cases[cases['id']==value].iloc[0]['titulo']}")
        row = cases[cases["id"] == case_id].iloc[0]
        new_state = st.selectbox("Nuevo estado", STATES, index=STATES.index(row["estado"]) if row["estado"] in STATES else 0)
        new_risk = st.selectbox("Nuevo riesgo", RISKS, index=RISKS.index(row["riesgo"]) if row["riesgo"] in RISKS else 1)
        comment = st.text_area("Comentario / motivo")
        if st.button("Guardar actualización", type="primary"):
            with db_transaction() as conn:
                conn.execute("UPDATE legal_v2_cases SET estado=?, riesgo=?, actualizado_por=?, actualizado_en=? WHERE id=?", (new_state, new_risk, user, pd.Timestamp.now().isoformat(), int(case_id)))
            _audit(user, "Actualizar expediente", int(case_id), row["modulo_codigo"], {"estado": new_state, "riesgo": new_risk}, comment)
            st.success("Expediente actualizado.")
            st.rerun()


def _contracts(user: str) -> None:
    st.subheader("Gestión contractual")
    with st.form("enterprise_contract"):
        a, b, c = st.columns(3)
        contract_type = a.selectbox("Tipo de contrato", CONTRACT_TYPES)
        title = b.text_input("Título *")
        party = c.text_input("Contraparte *")
        description = st.text_area("Objeto y alcance")
        d, e, f = st.columns(3)
        responsible = d.text_input("Responsable *", value=user)
        reviewer = e.text_input("Revisor")
        approver = f.text_input("Aprobador")
        g, h, i = st.columns(3)
        start = g.date_input("Inicio", value=date.today())
        expiration = h.date_input("Vencimiento", value=date.today() + timedelta(days=365))
        amount = i.number_input("Monto USD", min_value=0.0)
        risk = st.selectbox("Riesgo", RISKS, index=1)
        jurisdiction = st.text_input("Jurisdicción", value="Venezuela")
        submit = st.form_submit_button("Crear contrato", type="primary")
    if submit:
        if not title.strip() or not party.strip() or not responsible.strip():
            st.error("Título, contraparte y responsable son obligatorios.")
        else:
            module = "CONTRATOS_" + contract_type.upper().replace(" ", "_")
            case_id = _create_case({"codigo": _next_code("CTR"), "modulo_codigo": module, "modulo_nombre": f"Contrato {contract_type}", "categoria": "Contratos", "titulo": title, "descripcion": description, "responsable": responsible, "revisor": reviewer, "aprobador": approver, "estado": "Borrador", "riesgo": risk, "confidencialidad": "Confidencial", "contraparte": party, "jurisdiccion": jurisdiction, "fecha_inicio": start.isoformat(), "fecha_limite": expiration.isoformat(), "fecha_vencimiento": expiration.isoformat(), "monto_usd": float(amount), "version_actual": "1.0"}, user)
            st.success(f"Contrato #{case_id} creado.")
            st.rerun()
    contracts = _read("SELECT * FROM legal_v2_cases WHERE categoria='Contratos' ORDER BY id DESC")
    if not contracts.empty:
        st.dataframe(contracts[["codigo", "modulo_nombre", "titulo", "contraparte", "estado", "riesgo", "fecha_vencimiento", "responsable"]], use_container_width=True, hide_index=True)


def _compliance(user: str) -> None:
    st.subheader("Cumplimiento y políticas")
    with st.form("enterprise_compliance"):
        a, b = st.columns(2)
        doc_type = a.selectbox("Documento", COMPLIANCE_TYPES)
        title = b.text_input("Título *")
        summary = st.text_area("Contenido / resumen")
        c, d, e = st.columns(3)
        responsible = c.text_input("Responsable *", value=user)
        reviewer = d.text_input("Revisor legal")
        approver = e.text_input("Aprobador")
        f, g = st.columns(2)
        effective = f.date_input("Vigencia", value=date.today())
        review = g.date_input("Próxima revisión", value=date.today() + timedelta(days=365))
        risk = st.selectbox("Riesgo", RISKS, index=1, key="compliance_risk")
        submit = st.form_submit_button("Crear documento", type="primary")
    if submit:
        if not title.strip() or not responsible.strip():
            st.error("Título y responsable son obligatorios.")
        else:
            module = doc_type.upper().replace(" ", "_").replace("Í", "I").replace("Ó", "O")
            case_id = _create_case({"codigo": _next_code("CMP"), "modulo_codigo": module, "modulo_nombre": doc_type, "categoria": "Cumplimiento", "titulo": title, "descripcion": summary, "responsable": responsible, "revisor": reviewer, "aprobador": approver, "estado": "Borrador", "riesgo": risk, "confidencialidad": "Interno", "jurisdiccion": "Venezuela", "fecha_inicio": effective.isoformat(), "fecha_limite": review.isoformat(), "fecha_vencimiento": review.isoformat(), "monto_usd": 0.0, "version_actual": "1.0"}, user)
            st.success(f"Documento #{case_id} creado.")
            st.rerun()
    docs = _read("SELECT * FROM legal_v2_cases WHERE categoria='Cumplimiento' ORDER BY id DESC")
    if not docs.empty:
        st.dataframe(docs[["codigo", "modulo_nombre", "titulo", "estado", "riesgo", "fecha_inicio", "fecha_vencimiento", "responsable"]], use_container_width=True, hide_index=True)


def _calendar(user: str) -> None:
    cases = _read("SELECT id,codigo,titulo,modulo_codigo FROM legal_v2_cases ORDER BY id DESC")
    with st.form("enterprise_calendar"):
        case_options = [0] + (cases["id"].astype(int).tolist() if not cases.empty else [])
        case_id = st.selectbox("Expediente relacionado", case_options, format_func=lambda value: "General" if value == 0 else f"{cases[cases['id']==value].iloc[0]['codigo']} · {cases[cases['id']==value].iloc[0]['titulo']}")
        title = st.text_input("Evento *")
        a, b, c = st.columns(3)
        event_type = a.selectbox("Tipo", ["Vencimiento", "Renovación", "Audiencia", "Revisión", "Aprobación", "Recordatorio"])
        event_date = b.date_input("Fecha", value=date.today() + timedelta(days=7))
        alert_days = c.number_input("Alertar días antes", min_value=0, value=7)
        submit = st.form_submit_button("Crear evento")
    if submit and title.strip():
        module = "GENERAL"
        if case_id and not cases.empty:
            module = str(cases[cases["id"] == case_id].iloc[0]["modulo_codigo"])
        with db_transaction() as conn:
            conn.execute("INSERT INTO legal_v2_calendar(case_id,modulo_codigo,titulo,tipo_evento,fecha_evento,responsable,alerta_dias) VALUES(?,?,?,?,?,?,?)", (int(case_id) or None, module, title, event_type, event_date.isoformat(), user, int(alert_days)))
        st.success("Evento creado.")
        st.rerun()
    events = _read("SELECT * FROM legal_v2_calendar ORDER BY fecha_evento")
    st.dataframe(events, use_container_width=True, hide_index=True) if not events.empty else st.info("Sin eventos legales.")


def _governance() -> None:
    tabs = st.tabs(["Roles y permisos", "Reglas", "Auditoría"])
    with tabs[0]:
        st.dataframe(_read("SELECT * FROM legal_v2_roles ORDER BY rol"), use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(_read("SELECT * FROM legal_v2_rules ORDER BY severidad DESC"), use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(_read("SELECT * FROM legal_v2_audit ORDER BY id DESC LIMIT 500"), use_container_width=True, hide_index=True)


def render_legal_enterprise_phase2(user: str = "Sistema") -> None:
    _ensure_schema()
    st.title("🏛️ Departamento Jurídico Enterprise")
    st.caption("Mesa jurídica operativa: dashboard, cartera, contratos, cumplimiento, calendario y gobierno.")
    section = st.radio("Área", ["Dashboard", "Cartera jurídica", "Contratos", "Cumplimiento", "Calendario", "Gobierno"], horizontal=True, key="legal_enterprise_phase2_view")
    st.divider()
    if section == "Dashboard": _dashboard()
    elif section == "Cartera jurídica": _portfolio(user)
    elif section == "Contratos": _contracts(user)
    elif section == "Cumplimiento": _compliance(user)
    elif section == "Calendario": _calendar(user)
    else: _governance()
