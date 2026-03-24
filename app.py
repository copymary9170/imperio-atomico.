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

init_schema()

# ==================================================
# IMPORTAR VISTAS
# ==================================================

from views.dashboard import render_dashboard
from views.venta_directa import render_venta_directa
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
from views.configuracion import render_configuracion
from views.contabilidad import render_contabilidad
from views.rentabilidad import render_rentabilidad
from views.erp_nuevos_modulos import (
    render_portafolio_modulos,
    render_compras_proveedores,
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
    render_crm,
    render_marketing_ventas,
    render_fidelizacion,
    render_catalogo,
    render_rrhh,
    render_seguridad_roles,
    render_manuales_sop,
)
from modules.configuracion import render_sidebar_config_snapshot

# NUEVA VISTA DEL MOTOR INDUSTRIAL
from views.engine_demo import render_engine_demo


# ==================================================
# USUARIO
# ==================================================

usuario = st.session_state.get("usuario", "Sistema")


# ==================================================
# SIDEBAR
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

st.sidebar.title("⚛️ Imperio Atómico ERP")
st.sidebar.caption("Accede rápido a cada módulo desde el menú lateral fijo.")

# ==================================================
# MENÚ PRINCIPAL
# ==================================================

MENU_ROUTES = {

    "📊 Dashboard": lambda: render_dashboard(),

    "🛒 Venta Directa": lambda: render_venta_directa(usuario),

    "📦 Inventario": lambda: render_inventario(usuario),

    "📊 Kardex": lambda: render_kardex(usuario),

    "👥 Clientes": lambda: render_clientes(usuario),

    "🎨 Análisis CMYK": lambda: render_cmyk(usuario),

    "🏗️ Activos": lambda: render_activos(usuario),

    "🧠 Diagnóstico IA": lambda: render_diagnostico(usuario),

    "🛠️ Otros Procesos": lambda: render_otros_procesos(usuario),

    "✂️ Corte Industrial": lambda: render_corte(usuario),

    "🔥 Sublimación Industrial": lambda: render_sublimacion(usuario),

    "🎨 Producción Manual": lambda: render_produccion_manual(usuario),

    "💰 Ventas": lambda: render_ventas(usuario),

    "📉 Gastos": lambda: render_gastos(usuario),

    "🏁 Cierre de Caja": lambda: render_caja(usuario),

    "📊 Auditoría y Métricas": lambda: render_auditoria(usuario),

    "📝 Cotizaciones": lambda: render_cotizaciones(usuario),
   
    "🧮 Costeo": lambda: render_costeo(usuario),

    "🧮 Calculadora": lambda: render_calculadora(usuario),

    "⚙️ Configuración": lambda: render_configuracion(usuario),

    "📚 Contabilidad": lambda: render_contabilidad(usuario),

    "📈 Rentabilidad analítica": lambda: render_rentabilidad(usuario),

    # NUEVA HERRAMIENTA DEL MOTOR
    "⚙️ Motor Industrial": lambda: render_engine_demo(usuario),

    # PORTAFOLIO DE EXPANSIÓN ERP
    "🧩 Nuevos módulos ERP": lambda: render_portafolio_modulos(usuario),
    "🚚 Compras / Proveedores": lambda: render_compras_proveedores(usuario),
    "💸 Cuentas por pagar": lambda: render_cuentas_por_pagar(usuario),
    "🏦 Tesorería / Flujo de caja": lambda: render_tesoreria(usuario),
    "🧮 Costos / Costeo industrial": lambda: render_costeo_industrial(usuario),
    "♻️ Mermas y desperdicio": lambda: render_mermas_desperdicio(usuario),
    "🛠️ Mantenimiento de activos": lambda: render_mantenimiento_activos(usuario),
    "🗓️ Planificación de producción": lambda: render_planificacion_produccion(usuario),
    "✅ Control de calidad": lambda: render_control_calidad(usuario),
    "🧭 Rutas de producción": lambda: render_rutas_produccion(usuario),
    "🧾 Impuestos": lambda: render_impuestos(usuario),
    "🏛️ Conciliación bancaria": lambda: render_conciliacion_bancaria(usuario),
    "🤝 CRM": lambda: render_crm(usuario),
    "📣 Marketing / Ventas": lambda: render_marketing_ventas(usuario),
    "⭐ Fidelización": lambda: render_fidelizacion(usuario),
    "🛍️ Catálogo": lambda: render_catalogo(usuario),
    "👨‍💼 RRHH": lambda: render_rrhh(usuario),
    "🔐 Seguridad / Roles": lambda: render_seguridad_roles(usuario),
    "📘 Manuales / SOP": lambda: render_manuales_sop(usuario),

}

render_sidebar_config_snapshot()

menu = st.sidebar.radio(
    "Menú principal",
    list(MENU_ROUTES.keys()),
    label_visibility="collapsed",
)


# ==================================================
# EJECUTAR VISTA
# ==================================================

MENU_ROUTES[menu]()
