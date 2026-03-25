from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, require_text

ETAPAS_CRM = (
    "Nuevo",
    "Contactado",
    "Propuesta",
    "Negociación",
    "Ganado",
    "Perdido",
)



def _load_pipeline() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                l.id,
                l.fecha,
                l.nombre,
                l.canal,
                l.etapa,
                l.valor_estimado_usd,
                l.probabilidad_pct,
                l.proximo_contacto,
                l.notas,
                c.nombre AS cliente
            FROM crm_leads l
            LEFT JOIN clientes c ON c.id = l.cliente_id
            WHERE l.estado = 'activo'
            ORDER BY l.fecha DESC, l.id DESC
            """,
            conn,
        )



def _load_recent_interactions(limit: int = 25) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                i.fecha,
                l.nombre AS lead,
                i.tipo,
                i.resultado,
                i.detalle,
                i.proxima_accion,
                i.usuario
            FROM crm_interacciones i
            JOIN crm_leads l ON l.id = i.lead_id
            ORDER BY i.fecha DESC, i.id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )



def _load_commercial_overview() -> dict[str, float]:
    with db_transaction() as conn:
        ventas = conn.execute(
            """
            SELECT COALESCE(SUM(total_usd), 0) AS total_ventas,
                   COUNT(*) AS ventas_registradas
            FROM ventas
            WHERE estado = 'registrada'
            """
        ).fetchone()
        cotizaciones = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(precio_final_usd), 0) AS monto,
                COALESCE(SUM(CASE WHEN LOWER(COALESCE(estado, '')) IN ('aprobada','aprobado','ganada') THEN 1 ELSE 0 END), 0) AS aprobadas
            FROM cotizaciones
            """
        ).fetchone()
    total_cotizaciones = float(cotizaciones["total"] or 0)
    aprobadas = float(cotizaciones["aprobadas"] or 0)
    ratio = (aprobadas / total_cotizaciones) * 100 if total_cotizaciones > 0 else 0
    return {
        "total_ventas": float(ventas["total_ventas"] or 0),
        "ventas_registradas": float(ventas["ventas_registradas"] or 0),
        "total_cotizaciones": total_cotizaciones,
        "monto_cotizado": float(cotizaciones["monto"] or 0),
        "ratio_aprobacion": ratio,
    }



def _render_header_metrics(df: pd.DataFrame) -> None:
    activos = df[~df["etapa"].isin(["Ganado", "Perdido"])] if not df.empty else df
    valor_pipeline = float(activos["valor_estimado_usd"].fillna(0).sum()) if not activos.empty else 0.0
    weighted_pipeline = float(
        (activos["valor_estimado_usd"].fillna(0) * activos["probabilidad_pct"].fillna(0) / 100).sum()
    ) if not activos.empty else 0.0
    ganados = int((df["etapa"] == "Ganado").sum()) if not df.empty else 0
    perdidos = int((df["etapa"] == "Perdido").sum()) if not df.empty else 0
    win_rate = (ganados / (ganados + perdidos) * 100) if ganados + perdidos else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Leads activos", int(len(activos)))
    m2.metric("Pipeline estimado", f"$ {valor_pipeline:,.2f}")
    m3.metric("Pipeline ponderado", f"$ {weighted_pipeline:,.2f}")
    m4.metric("Win rate", f"{win_rate:.1f}%")



def _render_pipeline_tab(df: pd.DataFrame) -> None:
    st.markdown("### Embudo comercial")
    if df.empty:
        st.info("Aún no hay leads. Registra el primero en la pestaña **Leads**.")
        return

    ordered = pd.Categorical(df["etapa"], categories=ETAPAS_CRM, ordered=True)
    stage_df = (
        df.assign(etapa_orden=ordered)
        .groupby("etapa", as_index=False)
        .agg(leads=("id", "count"), valor=("valor_estimado_usd", "sum"))
    )
    stage_df["etapa"] = pd.Categorical(stage_df["etapa"], categories=ETAPAS_CRM, ordered=True)
    stage_df = stage_df.sort_values("etapa")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.funnel(stage_df, y="etapa", x="leads", title="Leads por etapa")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig_valor = px.bar(stage_df, x="etapa", y="valor", color="etapa", title="Valor estimado por etapa")
        st.plotly_chart(fig_valor, use_container_width=True)

    st.dataframe(
        df[["fecha", "nombre", "canal", "cliente", "etapa", "valor_estimado_usd", "probabilidad_pct", "proximo_contacto"]],
        use_container_width=True,
        hide_index=True,
    )



def _render_leads_tab(usuario: str, df: pd.DataFrame) -> None:
    st.markdown("### Gestión de leads")

    with st.form("crm_new_lead"):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Lead / empresa")
        canal = c2.selectbox("Canal", ["WhatsApp", "Instagram", "Web", "Referido", "Llamada", "Otro"])
        etapa = c3.selectbox("Etapa inicial", ETAPAS_CRM)

        c4, c5, c6 = st.columns(3)
        valor_estimado = c4.number_input("Valor estimado (USD)", min_value=0.0, step=10.0)
        probabilidad = c5.slider("Probabilidad (%)", min_value=0, max_value=100, value=20)
        proximo_contacto = c6.text_input("Próximo contacto (YYYY-MM-DD)")

        notas = st.text_area("Notas")
        submit = st.form_submit_button("Guardar lead")

    if submit:
        try:
            lead_name = require_text(nombre, "Lead")
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO crm_leads
                    (usuario, nombre, canal, etapa, valor_estimado_usd, probabilidad_pct, proximo_contacto, notas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usuario,
                        lead_name,
                        canal,
                        etapa,
                        float(valor_estimado),
                        int(probabilidad),
                        clean_text(proximo_contacto),
                        clean_text(notas),
                    ),
                )
            st.success("Lead registrado")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("No se pudo guardar el lead")
            st.exception(exc)

    if df.empty:
        return

    st.markdown("### Actualización rápida")
    ids = df[["id", "nombre"]]
    lead_id = st.selectbox(
        "Lead",
        ids["id"],
        format_func=lambda x: ids.loc[ids["id"] == x, "nombre"].iloc[0],
    )
    row = df[df["id"] == lead_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    new_etapa = c1.selectbox("Mover a etapa", ETAPAS_CRM, index=ETAPAS_CRM.index(str(row["etapa"])))
    new_prob = c2.slider("Probabilidad", 0, 100, int(row.get("probabilidad_pct") or 0), key="crm_prob_update")
    new_next = c3.text_input("Próximo contacto", str(row.get("proximo_contacto") or ""), key="crm_next_update")

    if st.button("Actualizar lead", key="crm_update_lead"):
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE crm_leads
                SET etapa=?, probabilidad_pct=?, proximo_contacto=?, actualizado_en=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (new_etapa, int(new_prob), clean_text(new_next), int(lead_id)),
            )
        st.success("Lead actualizado")
        st.rerun()



def _render_activity_tab(usuario: str, df: pd.DataFrame) -> None:
    st.markdown("### Seguimiento y próxima acción")
    if df.empty:
        st.info("Primero crea un lead para registrar actividad.")
        return

    ids = df[["id", "nombre"]]
    with st.form("crm_activity"):
        lead_id = st.selectbox(
            "Lead",
            ids["id"],
            format_func=lambda x: ids.loc[ids["id"] == x, "nombre"].iloc[0],
            key="crm_activity_lead",
        )
        c1, c2 = st.columns(2)
        tipo = c1.selectbox("Tipo", ["Llamada", "WhatsApp", "Email", "Reunión", "Cotización", "Otro"])
        resultado = c2.selectbox("Resultado", ["Pendiente", "Interesado", "Sin respuesta", "Negociando", "Cerrado ganado", "Cerrado perdido"])
        detalle = st.text_area("Detalle")
        proxima_accion = st.text_input("Próxima acción (YYYY-MM-DD)")
        save = st.form_submit_button("Registrar interacción")

    if save:
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO crm_interacciones (lead_id, usuario, tipo, resultado, detalle, proxima_accion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(lead_id), usuario, tipo, resultado, clean_text(detalle), clean_text(proxima_accion)),
            )
        st.success("Interacción registrada")
        st.rerun()

    interactions = _load_recent_interactions()
    if interactions.empty:
        st.caption("Sin interacciones aún.")
        return
    st.dataframe(interactions, use_container_width=True, hide_index=True)



def render_crm(usuario: str) -> None:
    st.subheader("🤝 CRM Next Level")
    st.caption(f"Pipeline comercial independiente · Usuario: {usuario}")

    df = _load_pipeline()
    _render_header_metrics(df)

    overview = _load_commercial_overview()
    c1, c2, c3 = st.columns(3)
    c1.metric("Cotizaciones", int(overview["total_cotizaciones"]))
    c2.metric("Aprobación cotizaciones", f"{overview['ratio_aprobacion']:.1f}%")
    c3.metric("Ventas históricas", f"$ {overview['total_ventas']:,.2f}")

    tabs = st.tabs(["📈 Pipeline", "🧲 Leads", "🗂️ Actividad"])
    with tabs[0]:
        _render_pipeline_tab(df)
    with tabs[1]:
        _render_leads_tab(usuario, df)
    with tabs[2]:
        _render_activity_tab(usuario, df)

    st.caption(f"Última actualización: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
