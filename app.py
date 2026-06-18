from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Imperio Atómico ERP", layout="wide", page_icon="⚛️")

from database.schema import init_schema
from database.auto_migrations import run_auto_migrations
from database.transactional_core import ensure_transactional_core_schema
from database.rate_config_defaults import ensure_rate_config_defaults
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from services.alert_service import get_alert_summary
from services.backup_service import create_daily_backup_if_needed

init_schema()
run_auto_migrations()
ensure_transactional_core_schema()
ensure_rate_config_defaults()
ensure_extended_permissions()
restore_session_snapshot()
try:
    create_daily_backup_if_needed()
except Exception:
    pass


def _render_login() -> None:
    st.title("⚛️ Imperio Atómico ERP")
    st.subheader("Iniciar sesión")
    with st.form("login_form"):
        login_usuario = st.text_input("Usuario")
        st.text_input("Contraseña", type="password")
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

from views.dashboard import render_dashboard
from views.panel_ejecutivo import render_panel_ejecutivo
from views.centro_alertas import render_centro_alertas
from views.inventario_almacen_unificado import render_inventario_almacen_unificado
from views.clientes import render_clientes
from views.contactos import render_contactos
from views.reportes import render_reportes
from views.respaldo import render_respaldo
from views.configuracion_sistema import render_configuracion_sistema
from views.cmyk import render_cmyk
from views.activos import render_activos
from views.activos_comprados import render_activos_comprados
from views.impresora_consumibles import render_impresora_consumibles
from views.otros_procesos import render_otros_procesos
from views.corte import render_corte
from views.sublimacion import render_sublimacion
from views.produccion_manual import render_produccion_manual
from views.ventas import render_ventas
from views.cotizaciones import render_cotizaciones
from views.calculadora import render_calculadora
from views.costeo import render_costeo
from views.costeo_impresion_real import render_costeo_impresion_real
from views.rentabilidad import render_rentabilidad
from views.planeacion_financiera import render_planeacion_financiera
from views.estado_resultados import render_estado_resultados
from views.cuentas_por_cobrar import render_cuentas_por_cobrar
from views.cuentas_por_pagar import render_cuentas_por_pagar
from views.gastos_operativos import render_gastos_operativos
from views.presupuesto_equilibrio import render_presupuesto_equilibrio
from views.rutas_produccion import render_rutas_produccion
from views.planificacion_produccion import render_planificacion_produccion
from views.areas_empresariales import render_area_combinada, render_area_empresarial
from views.activos_patrimonial import render_activos_patrimonial
from views.despacho_entregas import render_despacho_entregas
from views.disenos_aprobaciones import render_disenos_aprobaciones
from views.fichas_tecnicas_bom import render_fichas_tecnicas_bom
from views.legal_hub import render_legal_hub
from views.nomina_trabajadores import render_nomina_trabajadores
from views.publicaciones_marketing import render_publicaciones_marketing
from views.dia_caja import render_dia_caja
from views.nucleo_transaccional import render_nucleo_transaccional
from modules.mermas import render_mermas
from modules.configuracion import get_current_config, DEFAULT_CONFIG, _to_float
from views.erp_nuevos_modulos import (
    render_costeo_industrial,
    render_mantenimiento_activos,
    render_control_calidad,
    render_rrhh,
)

usuario = st.session_state.get("usuario", "Sistema")
user_role = st.session_state.get("rol", "Operator")


def render_dashboard_unificado(usuario: str) -> None:
    tab_alertas, tab_operativo, tab_ejecutivo = st.tabs(["🚨 Alertas operativas", "Panel operativo", "📊 Panel ejecutivo"])
    with tab_alertas:
        render_centro_alertas(usuario)
    with tab_operativo:
        render_dashboard()
    with tab_ejecutivo:
        render_panel_ejecutivo(usuario)


def render_produccion_unificada(usuario: str) -> None:
    st.title("🏭 Producción")
    secciones = {
        "🧾 OT / Planificación": lambda: render_planificacion_produccion(usuario),
        "📁 Diseños": lambda: render_disenos_aprobaciones(usuario),
        "🖨️ CMYK": lambda: render_cmyk(usuario),
        "🧭 Rutas / BOM": lambda: render_rutas_produccion(usuario),
        "✂️ Corte": lambda: render_corte(usuario),
        "🔥 Sublimación": lambda: render_sublimacion(usuario),
        "🎨 Manual": lambda: render_produccion_manual(usuario),
        "✅ Calidad": lambda: render_control_calidad(usuario),
        "♻️ Mermas": lambda: render_mermas(usuario),
        "🚚 Despacho": lambda: render_despacho_entregas(usuario),
    }
    seccion = st.radio("Sección de producción", list(secciones.keys()), horizontal=True)
    st.divider()
    secciones[seccion]()


def render_costeo_margenes_unificado(usuario: str) -> None:
    st.title("🧮 Costeo y Márgenes")
    tab_simple, tab_real, tab_industrial, tab_bom, tab_rentabilidad = st.tabs([
        "Costeo simple", "🖨️ Costeo real por impresora", "Costeo industrial", "📝 BOM", "📈 Rentabilidad"
    ])
    with tab_simple:
        render_costeo(usuario)
    with tab_real:
        render_costeo_impresion_real(usuario)
    with tab_industrial:
        render_costeo_industrial(usuario)
    with tab_bom:
        render_fichas_tecnicas_bom(usuario)
    with tab_rentabilidad:
        render_rentabilidad(usuario)


def render_activos_unificado(usuario: str) -> None:
    st.title("🏗️ Activos")
    tab_operacion, tab_comprados, tab_consumibles, tab_mantenimiento, tab_patrimonial = st.tabs([
        "🖥️ Equipos", "🧾 Comprados por factura", "🔗 Consumibles por impresora", "🛠️ Mantenimiento", "🧾 Patrimonio"
    ])
    with tab_operacion:
        render_activos(usuario)
    with tab_comprados:
        render_activos_comprados(usuario)
    with tab_consumibles:
        render_impresora_consumibles(usuario)
    with tab_mantenimiento:
        render_mantenimiento_activos(usuario)
    with tab_patrimonial:
        render_activos_patrimonial(usuario)


def render_finanzas_unificado(usuario: str) -> None:
    st.title("💼 Finanzas")
    tab_plan, tab_estado, tab_cxc, tab_cxp, tab_gastos, tab_presupuesto = st.tabs([
        "Planeación", "📊 Estado de resultados", "💰 Cuentas por cobrar", "💸 Cuentas por pagar", "📌 Gastos operativos", "📅 Presupuesto / Equilibrio"
    ])
    with tab_plan:
        render_planeacion_financiera(usuario)
    with tab_estado:
        render_estado_resultados(usuario)
    with tab_cxc:
        render_cuentas_por_cobrar(usuario)
    with tab_cxp:
        render_cuentas_por_pagar(usuario)
    with tab_gastos:
        render_gastos_operativos(usuario)
    with tab_presupuesto:
        render_presupuesto_equilibrio(usuario)


MENU_ROUTES = {
    "🌅 Día / Caja": (("dashboard.view", "caja.view"), lambda: render_dia_caja(usuario)),
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),
    "⚛️ Núcleo transaccional": ("dashboard.view", lambda: render_nucleo_transaccional(usuario)),
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "🏗️ Activos": (("activos.view", "mantenimiento.view"), lambda: render_activos_unificado(usuario)),
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "📇 Contactos": (("clientes.view", "inventario.view", "dashboard.view"), lambda: render_contactos(usuario)),
    "📊 Reportes": (("dashboard.view", "reportes.export", "contabilidad.view"), lambda: render_reportes(usuario)),
    "💾 Respaldo": (("dashboard.view", "config.view", "reportes.export"), lambda: render_respaldo(usuario)),
    "⚙️ Configuración": (("dashboard.view", "config.view", "reportes.export"), lambda: render_configuracion_sistema(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "💰 Cuentas por cobrar": (("ventas.view", "clientes.view", "dashboard.view"), lambda: render_cuentas_por_cobrar(usuario)),
    "💸 Cuentas por pagar": (("tesoreria.view", "cxp.view", "contabilidad.view", "dashboard.view"), lambda: render_cuentas_por_pagar(usuario)),
    "📅 Presupuesto / Equilibrio": (("dashboard.view", "contabilidad.view", "presupuesto.view"), lambda: render_presupuesto_equilibrio(usuario)),
    "♻️ Mermas / Desperdicio": (("inventario.view", "dashboard.view", "produccion.scrap"), lambda: render_mermas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing": (("crm.view", "publicaciones.view"), lambda: render_publicaciones_marketing(usuario)),
    "🏭 Producción": (("produccion.plan", "produccion.execute", "produccion.route", "produccion.quality", "produccion.scrap"), lambda: render_produccion_unificada(usuario)),
    "💼 Finanzas": (("tesoreria.view", "dashboard.view", "gastos.view", "caja.view", "cxp.view", "contabilidad.view", "conciliacion.view", "impuestos.view", "presupuesto.view"), lambda: render_finanzas_unificado(usuario)),
    "🗂️ Administración": (("dashboard.view", "config.view", "security.view", "reportes.export", "manuales.view", "auditoria.view", "calendario_operativo.view"), lambda: render_area_empresarial("Administración", usuario)),
    "👨‍💼 Nómina y trabajadores": ("nomina.view", lambda: render_nomina_trabajadores(usuario)),
    "👥 RRHH": (("rrhh.view", "dashboard.view"), lambda: render_area_combinada("Recursos Humanos", render_rrhh, usuario)),
    "⚖️ Legal": (("dashboard.view", "config.view"), lambda: render_legal_hub(usuario)),
    "🧮 Costeo y Márgenes": (("costeo.view", "costeo_industrial.view"), lambda: render_costeo_margenes_unificado(usuario)),
    "🧮 Calculadora": ("dashboard.view", lambda: render_calculadora(usuario)),
    "🛠️ Otros procesos": ("dashboard.view", lambda: render_otros_procesos(usuario)),
}


def _can_access_menu_route(permission_rule):
    if isinstance(permission_rule, str):
        return has_permission(permission_rule)
    if isinstance(permission_rule, (tuple, list, set)):
        return any(has_permission(permission_code) for permission_code in permission_rule)
    return False


visible_menu = {label: callback for label, (permiso, callback) in MENU_ROUTES.items() if _can_access_menu_route(permiso)}

if not visible_menu:
    st.error("🚫 Tu usuario no tiene acceso a módulos habilitados.")
    save_session_snapshot()
    st.stop()

try:
    ensure_rate_config_defaults()
    config = get_current_config()
except Exception:
    config = DEFAULT_CONFIG

st.title("⚛️ Imperio Atómico ERP")
st.caption(f"Centro administrativo y operativo de Copy Mary · Usuario: {usuario} · Rol: {user_role}")

rate_cols = st.columns(6)
rate_fields = [
    ("tasa_bcv", "BCV", "Bs/$", "%.2f"),
    ("tasa_binance", "Binance", "Bs/$", "%.2f"),
    ("tasa_euro", "Euro", "Bs/€", "%.2f"),
    ("tasa_menudeo", "Menudeo", "Bs/$", "%.2f"),
    ("tasa_kontigo_entrada", "Kontigo entrada", "Bs/$", "%.2f"),
    ("tasa_kontigo_salida", "Kontigo salida", "Bs/$", "%.2f"),
]
legacy_kontigo = _to_float(config, "tasa_kontigo", 0.0)
for col, (key, label, unit, fmt) in zip(rate_cols, rate_fields):
    fallback = legacy_kontigo if key in {"tasa_kontigo_entrada", "tasa_kontigo_salida"} else float(DEFAULT_CONFIG.get(key, 0))
    value = _to_float(config, key, fallback)
    col.metric(label, f"{fmt % value} {unit}")

cols = st.columns([1, 1, 5])
with cols[0]:
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        snapshot_path = Path(__file__).resolve().parent / "data" / "session_snapshot.json"
        try:
            snapshot_path.unlink(missing_ok=True)
        except Exception:
            pass
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
with cols[1]:
    alert_summary = get_alert_summary()
    if alert_summary.total:
        st.warning(f"🚨 {alert_summary.total} alertas")
    else:
        st.success("✅ Sin alertas")

menu = st.radio("Menú principal", list(visible_menu.keys()), horizontal=True, label_visibility="collapsed", key="menu_principal_superior")
st.divider()
visible_menu[menu]()
save_session_snapshot()
