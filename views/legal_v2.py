import streamlit as st

from security.permissions import has_permission
from views.legal_enterprise_core import render_legal_enterprise_core
from views.legal_hub import render_legal_hub

LEGAL_V2_RELEASE = "2026.06.28 · Núcleo jurídico Enterprise"


def render_legal_v2(user: str = "Sistema") -> None:
    if not has_permission("legal.view"):
        st.error("No tienes permiso para acceder al Departamento Jurídico.")
        return

    st.title("⚖️ Departamento Jurídico")
    st.caption("Operación jurídica diaria y núcleo Enterprise desde un mismo módulo.")
    st.success(f"✅ Legal V2 actualizado: {LEGAL_V2_RELEASE}")

    with st.expander("Controles activos en esta versión"):
        st.markdown(
            """
- Acceso mediante permisos jurídicos granulares.
- Expediente maestro para todos los módulos legales obligatorios.
- Workflows diferenciados para documentos, contratos, casos y riesgos.
- Segregación entre creador, revisor y aprobador.
- Gestión documental con formatos, tamaño máximo, hash SHA-256 y detección de duplicados.
- Control de versiones con motivo obligatorio e historial.
- Auditoría de acciones con antes, después, usuario, contexto de sesión y resultado.
- Calendario jurídico, vencimientos, alertas y reportes exportables.
- Reglas de bloqueo para documentos firmados y registros aprobados.
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
        render_legal_enterprise_core(user)
    else:
        render_legal_hub(user)
