from __future__ import annotations

import streamlit as st

from legal_v4.domain import CreateMatterCommand
from legal_v4.reports import summarize_portfolio
from legal_v4.service import LegalService
from security.permissions import has_permission

MATTER_TYPES = [
    "Aviso legal", "Terminos y condiciones", "Privacidad", "Cookies", "Consentimiento",
    "Propiedad intelectual", "Marca", "Derecho de autor", "Contrato cliente",
    "Contrato proveedor", "Contrato laboral", "Garantia", "Reclamo", "Devolucion",
    "Demanda", "Litigio", "Evidencia", "Riesgo", "Cumplimiento", "Licencia o permiso",
    "Auditoria", "Gobierno corporativo",
]


def render_legal_v4(user: str = "Sistema") -> None:
    service = LegalService()
    st.title("Departamento Juridico Enterprise")
    st.caption("Legal V4.1: expedientes, documentos, tareas, calendario, auditoria, cumplimiento y gobierno corporativo.")

    metrics = service.dashboard()
    a, b, c, d = st.columns(4)
    a.metric("Expedientes", metrics["total"])
    b.metric("Aprobados o vigentes", metrics["active"])
    c.metric("Riesgo alto o critico", metrics["critical"])
    d.metric("Vencidos", metrics["overdue"])

    tabs = st.tabs(["Dashboard", "Expedientes", "Documentos", "Calendario", "Migracion", "Auditoria", "Arquitectura"])
    with tabs[0]:
        st.subheader("Resumen ejecutivo")
        st.dataframe(summarize_portfolio(), use_container_width=True, hide_index=True)
        matters = service.list_matters()
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
        documents = service.list_documents()
        if documents.empty:
            st.info("No hay documentos migrados o registrados en Legal V4.")
        else:
            st.dataframe(documents[["code", "matter_title", "document_type", "original_name", "extension", "size_bytes", "sha256", "signed", "uploaded_by", "uploaded_at"]], use_container_width=True, hide_index=True)

    with tabs[3]:
        calendar = service.list_calendar()
        if calendar.empty:
            st.info("No hay eventos legales registrados.")
        else:
            st.dataframe(calendar[["event_type", "title", "event_date", "alert_days", "owner", "status", "created_by"]], use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("Importa de forma idempotente los datos existentes de Legal V2 hacia Legal V4.")
        if has_permission("legal.admin"):
            col1, col2 = st.columns(2)
            if col1.button("Migrar expedientes", type="primary"):
                try:
                    imported = service.migrate_legacy(user)
                    st.success(f"Migracion de expedientes completada. Importados: {imported}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No fue posible completar la migracion: {exc}")
            if col2.button("Migrar operaciones V2"):
                try:
                    counts = service.migrate_legacy_operations(user)
                    st.success(f"Migracion operativa completada: {counts}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No fue posible completar la migracion operativa: {exc}")
        else:
            st.info("Solo un administrador juridico puede ejecutar la migracion.")

    with tabs[5]:
        result = service.verify_audit_chain()
        if result["valid"]:
            st.success(f"Cadena de auditoria valida. Eventos verificados: {result['events']}.")
        else:
            st.error(f"Cadena de auditoria alterada en evento #{result['failed_at']} de {result['events']}.")

    with tabs[6]:
        st.markdown(
            """
            **Controles activos Legal V4.1**

            - Esquema V4 paralelo y versionado.
            - Restricciones, claves foraneas e indices SQLite.
            - Segregacion entre responsable, revisor y aprobador.
            - Version inicial obligatoria por expediente.
            - Documentos con hash SHA-256 y referencia de almacenamiento.
            - Firmas registrables por proveedor desacoplado.
            - Calendario legal, comentarios, controles y matriz de riesgos.
            - Auditoria inmutable con hash encadenado y verificacion de integridad.
            - Migracion idempotente de expedientes, versiones, archivos, tareas y calendario de Legal V2.
            - Interfaz sin SQL directo.
            """
        )
