def has_permission(role, module):

    permissions = {

        "Admin": ["*"],

        "Operador": [
            "Ventas",
            "Producción",
            "Inventario"
        ],

        "Contador": [
            "Gastos",
            "Dashboard"
        ]

    }

    if "*" in permissions.get(role, []):
        return True

    return module in permissions.get(role, [])
