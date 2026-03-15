# ============================================================
# PRODUCCIÓN MANUAL
# ============================================================

import streamlit as st
import pandas as pd


def render_produccion_manual(usuario: str):

    st.title("🎨 Producción Manual")

    producto = st.text_input("Producto")

    descripcion = st.text_area("Descripción del trabajo")

    cantidad = st.number_input(
        "Cantidad",
        min_value=1
    )

    costo_unitario = st.number_input(
        "Costo unitario USD",
        min_value=0.0
    )

    if st.button("Registrar producción"):

        total = cantidad * costo_unitario

        st.success("Producción registrada")

        st.metric("Costo total", f"$ {total:.2f}")

        df = pd.DataFrame({
            "Producto": [producto],
            "Cantidad": [cantidad],
            "Costo unitario": [costo_unitario],
            "Total": [total]
        })

        st.dataframe(df, use_container_width=True)

        st.session_state["produccion_manual_ultima"] = {
            "producto": str(producto).strip() or "Trabajo manual",
            "descripcion": str(descripcion).strip(),
            "cantidad": int(cantidad),
            "costo_unitario": float(costo_unitario),
            "total": float(total),
            "usuario": str(usuario),
        }

    datos_prod = st.session_state.get("produccion_manual_ultima")
    if not datos_prod:
        return

    st.divider()
    st.subheader("📤 Enviar producción manual")
    st.caption("Usa estos botones para despachar el trabajo al módulo que corresponda.")

    e1, e2, e3, e4 = st.columns(4)

    if e1.button("📝 Enviar a Cotizaciones", use_container_width=True):
        st.session_state["datos_pre_cotizacion"] = {
            "trabajo": datos_prod["producto"],
            "descripcion": datos_prod.get("descripcion") or datos_prod["producto"],
            "costo_base": float(datos_prod["total"]),
            "unidades": int(datos_prod["cantidad"]),
            "tipo_produccion": "manual",
        }
        st.success("Producción enviada a Cotizaciones.")

    if e2.button("🔥 Enviar a Sublimación", use_container_width=True):
        cola = list(st.session_state.get("cola_sublimacion", []))
        cola.append(
            {
                "trabajo": datos_prod["producto"],
                "cantidad": int(datos_prod["cantidad"]),
                "costo_transfer_total": float(datos_prod["total"]),
                "origen": "Producción Manual",
                "descripcion": datos_prod.get("descripcion") or "",
            }
        )
        st.session_state["cola_sublimacion"] = cola
        st.success("Producción agregada a la cola de Sublimación.")

    if e3.button("✂️ Enviar a Corte", use_container_width=True):
        st.session_state["datos_corte_desde_cmyk"] = {
            "trabajo": datos_prod["producto"],
            "cantidad": int(datos_prod["cantidad"]),
            "costo_base": float(datos_prod["total"]),
            "observacion": datos_prod.get("descripcion") or "Trabajo enviado desde Producción Manual",
            "origen": "Producción Manual",
        }
        st.success("Producción enviada al módulo de Corte.")

    if e4.button("🛠️ Enviar a Otros Procesos", use_container_width=True):
        st.session_state["datos_proceso_desde_cmyk"] = {
            "trabajo": datos_prod["producto"],
            "unidades": int(datos_prod["cantidad"]),
            "costo_base": float(datos_prod["total"]),
            "observacion": datos_prod.get("descripcion") or "Trabajo enviado desde Producción Manual",
            "origen": "Producción Manual",
        }
        st.success("Producción enviada a Otros Procesos.")
