from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

PLATAFORMAS = ["Instagram", "Facebook", "WhatsApp", "TikTok", "Google", "Promociones tienda", "Email", "Otro"]
ESTADOS_CAMPANA = ["Borrador", "Activa", "Pausada", "Finalizada", "Cancelada"]
ESTADOS_PUBLICACION = ["Idea", "Pendiente diseño", "Programada", "Publicada", "Pausada", "Vencida", "Cancelada"]
OBJETIVOS = ["Ventas", "Leads", "Reactivación", "Fidelización", "Inventario", "Marca", "Temporada", "Otro"]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marketing_campanas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                nombre TEXT NOT NULL,
                objetivo TEXT NOT NULL DEFAULT 'Ventas',
                canal_principal TEXT NOT NULL DEFAULT 'Instagram',
                fecha_inicio TEXT,
                fecha_fin TEXT,
                presupuesto_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Borrador',
                segmento_objetivo TEXT,
                responsable TEXT,
                ventas_atribuidas_usd REAL NOT NULL DEFAULT 0,
                leads_generados INTEGER NOT NULL DEFAULT 0,
                roi_pct REAL NOT NULL DEFAULT 0,
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marketing_publicaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                campana_id INTEGER,
                plataforma TEXT NOT NULL DEFAULT 'Instagram',
                fecha_programada TEXT,
                copy TEXT NOT NULL,
                diseno_requerido TEXT,
                estado TEXT NOT NULL DEFAULT 'Idea',
                responsable TEXT,
                link_publicacion TEXT,
                alcance INTEGER NOT NULL DEFAULT 0,
                interacciones INTEGER NOT NULL DEFAULT 0,
                leads_generados INTEGER NOT NULL DEFAULT 0,
                ventas_generadas_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (campana_id) REFERENCES marketing_campanas(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_marketing_campanas_estado ON marketing_campanas(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_marketing_publicaciones_fecha ON marketing_publicaciones(fecha_programada)")


def _read_table(table: str, order: str = "id DESC", limit: int = 1000) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return pd.DataFrame()
        try:
            return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY {order} LIMIT {int(limit)}", conn)
        except Exception:
            return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {int(limit)}", conn)


def _insert(table: str, data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cols = _columns(conn, table)
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        placeholders = ",".join(["?"] * len(keys))
        cur = conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})", [payload[k] for k in keys])
        return int(cur.lastrowid)


def _update(table: str, row_id: int, data: dict[str, Any]) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        cols = _columns(conn, table)
        payload = {k: v for k, v in data.items() if k in cols}
        if not payload:
            return
        set_clause = ", ".join([f"{k}=?" for k in payload])
        conn.execute(f"UPDATE {table} SET {set_clause} WHERE id=?", [payload[k] for k in payload] + [int(row_id)])


def _safe_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _load_segments() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "clientes"):
                return pd.DataFrame()
            clientes = pd.read_sql_query("SELECT * FROM clientes", conn)
            ventas = pd.read_sql_query("SELECT cliente_id, COUNT(*) AS compras, SUM(total_usd) AS ventas_usd, MAX(fecha) AS ultima_compra FROM ventas GROUP BY cliente_id", conn) if _table_exists(conn, "ventas") else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
    if clientes.empty:
        return pd.DataFrame()
    if not ventas.empty and "id" in clientes.columns:
        df = clientes.merge(ventas, left_on="id", right_on="cliente_id", how="left")
    else:
        df = clientes.copy()
        df["compras"] = 0
        df["ventas_usd"] = 0
        df["ultima_compra"] = None
    df["compras"] = pd.to_numeric(df.get("compras", 0), errors="coerce").fillna(0)
    df["ventas_usd"] = pd.to_numeric(df.get("ventas_usd", 0), errors="coerce").fillna(0)
    ultima = pd.to_datetime(df.get("ultima_compra"), errors="coerce")
    hoy = pd.Timestamp.today()
    df["dias_sin_compra"] = (hoy - ultima).dt.days.fillna(9999).astype(int)
    df["segmento_marketing"] = "General"
    df.loc[df["ventas_usd"] >= 300, "segmento_marketing"] = "VIP / Alto valor"
    df.loc[(df["compras"] >= 3) & (df["ventas_usd"] < 300), "segmento_marketing"] = "Recurrente"
    df.loc[df["dias_sin_compra"].between(45, 9998), "segmento_marketing"] = "Dormido"
    df.loc[df["compras"].eq(0), "segmento_marketing"] = "Sin compra"
    return df


def _render_resumen() -> None:
    st.subheader("📊 Resumen de marketing")
    campanas = _read_table("marketing_campanas")
    pubs = _read_table("marketing_publicaciones")
    activas = campanas[campanas["estado"].eq("Activa")] if not campanas.empty and "estado" in campanas.columns else pd.DataFrame()
    pendientes = pubs[pubs["estado"].isin(["Idea", "Pendiente diseño", "Programada"])] if not pubs.empty and "estado" in pubs.columns else pd.DataFrame()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Campañas", len(campanas))
    c2.metric("Activas", len(activas))
    c3.metric("Publicaciones pendientes", len(pendientes))
    c4.metric("Ventas atribuidas", f"${_safe_sum(campanas, 'ventas_atribuidas_usd') + _safe_sum(pubs, 'ventas_generadas_usd'):,.2f}")
    if not campanas.empty:
        st.markdown("#### Campañas recientes")
        st.dataframe(campanas.head(10), use_container_width=True, hide_index=True)
    if not pubs.empty:
        st.markdown("#### Próximas publicaciones")
        vista = pubs.copy()
        vista["fecha_programada_dt"] = pd.to_datetime(vista.get("fecha_programada"), errors="coerce")
        vista = vista.sort_values("fecha_programada_dt", na_position="last").drop(columns=["fecha_programada_dt"])
        st.dataframe(vista.head(10), use_container_width=True, hide_index=True)


def _render_campanas(usuario: str) -> None:
    st.subheader("🎯 Campañas y promociones")
    st.caption("Promociones, descuentos, combos, objetivos comerciales y resultados por campaña.")
    with st.form("marketing_form_campana"):
        a, b, c = st.columns(3)
        nombre = a.text_input("Nombre campaña")
        objetivo = b.selectbox("Objetivo", OBJETIVOS)
        canal = c.selectbox("Canal principal", PLATAFORMAS)
        d, e, f = st.columns(3)
        fecha_inicio = d.date_input("Fecha inicio", value=date.today())
        fecha_fin = e.date_input("Fecha fin", value=date.today() + timedelta(days=7))
        presupuesto = f.number_input("Presupuesto USD", min_value=0.0, value=0.0, step=1.0)
        g, h, i = st.columns(3)
        estado = g.selectbox("Estado", ESTADOS_CAMPANA)
        segmento = h.text_input("Segmento objetivo", placeholder="VIP, dormidos, Instagram, estudiantes...")
        responsable = i.text_input("Responsable", value=usuario)
        observaciones = st.text_area("Observaciones / oferta / condiciones")
        guardar = st.form_submit_button("Guardar campaña", type="primary")
    if guardar:
        if not nombre.strip():
            st.error("El nombre de la campaña es obligatorio.")
        else:
            cid = _insert("marketing_campanas", {"nombre": nombre.strip(), "objetivo": objetivo, "canal_principal": canal, "fecha_inicio": fecha_inicio.isoformat(), "fecha_fin": fecha_fin.isoformat(), "presupuesto_usd": float(presupuesto), "estado": estado, "segmento_objetivo": segmento.strip(), "responsable": responsable.strip() or usuario, "observaciones": observaciones.strip()})
            st.success(f"Campaña #{cid} guardada.")
            st.rerun()
    campanas = _read_table("marketing_campanas")
    if campanas.empty:
        st.info("No hay campañas registradas.")
    else:
        st.dataframe(campanas, use_container_width=True, hide_index=True)
        with st.expander("Actualizar resultados de campaña"):
            ids = campanas["id"].astype(int).tolist()
            campana_id = st.selectbox("Campaña", ids, format_func=lambda x: f"#{x} · {campanas.loc[campanas['id'].eq(x), 'nombre'].iloc[0]}", key="marketing_result_campana")
            r1, r2, r3 = st.columns(3)
            ventas = r1.number_input("Ventas atribuidas USD", min_value=0.0, value=0.0, step=1.0, key="marketing_camp_ventas")
            leads = r2.number_input("Leads generados", min_value=0, value=0, step=1, key="marketing_camp_leads")
            nuevo_estado = r3.selectbox("Estado", ESTADOS_CAMPANA, key="marketing_camp_estado_update")
            if st.button("Actualizar campaña", use_container_width=True, key="marketing_update_camp"):
                presupuesto_actual = float(campanas.loc[campanas["id"].eq(campana_id), "presupuesto_usd"].iloc[0] or 0)
                roi = ((float(ventas) - presupuesto_actual) / presupuesto_actual * 100) if presupuesto_actual > 0 else 0.0
                _update("marketing_campanas", int(campana_id), {"ventas_atribuidas_usd": float(ventas), "leads_generados": int(leads), "roi_pct": roi, "estado": nuevo_estado})
                st.success("Campaña actualizada.")
                st.rerun()


def _render_publicaciones(usuario: str) -> None:
    st.subheader("📅 Calendario de publicaciones")
    campanas = _read_table("marketing_campanas")
    campana_options = [0] + (campanas["id"].astype(int).tolist() if not campanas.empty else [])
    with st.form("marketing_form_publicacion"):
        a, b, c = st.columns(3)
        campana_id = a.selectbox("Campaña", campana_options, format_func=lambda x: "Sin campaña" if x == 0 else f"#{x} · {campanas.loc[campanas['id'].eq(x), 'nombre'].iloc[0]}")
        plataforma = b.selectbox("Plataforma", PLATAFORMAS)
        fecha_prog = c.date_input("Fecha programada", value=date.today())
        copy = st.text_area("Copy / texto de publicación", placeholder="Escribe el texto o idea principal...")
        d, e, f = st.columns(3)
        diseno = d.text_input("Diseño requerido", placeholder="Post, historia, reel, flyer...")
        estado = e.selectbox("Estado", ESTADOS_PUBLICACION)
        responsable = f.text_input("Responsable", value=usuario)
        observaciones = st.text_area("Observaciones", key="marketing_pub_obs")
        guardar = st.form_submit_button("Guardar publicación", type="primary")
    if guardar:
        if not copy.strip():
            st.error("El copy o idea de publicación es obligatorio.")
        else:
            pid = _insert("marketing_publicaciones", {"campana_id": int(campana_id) or None, "plataforma": plataforma, "fecha_programada": fecha_prog.isoformat(), "copy": copy.strip(), "diseno_requerido": diseno.strip(), "estado": estado, "responsable": responsable.strip() or usuario, "observaciones": observaciones.strip()})
            st.success(f"Publicación #{pid} guardada.")
            st.rerun()
    pubs = _read_table("marketing_publicaciones", "fecha_programada ASC, id DESC")
    if pubs.empty:
        st.info("No hay publicaciones registradas.")
    else:
        f1, f2 = st.columns(2)
        estado_filter = f1.multiselect("Filtrar estado", ESTADOS_PUBLICACION, default=ESTADOS_PUBLICACION, key="marketing_pub_estado_filter")
        plataforma_filter = f2.multiselect("Filtrar plataforma", PLATAFORMAS, default=PLATAFORMAS, key="marketing_pub_plat_filter")
        vista = pubs[pubs["estado"].isin(estado_filter) & pubs["plataforma"].isin(plataforma_filter)]
        st.dataframe(vista, use_container_width=True, hide_index=True)
        with st.expander("Actualizar resultados de publicación"):
            ids = pubs["id"].astype(int).tolist()
            pub_id = st.selectbox("Publicación", ids, format_func=lambda x: f"#{x} · {pubs.loc[pubs['id'].eq(x), 'plataforma'].iloc[0]} · {pubs.loc[pubs['id'].eq(x), 'estado'].iloc[0]}", key="marketing_pub_update_id")
            r1, r2, r3, r4 = st.columns(4)
            alcance = r1.number_input("Alcance", min_value=0, value=0, step=1, key="marketing_pub_alcance")
            interacciones = r2.number_input("Interacciones", min_value=0, value=0, step=1, key="marketing_pub_interacciones")
            leads = r3.number_input("Leads", min_value=0, value=0, step=1, key="marketing_pub_leads")
            ventas = r4.number_input("Ventas USD", min_value=0.0, value=0.0, step=1.0, key="marketing_pub_ventas")
            link = st.text_input("Link publicación", key="marketing_pub_link")
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_PUBLICACION, key="marketing_pub_estado_update")
            if st.button("Actualizar publicación", use_container_width=True, key="marketing_update_pub"):
                _update("marketing_publicaciones", int(pub_id), {"alcance": int(alcance), "interacciones": int(interacciones), "leads_generados": int(leads), "ventas_generadas_usd": float(ventas), "link_publicacion": link.strip(), "estado": nuevo_estado})
                st.success("Publicación actualizada.")
                st.rerun()


def _render_segmentos() -> None:
    st.subheader("👥 Segmentos CRM")
    st.caption("Segmentos calculados desde clientes y ventas para alimentar campañas.")
    df = _load_segments()
    if df.empty:
        st.info("No hay clientes/ventas suficientes para segmentar.")
        return
    resumen = df.groupby("segmento_marketing", as_index=False).agg(clientes=("id", "count"), ventas_usd=("ventas_usd", "sum"), compras=("compras", "sum"))
    st.dataframe(resumen, use_container_width=True, hide_index=True)
    segmento = st.selectbox("Ver segmento", ["Todos"] + sorted(df["segmento_marketing"].unique().tolist()), key="marketing_segmento_ver")
    vista = df if segmento == "Todos" else df[df["segmento_marketing"].eq(segmento)]
    cols = [c for c in ["id", "nombre", "telefono", "email", "categoria", "compras", "ventas_usd", "ultima_compra", "dias_sin_compra", "segmento_marketing"] if c in vista.columns]
    st.dataframe(vista[cols], use_container_width=True, hide_index=True)
    st.download_button("⬇️ Descargar segmentos CSV", data=vista[cols].to_csv(index=False).encode("utf-8-sig"), file_name="segmentos_marketing.csv", mime="text/csv", use_container_width=True)


def _render_roi() -> None:
    st.subheader("📈 ROI / Resultados")
    campanas = _read_table("marketing_campanas")
    pubs = _read_table("marketing_publicaciones")
    if campanas.empty and pubs.empty:
        st.info("Aún no hay resultados de marketing.")
        return
    total_presupuesto = _safe_sum(campanas, "presupuesto_usd")
    total_ventas = _safe_sum(campanas, "ventas_atribuidas_usd") + _safe_sum(pubs, "ventas_generadas_usd")
    total_leads = int(_safe_sum(campanas, "leads_generados") + _safe_sum(pubs, "leads_generados"))
    roi = ((total_ventas - total_presupuesto) / total_presupuesto * 100) if total_presupuesto > 0 else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Presupuesto", f"${total_presupuesto:,.2f}")
    c2.metric("Ventas atribuidas", f"${total_ventas:,.2f}")
    c3.metric("Leads", total_leads)
    c4.metric("ROI", f"{roi:,.1f}%")
    if not campanas.empty:
        st.markdown("#### ROI por campaña")
        st.dataframe(campanas[[c for c in ["id", "nombre", "objetivo", "presupuesto_usd", "ventas_atribuidas_usd", "leads_generados", "roi_pct", "estado"] if c in campanas.columns]], use_container_width=True, hide_index=True)
    if not pubs.empty:
        st.markdown("#### Resultados por publicación")
        st.dataframe(pubs[[c for c in ["id", "plataforma", "fecha_programada", "estado", "alcance", "interacciones", "leads_generados", "ventas_generadas_usd", "link_publicacion"] if c in pubs.columns]], use_container_width=True, hide_index=True)


def _render_alertas() -> None:
    st.subheader("🚨 Alertas de marketing")
    campanas = _read_table("marketing_campanas")
    pubs = _read_table("marketing_publicaciones")
    today = pd.Timestamp.today().normalize()
    publicaciones_vencidas = pd.DataFrame()
    esperando_diseno = pd.DataFrame()
    campanas_activas_sin_pubs = pd.DataFrame()
    campanas_sin_presupuesto = pd.DataFrame()
    roi_negativo = pd.DataFrame()
    if not pubs.empty:
        fechas = pd.to_datetime(pubs.get("fecha_programada"), errors="coerce")
        publicaciones_vencidas = pubs[pubs["estado"].isin(["Idea", "Pendiente diseño", "Programada"]) & fechas.notna() & (fechas < today)]
        esperando_diseno = pubs[pubs["estado"].eq("Pendiente diseño")]
    if not campanas.empty:
        activas = campanas[campanas["estado"].eq("Activa")]
        if not activas.empty:
            pubs_campanas = set(pd.to_numeric(pubs.get("campana_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).tolist()) if not pubs.empty else set()
            campanas_activas_sin_pubs = activas[~activas["id"].astype(int).isin(pubs_campanas)]
        campanas_sin_presupuesto = campanas[(campanas["estado"].eq("Activa")) & (pd.to_numeric(campanas["presupuesto_usd"], errors="coerce").fillna(0) <= 0)]
        roi_negativo = campanas[pd.to_numeric(campanas["roi_pct"], errors="coerce").fillna(0) < 0]
    alertas = []
    for nivel, nombre, df, accion in [
        ("Alta", "Publicaciones vencidas", publicaciones_vencidas, "Reprogramar o publicar."),
        ("Media", "Publicaciones esperando diseño", esperando_diseno, "Asignar diseño o cambiar fecha."),
        ("Media", "Campañas activas sin publicaciones", campanas_activas_sin_pubs, "Crear calendario de publicaciones."),
        ("Media", "Campañas activas sin presupuesto", campanas_sin_presupuesto, "Asignar presupuesto o marcar orgánica."),
        ("Alta", "Campañas con ROI negativo", roi_negativo, "Revisar oferta, canal o presupuesto."),
    ]:
        if not df.empty:
            alertas.append({"nivel": nivel, "alerta": nombre, "cantidad": len(df), "acción": accion})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Publicaciones vencidas", len(publicaciones_vencidas))
    c2.metric("Pendiente diseño", len(esperando_diseno))
    c3.metric("Campañas sin publicaciones", len(campanas_activas_sin_pubs))
    c4.metric("ROI negativo", len(roi_negativo))
    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas críticas de marketing.")
    tabs = st.tabs(["Vencidas", "Diseño", "Campañas sin publicaciones", "Sin presupuesto", "ROI negativo"])
    datasets = [publicaciones_vencidas, esperando_diseno, campanas_activas_sin_pubs, campanas_sin_presupuesto, roi_negativo]
    for tab, data in zip(tabs, datasets):
        with tab:
            st.dataframe(data, use_container_width=True, hide_index=True) if not data.empty else st.success("Sin registros.")


def render_publicaciones_marketing(usuario="Sistema"):
    _ensure_tables()
    st.caption(f"Usuario activo: {usuario}. Marketing operativo conectado a clientes, ventas, catálogo, CRM y fidelización.")
    tabs = st.tabs([
        "📊 Resumen",
        "🎯 Campañas y promociones",
        "📅 Calendario publicaciones",
        "👥 Segmentos CRM",
        "📈 ROI / Resultados",
        "🚨 Alertas",
    ])
    with tabs[0]:
        _render_resumen()
    with tabs[1]:
        _render_campanas(usuario)
    with tabs[2]:
        _render_publicaciones(usuario)
    with tabs[3]:
        _render_segmentos()
    with tabs[4]:
        _render_roi()
    with tabs[5]:
        _render_alertas()
