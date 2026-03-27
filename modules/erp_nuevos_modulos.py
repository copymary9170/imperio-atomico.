rom __future__ import annotations

import streamlit as st

from modules.nuevos_modulos import (
    CATEGORY_KEYS,
    CATEGORY_LABELS,
    MODULE_BLUEPRINTS,
    MODULE_BY_KEY,
    get_related_flows,
)
from modules.nuevos_modulos.types import ModuleBlueprint


def _render_module(module: ModuleBlueprint) -> None:
    st.subheader(f"{module.icon} {module.name}")
    st.caption(f"{module.category} · Prioridad {module.priority}")
    st.info(module.summary)

    left, right = st.columns((1.4, 1))
    with left:
        st.markdown("### Alcance funcional")
        for capability in module.capabilities:
            st.markdown(f"- {capability}")

    with right:
        st.markdown("### Conecta con")
        for integration in module.integrations:
            st.markdown(f"- {integration}")
        st.markdown("### Valor de negocio")
        st.write(module.business_value)


def _render_data_flows(module_key: str) -> None:
    flows = get_related_flows(module_key)
    st.markdown("### 🔄 Flujo de información con otros módulos")
    if not flows:
        st.caption("Este módulo aún no tiene flujo de información definido en el blueprint.")
        return

    for flow in flows:
        direction = "salida" if flow.source == module_key else "entrada"
        st.markdown(
            f"- **{flow.source} → {flow.target}** · {flow.payload} · Frecuencia: {flow.frequency} ({direction})."
        )


def render_module_blueprint(module_key: str, usuario: str | None = None) -> None:
    module = MODULE_BY_KEY[module_key]
    st.markdown(f"## {module.icon} {module.name}")
    if usuario:
        st.caption(f"Vista estratégica para {usuario}")
    st.write(module.summary)

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Capacidades clave", len(module.capabilities))
    metric_2.metric("Integraciones", len(module.integrations))
    metric_3.metric("Prioridad", module.priority)

    tab1, tab2, tab3 = st.tabs(["📌 Definición", "🔗 Integraciones", "🚀 Implementación"])
    with tab1:
        st.markdown("### Debe incluir")
        for capability in module.capabilities:
            st.markdown(f"- {capability}")
        st.success(module.business_value)

    with tab2:
        st.markdown("### Sistemas conectados")
        for integration in module.integrations:
            st.markdown(f"- {integration}")
        _render_data_flows(module_key)
        st.caption(
            "Cada módulo tiene su propio espacio funcional, pero mantiene intercambio de datos para sostener trazabilidad entre finanzas, producción y operación."
        )

    with tab3:
        st.markdown("### Siguiente fase recomendada")
        st.markdown(
            "1. Definir tablas y eventos transaccionales.\n"
            "2. Construir servicios de dominio y reglas de negocio.\n"
            "3. Crear formularios, reportes y tableros operativos.\n"
            "4. Conectar métricas al dashboard ejecutivo."
        )
        st.warning("Blueprint listo para priorización funcional y técnica.")


def render_module_portfolio(usuario: str | None = None) -> None:
    st.subheader("🧩 Portafolio de módulos ERP propuestos")
    if usuario:
        st.caption(f"Mapa de expansión solicitado para {usuario}.")
    st.write(
        "Se organizó el módulo de nuevos módulos en bloques independientes: cada módulo mantiene su propio sitio funcional y, al mismo tiempo, un flujo de información conectado con el resto del ERP."
    )

    total_modules = len(MODULE_BLUEPRINTS)
    total_capabilities = sum(len(module.capabilities) for module in MODULE_BLUEPRINTS)
    high_priority = sum(module.priority in {"Crítica", "Alta"} for module in MODULE_BLUEPRINTS)

    m1, m2, m3 = st.columns(3)
    m1.metric("Módulos nuevos", total_modules)
    m2.metric("Capacidades definidas", total_capabilities)
    m3.metric("Prioridad alta/crítica", high_priority)

    for category_key, module_keys in CATEGORY_KEYS.items():
        with st.expander(CATEGORY_LABELS[category_key], expanded=True):
            for module_key in module_keys:
                _render_module(MODULE_BY_KEY[module_key])
                st.divider()


# Alias para mantener compatibilidad con llamadas existentes en vistas antiguas.
def render_portafolio_modulos(usuario: str | None = None) -> None:
    render_module_portfolio(usuario)
