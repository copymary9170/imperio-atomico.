import streamlit as st

from security.permissions import has_permission
from views.legal_enterprise_v3 import render_legal_enterprise_v3
from views.legal_hub import render_legal_hub

LEGAL_V2_RELEASE = "2026.06.28 · Enterprise V3 endurecido"


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
- Acceso mediante permisos jurídicos granulares y permisos específicos para revisar, aprobar, publicar y firmar.
- Expediente maestro con módulos jurídicos especializados y gestión contractual transversal.
- Confidencialidad por registro para expedientes internos, confidenciales y restringidos.
- Workflows diferenciados para documentos, contratos, casos, riesgos y registros oficiales.
- Segregación efectiva entre creador, revisor y aprobador asignado.
- Matriz documental obligatoria por módulo antes de publicar, firmar o declarar vigencia.
- Gestión documental con formatos, tamaño máximo, hash SHA-256 y detección global de duplicados.
- Control de versiones con comparación, restauración como nueva versión e historial.
- Obligaciones contractuales y jurídicas vinculadas al expediente.
- Auditoría encadenada con antes, después, usuario, contexto de sesión y hashes de integridad.
- Automatización de tareas por vencimientos y reportes exportables a Excel y CSV.
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
        render_legal_enterprise_v3(user)
    else:
        render_legal_hub(user)
