from __future__ import annotations

import streamlit as st
import pandas as pd

from modules.common import as_positive, clean_text
from services.inventory_service import InventoryService
from services.produccion_service import ConsumoInsumo, ProduccionService


# ============================================================
# FUNCIÓN VACÍA DE AUDITORÍA
# ============================================================

def _noop_audit(*_args, **_kwargs):
    return None


# ============================================================
# INTERFAZ PRODUCCIÓN
# ============================================================

def render_produccion(usuario: str) -> None:

    st.subheader("🏭 Producción")

    inventory_service = InventoryService(
        money_fn=lambda x: round(float(x), 2),
        audit_fn=_noop_audit
    )

    service = ProduccionService(
        inventory_service=inventory_service
    )

    # ------------------------------------------------
    # FORMULARIO ORDEN PRODUCCIÓN
    # ------------------------------------------------

    with st.form("orden_produccion"):

        st.write("Crear orden de producción")

        c1, c2 = st.columns(2)

        tipo = c1.selectbox(
            "Tipo de producción",
            ["CMYK", "Sublimación", "Corte", "Manual"]
        )

        referencia = c2.text_input("Referencia")

        costo_estimado = st.number_input(
            "Costo estimado",
            min_value=0.0
        )

        inventario_id = st.number_input(
            "ID Insumo",
            min_value=1,
            step=1
        )

        cantidad = st.number_input(
            "Cantidad insumo",
            min_value=0.0001,
            value=1.0
        )

        costo_u = st.number_input(
            "Costo unitario",
            min_value=0.0
        )

        submit = st.form_submit_button("💾 Crear orden")

    # ------------------------------------------------
    # CREAR ORDEN
    # ------------------------------------------------

    if submit:

        try:

            referencia = clean_text(referencia) or f"Orden {tipo}"

            costo_estimado = as_positive(
                costo_estimado,
                "Costo estimado"
            )

            cantidad = as_positive(
                cantidad,
                "Cantidad insumo",
                allow_zero=False
            )

            costo_u = as_positive(
                costo_u,
                "Costo unitario"
            )

            orden_id = service.registrar_orden(
                usuario=usuario,
                tipo_produccion=tipo,
                referencia=referencia,
                costo_estimado=costo_estimado,
                insumos=[
                    ConsumoInsumo(
                        inventario_id=int(inventario_id),
                        cantidad=float(cantidad),
                        costo_unitario=float(costo_u)
                    )
                ],
            )

            st.success(f"Orden de producción #{orden_id} registrada")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error creando orden")

            st.exception(e)

    st.divider()

    # ------------------------------------------------
    # HISTORIAL PRODUCCIÓN
    # ------------------------------------------------

    try:

        ordenes = service.obtener_ordenes()

    except Exception:

        ordenes = []

    if not ordenes:

        st.info("No hay órdenes registradas")

        return

    df = pd.DataFrame(ordenes)

    buscar = st.text_input("🔎 Buscar orden")

    if buscar:

        df = df[
            df.astype(str)
            .apply(lambda col: col.str.contains(buscar, case=False, na=False))
            .any(axis=1)
        ]

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric("Órdenes", len(df))

    if "costo_estimado" in df.columns:

        c2.metric(
            "Costo producción",
            f"$ {df['costo_estimado'].sum():,.2f}"
        )

    if "tipo_produccion" in df.columns:

        c3.metric(
            "Tipos producción",
            df["tipo_produccion"].nunique()
        )

    st.divider()

    # ------------------------------------------------
    # TABLA
    # ------------------------------------------------

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
