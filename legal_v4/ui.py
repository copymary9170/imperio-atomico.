from __future__ import annotations

import streamlit as st

from legal_v4.domain import CreateMatterCommand, STATUS_FLOW
from legal_v4.service import LegalService
from security.permissions import has_permission

MATTER_TYPES = [
    "Aviso legal", "Terminos y condiciones", "Privacidad", "Cookies", "Consentimiento",
    "Propiedad intelectual", "Marca", "Derecho de autor", "Contrato cliente",
    "Contrato proveedor", "Contrato laboral", "Garantia", "Reclamo", "Devolucion",
    "Demanda", "Litigio", "Evidencia", "Riesgo", "Cumplimiento", "Licencia o permiso",
    "Auditoria", "Gobierno corporativo",
]


def _matter_label(matters, matter_id: int) -> str:
    row = matters[matters["id"] == matter_id].iloc[0]
    return f"{row['code']} - {row['title']}"


def render_legal_v4(user: str = "Sistema") -> None:
    service = LegalService()
    st.title("Departamento Juridico Enterprise")
    st.caption("Legal V4.1: expedientes, documentos, workflows, obligaciones, auditoria y migracion controlada.")

    metrics = service.dashboard()
    a, b, c, d, e, f = st.columns(6)
    a.metric("Expedientes", metrics["total"])
    b.metric("Aprobados/vigentes", metrics["active"])
    c.metric("Riesgo alto/critico", metrics["critical"])
    d.metric("Vencidos", metrics["overdue"])
    e.metric("Documentos", metrics["documents"])
    f.metric("Obligaciones", metrics["obligations"])

    tabs = st.tabs(["Dashboard", "Expedientes", "Workflow", "Documentos", "Obligaciones", "Auditoria", "Migracion", "Arquitectura"])
    matters = service.list_matters()

    with tabs[0]:
        if matters.empty:
            st.info("No hay expedientes registrados en Legal V4.")
        else:
            q = st.text_input("Buscar", key="legal_v4_search")
            filtered = matters
            if q.strip():
                mask = matters.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
                filtered = matters[mask]
            st.dataframe(filtered[["code", "matter_type", "title", "status", "risk_level", "confidentiality", "owner", "due_date", "expiration_date"]], use_container_width=True, hide_index=True)

    with tabs[1]:
        if not has_permission("legal.create") and not has_permission("legal.admin"):
            st.warning("No tienes permiso para crear expedientes.")
        else:
            with st.form("legal_v4_create"):
                x, y = st.columns(2)
                matter_type = x.selectbox("Tipo de expediente", MATTER_TYPES)
                title = y.text_input("Titulo")
                description = st.text_area("Descripcion, objeto y alcance")
                p, q, r = st.columns(3)
                owner = p.text_input("Responsable", value=user)
                reviewer = q.text_input("Revisor")
                approver = r.text_input("Aprobador")
                submitted = st.form_submit_button("Crear expediente", type="primary")
            if submitted:
                try:
                    matter_id = service.create_matter(CreateMatterCommand(matter_type, title, description, owner, reviewer, approver), user)
                    st.success(f"Expediente {matter_id} creado con version inicial y auditoria.")
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))

    with tabs[2]:
        if matters.empty:
            st.info("Crea o migra expedientes antes de usar workflows.")
        else:
            matter_id = st.selectbox("Expediente", matters["id"].astype(int).tolist(), format_func=lambda value: _matter_label(matters, value), key="workflow_matter")
            selected = matters[matters["id"] == matter_id].iloc[0]
            allowed = sorted(STATUS_FLOW.get(selected["status"], set()))
            st.write(f"Estado actual: **{selected['status']}**")
            if not allowed:
                st.info("Este expediente no tiene transiciones disponibles.")
            else:
                target = st.selectbox("Nuevo estado", allowed)
                comment = st.text_area("Comentario obligatorio segun politica")
                if st.button("Cambiar estado", type="primary"):
                    try:
                        service.change_status(int(matter_id), target, comment, user)
                        st.success("Estado actualizado con evento de workflow y auditoria.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

    with tabs[3]:
        if matters.empty:
            st.info("No hay expedientes para adjuntar documentos.")
        else:
            matter_id = st.selectbox("Expediente documental", matters["id"].astype(int).tolist(), format_func=lambda value: _matter_label(matters, value), key="document_matter")
            with st.form("legal_v4_document"):
                document_type = st.text_input("Tipo documental", value="Evidencia")
                uploaded = st.file_uploader("Archivo")
                signed = st.checkbox("Documento firmado")
                provider = st.text_input("Proveedor de firma")
                reference = st.text_input("Referencia de firma")
                sent = st.form_submit_button("Adjuntar documento", type="primary")
            if sent:
                try:
                    if not uploaded:
                        raise ValueError("Debes seleccionar un archivo.")
                    service.attach_document(int(matter_id), uploaded, document_type, signed, user, provider, reference)
                    st.success("Documento adjuntado, hasheado y auditado.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            docs = service.list_documents(int(matter_id))
            if not docs.empty:
                st.dataframe(docs[["document_type", "original_name", "extension", "size_bytes", "sha256", "signed", "uploaded_by", "uploaded_at"]], use_container_width=True, hide_index=True)

    with tabs[4]:
        with st.form("legal_v4_obligation"):
            matter_id = None
            if not matters.empty:
                matter_id = st.selectbox("Expediente relacionado", [0] + matters["id"].astype(int).tolist(), format_func=lambda value: "Sin expediente" if value == 0 else _matter_label(matters, value))
            title = st.text_input("Obligacion")
            owner = st.text_input("Responsable", value=user)
            obligation_type = st.selectbox("Tipo", ["Cumplimiento", "Privacidad", "Contrato", "Fiscal", "Gobierno corporativo", "Licencia"])
            due_date = st.date_input("Fecha limite", value=None)
            description = st.text_area("Descripcion")
            sent = st.form_submit_button("Crear obligacion", type="primary")
        if sent:
            try:
                service.create_obligation(None if matter_id == 0 else int(matter_id), title, owner, user, obligation_type, due_date.isoformat() if due_date else None, description)
                st.success("Obligacion creada y auditada.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        obligations = service.list_obligations()
        if not obligations.empty:
            st.dataframe(obligations[["obligation_type", "title", "owner", "due_date", "status", "created_by", "created_at"]], use_container_width=True, hide_index=True)

    with tabs[5]:
        if not has_permission("legal.audit.view") and not has_permission("legal.admin"):
            st.warning("No tienes permiso para consultar auditoria juridica.")
        else:
            audit = service.list_audit()
            if audit.empty:
                st.info("No hay eventos de auditoria.")
            else:
                st.dataframe(audit[["event_time", "actor", "action", "entity_type", "entity_id", "previous_hash", "event_hash"]], use_container_width=True, hide_index=True)

    with tabs[6]:
        st.markdown("Importa una sola vez los expedientes existentes de Legal V2. La operacion es idempotente y conserva el identificador de origen.")
        if has_permission("legal.admin"):
            if st.button("Migrar datos de Legal V2", type="primary"):
                try:
                    imported = service.migrate_legacy(user)
                    st.success(f"Migracion completada. Expedientes importados: {imported}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No fue posible completar la migracion: {exc}")
        else:
            st.info("Solo un administrador juridico puede ejecutar la migracion.")

    with tabs[7]:
        st.markdown(
            """
            **Controles activos Legal V4.1**

            - Esquema V4 paralelo y versionado.
            - Restricciones, claves foraneas e indices SQLite.
            - Segregacion entre responsable, revisor y aprobador.
            - Version inicial obligatoria por expediente.
            - Auditoria inmutable con hash encadenado.
            - Eventos de workflow por transicion.
            - Repositorio documental con hash SHA-256, duplicados y legal hold.
            - Obligaciones legales y de cumplimiento.
            - Migracion idempotente desde Legal V2.
            - Interfaz sin SQL directo.
            """
        )
