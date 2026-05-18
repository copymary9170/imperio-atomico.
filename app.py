import os
from pathlib import Path

import streamlit as st

# ==================================================

st.set_page_config(
    page_title="Imperio Atómico ERP",
    layout="wide",
    page_icon="⚛️",
)

# ==================================================
# INICIALIZAR BASE DE DATOS
# ==================================================

from database.schema import init_schema
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db

init_schema()
restore_session_snapshot()

# ==================================================
# LOGIN
# ==================================================

def _render_login() -> None:
    st.title("⚛️ Imperio Atómico ERP")
    st.subheader("Iniciar sesión")

    with st.form("login_form"):
        login_usuario = st.text_input("Usuario")
        login_password = st.text_input("Contraseña", type="password")
        submit_login = st.form_submit_button("Entrar")

    if submit_login:
        usuario_clean = str(login_usuario or "").strip()
        if not usuario_clean:
            st.error("Ingresa tu usuario.")
            return

        st.session_state["usuario"] = usuario_clean
        st.session_state["rol"] = "Operator"
        st.session_state["authentication_status"] = True
        set_session_role_from_db()
        save_session_snapshot()
        st.rerun()


if not st.session_state.get("authentication_status"):
    _render_login()
    st.stop()

set_session_role_from_db()

# ==================================================
# IMPORTAR VISTAS
# ==================================================

from views.dashboard import render_dashboard
from views.panel_ejecutivo import render_panel_ejecutivo
from views.inventario import render_inventario
from views.kardex import render_kardex
from views.clientes import render_clientes
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
from views.manuales_sop import render_manuales_sop
from views.catalogo import render_catalogo
from views.rutas_produccion import render_rutas_produccion
from views.planificacion_produccion import render_planificacion_produccion
from views.modulos_rescatados import render_modulos_rescatados
from views.areas_empresariales import render_area_combinada, render_area_empresarial
from views.almacen_avanzado import render_almacen_avanzado
from views.activos_patrimonial import render_activos_patrimonial
from views.proveedores_compras import render_compras_suministro, render_proveedores
from views.despacho_entregas import render_despacho_entregas
from views.unidades_fraccionadas import render_unidades_fraccionadas

# NUEVAS VISTAS OPERATIVAS
from views.nomina_trabajadores import render_nomina_trabajadores
from views.presupuesto_mensual import render_presupuesto_mensual
from views.calendario_operativo import render_calendario_operativo
from views.publicaciones_marketing import render_publicaciones_marketing

# CONFIGURACION
from modules.configuracion import render_sidebar_config_snapshot, render_configuracion

# ERP EXPANDIDO INDEPENDIENTE
from views.erp_nuevos_modulos import (
    render_cuentas_por_pagar,
    render_tesoreria,
    render_costeo_industrial,
    render_mermas_desperdicio,
    render_mantenimiento_activos,
    render_control_calidad,
    render_impuestos,
    render_conciliacion_bancaria,
    render_marketing_ventas,
    render_rrhh,
    render_seguridad_roles,
)

# ==================================================
# USUARIO
# ==================================================

usuario = st.session_state.get("usuario", "Sistema")
user_role = st.session_state.get("rol", "Operator")


def render_dashboard_unificado(usuario: str) -> None:
    tab_operativo, tab_ejecutivo = st.tabs([
        "Dashboard operativo",
        "📊 Panel ejecutivo",
    ])
    with tab_operativo:
        render_dashboard()
    with tab_ejecutivo:
        render_panel_ejecutivo(usuario)


def render_inventario_almacen_unificado(usuario: str) -> None:
    tab_inventario, tab_almacen, tab_compras, tab_proveedores, tab_unidades, tab_archivos = st.tabs([
        "Inventario operativo",
        "Almacén avanzado",
        "🛒 Compras",
        "👥 Proveedores",
        "📏 Unidades fraccionadas",
        "Archivos de almacén",
    ])
    with tab_inventario:
        render_inventario(usuario)
    with tab_almacen:
        render_almacen_avanzado(usuario)
    with tab_compras:
        render_compras_suministro(usuario)
    with tab_proveedores:
        render_proveedores(usuario)
    with tab_unidades:
        render_unidades_fraccionadas(usuario)
    with tab_archivos:
        render_area_empresarial("Almacén", usuario, show_title=False)


def render_produccion_unificada(usuario: str) -> None:
    tab_plan, tab_area, tab_despacho = st.tabs([
        "Planificación producción",
        "Archivos de producción",
        "🚚 Despacho / Entregas",
    ])
    with tab_plan:
        render_planificacion_produccion(usuario)
    with tab_area:
        render_area_empresarial("Producción", usuario, show_title=False)
    with tab_despacho:
        render_despacho_entregas(usuario)


def render_activos_unificado(usuario: str) -> None:
    tab_operacion, tab_patrimonial = st.tabs([
        "Operación de activos",
        "Control patrimonial",
    ])
    with tab_operacion:
        render_activos(usuario)
    with tab_patrimonial:
        render_activos_patrimonial(usuario)

# ==================================================
# ESTILOS SIDEBAR
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
    snapshot_path = Path(__file__).resolve().parent / "data" / "session_snapshot.json"
    try:
        snapshot_path.unlink(missing_ok=True)
    except Exception:
        pass

    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.rerun()

render_sidebar_config_snapshot()

# ==================================================
# MENU PRINCIPAL
# ==================================================

MENU_ROUTES = {
    # CORE
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),

    # OPERACIONES
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "📊 Kardex": ("inventario.view", lambda: render_kardex(usuario)),
    "🏗️ Activos": ("activos.view", lambda: render_activos_unificado(usuario)),

    # CLIENTES Y VENTAS
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing / Ventas": ("crm.view", lambda: render_area_combinada("Marketing", render_marketing_ventas, usuario)),

    # PRODUCCION
    "🏭 Producción": (("produccion.plan", "produccion.execute"), lambda: render_produccion_unificada(usuario)),
    "✂️ Corte Industrial": (("produccion.execute", "produccion.plan"), lambda: render_corte(usuario)),
    "🔥 Sublimación": ("produccion.execute", lambda: render_sublimacion(usuario)),
    "🎨 Producción Manual": ("produccion.execute", lambda: render_produccion_manual(usuario)),
    "🧭 Rutas de producción": (("produccion.route", "produccion.execute"), lambda: render_rutas_produccion(usuario)),
    "✅ Control de calidad": ("produccion.quality", lambda: render_control_calidad(usuario)),
    "♻️ Mermas y desperdicio": ("produccion.scrap", lambda: render_mermas_desperdicio(usuario)),

    # FINANZAS
    "💼 Finanzas": (("tesoreria.view", "dashboard.view"), lambda: render_area_combinada("Finanzas", render_planeacion_financiera, usuario)),
    "📉 Gastos": ("gastos.view", lambda: render_gastos(usuario)),
    "🏦 Caja": ("caja.view", lambda: render_caja(usuario)),
    "🏦 Tesorería y cobranza": ("tesoreria.view", lambda: render_area_combinada("Tesorería y Cobranza", render_tesoreria, usuario)),
    "💸 Cuentas por pagar": (("cxp.view", "dashboard.view"), lambda: render_cuentas_por_pagar(usuario)),
    "📚 Contabilidad": ("contabilidad.view", lambda: render_area_combinada("Contabilidad", render_contabilidad, usuario)),
    "🏛️ Conciliación bancaria": ("conciliacion.view", lambda: render_conciliacion_bancaria(usuario)),
    "🧾 Impuestos": ("impuestos.view", lambda: render_impuestos(usuario)),

    # ADMINISTRACION Y RRHH
    "🗂️ Administración": (("dashboard.view", "config.view"), lambda: render_area_empresarial("Administración", usuario)),
    "👨‍💼 Nómina y trabajadores": ("nomina.view", lambda: render_nomina_trabajadores(usuario)),
    "💰 Presupuesto mensual": ("presupuesto.view", lambda: render_presupuesto_mensual(usuario)),
    "👥 RRHH": (("rrhh.view", "dashboard.view"), lambda: render_area_combinada("Recursos Humanos", render_rrhh, usuario)),

    # LEGAL
    "⚖️ Legal": (("dashboard.view", "config.view"), lambda: render_area_combinada("Legal", render_manuales_sop, usuario)),

    # ANALITICA
    "📈 Rentabilidad": ("costeo.view", lambda: render_rentabilidad(usuario)),
    "📊 Auditoría": ("auditoria.view", lambda: render_auditoria(usuario)),

    # COSTOS
    "🧮 Costeo": ("costeo.view", lambda: render_costeo(usuario)),
    "🧮 Costeo industrial": ("costeo_industrial.view", lambda: render_costeo_industrial(usuario)),
    "🧮 Calculadora": ("dashboard.view", lambda: render_calculadora(usuario)),

    # CALENDARIOS Y MARKETING
    "📅 Calendario operativo": ("calendario_operativo.view", lambda: render_calendario_operativo(usuario)),
    "📣 Publicaciones y marketing": ("publicaciones.view", lambda: render_publicaciones_marketing(usuario)),

    # SISTEMA
    "⚙️ Configuración": ("config.view", lambda: render_configuracion(usuario)),
    "🔐 Seguridad / Roles": (("security.view", "dashboard.view"), lambda: render_seguridad_roles(usuario)),
    "📘 Manuales / SOP": ("manuales.view", lambda: render_manuales_sop(usuario)),

    # OTROS
    "🎨 CMYK": ("produccion.view", lambda: render_cmyk(usuario)),
    "🧠 Diagnóstico IA": ("dashboard.view", lambda: render_diagnostico(usuario)),
    "🛠️ Otros procesos": ("dashboard.view", lambda: render_otros_procesos(usuario)),
    "🛍️ Catálogo": ("inventario.view", lambda: render_catalogo(usuario)),

    # MODULOS ERP INDEPENDIENTES
    "🧩 Módulos rescatados": ("dashboard.view", lambda: render_modulos_rescatados(usuario)),
    "🛠️ Mantenimiento": ("mantenimiento.view", lambda: render_mantenimiento_activos(usuario)),
}

# ==================================================
# FILTRAR POR PERMISOS
# ==================================================

def _can_access_menu_route(permission_rule):
    if isinstance(permission_rule, str):
        return has_permission(permission_rule)
    if isinstance(permission_rule, (tuple, list, set)):
        return any(has_permission(permission_code) for permission_code in permission_rule)
    return False


VISIBLE_MENU = {
    label: callback
    for label, (permiso, callback) in MENU_ROUTES.items()
    if _can_access_menu_route(permiso)
}


def _menu_debug_enabled() -> bool:
    env_value = os.getenv("IMPERIO_MENU_DEBUG", "").strip().casefold()
    return st.session_state.get("debug_menu", False) or env_value in {"1", "true", "yes", "on", "debug"}


def _render_sidebar_menu_debug() -> None:
    if not _menu_debug_enabled():
        return
    st.sidebar.divider()
    st.sidebar.caption(f"Rol activo: {user_role}")
    st.sidebar.caption(f"Rutas totales: {len(MENU_ROUTES)}")
    st.sidebar.caption(f"Rutas visibles: {len(VISIBLE_MENU)}")
    with st.sidebar.expander("Debug módulos visibles"):
        st.write(list(VISIBLE_MENU.keys()))


_render_sidebar_menu_debug()

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
# EJECUCION
# ==================================================

VISIBLE_MENU[menu]()
save_session_snapshot()
