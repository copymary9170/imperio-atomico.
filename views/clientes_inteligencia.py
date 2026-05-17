from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _load_customer_intelligence() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "clientes"):
            return pd.DataFrame()
        ventas_join = ""
        ventas_fields = "0 AS operaciones, 0 AS total_ventas_usd, NULL AS ultima_compra"
        if _table_exists(conn, "ventas"):
            ventas_cols = _columns(conn, "ventas")
            total_col = "total_usd" if "total_usd" in ventas_cols else "total" if "total" in ventas_cols else None
            fecha_col = "fecha" if "fecha" in ventas_cols else None
            if total_col and fecha_col and "cliente_id" in ventas_cols:
                ventas_join = f"""
                LEFT JOIN (
                    SELECT cliente_id,
                           COUNT(*) AS operaciones,
                           COALESCE(SUM({total_col}), 0) AS total_ventas_usd,
                           MAX({fecha_col}) AS ultima_compra
                    FROM ventas
                    WHERE COALESCE(estado,'') NOT IN ('anulada','cancelada')
                    GROUP BY cliente_id
                ) v ON v.cliente_id = c.id
                """
                ventas_fields = "COALESCE(v.operaciones,0) AS operaciones, COALESCE(v.total_ventas_usd,0) AS total_ventas_usd, COALESCE(v.ultima_compra,c.fecha) AS ultima_compra"

        cxc_join = ""
        cxc_fields = "0 AS deuda_usd, 0 AS cuentas_vencidas"
        if _table_exists(conn, "cuentas_por_cobrar"):
            cxc_cols = _columns(conn, "cuentas_por_cobrar")
            if {"cliente_id", "saldo_usd", "estado"}.issubset(cxc_cols):
                cxc_join = """
                LEFT JOIN (
                    SELECT cliente_id,
                           COALESCE(SUM(saldo_usd),0) AS deuda_usd,
                           SUM(CASE WHEN estado='vencida' THEN 1 ELSE 0 END) AS cuentas_vencidas
                    FROM cuentas_por_cobrar
                    WHERE estado IN ('pendiente','parcial','vencida','incobrable')
                    GROUP BY cliente_id
                ) cx ON cx.cliente_id = c.id
                """
                cxc_fields = "COALESCE(cx.deuda_usd,0) AS deuda_usd, COALESCE(cx.cuentas_vencidas,0) AS cuentas_vencidas"

        return pd.read_sql_query(
            f"""
            SELECT c.id,
                   c.fecha,
                   c.nombre,
                   COALESCE(c.telefono,'') AS whatsapp,
                   COALESCE(c.email,'') AS email,
                   COALESCE(c.categoria,'General') AS categoria,
                   COALESCE(c.limite_credito_usd,0) AS limite_credito_usd,
                   {ventas_fields},
                   {cxc_fields}
            FROM clientes c
            {ventas_join}
            {cxc_join}
            WHERE COALESCE(c.estado,'activo')='activo'
            ORDER BY total_ventas_usd DESC, operaciones DESC
            """,
            conn,
        )


def _clasificar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["ultima_compra"] = pd.to_datetime(out["ultima_compra"], errors="coerce")
    out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce")
    now = pd.Timestamp(datetime.now())
    out["dias_sin_compra"] = (now - out["ultima_compra"].fillna(out["fecha"])).dt.days.fillna(999).astype(int)
    out["ticket_promedio_usd"] = out.apply(
        lambda r: float(r["total_ventas_usd"] or 0) / float(r["operaciones"] or 1) if float(r["operaciones"] or 0) > 0 else 0.0,
        axis=1,
    )
    out["uso_credito_pct"] = out.apply(
        lambda r: (float(r["deuda_usd"] or 0) / float(r["limite_credito_usd"] or 1)) * 100 if float(r["limite_credito_usd"] or 0) > 0 else 0.0,
        axis=1,
    )
    out["segmento_inteligente"] = "Nuevo / sin compra"
    out.loc[(out["operaciones"] > 0) & (out["dias_sin_compra"] <= 30), "segmento_inteligente"] = "Activo reciente"
    out.loc[(out["operaciones"] >= 3) & (out["dias_sin_compra"] <= 90), "segmento_inteligente"] = "Recurrente"
    out.loc[(out["total_ventas_usd"] >= out["total_ventas_usd"].quantile(0.8)) & (out["total_ventas_usd"] > 0), "segmento_inteligente"] = "Alto valor"
    out.loc[(out["operaciones"] > 0) & (out["dias_sin_compra"] > 90), "segmento_inteligente"] = "Dormido"
    out.loc[(out["deuda_usd"] > 0) & ((out["cuentas_vencidas"] > 0) | (out["uso_credito_pct"] >= 90)), "segmento_inteligente"] = "Riesgo cobranza"

    out["accion_recomendada"] = "Mantener seguimiento"
    out.loc[out["segmento_inteligente"].eq("Nuevo / sin compra"), "accion_recomendada"] = "Enviar oferta de primera compra"
    out.loc[out["segmento_inteligente"].eq("Activo reciente"), "accion_recomendada"] = "Ofrecer producto complementario"
    out.loc[out["segmento_inteligente"].eq("Recurrente"), "accion_recomendada"] = "Crear promoción de fidelización"
    out.loc[out["segmento_inteligente"].eq("Alto valor"), "accion_recomendada"] = "Atención VIP y preventa"
    out.loc[out["segmento_inteligente"].eq("Dormido"), "accion_recomendada"] = "Campaña de reactivación"
    out.loc[out["segmento_inteligente"].eq("Riesgo cobranza"), "accion_recomendada"] = "Gestionar cobranza antes de vender a crédito"
    return out


def render_clientes_inteligencia(usuario: str = "Sistema") -> None:
    st.subheader("🧠 Inteligencia de clientes")
    st.caption("Segmentación comercial, riesgo de cobranza, recurrencia y acciones recomendadas.")

    try:
        df = _clasificar(_load_customer_intelligence())
    except Exception as exc:
        st.error("No se pudo cargar inteligencia de clientes.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay clientes activos para analizar.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes activos", len(df))
    c2.metric("Ventas históricas", f"${float(df['total_ventas_usd'].sum()):,.2f}")
    c3.metric("Deuda activa", f"${float(df['deuda_usd'].sum()):,.2f}")
    c4.metric("Ticket promedio", f"${float(df['ticket_promedio_usd'].mean()):,.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Alto valor", int(df["segmento_inteligente"].eq("Alto valor").sum()))
    c6.metric("Recurrentes", int(df["segmento_inteligente"].eq("Recurrente").sum()))
    c7.metric("Dormidos", int(df["segmento_inteligente"].eq("Dormido").sum()))
    c8.metric("Riesgo cobranza", int(df["segmento_inteligente"].eq("Riesgo cobranza").sum()))

    st.divider()

    tab_seg, tab_riesgo, tab_reactivar, tab_top = st.tabs([
        "Segmentación",
        "Riesgo y crédito",
        "Reactivación",
        "Top clientes",
    ])

    with tab_seg:
        resumen = df.groupby("segmento_inteligente", as_index=False).agg(
            clientes=("id", "count"),
            ventas=("total_ventas_usd", "sum"),
            deuda=("deuda_usd", "sum"),
        )
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.bar_chart(resumen.set_index("segmento_inteligente")["clientes"])

    with tab_riesgo:
        riesgo = df[(df["deuda_usd"] > 0) | (df["uso_credito_pct"] >= 80) | (df["cuentas_vencidas"] > 0)].copy()
        if riesgo.empty:
            st.success("No hay clientes con riesgo de crédito detectado.")
        else:
            cols = ["id", "nombre", "categoria", "deuda_usd", "limite_credito_usd", "uso_credito_pct", "cuentas_vencidas", "accion_recomendada"]
            st.dataframe(riesgo[cols].sort_values("deuda_usd", ascending=False), use_container_width=True, hide_index=True)

    with tab_reactivar:
        dormidos = df[df["segmento_inteligente"].eq("Dormido")].copy()
        if dormidos.empty:
            st.success("No hay clientes dormidos con compras históricas.")
        else:
            cols = ["id", "nombre", "whatsapp", "email", "ultima_compra", "dias_sin_compra", "total_ventas_usd", "accion_recomendada"]
            st.dataframe(dormidos[cols].sort_values("dias_sin_compra", ascending=False), use_container_width=True, hide_index=True)

    with tab_top:
        top = df.sort_values("total_ventas_usd", ascending=False).head(20)
        cols = ["id", "nombre", "categoria", "operaciones", "total_ventas_usd", "ticket_promedio_usd", "ultima_compra", "segmento_inteligente", "accion_recomendada"]
        st.dataframe(top[cols], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📣 Acciones comerciales sugeridas")
    for accion, grupo in df.groupby("accion_recomendada"):
        st.write(f"- **{accion}:** {len(grupo)} cliente(s)")
