from __future__ import annotations

import pandas as pd
import streamlit as st


def render_sublimacion(usuario: str):
    st.title("🔥 Sublimación Industrial")
    st.caption(f"Operador: {usuario}")

    cola = st.session_state.get("cola_sublimacion", [])
    if not cola:
        st.info("No hay trabajos recibidos desde CMYK.")
        return

    df_cola = pd.DataFrame(cola)
    st.subheader("📥 Trabajos pendientes")
    st.dataframe(df_cola, use_container_width=True, hide_index=True)

    total_transfer = float(df_cola.get("costo_transfer_total", pd.Series(dtype=float)).sum())
    total_unidades = int(df_cola.get("cantidad", pd.Series(dtype=float)).sum())
    costo_unitario_transfer = total_transfer / max(total_unidades, 1)

    st.subheader("⚙️ Costos de Sublimación")
    c1, c2, c3 = st.columns(3)

    potencia_kw = c1.number_input("Potencia kW", value=1.5, min_value=0.1)
    minutos_unidad = c2.number_input("Min por unidad", value=5.0, min_value=0.1)
    costo_kwh = c3.number_input("Costo kWh", value=0.15, min_value=0.0)

    energia_unit = (potencia_kw * minutos_unidad / 60.0) * costo_kwh

    c4, c5 = st.columns(2)
    salario_hora = c4.number_input("Salario hora operador", value=3.0, min_value=0.0)
    prod_hora = c5.number_input("Unidades por hora", value=12.0, min_value=0.1)
    mano_unit = salario_hora / prod_hora

    c6, c7 = st.columns(2)
    valor_maquina = c6.number_input("Valor máquina", value=1500.0, min_value=0.0)
    vida_horas = c7.number_input("Vida útil horas", value=5000.0, min_value=1.0)
    dep_unit = (valor_maquina / vida_horas) / prod_hora

    costo_unitario_final = costo_unitario_transfer + energia_unit + mano_unit + dep_unit
    costo_total = costo_unitario_final * total_unidades

    m1, m2, m3 = st.columns(3)
    m1.metric("Costo transfer promedio", f"$ {costo_unitario_transfer:.4f}")
    m2.metric("Costo unitario final", f"$ {costo_unitario_final:.4f}")
    m3.metric("Costo total", f"$ {costo_total:.2f}")

    if st.button("✅ Finalizar Sublimación", use_container_width=True):
        st.session_state["cola_sublimacion"] = []
        st.success("Producción de sublimación completada. Cola vaciada.")
        st.rerun()
