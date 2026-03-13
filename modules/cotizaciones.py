from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction

ESTADOS_COTIZACION = [
    "Cotización",
    "En revisión",
    "Aprobada",
    "Rechazada",
    "Convertida en orden",
]


def _normalizar_payload(payload: dict) -> tuple[str, float]:
    descripcion = (
        payload.get("descripcion")
        or payload.get("trabajo")
        or payload.get("tipo")
        or payload.get("tipo_produccion")
        or "Trabajo personalizado"
    )

    costo_base = float(payload.get("costo_estimado") or payload.get("costo_base") or 0.0)

    cantidad = float(payload.get("cantidad") or payload.get("unidades") or 1)
    if cantidad > 1 and costo_base > 0 and payload.get("costo_estimado") is None:
        costo_base *= cantidad

    return str(descripcion), round(float(costo_base), 2)


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

    datos_pre = st.session_state.get("datos_pre_cotizacion", {})
    descripcion_pre, costo_base_pre = _normalizar_payload(datos_pre) if datos_pre else ("", 0.0)

    with st.expander("⚡ Generador rápido de cotizaciones", expanded=True):
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
                value=max(float(costo_base_pre), 0.0),
                step=0.5,
                format="%.2f",
            )
            margen_pct = st.slider("Margen (%)", min_value=0, max_value=250, value=65, step=1)
            ajuste_usd = st.number_input(
                "Ajustes extras (USD)",
                value=0.0,
                step=0.5,
                format="%.2f",
                help="Incluye flete, instalación, urgencia o descuento (usa negativo).",
            )

        estado_nuevo = st.selectbox("Estado inicial", ESTADOS_COTIZACION, index=0)
        subtotal = float(costo_estimado) * (1 + float(margen_pct) / 100)
        precio_final = round(subtotal + float(ajuste_usd), 2)

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
                        costo_estimado_usd=float(costo_estimado),
                        margen_pct=float(margen_pct),
                        precio_final_usd=float(precio_final),
                        estado=estado_nuevo,
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

    if isinstance(rango, tuple) and len(rango) == 2:
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
