from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Imperio Atómico ERP", layout="wide", page_icon="⚛️")

from services.backup_service import restore_remote_database_if_needed

try:
    restore_remote_database_if_needed()
except Exception:
    pass

from database.schema import init_schema
from database.auto_migrations import run_auto_migrations
from database.transactional_core import ensure_transactional_core_schema
from database.rate_config_defaults import ensure_rate_config_defaults
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from services.alert_service import get_alert_summary
from services.backup_service import create_daily_backup_if_needed
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


def render_contactos_unificado(usuario: str) -> None:
    st.title("👥 Contactos")
    tab_clientes, tab_contactos = st.tabs(["Clientes", "Contactos"])
    with tab_clientes:
        render_clientes(usuario)
    with tab_contactos:
        render_contactos(usuario)


def render_configuracion_unificada(usuario: str) -> None:
    st.title("⚙️ Configuración")
    tab_sistema, tab_respaldo = st.tabs(["Sistema", "💾 Respaldo"])
    with tab_sistema:
        render_configuracion_sistema(usuario)
    with tab_respaldo:
        render_respaldo(usuario)


MENU = {
    "🏠 Dashboard": lambda: render_dashboard_unificado(usuario),
    "📦 Inventario / Almacén": lambda: render_inventario_almacen_unificado(usuario),
    "🏭 Producción": lambda: render_produccion_unificada(usuario),
    "💵 Ventas": lambda: render_ventas(usuario),
    "📝 Cotizaciones": lambda: render_cotizaciones(usuario),
    "🧮 Costeo y Márgenes": lambda: render_costeo_margenes_unificado(usuario),
    "💼 Finanzas": lambda: render_finanzas_unificado(usuario),
    "🏗️ Activos": lambda: render_activos_unificado(usuario),
    "👥 Contactos": lambda: render_contactos_unificado(usuario),
    "🧑‍⚖️ Legal": lambda: render_legal_hub(usuario),
    "👩‍💼 RRHH": lambda: render_rrhh(usuario),
    "📣 Marketing": lambda: render_publicaciones_marketing(usuario),
    "📊 Reportes": lambda: render_reportes(usuario),
    "⚙️ Configuración": lambda: render_configuracion_unificada(usuario),
}

st.sidebar.title("⚛️ Imperio Atómico")
menu_options = [name for name in MENU if has_permission(name)]
selected = st.sidebar.radio("Navegación", menu_options)

try:
    alertas = get_alert_summary(usuario)
    st.sidebar.metric("Alertas pendientes", alertas.get("total", 0))
except Exception:
    pass

config = get_current_config()
st.sidebar.caption(
    f"Tasa BCV: {_to_float(config.get('tasa_bcv'), DEFAULT_CONFIG['tasa_bcv']):,.2f} Bs/USD"
)
st.sidebar.caption(f"Usuario: {usuario} · Rol: {user_role}")

MENU[selected]()
