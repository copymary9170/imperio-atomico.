import streamlit as st

# ==================================================
# CONFIGURACIÓN DE LA APP
# ==================================================

st.set_page_config(
    page_title="Imperio Atómico ERP",
    layout="wide",
    page_icon="⚛️"
)

# ==================================================
# INICIALIZAR BASE DE DATOS
# ==================================================

from database.schema import init_schema
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db

init_schema()
restore_session_snapshot()
set_session_role_from_db()

# ==================================================
# IMPORTAR VISTAS
# ==================================================

from views.dashboard import render_dashboard
from views.inventario import render_inventario
from views.kardex import render_kardex
from views.clientes import render_clientes
from views.crm import render_crm
from views.cmyk import render_cmyk
from views.activos import render_activos
from views.diagnostico import render_diagnostico
from views.otros_procesos import render_otros_procesos
from views.corte import render_corte
from views.sublimacion import render_sublimacion
from views.produccion_manual import render_produccion_manual
from views.ventas import render_ventas
from views.gastos import render_gastos
from views.caja import render_caja
from views.auditoria import render_auditoria
from views.cotizaciones import render_cotizaciones
from views.calculadora import render_calculadora
from views.costeo import render_costeo
from views.contabilidad import render_contabilidad
from views.rentabilidad import render_rentabilidad
from views.planeacion_financiera import render_planeacion_financiera

# Usa tu módulo unificado de configuración
from modules.configuracion import render_sidebar_config_snapshot, render_configuracion

# ERP EXPANDIDO
from views.erp_nuevos_modulos import (
    render_portafolio_modulos,
    render_cuentas_por_pagar,
    render_tesoreria,
    render_costeo_industrial,
    render_mermas_desperdicio,
    render_mantenimiento_activos,
    render_planificacion_produccion,
    render_control_calidad,
    render_rutas_produccion,
    render_impuestos,
    render_conciliacion_bancaria,
    render_marketing_ventas,
    render_fidelizacion,
    render_rrhh,
    render_seguridad_roles,
    render_manuales_sop,
)

from views.catalogo import render_catalogo

# ==================================================
# USUARIO
# ==================================================

usuario = st.session_state.get("usuario", "Sistema")
user_role = st.session_state.get("rol", "Operator")

# ==================================================
# ESTILOS SIDEBAR PRO
# ==================================================

st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {
            min-width: 320px;
            max-width: 320px;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] {
            gap: 0.35rem;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 0.75rem;
            padding: 0.35rem 0.75rem;
            transition: all 0.2s ease;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
            border-color: rgba(255, 255, 255, 0.2);
            background: rgba(255, 255, 255, 0.08);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.title("⚛️ Imperio Atómico ERP")
st.sidebar.caption("Accede rápido a cada módulo desde el menú lateral.")

if st.sidebar.button("🚪 Cerrar sesión", use_container_width=True):
    st.session_state.pop("usuario", None)
    st.session_state.pop("rol", None)
    save_session_snapshot()
    st.rerun()

render_sidebar_config_snapshot()

# ==================================================
# MENÚ PRINCIPAL (ORDEN EMPRESARIAL + PERMISOS)
# Cada entrada: "Etiqueta": ("permiso", callback)
# ==================================================

MENU_ROUTES = {
    # CORE
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard()),

    # OPERACIONES
    "📦 Inventario": ("inventario.view", lambda: render_inventario(usuario)),
    "📊 Kardex": ("kardex.view", lambda: render_kardex(usuario)),
    "🏗️ Activos": ("activos.view", lambda: render_activos(usuario)),

    # CLIENTES Y VENTAS
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "🤝 CRM": ("crm.view", lambda: render_crm(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing / Ventas": ("crm.view", lambda: render_marketing_ventas(usuario)),
    "⭐ Fidelización": ("clientes.view", lambda: render_fidelizacion(usuario)),

    # PRODUCCIÓN
    "✂️ Corte Industrial": ("produccion.execute", lambda: render_corte(usuario)),
    "🔥 Sublimación": ("produccion.execute", lambda: render_sublimacion(usuario)),
    "🎨 Producción Manual": ("produccion.execute", lambda: render_produccion_manual(usuario)),
    "🗓️ Planificación de producción": ("produccion.plan", lambda: render_planificacion_produccion(usuario)),
    "🧭 Rutas de producción": ("produccion.route", lambda: render_rutas_produccion(usuario)),
    "✅ Control de calidad": ("produccion.quality", lambda: render_control_calidad(usuario)),
    "♻️ Mermas y desperdicio": ("produccion.scrap", lambda: render_mermas_desperdicio(usuario)),

    # FINANZAS
    "📉 Gastos": ("gastos.view", lambda: render_gastos(usuario)),
    "🏦 Caja empresarial": ("caja.view", lambda: render_caja(usuario)),
    "🏦 Tesorería": ("tesoreria.view", lambda: render_tesoreria(usuario)),
    "💸 Cuentas por pagar": ("cxp.view", lambda: render_cuentas_por_pagar(usuario)),
    "📚 Contabilidad": ("contabilidad.view", lambda: render_contabilidad(usuario)),
    "🏛️ Conciliación bancaria": ("conciliacion.view", lambda: render_conciliacion_bancaria(usuario)),
    "🧾 Impuestos": ("impuestos.view", lambda: render_impuestos(usuario)),

    # ANALÍTICA
    "📈 Rentabilidad": ("costeo.view", lambda: render_rentabilidad(usuario)),
    "🔮 Planeación financiera": ("tesoreria.view", lambda: render_planeacion_financiera(usuario)),
    "📊 Auditoría": ("auditoria.view", lambda: render_auditoria(usuario)),

    # COSTOS
    "🧮 Costeo": ("costeo.view", lambda: render_costeo(usuario)),
    "🧮 Costeo industrial": ("costeo_industrial.view", lambda: render_costeo_industrial(usuario)),
    "🧮 Calculadora": ("dashboard.view", lambda: render_calculadora(usuario)),

    # RRHH
    "👨‍💼 RRHH": ("rrhh.view", lambda: render_rrhh(usuario)),

    # SISTEMA
    "⚙️ Configuración": ("config.view", lambda: render_configuracion(usuario)),
    "🔐 Seguridad / Roles": ("security.view", lambda: render_seguridad_roles(usuario)),
    "📘 Manuales / SOP": ("dashboard.view", lambda: render_manuales_sop(usuario)),

    # OTROS
    "🎨 CMYK": ("produccion.view", lambda: render_cmyk(usuario)),
    "🧠 Diagnóstico IA": ("dashboard.view", lambda: render_diagnostico(usuario)),
    "🛠️ Otros procesos": ("dashboard.view", lambda: render_otros_procesos(usuario)),
    "🛍️ Catálogo": ("inventario.view", lambda: render_catalogo(usuario)),

    # EXPANSIÓN ERP
    "🧩 Nuevos módulos ERP": ("dashboard.view", lambda: render_portafolio_modulos(usuario)),
    "🛠️ Mantenimiento": ("mantenimiento.view", lambda: render_mantenimiento_activos(usuario)),
}

# ==================================================
# FILTRAR MENÚ SEGÚN PERMISOS
# ==================================================

VISIBLE_MENU = {
    label: callback
    for label, (permiso, callback) in MENU_ROUTES.items()
    if has_permission(permiso)
}

if not VISIBLE_MENU:
    st.error("🚫 Tu usuario no tiene acceso a módulos habilitados.")
    save_session_snapshot()
    st.stop()

# ==================================================
# SELECTOR
# ==================================================

menu = st.sidebar.radio(
    "Menú principal",
    list(VISIBLE_MENU.keys()),
    label_visibility="collapsed",
)

# ==================================================
# EJECUCIÓN
# ==================================================

VISIBLE_MENU[menu]()
save_session_snapshot()
