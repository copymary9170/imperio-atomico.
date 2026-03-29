from __future__ import annotations

from .types import ModuleBlueprint

ADMIN_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="rrhh_blueprint",
        name="RRHH Blueprint",
        icon="👨‍💼",
        category="Administración interna",
        summary="Centraliza el ciclo de vida del colaborador: alta, desarrollo, desempeño y compensación variable.",
        capabilities=(
            "Usuarios / empleados",
            "Onboarding y bajas",
            "Asistencia y novedades",
            "Evaluación de desempeño",
            "Comisiones / incentivos",
            "Capacitación y cumplimiento",
        ),
        integrations=("Seguridad", "Ventas", "Producción", "Contabilidad", "Auditoría"),
        business_value="Reduce rotación evitable, acelera decisiones de talento y conecta productividad con compensación.",
        priority="Media",
    ),
    ModuleBlueprint(
        key="seguridad_roles",
        name="Seguridad / Roles",
        icon="🔐",
        category="Administración interna",
        summary="Amplía el control de permisos por módulo, proceso y nivel de riesgo.",
        capabilities=(
            "Perfiles avanzados",
            "Permisos por módulo",
            "Restricciones por acción crítica",
        ),
        integrations=("RRHH", "Auditoría", "Configuración"),
        business_value="Protege datos sensibles y reduce errores humanos en procesos críticos.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="manuales_sop",
        name="Manuales / SOP",
        icon="📘",
        category="Administración interna",
        summary="Formaliza procedimientos, instructivos y conocimiento operativo dentro del ERP.",
        capabilities=(
            "Manuales internos",
            "Procedimientos estándar",
            "Versionado documental",
        ),
        integrations=("RRHH", "Calidad", "Activos", "Producción"),
        business_value="Reduce dependencia del conocimiento informal y mejora entrenamiento del personal.",
        priority="Media",
    ),
)



