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
from views.configuracion import render_configuracion
from modules.configuracion import render_sidebar_config_snapshot

# NUEVA VISTA DEL MOTOR INDUSTRIAL
from views.engine_demo import render_engine_demo


# ==================================================
# USUARIO
# ==================================================

usuario = st.session_state.get("usuario", "Sistema")

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

    "🧮 Calculadora": lambda: render_calculadora(usuario),

    "⚙️ Configuración": lambda: render_configuracion(usuario),

    # NUEVA HERRAMIENTA DEL MOTOR
    "⚙️ Motor Industrial": lambda: render_engine_demo(usuario),

}

# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.title("⚛️ Imperio Atómico ERP")

menu = st.sidebar.selectbox(
    "Menú",
    list(MENU_ROUTES.keys())
)

render_sidebar_config_snapshot()

# ==================================================
# EJECUTAR VISTA
# ==================================================

MENU_ROUTES[menu]()
