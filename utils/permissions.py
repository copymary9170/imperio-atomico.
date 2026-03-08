# ======================================================
# CONTROL DE PERMISOS ERP
# ======================================================

PERMISSIONS = {

    "Admin": ["*"],

    "Operador": [
        "Ventas",
        "Producción",
        "Inventario",
        "Corte",
        "Sublimación"
    ],

    "Contador": [
        "Dashboard",
        "Gastos",
        "Auditoría"
    ],

    "Diseñador": [
        "CMYK",
        "Producción",
        "Diagnóstico"
    ]

}


def has_permission(role: str, module: str) -> bool:
    """
    Verifica si un rol tiene acceso a un módulo.
    """

    allowed = PERMISSIONS.get(role, [])

    if "*" in allowed:
        return True

    return module in allowed
