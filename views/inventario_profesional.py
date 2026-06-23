from __future__ import annotations

import streamlit as st

from services.capacidad_profesional import listar_capacidad
from services.inventario_profesional_service import guardar_parametros, inventario_fisico


def render_inventario_profesional(usuario: str) -> None:
    st.subheader("📐 Inventario físico profesional")
    st.caption("Controla área, volumen, peso, longitud y unidades reales; calcula mínimos operativos y capacidad de producción.")
    tabs = st.tabs(["Semáforo físico", "Configurar mínimos", "Capacidad de producción"])

    with tabs[0]:
        df = inventario_fisico()
        if df.empty:
            st.info("No hay artículos activos.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Artículos", len(df))
            c2.metric("Críticos", int(df["estado"].astype(str).str.contains("Crítico").sum()))
            c3.metric("Comprar pronto", int(df["estado"].astype(str).str.contains("Comprar pronto").sum()))
            c4.metric("Agotados", int(df["estado"].astype(str).str.contains("Agotado").sum()))
            filtro = st.selectbox("Estado", ["Todos"] + sorted(df["estado"].unique().tolist()))
            vista = df if filtro == "Todos" else df[df["estado"] == filtro]
            st.dataframe(vista, use_container_width=True, hide_index=True)

    with tabs[1]:
        df = inventario_fisico()
        if df.empty:
            st.info("No hay artículos para configurar.")
        else:
            ids = [int(x) for x in df["id"].tolist()]
            etiquetas = {int(r["id"]): f"{r['artículo']} · {r['unidad_control']}" for _, r in df.iterrows()}
            item_id = st.selectbox("Artículo", ids, format_func=lambda x: etiquetas[x])
            fila = df[df["id"] == item_id].iloc[0]
            st.info(f"Disponible actual: {fila['disponible']:,.4f} {fila['unidad_control']}")
            with st.form("configurar_control_profesional"):
                c1, c2 = st.columns(2)
                minimo = c1.number_input("Mínimo operativo", min_value=0.0, value=float(fila["mínimo_operativo"]), step=1.0)
                seguridad = c2.number_input("Stock de seguridad", min_value=0.0, step=1.0)
                c3, c4 = st.columns(2)
                consumo = c3.number_input("Consumo promedio diario", min_value=0.0, step=1.0)
                reposicion = c4.number_input("Días de reposición del proveedor", min_value=0.0, step=1.0)
                st.caption("Punto de reorden = consumo diario × días de reposición + stock de seguridad.")
                guardar = st.form_submit_button("Guardar parámetros", type="primary")
            if guardar:
                try:
                    guardar_parametros(item_id, minimo_operativo=minimo, stock_seguridad=seguridad, consumo_promedio_diario=consumo, dias_reposicion=reposicion)
                    st.success("Parámetros guardados y punto de reorden recalculado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tabs[2]:
        capacidad = listar_capacidad()
        if capacidad.empty:
            st.info("Crea recetas con materiales para calcular capacidad de producción.")
        else:
            st.dataframe(capacidad, use_container_width=True, hide_index=True)
            criticas = capacidad[capacidad["capacidad_producción"] <= 0]
            if not criticas.empty:
                st.error("Hay recetas que no pueden producirse con el stock disponible.")
