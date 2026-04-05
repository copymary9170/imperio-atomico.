from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.integration_hub import render_module_inbox
from services.costeo_service import (
    calcular_costo_servicio,
    calcular_margen_estimado,
    guardar_costeo,
    obtener_parametros_costeo,
)


ESTADOS_COTIZACION = [
    "Cotización",
    "En revisión",
    "Aprobada",
    "Rechazada",
    "Convertida en orden",
]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(out) or math.isinf(out):
        return float(default)
    return out


def _normalizar_payload(payload: dict) -> tuple[str, float]:
    descripcion = (
        payload.get("descripcion")
        or payload.get("trabajo")
        or payload.get("tipo")
        or payload.get("tipo_produccion")
        or "Trabajo personalizado"
    )

    costo_base = _safe_float(payload.get("costo_estimado") or payload.get("costo_base"), 0.0)

    cantidad = _safe_float(payload.get("cantidad") or payload.get("unidades"), 1.0)
    if cantidad > 1 and costo_base > 0 and payload.get("costo_estimado") is None:
        costo_base *= cantidad

    return str(descripcion), round(_safe_float(costo_base, 0.0), 2)


def _insertar_cotizacion(
    usuario: str,
    descripcion: str,
    costo_estimado_usd: float,
    margen_pct: float,
    precio_final_usd: float,
    estado: str,
) -> int:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cotizaciones (usuario, descripcion, costo_estimado_usd, margen_pct, precio_final_usd, estado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                descripcion,
                float(costo_estimado_usd),
                float(margen_pct),
                float(precio_final_usd),
                estado,
            ),
        )
        return int(cur.lastrowid)


def _actualizar_estado(cotizacion_id: int, estado: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE cotizaciones SET estado=? WHERE id=?",
            (estado, int(cotizacion_id)),
        )


def render_cotizaciones(usuario: str):
    st.subheader("📝 Gestión de Cotizaciones")

    def _apply_inbox(inbox: dict) -> None:
        st.session_state["datos_pre_cotizacion"] = dict(inbox.get("payload_data", {}))

    render_module_inbox("cotizaciones", apply_callback=_apply_inbox, clear_after_apply=False)

    datos_pre = st.session_state.get("datos_pre_cotizacion", {})
    descripcion_pre, costo_base_pre = _normalizar_payload(datos_pre) if datos_pre else ("", 0.0)

    with st.expander("⚡ Generador rápido de cotizaciones", expanded=True):
        costeo_calculado: dict | None = None
        modo_precio = st.radio(
            "Modo de cotización",
            options=["Manual", "Calculada (costeo)"],
            horizontal=True,
            help="Manual mantiene el flujo actual. Calculada usa el motor básico de costeo.",
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            descripcion = st.text_area(
                "Descripción del trabajo",
                value=descripcion_pre,
                placeholder="Ej: Impresión CMYK 200 páginas + corte vinil",
                height=110,
            )
        with c2:
            costo_estimado = st.number_input(
                "Costo estimado (USD)",
                min_value=0.0,
                value=max(_safe_float(costo_base_pre, 0.0), 0.0),
                step=0.5,
                format="%.2f",
            )
            if modo_precio == "Manual":
                margen_pct = st.slider("Margen (%)", min_value=0, max_value=250, value=65, step=1)
            else:
                margen_pct = 0.0
            ajuste_usd = st.number_input(
                "Ajustes extras (USD)",
                value=0.0,
                step=0.5,
                format="%.2f",
                help="Incluye flete, instalación, urgencia o descuento (usa negativo).",
            )

        if modo_precio == "Calculada (costeo)":
            parametros_costeo = obtener_parametros_costeo()
            st.caption("Costeo incremental: usa parámetros del sistema y no altera el flujo actual.")
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                tipo_proceso = st.selectbox(
                    "Tipo proceso",
                    options=["Servicio general", "Impresión", "Sublimación", "Corte", "Instalación"],
                    key="cot_tipo_proceso",
                )
            with k2:
                cantidad = st.number_input("Cantidad", min_value=0.01, value=1.0, step=1.0, key="cot_cantidad")
            with k3:
                costo_materiales = st.number_input("Materiales (USD)", min_value=0.0, value=0.0, step=0.5, key="cot_mat")
            with k4:
                costo_mano_obra = st.number_input("Mano de obra (USD)", min_value=0.0, value=0.0, step=0.5, key="cot_mo")

            costo_indirecto = st.number_input(
                "Indirecto directo (USD)",
                min_value=0.0,
                value=0.0,
                step=0.5,
                key="cot_ind",
            )
            margen_pct = st.number_input(
                "Margen objetivo (%)",
                min_value=0.0,
                max_value=300.0,
                value=float(parametros_costeo.get("margen_objetivo_pct", 35.0)),
                step=1.0,
                key="cot_margen_calc",
            )

            costeo = calcular_costo_servicio(
                tipo_proceso=tipo_proceso,
                cantidad=float(cantidad),
                costo_materiales_usd=float(costo_materiales),
                costo_mano_obra_usd=float(costo_mano_obra),
                costo_indirecto_usd=float(costo_indirecto),
                parametros_override=parametros_costeo,
            )
            costo_estimado = float(costeo["costo_total_usd"])

            if costo_estimado <= 0:
                precio_final = round(_safe_float(ajuste_usd, 0.0), 2)
                st.warning(
                    "El costo total calculado es 0. Ingresa al menos un costo (> 0) para estimar margen y precio."
                )
            else:
                margen = calcular_margen_estimado(
                    costo_total_usd=float(costeo["costo_total_usd"]),
                    margen_pct=float(margen_pct),
                )
                precio_final = round(float(margen["precio_sugerido_usd"]) + _safe_float(ajuste_usd, 0.0), 2)
                costeo_calculado = {
                    "tipo_proceso": tipo_proceso,
                    "cantidad": float(cantidad),
                    "costo_materiales_usd": float(costo_materiales),
                    "costo_mano_obra_usd": float(costo_mano_obra),
                    "costo_indirecto_usd": float(costo_indirecto),
                    "margen_pct": float(margen_pct),
                    "precio_sugerido_usd": float(precio_final),
                }

            desglose = pd.DataFrame(
                [
                    ("Materiales", costeo["componentes"]["materiales_usd"]),
                    ("Mano de obra", costeo["componentes"]["mano_obra_usd"]),
                    ("Indirecto directo", costeo["componentes"]["indirecto_directo_usd"]),
                    ("Imprevistos", costeo["componentes"]["imprevistos_usd"]),
                    ("Indirecto factor", costeo["componentes"]["indirecto_factor_usd"]),
                ],
                columns=["Concepto", "Monto USD"],
            )
            st.dataframe(desglose, use_container_width=True, hide_index=True)
            st.caption(
                f"Costo estimado calculado: $ {costo_estimado:,.2f} · Precio sugerido: $ {precio_final:,.2f}"
            )

        estado_nuevo = st.selectbox("Estado inicial", ESTADOS_COTIZACION, index=0)
        if modo_precio == "Manual":
            subtotal = _safe_float(costo_estimado, 0.0) * (1 + _safe_float(margen_pct, 0.0) / 100)
            precio_final = round(subtotal + _safe_float(ajuste_usd, 0.0), 2)

        m1, m2, m3 = st.columns(3)
        m1.metric("Costo base", f"$ {float(costo_estimado):,.2f}")
        m2.metric("Margen aplicado", f"{float(margen_pct):,.0f}%")
        m3.metric("Precio recomendado", f"$ {precio_final:,.2f}")

        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("💾 Guardar cotización", use_container_width=True):
                if not descripcion.strip():
                    st.warning("Agrega una descripción para guardar la cotización.")
                else:
                    cid = _insertar_cotizacion(
                        usuario=usuario,
                        descripcion=descripcion.strip(),
                        costo_estimado_usd=_safe_float(costo_estimado, 0.0),
                        margen_pct=_safe_float(margen_pct, 0.0),
                        precio_final_usd=_safe_float(precio_final, 0.0),
                        estado=estado_nuevo,
                    )
                    if modo_precio == "Calculada (costeo)" and costeo_calculado is not None:
                        guardar_costeo(
                            usuario=usuario,
                            tipo_proceso=str(costeo_calculado["tipo_proceso"]),
                            descripcion=descripcion.strip(),
                            cantidad=float(costeo_calculado["cantidad"]),
                            costo_materiales_usd=float(costeo_calculado["costo_materiales_usd"]),
                            costo_mano_obra_usd=float(costeo_calculado["costo_mano_obra_usd"]),
                            costo_indirecto_usd=float(costeo_calculado["costo_indirecto_usd"]),
                            margen_pct=float(costeo_calculado["margen_pct"]),
                            precio_sugerido_usd=float(costeo_calculado["precio_sugerido_usd"]),
                            origen="cotizacion",
                            referencia_id=int(cid),
                            cotizacion_id=int(cid),
                            estado="cotizado",
                        )
                    if "datos_pre_cotizacion" in st.session_state:
                        del st.session_state["datos_pre_cotizacion"]
                    st.success(f"Cotización #{cid} registrada correctamente.")
                    st.rerun()
        with b2:
            if st.button("🧹 Limpiar borrador", use_container_width=True):
                if "datos_pre_cotizacion" in st.session_state:
                    del st.session_state["datos_pre_cotizacion"]
                st.rerun()

    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    usuario,
                    descripcion,
                    costo_estimado_usd,
                    margen_pct,
                    precio_final_usd,
                    estado,
                    fecha
                FROM cotizaciones
                ORDER BY fecha DESC
                """
            ).fetchall()
    except Exception as e:
        st.error("Error cargando cotizaciones")
        st.exception(e)
        return

    if not rows:
        st.info("No hay cotizaciones registradas.")
        st.caption("Crea la primera cotización desde el generador rápido o inserta una cotización de ejemplo.")
        if st.button("🧪 Insertar cotización de ejemplo", use_container_width=True):
            cid = _insertar_cotizacion(
                usuario=usuario,
                descripcion="Cotización demo · Impresión y acabado",
                costo_estimado_usd=25.0,
                margen_pct=65.0,
                precio_final_usd=41.25,
                estado="Cotización",
            )
            st.success(f"Cotización demo #{cid} creada.")
            st.rerun()
        return

    df = pd.DataFrame(rows)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    st.divider()
    st.subheader("📊 Inteligencia de cotizaciones")


    total_cot = int(len(df))
    total_monto = float(df["precio_final_usd"].sum())
    ticket_prom = float(df["precio_final_usd"].mean()) if total_cot else 0.0
    aprobadas = int((df["estado"] == "Aprobada").sum())
    tasa_aprob = (aprobadas / total_cot * 100) if total_cot else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cotizaciones", f"{total_cot:,}")
    k2.metric("Monto proyectado", f"$ {total_monto:,.2f}")
    k3.metric("Ticket promedio", f"$ {ticket_prom:,.2f}")
    k4.metric("Tasa de aprobación", f"{tasa_aprob:,.1f}%")

    f1, f2, f3 = st.columns([1.5, 1, 1])
    with f1:
        q = st.text_input("Buscar", placeholder="Cliente, descripción, usuario...")
    with f2:
        estados_disponibles = sorted(df["estado"].dropna().unique().tolist())
        estados_filtrados = st.multiselect(
            "Estado",
            options=estados_disponibles,
            default=estados_disponibles,
        )
    with f3:
        fecha_min = df["fecha"].dropna().min()
        fecha_max = df["fecha"].dropna().max()
        rango = st.date_input(
            "Rango de fechas",
            value=(fecha_min.date(), fecha_max.date()) if pd.notna(fecha_min) and pd.notna(fecha_max) else (),
        )

    df_filtrado = df.copy()
    if q.strip():
        qlow = q.lower()
        df_filtrado = df_filtrado[
            df_filtrado.astype(str).apply(lambda c: c.str.lower().str.contains(qlow, na=False)).any(axis=1)
        ]

    if estados_filtrados:
        df_filtrado = df_filtrado[df_filtrado["estado"].isin(estados_filtrados)]

    if isinstance(rango, (tuple, list)) and len(rango) == 2:
        inicio, fin = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])
        df_filtrado = df_filtrado[(df_filtrado["fecha"] >= inicio) & (df_filtrado["fecha"] <= fin + pd.Timedelta(days=1))]

    c1, c2 = st.columns(2)
    with c1:
        estado_chart = df_filtrado.groupby("estado", as_index=False).size().rename(columns={"size": "cantidad"})
        if not estado_chart.empty:
            fig_estado = px.pie(estado_chart, names="estado", values="cantidad", title="Distribución por estado")
            st.plotly_chart(fig_estado, use_container_width=True)
    with c2:
        trend = (
            df_filtrado.dropna(subset=["fecha"]) 
            .assign(dia=lambda d: d["fecha"].dt.date.astype(str))
            .groupby("dia", as_index=False)["precio_final_usd"]
            .sum()
        )
        if not trend.empty:
            fig_trend = px.line(trend, x="dia", y="precio_final_usd", markers=True, title="Monto cotizado por día")
            fig_trend.update_layout(yaxis_title="USD", xaxis_title="Fecha")
            st.plotly_chart(fig_trend, use_container_width=True)

    st.subheader("📋 Historial")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Exportar CSV",
        data=df_filtrado.to_csv(index=False).encode("utf-8"),
        file_name="cotizaciones_filtradas.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("🛠️ Actualizar estado de una cotización"):
        col_a, col_b = st.columns(2)
        with col_a:
            cot_id = st.number_input("ID de cotización", min_value=1, step=1)
        with col_b:
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_COTIZACION, index=0, key="nuevo_estado_cot")

        if st.button("Actualizar estado", use_container_width=True):
            try:
                _actualizar_estado(int(cot_id), nuevo_estado)
                st.success(f"Cotización #{int(cot_id)} actualizada a '{nuevo_estado}'.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo actualizar: {e}")
