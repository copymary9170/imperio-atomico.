from __future__ import annotations

import streamlit as st

from services.costeo_impresion_variable_service import (
    calcular_costeo_variable,
    guardar_costeo,
    guardar_perfil,
    listar_costeos,
    listar_perfiles,
)


FACTORES_AREA = {
    "Carta completa": 1.0,
    "Media carta": 0.5,
    "Cuarto de carta": 0.25,
    "Oficio": 1.27,
    "A4": 0.97,
    "Personalizado": None,
}


def render_costeo_impresion_variable(usuario: str) -> None:
    st.subheader("🖨️ Costeo variable por trabajo")
    st.caption(
        "Calcula cada pedido según cobertura real CMYK, tamaño, papel, cantidad, acabados, mano de obra y merma."
    )

    tabs = st.tabs(["Calcular trabajo", "Perfiles de impresora", "Historial"])

    with tabs[1]:
        st.info(
            "El rendimiento se expresa como páginas aproximadas al 5% de cobertura por color. "
            "Puedes crear un perfil distinto para cada impresora o tipo de tinta."
        )
        with st.form("perfil_impresion_variable"):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre del perfil *", placeholder="HP Smart Tank 580 original")
            impresora = c2.text_input("Impresora", placeholder="HP Smart Tank 580")

            st.markdown("#### Costo de cada botella o cartucho")
            t1, t2, t3, t4 = st.columns(4)
            costo_c = t1.number_input("Cian USD", min_value=0.0, value=19.0)
            costo_m = t2.number_input("Magenta USD", min_value=0.0, value=19.0)
            costo_y = t3.number_input("Amarillo USD", min_value=0.0, value=19.0)
            costo_k = t4.number_input("Negro USD", min_value=0.0, value=19.0)

            st.markdown("#### Rendimiento aproximado al 5%")
            r1, r2, r3, r4 = st.columns(4)
            rend_c = r1.number_input("Cian páginas", min_value=1.0, value=6000.0)
            rend_m = r2.number_input("Magenta páginas", min_value=1.0, value=6000.0)
            rend_y = r3.number_input("Amarillo páginas", min_value=1.0, value=6000.0)
            rend_k = r4.number_input("Negro páginas", min_value=1.0, value=12000.0)

            i1, i2, i3 = st.columns(3)
            mantenimiento = i1.number_input("Mantenimiento por página USD", min_value=0.0, value=0.0, format="%.6f")
            depreciacion = i2.number_input("Depreciación por página USD", min_value=0.0, value=0.0, format="%.6f")
            energia = i3.number_input("Energía por página USD", min_value=0.0, value=0.0, format="%.6f")
            guardar_p = st.form_submit_button("Guardar perfil", type="primary", use_container_width=True)

        if guardar_p:
            try:
                perfil_id = guardar_perfil(
                    nombre=nombre,
                    impresora=impresora,
                    costos_tinta={"c": costo_c, "m": costo_m, "y": costo_y, "k": costo_k},
                    rendimientos_5pct={"c": rend_c, "m": rend_m, "y": rend_y, "k": rend_k},
                    mantenimiento_por_pagina=mantenimiento,
                    depreciacion_por_pagina=depreciacion,
                    energia_por_pagina=energia,
                )
                st.success(f"Perfil #{perfil_id} guardado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        perfiles_tabla = listar_perfiles()
        if not perfiles_tabla.empty:
            st.dataframe(perfiles_tabla, use_container_width=True, hide_index=True)

    with tabs[0]:
        perfiles = listar_perfiles()
        if perfiles.empty:
            st.warning("Primero crea un perfil de impresora en la segunda pestaña.")
        else:
            ids = [int(x) for x in perfiles["id"].tolist()]
            etiquetas = {
                int(row["id"]): f"{row['nombre']} · {row['impresora'] or 'Sin modelo'}"
                for _, row in perfiles.iterrows()
            }
            perfil_id = st.selectbox("Perfil de impresión", ids, format_func=lambda value: etiquetas[value])
            perfil = perfiles[perfiles["id"] == perfil_id].iloc[0].to_dict()

            with st.form("costeo_impresion_variable_form"):
                descripcion = st.text_input("Trabajo *", placeholder="50 invitaciones a color en papel fotográfico")
                c1, c2, c3 = st.columns(3)
                cantidad = c1.number_input("Cantidad de trabajos", min_value=0.0001, value=1.0)
                paginas = c2.number_input("Páginas impresas por trabajo", min_value=0.0001, value=1.0)
                tamano = c3.selectbox("Tamaño impreso", list(FACTORES_AREA))
                if tamano == "Personalizado":
                    factor_area = st.number_input(
                        "Factor respecto a una hoja carta",
                        min_value=0.0001,
                        value=1.0,
                        help="Ejemplo: 0,25 equivale aproximadamente a un cuarto de carta.",
                    )
                else:
                    factor_area = float(FACTORES_AREA[tamano])

                st.markdown("#### Cobertura de tinta por canal")
                st.caption("0% significa que ese color no se usa; 100% representa cobertura total de la superficie.")
                q1, q2, q3, q4 = st.columns(4)
                cobertura_c = q1.number_input("Cian %", min_value=0.0, max_value=100.0, value=0.0)
                cobertura_m = q2.number_input("Magenta %", min_value=0.0, max_value=100.0, value=0.0)
                cobertura_y = q3.number_input("Amarillo %", min_value=0.0, max_value=100.0, value=0.0)
                cobertura_k = q4.number_input("Negro %", min_value=0.0, max_value=100.0, value=5.0)

                st.markdown("#### Materiales y operación")
                m1, m2, m3 = st.columns(3)
                costo_papel = m1.number_input("Costo por hoja o pieza USD", min_value=0.0, value=0.0, format="%.6f")
                hojas_por_unidad = m2.number_input("Hojas o piezas por trabajo", min_value=0.0, value=1.0)
                acabado_unitario = m3.number_input("Acabado por trabajo USD", min_value=0.0, value=0.0, format="%.6f")

                o1, o2, o3, o4 = st.columns(4)
                mano_obra = o1.number_input("Mano de obra total USD", min_value=0.0, value=0.0)
                indirectos = o2.number_input("Diseño y otros indirectos USD", min_value=0.0, value=0.0)
                merma = o3.number_input("Merma prevista %", min_value=0.0, max_value=99.99, value=5.0)
                margen = o4.number_input("Margen deseado %", min_value=0.0, max_value=99.99, value=40.0)
                observaciones = st.text_area("Observaciones")
                calcular = st.form_submit_button("Calcular costo y precio", type="primary", use_container_width=True)

            if calcular:
                try:
                    coberturas = {
                        "c": cobertura_c,
                        "m": cobertura_m,
                        "y": cobertura_y,
                        "k": cobertura_k,
                    }
                    resultado = calcular_costeo_variable(
                        perfil=perfil,
                        cantidad=cantidad,
                        paginas_por_unidad=paginas,
                        factor_area=factor_area,
                        coberturas_pct=coberturas,
                        costo_papel_unitario=costo_papel,
                        hojas_por_unidad=hojas_por_unidad,
                        costo_acabado_unitario=acabado_unitario,
                        mano_obra_total=mano_obra,
                        otros_indirectos_total=indirectos,
                        merma_pct=merma,
                        margen_pct=margen,
                    )
                    st.session_state["ultimo_costeo_variable"] = {
                        "descripcion": descripcion,
                        "perfil_id": perfil_id,
                        "cantidad": cantidad,
                        "paginas": paginas,
                        "factor_area": factor_area,
                        "coberturas": coberturas,
                        "resultado": resultado,
                        "margen": margen,
                        "observaciones": observaciones,
                    }
                except Exception as exc:
                    st.error(str(exc))

            datos = st.session_state.get("ultimo_costeo_variable")
            if datos:
                resultado = datos["resultado"]
                st.markdown("### Resultado del trabajo")
                a1, a2, a3, a4 = st.columns(4)
                a1.metric("Costo de tinta", f"${resultado['costo_tinta_usd']:,.6f}")
                a2.metric("Costo total", f"${resultado['costo_total_usd']:,.4f}")
                a3.metric("Costo unitario", f"${resultado['costo_unitario_usd']:,.4f}")
                a4.metric("Precio unitario sugerido", f"${resultado['precio_unitario_sugerido_usd']:,.4f}")

                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Precio total sugerido", f"${resultado['precio_sugerido_usd']:,.4f}")
                b2.metric("Utilidad estimada", f"${resultado['utilidad_estimada_usd']:,.4f}")
                b3.metric("Páginas físicas", f"{resultado['paginas_fisicas']:,.2f}")
                b4.metric("Equivalente carta", f"{resultado['paginas_equivalentes_carta']:,.2f}")

                st.markdown("#### Tinta por canal")
                detalle = resultado["detalle_tinta"]
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Cian", f"${detalle['c']:,.8f}")
                t2.metric("Magenta", f"${detalle['m']:,.8f}")
                t3.metric("Amarillo", f"${detalle['y']:,.8f}")
                t4.metric("Negro", f"${detalle['k']:,.8f}")

                if st.button("Guardar este costeo", use_container_width=True):
                    try:
                        costeo_id = guardar_costeo(
                            usuario=usuario,
                            descripcion=datos["descripcion"],
                            perfil_id=datos["perfil_id"],
                            cantidad=datos["cantidad"],
                            paginas_por_unidad=datos["paginas"],
                            factor_area=datos["factor_area"],
                            coberturas_pct=datos["coberturas"],
                            resultado=datos["resultado"],
                            margen_pct=datos["margen"],
                            observaciones=datos["observaciones"],
                        )
                        st.success(f"Costeo #{costeo_id} guardado.")
                    except Exception as exc:
                        st.error(str(exc))

    with tabs[2]:
        historial = listar_costeos()
        if historial.empty:
            st.info("Todavía no hay costeos variables guardados.")
        else:
            st.dataframe(historial, use_container_width=True, hide_index=True)
