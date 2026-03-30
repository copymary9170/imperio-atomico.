from __future__ import annotations

from datetime import datetime, date

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

CANALES_CRM = (
    "WhatsApp",
    "Instagram",
    "Sitio web",
    "Referido",
    "Llamada",
    "Facebook",
    "Correo",
    "Otro",
)

TIPOS_INTERACCION = (
    "Llamada",
    "WhatsApp",
    "Correo",
    "Reunión",
    "Cotización",
    "Seguimiento",
    "Otro",
)

RESULTADOS_INTERACCION = (
    "Pendiente",
    "Interesado",
    "Sin respuesta",
    "Negociando",
    "Cerrado ganado",
    "Cerrado perdido",
)


# ============================================================
# TABLAS / SCHEMA
# ============================================================

def _ensure_columns(conn, table_name: str, columns: dict[str, str]) -> None:
    current_columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_ddl in columns.items():
        if column_name in current_columns:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")


def _ensure_crm_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                cliente_id INTEGER,
                nombre TEXT NOT NULL,
                canal TEXT,
                etapa TEXT NOT NULL DEFAULT 'Nuevo',
                valor_estimado_usd REAL DEFAULT 0,
                probabilidad_pct INTEGER DEFAULT 0,
                proximo_contacto TEXT,
                notas TEXT,
                motivo_perdida TEXT,
                estado TEXT NOT NULL DEFAULT 'activo',
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
            """
        )

        _ensure_columns(
            conn,
            "crm_leads",
            {
                "actualizado_en": "actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP",
                "usuario": "usuario TEXT",
                "cliente_id": "cliente_id INTEGER",
                "canal": "canal TEXT",
                "etapa": "etapa TEXT NOT NULL DEFAULT 'Nuevo'",
                "valor_estimado_usd": "valor_estimado_usd REAL DEFAULT 0",
                "probabilidad_pct": "probabilidad_pct INTEGER DEFAULT 0",
                "proximo_contacto": "proximo_contacto TEXT",
                "notas": "notas TEXT",
                "motivo_perdida": "motivo_perdida TEXT",
                "estado": "estado TEXT NOT NULL DEFAULT 'activo'",
            },
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_interacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lead_id INTEGER NOT NULL,
                usuario TEXT,
                tipo TEXT,
                resultado TEXT,
                detalle TEXT,
                proxima_accion TEXT,
                FOREIGN KEY (lead_id) REFERENCES crm_leads(id)
            )
            """
        )

        _ensure_columns(
            conn,
            "crm_interacciones",
            {
                "usuario": "usuario TEXT",
                "tipo": "tipo TEXT",
                "resultado": "resultado TEXT",
                "detalle": "detalle TEXT",
                "proxima_accion": "proxima_accion TEXT",
            },
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_leads_estado ON crm_leads(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_leads_etapa ON crm_leads(etapa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_leads_proximo_contacto ON crm_leads(proximo_contacto)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_interacciones_lead ON crm_interacciones(lead_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_interacciones_fecha ON crm_interacciones(fecha)")


# ============================================================
# CARGADORES
# ============================================================

def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn, table_name: str, column_name: str) -> bool:
    return any(
        row["name"] == column_name
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    )


def _load_pipeline() -> pd.DataFrame:
    _ensure_crm_tables()
    with db_transaction() as conn:
        clientes_table_exists = _table_exists(conn, "clientes") and _table_has_column(conn, "clientes", "nombre")
        cliente_projection = "COALESCE(c.nombre, '') AS cliente" if clientes_table_exists else "'' AS cliente"
        cliente_join = "LEFT JOIN clientes c ON c.id = l.cliente_id" if clientes_table_exists else ""
        df = pd.read_sql_query(
            f"""
            SELECT
                l.id,
                l.fecha,
                l.actualizado_en,
                l.nombre,
                l.canal,
                l.etapa,
                l.valor_estimado_usd,
                l.probabilidad_pct,
                l.proximo_contacto,
                l.notas,
                l.motivo_perdida,
                {cliente_projection}
            FROM crm_leads l
            {cliente_join}
            WHERE COALESCE(l.estado, 'activo') = 'activo'
            ORDER BY l.fecha DESC, l.id DESC
            """,
            conn,
        )

    if df.empty:
        return df

    df["valor_estimado_usd"] = pd.to_numeric(df["valor_estimado_usd"], errors="coerce").fillna(0.0)
    df["probabilidad_pct"] = pd.to_numeric(df["probabilidad_pct"], errors="coerce").fillna(0).astype(int)
    return df


def _load_recent_interactions(limit: int = 25) -> pd.DataFrame:
    _ensure_crm_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
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
            params=(int(limit),),
        )
    return df


def _load_interactions_by_lead(lead_id: int) -> pd.DataFrame:
    _ensure_crm_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                tipo,
                resultado,
                detalle,
                proxima_accion,
                usuario
            FROM crm_interacciones
            WHERE lead_id = ?
            ORDER BY fecha DESC, id DESC
            """,
            conn,
            params=(int(lead_id),),
        )
    return df


def _load_commercial_overview() -> dict[str, float]:
    with db_transaction() as conn:
        ventas = conn.execute(
            """
            SELECT COALESCE(SUM(total_usd), 0) AS total_ventas,
                   COUNT(*) AS ventas_registradas
            FROM ventas
            WHERE LOWER(COALESCE(estado, '')) = 'registrada'
            """
        ).fetchone()

        cotizaciones = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(precio_final_usd), 0) AS monto,
                COALESCE(SUM(CASE
                    WHEN LOWER(COALESCE(estado, '')) IN ('aprobada', 'aprobado', 'ganada')
                    THEN 1 ELSE 0 END), 0) AS aprobadas
            FROM cotizaciones
            """
        ).fetchone()

    total_cotizaciones = float(cotizaciones["total"] or 0)
    aprobadas = float(cotizaciones["aprobadas"] or 0)
    ratio = (aprobadas / total_cotizaciones) * 100 if total_cotizaciones > 0 else 0.0

    return {
        "total_ventas": float(ventas["total_ventas"] or 0),
        "ventas_registradas": float(ventas["ventas_registradas"] or 0),
        "total_cotizaciones": total_cotizaciones,
        "monto_cotizado": float(cotizaciones["monto"] or 0),
        "ratio_aprobacion": ratio,
    }


# ============================================================
# AYUDANTES
# ============================================================

def _safe_date_text(value: str) -> str:
    txt = clean_text(value)
    if not txt:
        return ""
    try:
        return pd.to_datetime(txt).date().isoformat()
    except Exception:
        return ""


def _filter_pipeline(df: pd.DataFrame, search: str, etapa: str, canal: str) -> pd.DataFrame:
    if df.empty:
        return df

    view = df.copy()

    if search:
        txt = clean_text(search)
        mask = (
            view["nombre"].astype(str).str.contains(txt, case=False, na=False)
            | view["cliente"].astype(str).str.contains(txt, case=False, na=False)
            | view["canal"].astype(str).str.contains(txt, case=False, na=False)
            | view["notas"].astype(str).str.contains(txt, case=False, na=False)
        )
        view = view[mask]

    if etapa != "Todas":
        view = view[view["etapa"].astype(str) == etapa]

    if canal != "Todos":
        view = view[view["canal"].astype(str) == canal]

    return view


# ============================================================
# MÉTRICAS
# ============================================================

def _render_header_metrics(df: pd.DataFrame) -> None:
    activos = df[~df["etapa"].isin(["Ganado", "Perdido"])] if not df.empty else df
    valor_pipeline = float(activos["valor_estimado_usd"].fillna(0).sum()) if not activos.empty else 0.0
    pipeline_ponderado = float(
        (activos["valor_estimado_usd"].fillna(0) * activos["probabilidad_pct"].fillna(0) / 100).sum()
    ) if not activos.empty else 0.0
    ganados = int((df["etapa"] == "Ganado").sum()) if not df.empty else 0
    perdidos = int((df["etapa"] == "Perdido").sum()) if not df.empty else 0
    tasa_cierre = (ganados / (ganados + perdidos) * 100) if (ganados + perdidos) else 0.0

    hoy = date.today().isoformat()
    seguimientos_vencidos = int(
        ((df["proximo_contacto"].fillna("").astype(str) != "") & (df["proximo_contacto"].astype(str) <= hoy)).sum()
    ) if not df.empty else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Leads activos", int(len(activos)))
    m2.metric("Valor estimado", f"$ {valor_pipeline:,.2f}")
    m3.metric("Valor ponderado", f"$ {pipeline_ponderado:,.2f}")
    m4.metric("Tasa de cierre", f"{tasa_cierre:.1f}%")
    m5.metric("Seguimientos vencidos", seguimientos_vencidos)


# ============================================================
# TAB: EMBUDO
# ============================================================

def _render_pipeline_tab(df: pd.DataFrame) -> None:
    st.markdown("### Embudo comercial")

    if df.empty:
        st.info("Aún no hay oportunidades. Registra la primera en la pestaña **Leads**.")
        return

    f1, f2, f3 = st.columns([2, 1, 1])
    buscar = f1.text_input("Buscar lead / cliente / notas", key="crm_buscar_pipeline")
    etapa = f2.selectbox("Etapa", ["Todas"] + list(ETAPAS_CRM), key="crm_etapa_pipeline")
    canal = f3.selectbox("Canal", ["Todos"] + list(CANALES_CRM), key="crm_canal_pipeline")

    view = _filter_pipeline(df, buscar, etapa, canal)

    ordered = pd.Categorical(view["etapa"], categories=ETAPAS_CRM, ordered=True)
    stage_df = (
        view.assign(etapa_orden=ordered)
        .groupby("etapa", as_index=False)
        .agg(cantidad=("id", "count"), valor=("valor_estimado_usd", "sum"))
    )
    stage_df["etapa"] = pd.Categorical(stage_df["etapa"], categories=ETAPAS_CRM, ordered=True)
    stage_df = stage_df.sort_values("etapa")

    c1, c2 = st.columns(2)
    with c1:
        if not stage_df.empty:
            fig = px.funnel(stage_df, y="etapa", x="cantidad", title="Oportunidades por etapa")
            fig.update_layout(xaxis_title="Cantidad", yaxis_title="Etapa")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if not stage_df.empty:
            fig_valor = px.bar(stage_df, x="etapa", y="valor", color="etapa", title="Valor estimado por etapa")
            fig_valor.update_layout(xaxis_title="Etapa", yaxis_title="Valor estimado USD")
            st.plotly_chart(fig_valor, use_container_width=True)

    st.dataframe(
        view[
            [
                "fecha",
                "nombre",
                "canal",
                "cliente",
                "etapa",
                "valor_estimado_usd",
                "probabilidad_pct",
                "proximo_contacto",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha": "Fecha",
            "nombre": "Lead",
            "canal": "Canal",
            "cliente": "Cliente",
            "etapa": "Etapa",
            "valor_estimado_usd": st.column_config.NumberColumn("Valor estimado", format="%.2f"),
            "probabilidad_pct": st.column_config.NumberColumn("Probabilidad %", format="%d"),
            "proximo_contacto": "Próximo contacto",
        },
    )


# ============================================================
# TAB: LEADS
# ============================================================

def _render_leads_tab(usuario: str, df: pd.DataFrame) -> None:
    st.markdown("### Gestión de leads")

    with st.form("crm_new_lead"):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Nombre del lead / empresa")
        canal = c2.selectbox("Canal de entrada", CANALES_CRM)
        etapa = c3.selectbox("Etapa inicial", ETAPAS_CRM)

        c4, c5, c6 = st.columns(3)
        valor_estimado = c4.number_input("Valor estimado (USD)", min_value=0.0, step=10.0, value=0.0)
        probabilidad = c5.slider("Probabilidad de cierre (%)", min_value=0, max_value=100, value=20)
        proximo_contacto = c6.text_input("Próximo contacto (YYYY-MM-DD)")

        notas = st.text_area("Notas")
        submit = st.form_submit_button("Guardar lead", use_container_width=True)

    if submit:
        try:
            lead_name = require_text(nombre, "Lead")
            prox = _safe_date_text(proximo_contacto)

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
                        prox,
                        clean_text(notas),
                    ),
                )

            st.success("Lead registrado correctamente.")
            st.rerun()

        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("No se pudo guardar el lead.")
            st.exception(exc)

    if df.empty:
        return

    st.divider()
    st.markdown("### Edición rápida")

    ids = df[["id", "nombre"]]
    lead_id = st.selectbox(
        "Selecciona un lead",
        ids["id"],
        format_func=lambda x: ids.loc[ids["id"] == x, "nombre"].iloc[0],
        key="crm_select_update",
    )
    row = df[df["id"] == lead_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    new_etapa = c1.selectbox(
        "Mover a etapa",
        ETAPAS_CRM,
        index=ETAPAS_CRM.index(str(row["etapa"])),
        key="crm_new_etapa",
    )
    new_prob = c2.slider(
        "Probabilidad de cierre",
        0,
        100,
        int(row.get("probabilidad_pct") or 0),
        key="crm_prob_update",
    )
    new_next = c3.text_input(
        "Próximo contacto",
        str(row.get("proximo_contacto") or ""),
        key="crm_next_update",
    )

    c4, c5 = st.columns(2)
    new_valor = c4.number_input(
        "Valor estimado USD",
        min_value=0.0,
        value=float(row.get("valor_estimado_usd") or 0.0),
        step=10.0,
        key="crm_valor_update",
    )
    motivo_perdida = c5.text_input(
        "Motivo de pérdida",
        value=str(row.get("motivo_perdida") or ""),
        key="crm_motivo_perdida",
    )

    notas_edit = st.text_area(
        "Notas del lead",
        value=str(row.get("notas") or ""),
        key="crm_notas_update",
    )

    if st.button("Actualizar lead", key="crm_update_lead", use_container_width=True):
        with db_transaction() as conn:
            conn.execute(
                """
                UPDATE crm_leads
                SET etapa=?,
                    probabilidad_pct=?,
                    proximo_contacto=?,
                    valor_estimado_usd=?,
                    motivo_perdida=?,
                    notas=?,
                    actualizado_en=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    new_etapa,
                    int(new_prob),
                    _safe_date_text(new_next),
                    float(new_valor),
                    clean_text(motivo_perdida),
                    clean_text(notas_edit),
                    int(lead_id),
                ),
            )
        st.success("Lead actualizado correctamente.")
        st.rerun()

    st.divider()
    st.markdown("### Historial del lead seleccionado")
    df_hist = _load_interactions_by_lead(int(lead_id))
    if df_hist.empty:
        st.caption("Este lead aún no tiene interacciones registradas.")
    else:
        st.dataframe(
            df_hist,
            use_container_width=True,
            hide_index=True,
            column_config={
                "fecha": "Fecha",
                "tipo": "Tipo",
                "resultado": "Resultado",
                "detalle": "Detalle",
                "proxima_accion": "Próxima acción",
                "usuario": "Usuario",
            },
        )


# ============================================================
# TAB: ACTIVIDAD
# ============================================================

def _render_activity_tab(usuario: str, df: pd.DataFrame) -> None:
    st.markdown("### Seguimiento y próximas acciones")

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
        tipo = c1.selectbox("Tipo de interacción", TIPOS_INTERACCION)
        resultado = c2.selectbox("Resultado", RESULTADOS_INTERACCION)

        detalle = st.text_area("Detalle")
        proxima_accion = st.text_input("Próxima acción (YYYY-MM-DD)")
        save = st.form_submit_button("Registrar interacción", use_container_width=True)

    if save:
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO crm_interacciones (lead_id, usuario, tipo, resultado, detalle, proxima_accion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(lead_id),
                    usuario,
                    tipo,
                    resultado,
                    clean_text(detalle),
                    _safe_date_text(proxima_accion),
                ),
            )

            if resultado == "Cerrado ganado":
                conn.execute(
                    """
                    UPDATE crm_leads
                    SET etapa='Ganado', actualizado_en=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (int(lead_id),),
                )
            elif resultado == "Cerrado perdido":
                conn.execute(
                    """
                    UPDATE crm_leads
                    SET etapa='Perdido', actualizado_en=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (int(lead_id),),
                )
            elif _safe_date_text(proxima_accion):
                conn.execute(
                    """
                    UPDATE crm_leads
                    SET proximo_contacto=?, actualizado_en=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (_safe_date_text(proxima_accion), int(lead_id)),
                )

        st.success("Interacción registrada correctamente.")
        st.rerun()

    interactions = _load_recent_interactions()
    if interactions.empty:
        st.caption("Aún no hay interacciones registradas.")
        return

    st.dataframe(
        interactions,
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha": "Fecha",
            "lead": "Lead",
            "tipo": "Tipo",
            "resultado": "Resultado",
            "detalle": "Detalle",
            "proxima_accion": "Próxima acción",
            "usuario": "Usuario",
        },
    )


# ============================================================
# TAB: SEGUIMIENTOS
# ============================================================

def _render_followup_alerts(df: pd.DataFrame) -> None:
    st.markdown("### Agenda de seguimientos")

    if df.empty:
        st.info("No hay leads cargados.")
        return

    view = df.copy()
    view["proximo_contacto"] = view["proximo_contacto"].fillna("").astype(str)
    view = view[view["proximo_contacto"] != ""].copy()

    if view.empty:
        st.caption("No hay seguimientos programados.")
        return

    hoy = date.today().isoformat()
    view["estado_seguimiento"] = view["proximo_contacto"].apply(
        lambda x: "Vencido" if x < hoy else "Hoy" if x == hoy else "Próximo"
    )

    st.dataframe(
        view[["nombre", "canal", "etapa", "valor_estimado_usd", "proximo_contacto", "estado_seguimiento"]]
        .sort_values(["proximo_contacto", "nombre"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "nombre": "Lead",
            "canal": "Canal",
            "etapa": "Etapa",
            "valor_estimado_usd": st.column_config.NumberColumn("Valor estimado", format="%.2f"),
            "proximo_contacto": "Próximo contacto",
            "estado_seguimiento": "Estado",
        },
    )


# ============================================================
# UI PRINCIPAL
# ============================================================

def render_crm(usuario: str) -> None:
    _ensure_crm_tables()

    st.subheader("🤝 CRM")
    st.caption(f"Gestión comercial y seguimiento de oportunidades · Usuario: {usuario}")

    df = _load_pipeline()
    _render_header_metrics(df)

    overview = _load_commercial_overview()
    c1, c2, c3 = st.columns(3)
    c1.metric("Cotizaciones registradas", int(overview["total_cotizaciones"]))
    c2.metric("Tasa de aprobación", f"{overview['ratio_aprobacion']:.1f}%")
    c3.metric("Ventas históricas", f"$ {overview['total_ventas']:,.2f}")

    tabs = st.tabs(["📈 Embudo", "🧲 Leads", "🗂️ Actividad", "⏰ Seguimientos"])

    with tabs[0]:
        _render_pipeline_tab(df)

    with tabs[1]:
        _render_leads_tab(usuario, df)

    with tabs[2]:
        _render_activity_tab(usuario, df)

    with tabs[3]:
        _render_followup_alerts(df)

    st.caption(f"Última actualización: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")





















