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
from database.auto_migrations import run_auto_migrations
from security.permission_extensions import ensure_extended_permissions
from ui.session_persistence import restore_session_snapshot, save_session_snapshot
from security.permissions import has_permission, set_session_role_from_db
from services.alert_service import get_alert_summary

init_schema()
run_auto_migrations()
ensure_extended_permissions()
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
from views.centro_alertas import render_centro_alertas
from views.respaldo_datos import render_respaldo_datos
from views.inventario import render_inventario
from views.stock_minimo import render_stock_minimo
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
from views.disenos_aprobaciones import render_disenos_aprobaciones
from views.fichas_tecnicas_bom import render_fichas_tecnicas_bom

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
    render_rrhh,
    render_seguridad_roles,
)

# ==================================================
# USUARIO
# ==================================================

usuario = st.session_state.get("usuario", "Sistema")
user_role = st.session_state.get("rol", "Operator")


def render_dashboard_unificado(usuario: str) -> None:
    tab_alertas, tab_operativo, tab_ejecutivo = st.tabs([
        "🚨 Alertas operativas",
        "Dashboard operativo",
        "📊 Panel ejecutivo",
    ])
    with tab_alertas:
        render_centro_alertas(usuario)
    with tab_operativo:
        render_dashboard()
    with tab_ejecutivo:
        render_panel_ejecutivo(usuario)


def render_inventario_almacen_unificado(usuario: str) -> None:
    st.title("📦 Inventario / Almacén")
    st.caption("Navegación unificada para inventario operativo, reposición, movimientos, compras, proveedores y archivos físicos.")

    (
        tab_inventario,
        tab_stock,
        tab_unidades,
        tab_kardex,
        tab_compras,
        tab_proveedores,
        tab_almacen_fisico,
        tab_catalogo,
        tab_documentos,
    ) = st.tabs([
        "📦 Inventario operativo",
        "📉 Stock mínimo / Reposición",
        "📏 Unidades fraccionadas",
        "🧾 Kardex / Movimientos",
        "🛒 Compras",
        "👥 Proveedores",
        "🏬 Almacén físico / Históricos CSV",
        "🛍️ Catálogo",
        "📁 Documentos de almacén",
    ])

    with tab_inventario:
        render_inventario(usuario)
    with tab_stock:
        render_stock_minimo(usuario)
    with tab_unidades:
        render_unidades_fraccionadas(usuario)
    with tab_kardex:
        render_kardex(usuario)
    with tab_compras:
        render_compras_suministro(usuario)
    with tab_proveedores:
        render_proveedores(usuario)
    with tab_almacen_fisico:
        render_almacen_avanzado(usuario)
    with tab_catalogo:
        render_catalogo(usuario)
    with tab_documentos:
        render_area_empresarial("Almacén", usuario, show_title=False)


def _render_alertas_produccion(usuario: str) -> None:
    import pandas as pd
    from database.connection import db_transaction

    st.subheader("🚨 Alertas de producción")
    st.caption("Detecta diseños bloqueados, OT pendientes, despachos abiertos, incidencias y trabajos sin cierre.")

    def _table_exists(conn, table_name: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None

    def _read_table(table_name: str) -> pd.DataFrame:
        try:
            with db_transaction() as conn:
                if not _table_exists(conn, table_name):
                    return pd.DataFrame()
                return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 1000", conn)
        except Exception:
            return pd.DataFrame()

    disenos = _read_table("disenos_aprobaciones")
    despachos = _read_table("despachos_entregas")
    ordenes = _read_table("ordenes_trabajo")

    disenos_bloqueados = disenos[disenos.get("bloqueo_produccion", pd.Series(dtype=int)).eq(1)] if not disenos.empty else pd.DataFrame()
    disenos_modificar = disenos[disenos.get("estado", pd.Series(dtype=str)).fillna("").eq("Modificar")] if not disenos.empty else pd.DataFrame()

    ot_abiertas = pd.DataFrame()
    ot_sin_responsable = pd.DataFrame()
    ot_sin_ruta = pd.DataFrame()
    if not ordenes.empty:
        estado_ot = ordenes.get("estado", pd.Series(dtype=str)).fillna("").astype(str)
        ot_abiertas = ordenes[~estado_ot.isin(["Finalizada", "Cerrada", "Cancelada", "Entregada"])]
        if "responsable" in ordenes.columns:
            ot_sin_responsable = ordenes[ordenes["responsable"].fillna("").astype(str).str.strip().eq("")]
        if "ruta_id" in ordenes.columns:
            ot_sin_ruta = ordenes[pd.to_numeric(ordenes["ruta_id"], errors="coerce").fillna(0).le(0)]

    despachos_abiertos = pd.DataFrame()
    despachos_incidencia = pd.DataFrame()
    if not despachos.empty:
        estado_desp = despachos.get("estado", pd.Series(dtype=str)).fillna("").astype(str)
        despachos_abiertos = despachos[~estado_desp.isin(["Entregado", "Devuelto"])]
        despachos_incidencia = despachos[estado_desp.eq("Incidencia")]

    alertas = []
    for nivel, nombre, df, accion in [
        ("Alta", "Diseños bloqueando producción", disenos_bloqueados, "Aprobar diseño o solicitar modificación antes de producir."),
        ("Media", "Diseños en modificación", disenos_modificar, "Corregir archivo y reenviar a cliente."),
        ("Media", "OT abiertas", ot_abiertas, "Revisar avance, responsable y fecha compromiso."),
        ("Media", "OT sin responsable", ot_sin_responsable, "Asignar responsable de producción."),
        ("Media", "OT sin ruta/BOM", ot_sin_ruta, "Asignar ruta productiva o ficha técnica."),
        ("Media", "Despachos abiertos", despachos_abiertos, "Completar entrega o actualizar estado."),
        ("Alta", "Despachos con incidencia", despachos_incidencia, "Resolver incidencia con cliente, agencia o motorizado."),
    ]:
        if not df.empty:
            alertas.append({"nivel": nivel, "alerta": nombre, "cantidad": len(df), "acción": accion})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Diseños bloqueados", len(disenos_bloqueados))
    c2.metric("OT abiertas", len(ot_abiertas))
    c3.metric("Despachos abiertos", len(despachos_abiertos))
    c4.metric("Incidencias", len(despachos_incidencia))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas críticas de producción con la información disponible.")

    tabs = st.tabs([
        "Diseños bloqueados",
        "OT abiertas",
        "OT sin responsable/ruta",
        "Despachos abiertos",
        "Incidencias",
    ])
    with tabs[0]:
        st.dataframe(disenos_bloqueados, use_container_width=True, hide_index=True) if not disenos_bloqueados.empty else st.success("Sin diseños bloqueados.")
    with tabs[1]:
        st.dataframe(ot_abiertas, use_container_width=True, hide_index=True) if not ot_abiertas.empty else st.success("Sin OT abiertas detectadas.")
    with tabs[2]:
        if not ot_sin_responsable.empty:
            st.markdown("#### Sin responsable")
            st.dataframe(ot_sin_responsable, use_container_width=True, hide_index=True)
        if not ot_sin_ruta.empty:
            st.markdown("#### Sin ruta/BOM")
            st.dataframe(ot_sin_ruta, use_container_width=True, hide_index=True)
        if ot_sin_responsable.empty and ot_sin_ruta.empty:
            st.success("Sin OT pendientes de responsable/ruta.")
    with tabs[3]:
        st.dataframe(despachos_abiertos, use_container_width=True, hide_index=True) if not despachos_abiertos.empty else st.success("Sin despachos abiertos.")
    with tabs[4]:
        st.dataframe(despachos_incidencia, use_container_width=True, hide_index=True) if not despachos_incidencia.empty else st.success("Sin incidencias de despacho.")


def render_produccion_unificada(usuario: str) -> None:
    st.title("🏭 Producción")
    st.caption("Hub productivo: OT, planificación, diseños, impresiones CMYK, rutas, corte, sublimación, producción manual, calidad, mermas, despacho y archivos.")

    secciones = {
        "🧾 OT / Planificación": lambda: render_planificacion_produccion(usuario),
        "📁 Diseños y aprobaciones": lambda: render_disenos_aprobaciones(usuario),
        "🖨️ Impresiones / CMYK": lambda: render_cmyk(usuario),
        "🧭 Rutas / BOM": lambda: render_rutas_produccion(usuario),
        "✂️ Corte": lambda: render_corte(usuario),
        "🔥 Sublimación": lambda: render_sublimacion(usuario),
        "🎨 Producción manual": lambda: render_produccion_manual(usuario),
        "✅ Calidad": lambda: render_control_calidad(usuario),
        "♻️ Mermas / Reprocesos": lambda: render_mermas_desperdicio(usuario),
        "🚚 Despacho / Entregas": lambda: render_despacho_entregas(usuario),
        "📁 Archivos de producción": lambda: render_area_empresarial("Producción", usuario, show_title=False),
        "🚨 Alertas producción": lambda: _render_alertas_produccion(usuario),
    }

    seccion = st.radio(
        "Sección de producción",
        list(secciones.keys()),
        horizontal=True,
        key="produccion_seccion_activa",
    )
    st.divider()
    secciones[seccion]()


def render_costeo_margenes_unificado(usuario: str) -> None:
    st.title("🧮 Costeo y Márgenes")
    tab_simple, tab_industrial, tab_bom, tab_rentabilidad = st.tabs([
        "Costeo simple",
        "Costeo industrial",
        "📝 BOM / Recetas",
        "📈 Rentabilidad",
    ])
    with tab_simple:
        render_costeo(usuario)
    with tab_industrial:
        render_costeo_industrial(usuario)
    with tab_bom:
        render_fichas_tecnicas_bom(usuario)
    with tab_rentabilidad:
        render_rentabilidad(usuario)


def render_marketing_unificado(usuario: str) -> None:
    st.title("📣 Marketing")
    st.caption("Campañas, calendario de publicaciones, segmentos CRM, ROI y alertas. Sin blueprint: solo operación funcional.")
    render_publicaciones_marketing(usuario)


def render_activos_unificado(usuario: str) -> None:
    st.title("🏗️ Activos")
    st.caption("Equipos, componentes, diagnóstico, mantenimiento, documentos, garantías, depreciación y archivos patrimoniales.")

    tab_operacion, tab_mantenimiento, tab_patrimonial = st.tabs([
        "🖥️ Equipos / Operación",
        "🛠️ Mantenimiento operativo",
        "🧾 Patrimonio / Históricos CSV",
    ])
    with tab_operacion:
        render_activos(usuario)
    with tab_mantenimiento:
        render_mantenimiento_activos(usuario)
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

alert_summary = get_alert_summary()
if alert_summary.total:
    st.sidebar.warning(
        f"🚨 Alertas: 🔴 {alert_summary.criticas} · 🟠 {alert_summary.medias} · 🔵 {alert_summary.informativas}"
    )
else:
    st.sidebar.success("✅ Sin alertas activas")

# ==================================================
# MENU PRINCIPAL
# ==================================================

MENU_ROUTES = {
    # CORE
    "📊 Panel de control": ("dashboard.view", lambda: render_dashboard_unificado(usuario)),

    # OPERACIONES
    "📦 Inventario / Almacén": ("inventario.view", lambda: render_inventario_almacen_unificado(usuario)),
    "🏗️ Activos": (("activos.view", "mantenimiento.view"), lambda: render_activos_unificado(usuario)),

    # CLIENTES Y VENTAS
    "👥 Clientes": ("clientes.view", lambda: render_clientes(usuario)),
    "💰 Ventas": ("ventas.view", lambda: render_ventas(usuario)),
    "📝 Cotizaciones": ("cotizaciones.view", lambda: render_cotizaciones(usuario)),
    "📣 Marketing": (("crm.view", "publicaciones.view"), lambda: render_marketing_unificado(usuario)),

    # PRODUCCION
    "🏭 Producción": (("produccion.plan", "produccion.execute", "produccion.route", "produccion.quality", "produccion.scrap"), lambda: render_produccion_unificada(usuario)),

    # FINANZAS
    "💼 Finanzas": (("tesoreria.view", "dashboard.view", "gastos.view", "caja.view", "cxp.view", "contabilidad.view", "conciliacion.view", "impuestos.view", "presupuesto.view"), lambda: render_planeacion_financiera(usuario)),

    # ADMINISTRACION Y RRHH
    "🗂️ Administración": (("dashboard.view", "config.view", "security.view", "reportes.export", "manuales.view", "auditoria.view", "calendario_operativo.view"), lambda: render_area_empresarial("Administración", usuario)),
    "👨‍💼 Nómina y trabajadores": ("nomina.view", lambda: render_nomina_trabajadores(usuario)),
    "👥 RRHH": (("rrhh.view", "dashboard.view"), lambda: render_area_combinada("Recursos Humanos", render_rrhh, usuario)),

    # LEGAL
    "⚖️ Legal": (("dashboard.view", "config.view"), lambda: render_area_combinada("Legal", render_manuales_sop, usuario)),

    # ANALITICA Y COSTOS
    "🧮 Costeo y Márgenes": (("costeo.view", "costeo_industrial.view"), lambda: render_costeo_margenes_unificado(usuario)),
    "🧮 Calculadora": ("dashboard.view", lambda: render_calculadora(usuario)),

    # OTROS
    "🛠️ Otros procesos": ("dashboard.view", lambda: render_otros_procesos(usuario)),
}

# Rutas movidas al hub de Administración. Se conservan sus funciones dentro de
# 🗂️ Administración, pero se ocultan del menú principal para evitar duplicados.
ADMIN_MENU_MOVED = {
    "📊 Auditoría",
    "📅 Calendario operativo",
    "⚙️ Configuración",
    "🔐 Seguridad / Roles",
    "🧰 Respaldo / Exportación",
    "📘 Manuales / SOP",
    "🧠 Diagnóstico IA",
    "🧩 Módulos rescatados",
}
for _moved_label in ADMIN_MENU_MOVED:
    MENU_ROUTES.pop(_moved_label, None)

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
