import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint, render_module_portfolio


def render_portafolio_modulos(usuario):
    st.title("🧩 Nuevos módulos ERP")
    render_module_portfolio(usuario)


def render_compras_proveedores(usuario):
    render_module_blueprint("compras_proveedores", usuario)


def render_cuentas_por_pagar(usuario):
    render_module_blueprint("cuentas_por_pagar", usuario)


def render_tesoreria(usuario):
    render_module_blueprint("tesoreria", usuario)


def render_costeo_industrial(usuario):
    render_module_blueprint("costeo_industrial", usuario)


def render_mermas_desperdicio(usuario):
    render_module_blueprint("mermas_desperdicio", usuario)


def render_mantenimiento_activos(usuario):
    render_module_blueprint("mantenimiento_activos", usuario)


def render_planificacion_produccion(usuario):
    render_module_blueprint("planificacion_produccion", usuario)


def render_control_calidad(usuario):
    render_module_blueprint("control_calidad", usuario)


def render_rutas_produccion(usuario):
    render_module_blueprint("rutas_produccion", usuario)


def render_impuestos(usuario):
    render_module_blueprint("impuestos", usuario)


def render_conciliacion_bancaria(usuario):
    render_module_blueprint("conciliacion_bancaria", usuario)


def render_crm(usuario):
    render_module_blueprint("crm", usuario)


def render_marketing_ventas(usuario):
    render_module_blueprint("marketing_ventas", usuario)


def render_fidelizacion(usuario):
    render_module_blueprint("fidelizacion", usuario)


def render_catalogo(usuario):
    render_module_blueprint("catalogo", usuario)


def render_rrhh(usuario):
    render_module_blueprint("catalogo", usuario)


def render_rrhh(usuario):
    render_module_blueprint("rrhh", usuario)


def render_seguridad_roles(usuario):
    render_module_blueprint("seguridad_roles", usuario)


def render_manuales_sop(usuario):
    render_module_blueprint("manuales_sop", usuario)
