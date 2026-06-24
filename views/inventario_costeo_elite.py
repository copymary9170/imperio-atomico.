from __future__ import annotations

import streamlit as st

from services.inventario_costeo_elite_service import calcular_corte, guardar_costeo, listar_costeo_elite
from views.costeo_impresion_variable import render_costeo_impresion_variable


def render_inventario_costeo_elite(usuario: str) -> None:
    st.subheader("📐 Costeo técnico y variable")
    st.caption(
        "Costea tanto los materiales comprados como cada trabajo personalizado según tinta, "
        "tamaño, cobertura, papel, cortes, merma, mano de obra y margen."
    )

    tabs = st.tabs([
        "🖨️ Trabajo de impresión variable",
        "💰 Costo puesto del material",
        "✂️ Rendimiento por corte",
        "📊 Resumen técnico",
    ])

    with tabs[0]:
        render_costeo_impresion_variable(usuario)

    df = listar_costeo_elite()

    with tabs[1]:
        if df.empty:
            st.info("Primero crea artículos en Maestro y parámetros.")
        else:
            ids = [int(x) for x in df["id"].tolist()]
            etiquetas = {
                int(row["id"]): f"{row['sku']} · {row['nombre']} · {row['tipo_fisico']}"
                for _, row in df.iterrows()
            }
            item_id = st.selectbox("Artículo", ids, format_func=lambda value: etiquetas[value], key="costeo_elite_item")
            row = df[df["id"] == item_id].iloc[0]

            with st.form("costeo_elite_form"):
                st.markdown("#### Compra y contenido")
                c1, c2, c3 = st.columns(3)
                cantidad_comprada = c1.number_input("Cantidad de bultos comprados", min_value=0.0001, value=float(row["cantidad_comprada"] or 1), step=1.0)
                unidad_compra = c2.text_input("Unidad de compra", value=str(row["unidad_compra"] or ""), placeholder="resma, caja, botella, rollo...")
                piezas_por_compra = c3.number_input("Contenido por bulto", min_value=0.0001, value=max(float(row["piezas_por_compra"] or 1), 0.0001), step=1.0)

                st.markdown("#### Medidas y contenido físico")
                c4, c5, c6 = st.columns(3)
                ancho = c4.number_input("Ancho (cm)", min_value=0.0, value=float(row["ancho_cm"] or 0))
                alto = c5.number_input("Alto (cm)", min_value=0.0, value=float(row["alto_cm"] or 0))
                largo = c6.number_input("Largo total por rollo (cm)", min_value=0.0, value=float(row["largo_cm"] or 0))
                c7, c8 = st.columns(2)
                peso = c7.number_input("Peso por bulto (g)", min_value=0.0, value=float(row["peso_total_g"] or 0))
                volumen = c8.number_input("Volumen por bulto (ml)", min_value=0.0, value=float(row["volumen_total_ml"] or 0))

                st.markdown("#### Costo real de adquisición")
                d1, d2, d3 = st.columns(3)
                costo_producto = d1.number_input("Costo del producto USD", min_value=0.0, value=float(row["costo_producto_usd"] or 0), format="%.4f")
                delivery = d2.number_input("Delivery / flete USD", min_value=0.0, value=float(row["delivery_usd"] or 0), format="%.4f")
                impuestos = d3.number_input("Impuestos / aranceles USD", min_value=0.0, value=float(row["impuestos_usd"] or 0), format="%.4f")
                d4, d5, d6 = st.columns(3)
                comision = d4.number_input("Comisión de pago USD", min_value=0.0, value=float(row["comision_usd"] or 0), format="%.4f")
                otros = d5.number_input("Otros gastos USD", min_value=0.0, value=float(row["otros_usd"] or 0), format="%.4f")
                merma = d6.number_input("Merma prevista (%)", min_value=0.0, max_value=99.99, value=float(row["merma_pct"] or 0))
                guardar = st.form_submit_button("Guardar costeo técnico", type="primary", use_container_width=True)

            if guardar:
                try:
                    guardar_costeo(
                        item_id,
                        cantidad_comprada=cantidad_comprada,
                        unidad_compra=unidad_compra,
                        piezas_por_compra=piezas_por_compra,
                        ancho_cm=ancho,
                        alto_cm=alto,
                        largo_cm=largo,
                        peso_total_g=peso,
                        volumen_total_ml=volumen,
                        costo_producto_usd=costo_producto,
                        delivery_usd=delivery,
                        impuestos_usd=impuestos,
                        comision_usd=comision,
                        otros_usd=otros,
                        merma_pct=merma,
                    )
                    st.success("Costeo técnico guardado.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            actual = listar_costeo_elite()
            fila = actual[actual["id"] == item_id].iloc[0]
            st.markdown("#### Resultado")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Costo puesto", f"${float(fila['costo_puesto_usd']):,.4f}")
            r2.metric("Costo por unidad", f"${float(fila['costo_por_unidad_usd']):,.6f}")
            r3.metric("Costo unidad útil", f"${float(fila['costo_por_unidad_util_usd']):,.6f}")
            r4.metric("Merma", f"{float(fila['merma_pct']):,.2f}%")
            r5, r6, r7 = st.columns(3)
            r5.metric("Costo por cm²", f"${float(fila['costo_por_cm2_usd']):,.8f}")
            r6.metric("Costo por gramo", f"${float(fila['costo_por_g_usd']):,.8f}")
            r7.metric("Costo por ml", f"${float(fila['costo_por_ml_usd']):,.8f}")

    with tabs[2]:
        st.markdown("### Simulador de aprovechamiento")
        st.info("Úsalo para papel, cartulina, foami, vinil, adhesivo, tela o cualquier material que se corte.")
        with st.form("calculadora_corte_elite"):
            a1, a2 = st.columns(2)
            ancho_material = a1.number_input("Ancho del material (cm)", min_value=0.01, value=21.59)
            alto_material = a2.number_input("Alto del material (cm)", min_value=0.01, value=27.94)
            p1, p2 = st.columns(2)
            ancho_pieza = p1.number_input("Ancho de cada pieza (cm)", min_value=0.01, value=5.0)
            alto_pieza = p2.number_input("Alto de cada pieza (cm)", min_value=0.01, value=5.0)
            e1, e2 = st.columns(2)
            separacion = e1.number_input("Separación entre piezas (cm)", min_value=0.0, value=0.2)
            margen = e2.number_input("Margen exterior (cm)", min_value=0.0, value=0.5)
            calcular = st.form_submit_button("Calcular rendimiento", type="primary", use_container_width=True)

        if calcular:
            try:
                resultado = calcular_corte(
                    ancho_material_cm=ancho_material,
                    alto_material_cm=alto_material,
                    ancho_pieza_cm=ancho_pieza,
                    alto_pieza_cm=alto_pieza,
                    separacion_cm=separacion,
                    margen_cm=margen,
                )
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Columnas", int(resultado["columnas"]))
                c2.metric("Filas", int(resultado["filas"]))
                c3.metric("Piezas", int(resultado["piezas"]))
                c4.metric("Aprovechamiento", f"{resultado['aprovechamiento_pct']:.2f}%")
                c5, c6, c7 = st.columns(3)
                c5.metric("Área total", f"{resultado['area_total_cm2']:,.2f} cm²")
                c6.metric("Área usada", f"{resultado['area_usada_cm2']:,.2f} cm²")
                c7.metric("Área de merma", f"{resultado['area_merma_cm2']:,.2f} cm²")
            except Exception as exc:
                st.error(str(exc))

    with tabs[3]:
        st.markdown("### Costos técnicos consolidados")
        if df.empty:
            st.info("No hay materiales configurados todavía.")
        else:
            resumen = listar_costeo_elite()
            columnas = [
                "sku", "nombre", "tipo_fisico", "unidad_base", "unidad_compra",
                "cantidad_comprada", "piezas_por_compra", "ancho_cm", "alto_cm",
                "largo_cm", "peso_total_g", "volumen_total_ml", "costo_producto_usd",
                "delivery_usd", "impuestos_usd", "comision_usd", "otros_usd",
                "merma_pct", "costo_puesto_usd", "costo_por_unidad_usd",
                "costo_por_cm2_usd", "costo_por_g_usd", "costo_por_ml_usd",
            ]
            st.dataframe(resumen[columnas], use_container_width=True, hide_index=True)
