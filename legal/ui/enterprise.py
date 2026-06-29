from __future__ import annotations

import pandas as pd
import streamlit as st

from legal.application.commands import CreateLegalMatterCommand
from legal.application.facade import LegalEnterpriseFacade, serialize_for_export
from legal.domain.enums import Confidentiality, RiskLevel
from legal.security.rbac import LegalPermission, SecurityContext
from security.permissions import has_permission

MATTER_TYPES = [
    "Aviso legal",
    "Terminos y condiciones",
    "Privacidad",
    "Cookies",
    "Consentimiento",
    "Propiedad intelectual",
    "Marca",
    "Derecho de autor",
    "Contrato cliente",
    "Contrato proveedor",
    "Contrato laboral",
    "Garantia",
    "Reclamo",
    "Devolucion",
    "Demanda",
    "Litigio",
    "Evidencia",
    "Riesgo",
    "Cumplimiento",
    "Licencia o permiso",
    "Auditoria",
    "Gobierno corporativo",
]


def build_security_context(user: str) -> SecurityContext:
    permissions = {permission.value for permission in LegalPermission if has_permission(permission.value)}
    return SecurityContext(
        user=user or "Sistema",
        roles=tuple([str(st.session_state.get("rol", ""))]),
        permissions=frozenset(permissions),
        session_id=str(st.session_state.get("session_id", "streamlit-session")),
        correlation_id=str(st.session_state.get("legal_correlation_id", "")),
    )


def render_legal_enterprise(user: str = "Sistema") -> None:
    """Render the first enterprise Legal UI backed by application services."""
    context = build_security_context(user)
    app = LegalEnterpriseFacade()

    st.title("⚖️ Departamento Jurídico Enterprise")
    st.caption("Arquitectura nueva: UI → Application Facade → Repositories → SQLite. Legal V2/V4 legacy permanecen como respaldo de migración.")

    try:
        metrics = app.dashboard(context)
    except PermissionError as exc:
        st.error(str(exc))
        return

    a, b, c, d, e, f = st.columns(6)
    a.metric("Expedientes", metrics["matters"])
    b.metric("Críticos", metrics["critical"])
    c.metric("Contratos", metrics["contracts"])
    d.metric("Litigios", metrics["litigations"])
    e.metric("Riesgos abiertos", metrics["open_risks"])
    f.metric("Tareas abiertas", metrics["open_tasks"])

    tabs = st.tabs([
        "Dashboard",
        "Expedientes",
        "Contratos",
        "Privacidad",
        "Litigios",
        "Riesgos y cumplimiento",
        "Gobierno",
        "Auditoría",
        "Arquitectura",
    ])

    with tabs[0]:
        rows = app.matters(context)
        df = pd.DataFrame(rows)
        q = st.text_input("Buscar en el departamento jurídico", key="legal_enterprise_q")
        if not df.empty and q.strip():
            mask = df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
            df = df[mask]
        if df.empty:
            st.info("No hay expedientes Enterprise registrados todavía.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "Exportar JSON controlado",
                serialize_for_export(df.to_dict(orient="records")),
                file_name="legal_enterprise_expedientes.json",
                mime="application/json",
            )

    with tabs[1]:
        if not context.has(LegalPermission.CREATE):
            st.warning("No tienes permiso para crear expedientes jurídicos.")
        else:
            with st.form("legal_enterprise_create_matter"):
                x, y = st.columns(2)
                matter_type = x.selectbox("Tipo", MATTER_TYPES)
                title = y.text_input("Título")
                description = st.text_area("Descripción, objeto, alcance y base documental")
                p, q, r = st.columns(3)
                owner = p.text_input("Responsable", value=user)
                reviewer = q.text_input("Revisor")
                approver = r.text_input("Aprobador")
                p2, q2, r2 = st.columns(3)
                risk = p2.selectbox("Riesgo", list(RiskLevel), format_func=lambda item: item.value, index=1)
                confidentiality = q2.selectbox("Confidencialidad", list(Confidentiality), format_func=lambda item: item.value, index=1)
                counterparty = r2.text_input("Contraparte")
                jurisdiction = st.text_input("Jurisdicción", value="Venezuela")
                legal_basis = st.text_area("Base legal / fundamento")
                tags = st.text_input("Etiquetas")
                retention_years = st.number_input("Retención documental en años", min_value=1, max_value=100, value=5)
                submitted = st.form_submit_button("Crear expediente Enterprise", type="primary")
            if submitted:
                try:
                    matter_id = app.create_matter(
                        CreateLegalMatterCommand(
                            code="",
                            matter_type=matter_type,
                            title=title,
                            description=description,
                            owner=owner,
                            created_by=user,
                            reviewer=reviewer,
                            approver=approver,
                            risk_level=risk,
                            confidentiality=confidentiality,
                            counterparty=counterparty,
                            jurisdiction=jurisdiction,
                            legal_basis=legal_basis,
                            tags=tags,
                            retention_years=int(retention_years),
                        ),
                        context,
                    )
                    st.success(f"Expediente Enterprise creado y auditado: {matter_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tabs[2]:
        _render_domain_placeholder("Gestión contractual", "legal_contracts", ["contratos", "obligaciones", "renovaciones", "firmas", "penalidades"])

    with tabs[3]:
        _render_domain_placeholder("Privacidad y documentos públicos", "legal_privacy_notices / legal_consents", ["avisos", "cookies", "consentimientos", "revocaciones", "evidencia de aceptación"])

    with tabs[4]:
        _render_domain_placeholder("Litigios y evidencias", "legal_litigation_cases / legal_evidence", ["casos", "audiencias", "cuantías", "abogados", "cadena de custodia"])

    with tabs[5]:
        _render_domain_placeholder("Riesgos y cumplimiento", "legal_risks / legal_compliance_obligations", ["matriz de riesgos", "controles", "hallazgos", "planes", "evidencias"])

    with tabs[6]:
        _render_domain_placeholder("Gobierno corporativo", "legal_governance_meetings", ["órganos", "actas", "quórum", "resoluciones", "seguimiento"])

    with tabs[7]:
        if not context.has(LegalPermission.AUDIT_VIEW):
            st.warning("No tienes permiso para ver auditoría jurídica.")
        else:
            audit_rows = app.audit(context)
            if not audit_rows:
                st.info("No hay auditoría Enterprise registrada.")
            else:
                st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)

    with tabs[8]:
        st.markdown(
            """
            ### Arquitectura activa

            - `legal/domain`: entidades, enums, errores y reglas de workflow.
            - `legal/application`: comandos y fachada de casos de uso.
            - `legal/infrastructure/sqlite`: migraciones, repositorios y consultas.
            - `legal/security`: RBAC jurídico con denegación por defecto.
            - `legal/audit`: eventos sellados con hash.
            - `legal/ui`: interfaz Streamlit sin SQL directo.

            ### Estado

            Esta pantalla usa el nuevo esquema Enterprise y convive con Legal V2/V4 mientras se completa la migración.
            """
        )


def _render_domain_placeholder(title: str, table: str, capabilities: list[str]) -> None:
    st.subheader(title)
    st.info(f"Base de datos creada: `{table}`. Pendiente conectar formularios operativos y casos de uso específicos.")
    st.write("Capacidades previstas:")
    st.write(", ".join(capabilities))
