import streamlit as st

from security.permissions import has_permission
from views import legal_enterprise_phase2
from views.legal_hub import render_legal_hub

LEGAL_V2_RELEASE = "2026.06.28 · Seguridad y flujos jurídicos"


def _validate_assignment(data: dict, user: str) -> None:
    creator = str(user or "").strip().casefold()
    reviewer = str(data.get("revisor") or "").strip().casefold()
    approver = str(data.get("aprobador") or "").strip().casefold()

    if reviewer and reviewer == creator:
        raise ValueError("El creador y el revisor deben ser personas diferentes.")
    if approver and approver == creator:
        raise ValueError("El creador y el aprobador deben ser personas diferentes.")
    if reviewer and approver and reviewer == approver:
        raise ValueError("El revisor y el aprobador deben ser personas diferentes.")


def _enable_assignment_validation() -> None:
    if getattr(legal_enterprise_phase2, "assignment_validation_enabled", False):
        return

    create_case = legal_enterprise_phase2._create_case

    def create_case_with_validation(data: dict, user: str) -> int:
        _validate_assignment(data, user)
        return create_case(data, user)

    legal_enterprise_phase2._create_case = create_case_with_validation
    legal_enterprise_phase2.assignment_validation_enabled = True


def render_legal_v2(user: str = "Sistema") -> None:
    if not has_permission("legal.view"):
        st.error("No tienes permiso para acceder al Departamento Jurídico.")
        return

    st.title("⚖️ Departamento Jurídico")
    st.caption("Operación legal y arquitectura Enterprise visibles desde el mismo módulo.")
    st.success(f"✅ Legal V2 actualizado: {LEGAL_V2_RELEASE}")

    with st.expander("Controles activos en esta versión"):
        st.markdown(
            """
- Acceso al módulo mediante `legal.view`.
- Permisos separados por contratos, reclamos, privacidad, autorizaciones, incidentes y documentos.
- Transiciones de estado controladas.
- Motivo obligatorio para cerrar, cancelar o marcar como vencido.
- Auditoría con datos anteriores y posteriores.
- Segregación entre creador, revisor y aprobador en Enterprise.
            """
        )

    available_modes = ["Operación jurídica"]
    if has_permission("legal.admin"):
        available_modes.append("Enterprise")

    mode = st.radio(
        "Vista",
        available_modes,
        horizontal=True,
        key="legal_v2_visible_mode",
    )
    st.divider()

    if mode == "Enterprise":
        _enable_assignment_validation()
        try:
            legal_enterprise_phase2.render_legal_enterprise_phase2(user)
        except ValueError as exc:
            st.error(str(exc))
    else:
        render_legal_hub(user)
