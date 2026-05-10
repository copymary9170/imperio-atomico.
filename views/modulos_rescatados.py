import streamlit as st


MODULOS_RESCATADOS = [
    {
        "nombre": "Cuentas por pagar",
        "estado": "Ya independiente",
        "ruta": "💸 Cuentas por pagar",
        "utilidad": "Controlar deudas con proveedores, vencimientos, saldos y pagos pendientes.",
        "accion": "Mantener como módulo financiero operativo.",
    },
    {
        "nombre": "Tesorería",
        "estado": "Ya independiente",
        "ruta": "🏦 Tesorería",
        "utilidad": "Ver entradas, salidas, métodos de pago y flujo de caja real.",
        "accion": "Usarlo como centro de liquidez y pagos.",
    },
    {
        "nombre": "Costeo industrial",
        "estado": "Ya independiente",
        "ruta": "🧮 Costeo industrial",
        "utilidad": "Calcular costos reales por proceso, materiales, mano de obra e indirectos.",
        "accion": "Conectarlo con cotizaciones, producción y rentabilidad.",
    },
    {
        "nombre": "Mermas y desperdicio",
        "estado": "Ya independiente",
        "ruta": "♻️ Mermas y desperdicio",
        "utilidad": "Registrar material perdido, causa, costo y recuperación posible.",
        "accion": "Usarlo para reducir desperdicio y ajustar precios.",
    },
    {
        "nombre": "Control de calidad",
        "estado": "Ya independiente",
        "ruta": "✅ Control de calidad",
        "utilidad": "Revisar trabajos antes de entrega, detectar fallas y aprobar producción.",
        "accion": "Conectarlo con corte, sublimación y producción manual.",
    },
    {
        "nombre": "Mantenimiento de activos",
        "estado": "Ya independiente",
        "ruta": "🛠️ Mantenimiento",
        "utilidad": "Planificar mantenimiento de máquinas, impresoras y equipos críticos.",
        "accion": "Conectarlo con activos y calendario operativo.",
    },
    {
        "nombre": "Marketing / Ventas",
        "estado": "Ya independiente",
        "ruta": "📣 Marketing / Ventas",
        "utilidad": "Planificar promociones, campañas y acciones comerciales.",
        "accion": "Conectarlo con publicaciones, catálogo y CRM.",
    },
    {
        "nombre": "Fidelización",
        "estado": "Ya independiente",
        "ruta": "⭐ Fidelización",
        "utilidad": "Dar seguimiento a clientes frecuentes, beneficios y recompra.",
        "accion": "Conectarlo con clientes, ventas y CRM.",
    },
    {
        "nombre": "RRHH",
        "estado": "Ya independiente",
        "ruta": "👨‍💼 RRHH",
        "utilidad": "Gestionar personas, roles operativos y responsabilidades.",
        "accion": "Complementarlo con nómina y trabajadores.",
    },
    {
        "nombre": "Seguridad / Roles",
        "estado": "Ya independiente",
        "ruta": "🔐 Seguridad / Roles",
        "utilidad": "Controlar permisos, accesos y seguridad del sistema.",
        "accion": "Mantenerlo como módulo de administración del ERP.",
    },
    {
        "nombre": "Compras y proveedores",
        "estado": "Rescatable",
        "ruta": "No visible en app.py",
        "utilidad": "Gestionar proveedores, compras, condiciones de pago y documentos.",
        "accion": "Agregarlo al menú como módulo independiente si la vista existe.",
    },
]


def render_modulos_rescatados(usuario="Sistema"):
    st.title("🧩 Módulos ERP rescatados")
    st.caption(f"Usuario activo: {usuario}")

    st.info(
        "Este módulo convierte el antiguo portafolio de 'Nuevos módulos ERP' en una vista útil: muestra qué ya está separado, qué se puede usar y qué falta conectar."
    )

    total = len(MODULOS_RESCATADOS)
    independientes = sum(1 for item in MODULOS_RESCATADOS if item["estado"] == "Ya independiente")
    rescatables = sum(1 for item in MODULOS_RESCATADOS if item["estado"] == "Rescatable")

    col1, col2, col3 = st.columns(3)
    col1.metric("Módulos revisados", total)
    col2.metric("Ya independientes", independientes)
    col3.metric("Por rescatar", rescatables)

    st.divider()

    filtro = st.radio(
        "Filtro",
        ["Todos", "Ya independiente", "Rescatable"],
        horizontal=True,
    )

    for modulo in MODULOS_RESCATADOS:
        if filtro != "Todos" and modulo["estado"] != filtro:
            continue

        with st.container(border=True):
            cols = st.columns([1.2, 1, 2])
            cols[0].subheader(modulo["nombre"])
            cols[1].badge(modulo["estado"]) if hasattr(cols[1], "badge") else cols[1].write(modulo["estado"])
            cols[2].write(f"Ruta: {modulo['ruta']}")
            st.write(f"**Utilidad:** {modulo['utilidad']}")
            st.write(f"**Acción recomendada:** {modulo['accion']}")

    st.divider()
    st.subheader("Decisión operativa")
    st.write(
        "El botón 'Nuevos módulos ERP' debe quedar como portafolio estratégico. Los módulos que ya tienen operación real deben vivir como entradas independientes en el menú principal."
    )
