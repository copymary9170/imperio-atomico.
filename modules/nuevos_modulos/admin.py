from __future__ import annotations

from .types import ModuleBlueprint

ADMIN_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="rrhh",
        name="RRHH",
        icon="👨‍💼",
        category="Administración interna",
        summary="Centraliza empleados, roles operativos, asistencia y comisiones.",
        capabilities=(
            "Usuarios / empleados",
            "Roles",
            "Asistencia",
            "Comisiones",
        ),
        integrations=("Seguridad", "Ventas", "Producción", "Auditoría"),
        business_value="Ordena la operación interna y facilita medir productividad y pago variable.",
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
