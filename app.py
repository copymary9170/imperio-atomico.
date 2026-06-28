from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Imperio Atómico ERP", layout="wide", page_icon="⚛️")

from services.backup_service import create_daily_backup_if_needed, restore_remote_database_if_needed

try:
    restore_remote_database_if_needed()
except Exception:
    pass

from database.schema import init_schema
from database.auto_migrations import run_auto_migrations
from database.transactional_core import ensure_transactional_core_schema
from database.rate_config_defaults import ensure_rate_config_defaults
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot, clear_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from security.auth import authenticate_user, users_count, create_initial_admin
from services.alert_service import get_alert_summary
from services.persistent_config_service import restore_persistent_rates_to_db

init_schema()
run_auto_migrations()
ensure_transactional_core_schema()
ensure_rate_config_defaults()
restore_persistent_rates_to_db("Sistema")
ensure_extended_permissions()
restore_session_snapshot()
try:
    create_daily_backup_if_needed()
except Exception:
    pass


def _render_login_form() -> None:
    with st.form("login_form"):
        login_usuario = st.text_input("Usuario")
        login_password = st.text_input("Contraseña", type="password")
        submit_login = st.form_submit_button("Entrar", type="primary")

    if submit_login:
        try:
            with st.spinner("Verificando credenciales..."):
                result = authenticate_user(login_usuario, login_password)
        except Exception as exc:
            st.error(f"Error interno al iniciar sesión: {exc}")
            return

        if not result.ok:
            st.error(result.message or "Credenciales inválidas.")
            return

        st.session_state["usuario"] = result.usuario
        st.session_state["rol"] = result.rol
        st.session_state["authentication_status"] = True
        set_session_role_from_db()
        save_session_snapshot()
        st.rerun()


def _render_login() -> None:
    st.title("⚛️ Imperio Atómico ERP")
    st.subheader("Iniciar sesión")

    if users_count() == 0 and not st.session_state.get("bootstrap_admin_created"):
        st.warning("No existen usuarios registrados. Crea el primer administrador.")

        with st.form("crear_admin_inicial"):
            admin_user = st.text_input("Usuario administrador")
            admin_name = st.text_input("Nombre completo")
            admin_pass = st.text_input("Contraseña", type="password")
            admin_pass_2 = st.text_input("Confirmar contraseña", type="password")
            crear = st.form_submit_button("Crear administrador", type="primary")

        if crear:
            if admin_pass != admin_pass_2:
                st.error("Las contraseñas no coinciden.")
                return

            try:
                create_initial_admin(admin_user, admin_name, admin_pass)
                clear_session_snapshot()
                for key in ("authentication_status", "usuario", "rol"):
                    st.session_state.pop(key, None)
                st.session_state["bootstrap_admin_created"] = True
                st.success("Administrador creado. Ya puedes iniciar sesión abajo.")
                _render_login_form()
            except Exception as exc:
                st.error(f"No se pudo crear el administrador: {exc}")

        return

    if st.session_state.get("bootstrap_admin_created"):
        st.success("Administrador creado. Ingresa con el usuario y contraseña que acabas de registrar.")

    _render_login_form()


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
from views.legal_v2 import render_legal_v2
from views.nomina_trabajadores import render_nomina_trabajadores
from views.publicaciones_marketing import render_publicaciones_marketing
from views.dia_caja import render_dia_caja
from modules.mermas import render_mermas
from modules.configuracion import get_current_config, DEFAULT_CONFIG, _to_float
from views.erp_nuevos_modulos import render_costeo_industrial, render_mantenimiento_activos, render_control_calidad, render_rrhh

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
    secciones = {"🧾 OT / Planificación": lambda: render_planificacion_produccion(usuario), "📁 Diseños": lambda: render_disenos_aprobaciones(usuario), "🖨️ CMYK": lambda: render_cmyk(usuario), "🧭 Rutas / BOM": lambda: render_rutas_produccion(usuario), "✂️ Corte": lambda: render_corte(usuario), "🔥 Sublimación": lambda: render_sublimacion(usuario), "🎨 Manual": lambda: render_produccion_manual(usuario), "✅ Calidad": lambda: render_control_calidad(usuario), "♻️ Mermas": lambda: render_mermas(usuario), "🚚 Despacho": lambda: render_despacho_entregas(usuario)}
    seccion = st.radio("Sección de producción", list(secciones.keys()), horizontal=True)
    st.divider()
    secciones[seccion]()


def render_costeo_margenes_unificado(usuario: str) -> None:
    st.title("🧮 Costeo y Márgenes")
    tab_simple, tab_real, tab_industrial, tab_bom, tab_rentabilidad = st.tabs(["Costeo simple", "🖨️ Costeo real por impresora", "Costeo industrial", "📝 BOM", "📈 Rentabilidad"])
    with tab_simple: render_costeo(usuario)
    with tab_real: render_costeo_impresion_real(usuario)
    with tab_industrial: render_costeo_industrial(usuario)
    with tab_bom: render_fichas_tecnicas_bom(usuario)
    with tab_rentabilidad: render_rentabilidad(usuario)


def render_activos_unificado(usuario: str) -> None:
    st.title("🏗️ Activos")
    tab_operacion, tab_comprados, tab_consumibles, tab_mantenimiento, tab_patrimonial = st.tabs(["🖥️ Equipos", "🧾 Comprados por factura", "🔗 Consumibles por impresora", "🛠️ Mantenimiento", "🧾 Patrimonio"])
    with tab_operacion: render_activos(usuario)
    with tab_comprados: render_activos_comprados(usuario)
    with tab_consumibles: render_impresora_consumibles(usuario)
    with tab_mantenimiento: render_mantenimiento_activos(usuario)
    with tab_patrimonial: render_activos_patrimonial(usuario)


def render_finanzas_unificado(usuario: str) -> None:
    st.title("💼 Finanzas")
    tabs = st.tabs(["Planeación", "📊 Estado", "💰 CXC", "💸 CXP", "📌 Gastos", "📅 Presupuesto"])
    with tabs[0]: render_planeacion_financiera(usuario)
    with tabs[1]: render_estado_resultados(usuario)
    with tabs[2]: render_cuentas_por_cobrar(usuario)
    with tabs[3]: render_cuentas_por_pagar(usuario)
    with tabs[4]: render_gastos_operativos(usuario)
    with tabs[5]: render_presupuesto_equilibrio(usuario)


def render_marketing_unificado(usuario: str) -> None:
    st.title("📣 Marketing")
    render_publicaciones_marketing(usuario)


st.markdown("""
<style>
section[data-testid="stSidebar"] {display:none !important;}
.block-container {padding-top:1rem; max-width:1540px;}
div[role="radiogroup"] {gap:.45rem; flex-wrap:wrap; align-items:center;}
div[role="radiogroup"] label {border:1px solid #dce5ef;border-radius:999px;padding:.42rem .92rem;background:#fff;}
.top-shell {background:linear-gradient(135deg,#073b63,#0f4c81,#20b8b8);color:white;border-radius:24px;padding:1.25rem 1.35rem;margin-bottom:1rem;}
.top-header {display:flex;align-items:center;justify-content:space-between;gap:1rem;}
.brand-wrap {display:flex;align-items:center;gap:.9rem;}
.brand-icon {width:48px;height:48px;border-radius:18px;background:#fff;color:#073b63;display:grid;place-items:center;font-size:1.35rem;font-weight:900;}
.top-brand {font-size:1.35rem;font-weight:900;}
.top-subtitle {font-size:.82rem;opacity:.82;margin-top:.25rem;}
.top-actions {font-size:.85rem;background:rgba(255,255,255,.13);padding:.55rem .75rem;border-radius:999px;}
.rate-title {font-size:.85rem;font-weight:800;color:#334155;margin:.6rem 0 .2rem;}
[data-testid="stMetric"] {background:#fff;border:1px solid #e7edf5;border-radius:18px;padding:1rem;}
</style>
""", unsafe_allow_html=True)

MENU_ROUTES = {
    "🌅 Día / Caja": (("dashboard.view", "caja.view"), lambda: render_dia_caja(usuario)),
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "🏗️ Activos": (("activos.view", "mantenimiento.view"), lambda: render_activos_unificado(usuario)),
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "🏢 Proveedores": (("clientes.view", "inventario.view", "dashboard.view"), lambda: render_contactos(usuario)),
    "📊 Reportes": (("dashboard.view", "reportes.export", "contabilidad.view"), lambda: render_reportes(usuario)),
    "💾 Respaldo": (("dashboard.view", "config.view", "reportes.export"), lambda: render_respaldo(usuario)),
    "⚙️ Configuración": (("dashboard.view", "config.view", "reportes.export"), lambda: render_configuracion_sistema(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "💰 Cuentas por cobrar": (("ventas.view", "clientes.view", "dashboard.view"), lambda: render_cuentas_por_cobrar(usuario)),
    "💸 Cuentas por pagar": (("tesoreria.view", "cxp.view", "contabilidad.view", "dashboard.view"), lambda: render_cuentas_por_pagar(usuario)),
    "📅 Presupuesto / Equilibrio": (("dashboard.view", "contabilidad.view", "presupuesto.view"), lambda: render_presupuesto_equilibrio(usuario)),
    "♻️ Mermas / Desperdicio": (("inventario.view", "dashboard.view", "produccion.scrap"), lambda: render_mermas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing": (("crm.view", "publicaciones.view"), lambda: render_marketing_unificado(usuario)),
    "🏭 Producción": (("produccion.plan", "produccion.execute", "produccion.route", "produccion.quality", "produccion.scrap"), lambda: render_produccion_unificada(usuario)),
    "💼 Finanzas": (("tesoreria.view", "dashboard.view", "gastos.view", "caja.view", "cxp.view", "contabilidad.view", "conciliacion.view", "impuestos.view", "presupuesto.view"), lambda: render_finanzas_unificado(usuario)),
    "🗂️ Administración": (("dashboard.view", "config.view", "security.view", "reportes.export"), lambda: render_area_empresarial("Administración", usuario)),
    "👨‍💼 Nómina y trabajadores": ("nomina.view", lambda: render_nomina_trabajadores(usuario)),
    "👥 RRHH": (("rrhh.view", "dashboard.view"), lambda: render_area_combinada("Recursos Humanos", render_rrhh, usuario)),
    "⚖️ Legal V4.1": ("legal.view", lambda: render_legal_v2(usuario)),
    "🧮 Costeo y Márgenes": (("costeo.view", "costeo_industrial.view"), lambda: render_costeo_margenes_unificado(usuario)),
    "🧮 Calculadora": ("dashboard.view", lambda: render_calculadora(usuario)),
    "🛠️ Otros procesos": ("dashboard.view", lambda: render_otros_procesos(usuario)),
}

VISIBLE_MENU = {label: callback for label, (permiso, callback) in MENU_ROUTES.items() if (has_permission(permiso) if isinstance(permiso, str) else any(has_permission(p) for p in permiso))}
if not VISIBLE_MENU:
    st.error("🚫 Tu usuario no tiene acceso a módulos habilitados.")
    save_session_snapshot()
    st.stop()

try:
    config = get_current_config()
except Exception:
    config = DEFAULT_CONFIG

st.markdown(f"<div class='top-shell'><div class='top-header'><div class='brand-wrap'><div class='brand-icon'>⚛️</div><div><div class='top-brand'>Imperio Atómico ERP</div><div class='top-subtitle'>Centro administrativo y operativo de Copy Mary · Legal V4.1 Enterprise</div></div></div><div class='top-actions'>Usuario: {usuario} · Rol: {user_role}</div></div></div>", unsafe_allow_html=True)

st.markdown('<div class="rate-title">Tasas de cambio activas</div>', unsafe_allow_html=True)
a, b, c, d, e = st.columns(5)
def _cfg_float(key: str, fallback: float) -> float:
    return _to_float(config, key, float(DEFAULT_CONFIG.get(key, fallback)))
a.metric("BCV", f"{_cfg_float('tasa_bcv', 0):,.2f} Bs/USD")
b.metric("Binance", f"{_cfg_float('tasa_binance', 0):,.2f} Bs/USD")
c.metric("Kontigo entrada", f"{_cfg_float('tasa_kontigo_entrada', 0):,.2f} Bs/USD")
d.metric("Kontigo salida", f"{_cfg_float('tasa_kontigo_salida', 0):,.2f} Bs/USD")
e.metric("Euro", f"{_cfg_float('tasa_euro', 0):,.2f} Bs/EUR")

try:
    alert_summary = get_alert_summary()
except Exception:
    alert_summary = {}
if not isinstance(alert_summary, dict):
    alert_summary = {}
alert_total = int(alert_summary.get("total", 0) or 0)
if alert_total:
    st.warning(f"🚨 Alertas activas: {alert_total} · Stock bajo: {int(alert_summary.get('stock', 0) or 0)} · CxC vencida: {int(alert_summary.get('cxc', 0) or 0)} · CxP vencida: {int(alert_summary.get('cxp', 0) or 0)}")

menu = st.radio("Módulos", list(VISIBLE_MENU.keys()), horizontal=True, label_visibility="collapsed")
st.divider()
VISIBLE_MENU[menu]()
save_session_snapshot()
