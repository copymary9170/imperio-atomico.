import os
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Imperio Atómico ERP", layout="wide", page_icon="⚛️")

from database.schema import init_schema
from database.auto_migrations import run_auto_migrations
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from services.alert_service import get_alert_summary
from services.backup_service import create_daily_backup_if_needed
from database.connection import db_transaction

init_schema()
run_auto_migrations()
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
from views.contactos import render_contactos
from views.reportes import render_reportes
from views.respaldo import render_respaldo
from views.configuracion_sistema import render_configuracion_sistema
from views.cmyk import render_cmyk
from views.activos import render_activos
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
from views.catalogo import render_catalogo
from views.productos_terminados import render_productos_terminados
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
from views.dia_caja import render_dia_caja
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
    tabs = st.tabs(["📦 Materia prima", "🧩 Productos terminados", "📉 Stock mínimo", "📏 Unidades", "🧾 Kardex", "🛒 Compras", "👥 Proveedores", "🏬 Almacén", "🛍️ Catálogo"])
    with tabs[0]: render_inventario(usuario)
    with tabs[1]: render_productos_terminados(usuario)
    with tabs[2]: render_stock_minimo(usuario)
    with tabs[3]: render_unidades_fraccionadas(usuario)
    with tabs[4]: render_kardex(usuario)
    with tabs[5]: render_compras_suministro(usuario)
    with tabs[6]: render_proveedores(usuario)
    with tabs[7]: render_almacen_avanzado(usuario)
    with tabs[8]: render_catalogo(usuario)


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
    tab_simple, tab_real, tab_industrial, tab_bom, tab_rentabilidad = st.tabs(["Costeo simple", "🖨️ Costeo real por impresora", "Costeo industrial", "📝 BOM", "📈 Rentabilidad"])
    with tab_simple: render_costeo(usuario)
    with tab_real: render_costeo_impresion_real(usuario)
    with tab_industrial: render_costeo_industrial(usuario)
    with tab_bom: render_fichas_tecnicas_bom(usuario)
    with tab_rentabilidad: render_rentabilidad(usuario)


def render_marketing_unificado(usuario: str) -> None:
    st.title("📣 Marketing")
    render_publicaciones_marketing(usuario)


def render_activos_unificado(usuario: str) -> None:
    st.title("🏗️ Activos")
    tab_operacion, tab_consumibles, tab_mantenimiento, tab_patrimonial = st.tabs(["🖥️ Equipos", "🔗 Consumibles por impresora", "🛠️ Mantenimiento", "🧾 Patrimonio"])
    with tab_operacion: render_activos(usuario)
    with tab_consumibles: render_impresora_consumibles(usuario)
    with tab_mantenimiento: render_mantenimiento_activos(usuario)
    with tab_patrimonial: render_activos_patrimonial(usuario)


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _search_table(table_name: str, query: str) -> pd.DataFrame:
    query = str(query or "").strip()
    if not query:
        return pd.DataFrame()
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table_name):
                return pd.DataFrame()
            df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 1000", conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    mask = df.astype(str).apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
    return df[mask].head(30)


def render_global_search() -> None:
    consulta = st.text_input(
        "🔎 Buscador universal",
        placeholder="Buscar cualquier cosa: cliente, producto, servicio, venta, cotización...",
        key="busqueda_universal_texto",
    )
    if not consulta.strip():
        st.caption("Busca en productos, servicios, clientes, ventas, cotizaciones e inventario desde un solo lugar.")
        return

    fuentes = [
        ("🛍️ Productos / Inventario", "inventario"),
        ("🧾 Servicios", "servicios"),
        ("👥 Clientes", "clientes"),
        ("📇 Contactos", "clientes"),
        ("📊 Reportes", "ventas"),
        ("💰 Ventas", "ventas"),
        ("📝 Cotizaciones", "cotizaciones"),
        ("📦 Stock", "stock"),
    ]
    total = 0
    tabs = st.tabs([nombre for nombre, _tabla in fuentes])
    for tab, (nombre, tabla) in zip(tabs, fuentes):
        with tab:
            results = _search_table(tabla, consulta)
            total += len(results)
            if results.empty:
                st.info(f"Sin resultados en {nombre}.")
            else:
                st.success(f"{len(results)} resultado(s) en {nombre}.")
                st.dataframe(results, use_container_width=True, hide_index=True)
    if total == 0:
        st.warning(f"No encontré coincidencias para: {consulta}")


st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {display:none !important;}
        div[data-testid="stAppViewContainer"] > .main {margin-left:0 !important;}
        div[data-testid="stHeader"] {background:transparent;}
        .block-container {padding-top:1rem; max-width:1540px;}
        .main .block-container {padding-left:2.4rem; padding-right:2.4rem;}
        div[role="radiogroup"] {gap:.45rem; flex-wrap:wrap; align-items:center;}
        div[role="radiogroup"] label {border:1px solid #dce5ef;border-radius:999px;padding:.42rem .92rem;background:linear-gradient(180deg,#ffffff,#f8fbff);box-shadow:0 3px 10px rgba(15,23,42,.04);transition:all .18s ease;}
        div[role="radiogroup"] label:hover {border-color:#20b8b8; background:#eefafa; transform:translateY(-1px);}
        .top-shell {background:linear-gradient(135deg,#073b63 0%,#0f4c81 48%,#20b8b8 120%);color:white;border-radius:24px;padding:1.25rem 1.35rem;margin-bottom:1rem;box-shadow:0 18px 45px rgba(15,76,129,.22);position:relative;overflow:hidden;}
        .top-shell:after {content:"";position:absolute;width:220px;height:220px;border-radius:999px;right:-70px;top:-95px;background:rgba(255,255,255,.16);}
        .top-header {display:flex; align-items:center; justify-content:space-between; gap:1rem; position:relative; z-index:1;}
        .brand-wrap {display:flex; align-items:center; gap:.9rem;}
        .brand-icon {width:48px;height:48px;border-radius:18px;background:linear-gradient(135deg,#fff,#dffafa);color:#073b63;display:grid;place-items:center;font-size:1.35rem;font-weight:900;box-shadow:0 12px 26px rgba(0,0,0,.18);}
        .top-brand {font-size:1.35rem; font-weight:900; letter-spacing:-.03em; line-height:1;}
        .top-subtitle {font-size:.82rem; opacity:.82; margin-top:.25rem;}
        .top-actions {font-size:.85rem; opacity:.95; background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.18); padding:.55rem .75rem; border-radius:999px;}
        .rate-title {font-size:.85rem;font-weight:800;color:#334155;margin:.6rem 0 .2rem;}
        [data-testid="stMetric"] {background:#fff;border:1px solid #e7edf5;border-radius:18px;padding:1rem;box-shadow:0 10px 24px rgba(15,76,129,.07);}
        .stButton button {border-radius:14px !important; font-weight:800 !important; border:1px solid #dce5ef !important; box-shadow:0 6px 16px rgba(15,76,129,.06) !important;}
        @media(max-width:650px){.main .block-container{padding-left:1rem;padding-right:1rem}.top-header{align-items:flex-start;flex-direction:column}}
    </style>
    """,
    unsafe_allow_html=True,
)

MENU_ROUTES = {
    "🌅 Día / Caja": (("dashboard.view", "caja.view"), lambda: render_dia_caja(usuario)),
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "🏗️ Activos": (("activos.view", "mantenimiento.view"), lambda: render_activos_unificado(usuario)),
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "📇 Contactos": (("clientes.view", "inventario.view", "dashboard.view"), lambda: render_contactos(usuario)),
    "📊 Reportes": (("dashboard.view", "reportes.export", "contabilidad.view"), lambda: render_reportes(usuario)),
    "💾 Respaldo": (("dashboard.view", "config.view", "reportes.export"), lambda: render_respaldo(usuario)),
    "⚙️ Configuración": (("dashboard.view", "config.view", "reportes.export"), lambda: render_configuracion_sistema(usuario)),
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

try:
    config = get_current_config()
except Exception:
    config = DEFAULT_CONFIG

st.markdown(
    f"""
    <div class="top-shell">
        <div class="top-header">
            <div class="brand-wrap">
                <div class="brand-icon">⚛️</div>
                <div>
                    <div class="top-brand">Imperio Atómico ERP</div>
                    <div class="top-subtitle">Centro administrativo y operativo de Copy Mary</div>
                </div>
            </div>
            <div class="top-actions">Usuario: {usuario} · Rol: {user_role}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="rate-title">Tasas, impuestos y comisiones activas</div>', unsafe_allow_html=True)
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
    col.metric(label, f"{fmt % value} {unit}")

with st.expander("🔎 Buscador universal", expanded=True):
    render_global_search()

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
