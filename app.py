import streamlit as st

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
from views.kontigo import render_kontigo
from views.configuracion import render_configuracion


st.set_page_config(
    page_title="Imperio Atómico ERP",
    layout="wide"
)

menu = st.sidebar.selectbox(
    "Menú",
    [
        "📊 Dashboard",
        "🛒 Venta Directa",
        "📦 Inventario",
        "📊 Kardex",
        "👥 Clientes",
        "🎨 Análisis CMYK",
        "🏗️ Activos",
        "🧠 Diagnóstico IA",
        "🛠️ Otros Procesos",
        "✂️ Corte Industrial",
        "🔥 Sublimación Industrial",
        "🎨 Producción Manual",
        "💰 Ventas",
        "📉 Gastos",
        "🏁 Cierre de Caja",
        "📊 Auditoría y Métricas",
        "📝 Cotizaciones",
        "💳 Kontigo",
        "⚙️ Configuración"
    ]
)

usuario = st.session_state.get("usuario", "Sistema")

if menu == "📊 Dashboard":
    render_dashboard()

elif menu == "🛒 Venta Directa":
    render_venta_directa(usuario)

elif menu == "📦 Inventario":
    render_inventario(usuario)

elif menu == "📊 Kardex":
    render_kardex(usuario)

elif menu == "👥 Clientes":
    render_clientes(usuario)

elif menu == "🎨 Análisis CMYK":
    render_cmyk(usuario)

elif menu == "🏗️ Activos":
    render_activos(usuario)

elif menu == "🧠 Diagnóstico IA":
    render_diagnostico(usuario)

elif menu == "🛠️ Otros Procesos":
    render_otros_procesos(usuario)

elif menu == "✂️ Corte Industrial":
    render_corte(usuario)

elif menu == "🔥 Sublimación Industrial":
    render_sublimacion(usuario)

elif menu == "🎨 Producción Manual":
    render_produccion_manual(usuario)

elif menu == "💰 Ventas":
    render_ventas(usuario)

elif menu == "📉 Gastos":
    render_gastos(usuario)

elif menu == "🏁 Cierre de Caja":
    render_caja(usuario)

elif menu == "📊 Auditoría y Métricas":
    render_auditoria(usuario)

elif menu == "📝 Cotizaciones":
    render_cotizaciones(usuario)

elif menu == "💳 Kontigo":
    render_kontigo(usuario)

elif menu == "⚙️ Configuración":
    render_configuracion(usuario)
