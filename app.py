import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Imperio Atómico ERP", layout="wide", page_icon="⚛️")

from database.schema import init_schema
from database.auto_migrations import run_auto_migrations
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from services.alert_service import get_alert_summary

init_schema()
run_auto_migrations()
ensure_extended_permissions()
restore_session_snapshot()


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

from views.dashboard import render_dashboard
from views.panel_ejecutivo import render_panel_ejecutivo
from views.centro_alertas import render_centro_alertas
from views.inventario import render_inventario
from views.stock_minimo import render_stock_minimo
from views.kardex import render_kardex
from views.clientes import render_clientes
from views.cmyk import render_cmyk
from views.activos import render_activos
from views.otros_procesos import render_otros_procesos
from views.corte import render_corte
from views.sublimacion import render_sublimacion
from views.produccion_manual import render_produccion_manual
from views.ventas import render_ventas
from views.cotizaciones import render_cotizaciones
from views.calculadora import render_calculadora
from views.costeo import render_costeo
from views.rentabilidad import render_rentabilidad
from views.planeacion_financiera import render_planeacion_financiera
from views.catalogo import render_catalogo
from views.rutas_produccion import render_rutas_produccion
from views.planificacion_produccion import render_planificacion_produccion
from views.areas_empresariales import render_area_combinada, render_area_empresarial
from views.almacen_avanzado import render_almacen_avanzado
from views.activos_patrimonial import render_activos_patrimonial
from views.proveedores_compras import render_compras_suministro, render_proveedores
from views.despacho_entregas import render_despacho_entregas
from views.unidades_fraccionadas import render_unidades_fraccionadas
from views.disenos_aprobaciones import render_disenos_aprobaciones
from views.fichas_tecnicas_bom import render_fichas_tecnicas_bom
from views.legal_hub import render_legal_hub
from views.nomina_trabajadores import render_nomina_trabajadores
from views.publicaciones_marketing import render_publicaciones_marketing
from modules.configuracion import get_current_config, DEFAULT_CONFIG, _to_float
from views.erp_nuevos_modulos import (
    render_costeo_industrial,
    render_mermas_desperdicio,
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


def render_inventario_almacen_unificado(usuario: str) -> None:
    st.title("📦 Inventario / Almacén")
    tabs = st.tabs(["📦 Inventario operativo", "📉 Stock mínimo", "📏 Unidades", "🧾 Kardex", "🛒 Compras", "👥 Proveedores", "🏬 Almacén", "🛍️ Catálogo"])
    with tabs[0]: render_inventario(usuario)
    with tabs[1]: render_stock_minimo(usuario)
    with tabs[2]: render_unidades_fraccionadas(usuario)
    with tabs[3]: render_kardex(usuario)
    with tabs[4]: render_compras_suministro(usuario)
    with tabs[5]: render_proveedores(usuario)
    with tabs[6]: render_almacen_avanzado(usuario)
    with tabs[7]: render_catalogo(usuario)


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
        "♻️ Mermas": lambda: render_mermas_desperdicio(usuario),
        "🚚 Despacho": lambda: render_despacho_entregas(usuario),
    }
    seccion = st.radio("Sección de producción", list(secciones.keys()), horizontal=True)
    st.divider()
    secciones[seccion]()


def render_costeo_margenes_unificado(usuario: str) -> None:
    st.title("🧮 Costeo y Márgenes")
    tab_simple, tab_industrial, tab_bom, tab_rentabilidad = st.tabs(["Costeo simple", "Costeo industrial", "📝 BOM", "📈 Rentabilidad"])
    with tab_simple: render_costeo(usuario)
    with tab_industrial: render_costeo_industrial(usuario)
    with tab_bom: render_fichas_tecnicas_bom(usuario)
    with tab_rentabilidad: render_rentabilidad(usuario)


def render_marketing_unificado(usuario: str) -> None:
    st.title("📣 Marketing")
    render_publicaciones_marketing(usuario)


def render_activos_unificado(usuario: str) -> None:
    st.title("🏗️ Activos")
    tab_operacion, tab_mantenimiento, tab_patrimonial = st.tabs(["🖥️ Equipos", "🛠️ Mantenimiento", "🧾 Patrimonio"])
    with tab_operacion: render_activos(usuario)
    with tab_mantenimiento: render_mantenimiento_activos(usuario)
    with tab_patrimonial: render_activos_patrimonial(usuario)


st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {display:none !important;}
        div[data-testid="stAppViewContainer"] > .main {margin-left:0 !important;}
        div[data-testid="stHeader"] {background:transparent;}
        .block-container {padding-top:1.2rem; max-width:1500px;}
        div[role="radiogroup"] {gap:.45rem; flex-wrap:wrap;}
        div[role="radiogroup"] label {border:1px solid #e5e7eb;border-radius:999px;padding:.35rem .85rem;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.05);}
        div[role="radiogroup"] label:hover {border-color:#0f4c81; background:#eefafa;}
        .top-header {display:flex; align-items:center; justify-content:space-between; gap:1rem;padding:1rem 1.2rem; border:1px solid #e5e7eb; border-radius:1rem;background:linear-gradient(90deg,#073b63,#0f4c81); color:white; margin-bottom:1rem;box-shadow:0 10px 28px rgba(15,76,129,.18);}
        .top-brand {font-size:1.25rem; font-weight:800;}
        .top-actions {font-size:.85rem; opacity:.9;}
        .rate-card {border:1px solid #e5e7eb;border-radius:14px;padding:.75rem .9rem;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.04);}
        .rate-label {font-size:.74rem;color:#6b7280;margin-bottom:.2rem;}
        .rate-value {font-size:1.1rem;font-weight:750;color:#111827;}
    </style>
    """,
    unsafe_allow_html=True,
)

MENU_ROUTES = {
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "🏗️ Activos": (("activos.view", "mantenimiento.view"), lambda: render_activos_unificado(usuario)),
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing": (("crm.view", "publicaciones.view"), lambda: render_marketing_unificado(usuario)),
    "🏭 Producción": (("produccion.plan", "produccion.execute", "produccion.route", "produccion.quality", "produccion.scrap"), lambda: render_produccion_unificada(usuario)),
    "💼 Finanzas": (("tesoreria.view", "dashboard.view", "gastos.view", "caja.view", "cxp.view", "contabilidad.view", "conciliacion.view", "impuestos.view", "presupuesto.view"), lambda: render_planeacion_financiera(usuario)),
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


VISIBLE_MENU = {label: callback for label, (permiso, callback) in MENU_ROUTES.items() if _can_access_menu_route(permiso)}

if not VISIBLE_MENU:
    st.error("🚫 Tu usuario no tiene acceso a módulos habilitados.")
    save_session_snapshot()
    st.stop()

st.markdown(
    f"""
    <div class="top-header">
        <div class="top-brand">⚛️ Imperio Atómico ERP</div>
        <div class="top-actions">Usuario: {usuario} · Rol: {user_role}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    config = get_current_config()
except Exception:
    config = DEFAULT_CONFIG

rate_fields = [
    ("tasa_bcv", "BCV", "Bs/$", "%.2f"),
    ("tasa_binance", "Binance", "Bs/$", "%.2f"),
    ("iva_perc", "IVA", "%", "%.2f"),
    ("igtf_perc", "IGTF", "%", "%.2f"),
    ("banco_perc", "Banco", "%", "%.3f"),
    ("kontigo_perc", "Kontigo", "%", "%.3f"),
]
rate_cols = st.columns(len(rate_fields))
for col, (key, label, unit, fmt) in zip(rate_cols, rate_fields):
    value = _to_float(config, key, float(DEFAULT_CONFIG[key]))
    col.markdown(
        f"""
        <div class="rate-card">
            <div class="rate-label">{label}</div>
            <div class="rate-value">{fmt % value} {unit}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

cols = st.columns([1, 1, 6])
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

menu = st.radio("Menú principal", list(VISIBLE_MENU.keys()), horizontal=True, label_visibility="collapsed", key="menu_principal_superior")

st.divider()
VISIBLE_MENU[menu]()
save_session_snapshot()
