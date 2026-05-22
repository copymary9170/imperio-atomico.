from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import render_configuracion
from views.areas_empresariales import render_area_empresarial
from views.auditoria import render_auditoria
from views.calendario_operativo import render_calendario_operativo
from views.diagnostico import render_diagnostico
from views.manuales_sop import render_manuales_sop
from views.modulos_rescatados import render_modulos_rescatados
from views.respaldo_datos import render_respaldo_datos
from views.erp_nuevos_modulos import render_seguridad_roles

ESTADOS_TAREA = ["Pendiente", "En proceso", "Completada", "Cancelada"]
PRIORIDADES = ["Baja", "Media", "Alta", "Crítica"]
TIPOS_OBLIGACION = ["Pago", "Legal", "Operativa", "Fiscal", "Mantenimiento", "Renovación", "Otro"]


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS administracion_tareas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                responsable TEXT,
                prioridad TEXT NOT NULL DEFAULT 'Media',
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                fecha_limite TEXT,
                area_relacionada TEXT,
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS administracion_obligaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Operativa',
                responsable TEXT,
                fecha_vencimiento TEXT,
                monto_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                documento_referencia TEXT,
                observaciones TEXT
            )
            """
        )


def _read_table(table_name: str) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if not _table_exists(conn, table_name):
            return pd.DataFrame()
        return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)


def _insert(table_name: str, data: dict) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        cur = conn.execute(
            f"INSERT INTO {table_name} ({','.join(keys)}) VALUES ({','.join(['?'] * len(keys))})",
            [payload[k] for k in keys],
        )
        return int(cur.lastrowid)


def _update_estado(table_name: str, row_id: int, estado: str) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        conn.execute(f"UPDATE {table_name} SET estado=? WHERE id=?", (estado, int(row_id)))


def _render_resumen(usuario: str) -> None:
    st.subheader("📊 Resumen administrativo")
    tareas = _read_table("administracion_tareas")
    obligaciones = _read_table("administracion_obligaciones")
    hoy = pd.Timestamp.today().normalize()

    tareas_pendientes = tareas[tareas["estado"].isin(["Pendiente", "En proceso"])] if not tareas.empty else pd.DataFrame()
    tareas_vencidas = pd.DataFrame()
    if not tareas_pendientes.empty:
        fechas = pd.to_datetime(tareas_pendientes["fecha_limite"], errors="coerce")
        tareas_vencidas = tareas_pendientes[fechas.notna() & (fechas < hoy)]

    obligaciones_pendientes = obligaciones[obligaciones["estado"].isin(["Pendiente", "En proceso"])] if not obligaciones.empty else pd.DataFrame()
    obligaciones_vencidas = pd.DataFrame()
    if not obligaciones_pendientes.empty:
        fechas_o = pd.to_datetime(obligaciones_pendientes["fecha_vencimiento"], errors="coerce")
        obligaciones_vencidas = obligaciones_pendientes[fechas_o.notna() & (fechas_o < hoy)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tareas pendientes", len(tareas_pendientes))
    c2.metric("Tareas vencidas", len(tareas_vencidas))
    c3.metric("Obligaciones pendientes", len(obligaciones_pendientes))
    c4.metric("Obligaciones vencidas", len(obligaciones_vencidas))

    if not tareas_pendientes.empty:
        st.markdown("#### Próximas tareas")
        st.dataframe(tareas_pendientes.head(10), use_container_width=True, hide_index=True)
    if not obligaciones_pendientes.empty:
        st.markdown("#### Próximas obligaciones")
        st.dataframe(obligaciones_pendientes.head(10), use_container_width=True, hide_index=True)


def _render_tareas(usuario: str) -> None:
    st.subheader("✅ Tareas internas")
    with st.form("admin_tarea_form"):
        a, b, c = st.columns(3)
        titulo = a.text_input("Título")
        responsable = b.text_input("Responsable", value=usuario)
        prioridad = c.selectbox("Prioridad", PRIORIDADES, index=1)
        d, e, f = st.columns(3)
        estado = d.selectbox("Estado", ESTADOS_TAREA)
        fecha_limite = e.date_input("Fecha límite", value=date.today() + timedelta(days=7))
        area = f.text_input("Área relacionada", placeholder="Finanzas, Producción, Ventas...")
        descripcion = st.text_area("Descripción")
        observaciones = st.text_area("Observaciones", key="admin_tarea_obs")
        guardar = st.form_submit_button("Guardar tarea", type="primary")
    if guardar:
        if not titulo.strip():
            st.error("El título es obligatorio.")
        else:
            tid = _insert("administracion_tareas", {"titulo": titulo.strip(), "descripcion": descripcion.strip(), "responsable": responsable.strip() or usuario, "prioridad": prioridad, "estado": estado, "fecha_limite": fecha_limite.isoformat(), "area_relacionada": area.strip(), "observaciones": observaciones.strip()})
            st.success(f"Tarea #{tid} creada.")
            st.rerun()

    df = _read_table("administracion_tareas")
    if df.empty:
        st.info("No hay tareas internas registradas.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    with st.expander("Actualizar estado de tarea"):
        ids = df["id"].astype(int).tolist()
        tarea_id = st.selectbox("Tarea", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'titulo'].iloc[0]}", key="admin_tarea_update_id")
        nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_TAREA, key="admin_tarea_update_estado")
        if st.button("Actualizar tarea", use_container_width=True, key="admin_tarea_update_btn"):
            _update_estado("administracion_tareas", int(tarea_id), nuevo_estado)
            st.success("Tarea actualizada.")
            st.rerun()


def _render_obligaciones(usuario: str) -> None:
    st.subheader("📌 Obligaciones y vencimientos")
    with st.form("admin_obligacion_form"):
        a, b, c = st.columns(3)
        nombre = a.text_input("Nombre / obligación")
        tipo = b.selectbox("Tipo", TIPOS_OBLIGACION)
        responsable = c.text_input("Responsable", value=usuario, key="admin_obl_resp")
        d, e, f = st.columns(3)
        fecha_vencimiento = d.date_input("Fecha vencimiento", value=date.today() + timedelta(days=7))
        monto = e.number_input("Monto USD", min_value=0.0, value=0.0, step=1.0)
        estado = f.selectbox("Estado", ESTADOS_TAREA, key="admin_obl_estado")
        documento = st.text_input("Documento / referencia")
        observaciones = st.text_area("Observaciones", key="admin_obl_obs")
        guardar = st.form_submit_button("Guardar obligación", type="primary")
    if guardar:
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
        else:
            oid = _insert("administracion_obligaciones", {"nombre": nombre.strip(), "tipo": tipo, "responsable": responsable.strip() or usuario, "fecha_vencimiento": fecha_vencimiento.isoformat(), "monto_usd": float(monto), "estado": estado, "documento_referencia": documento.strip(), "observaciones": observaciones.strip()})
            st.success(f"Obligación #{oid} creada.")
            st.rerun()

    df = _read_table("administracion_obligaciones")
    if df.empty:
        st.info("No hay obligaciones registradas.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    with st.expander("Actualizar estado de obligación"):
        ids = df["id"].astype(int).tolist()
        obligacion_id = st.selectbox("Obligación", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'nombre'].iloc[0]}", key="admin_obl_update_id")
        nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_TAREA, key="admin_obl_update_estado")
        if st.button("Actualizar obligación", use_container_width=True, key="admin_obl_update_btn"):
            _update_estado("administracion_obligaciones", int(obligacion_id), nuevo_estado)
            st.success("Obligación actualizada.")
            st.rerun()


def _render_alertas(usuario: str) -> None:
    st.subheader("🚨 Alertas administrativas")
    tareas = _read_table("administracion_tareas")
    obligaciones = _read_table("administracion_obligaciones")
    hoy = pd.Timestamp.today().normalize()
    alertas = []
    datasets = {}

    if not tareas.empty:
        pendientes = tareas[tareas["estado"].isin(["Pendiente", "En proceso"])]
        fechas = pd.to_datetime(pendientes["fecha_limite"], errors="coerce") if not pendientes.empty else pd.Series(dtype="datetime64[ns]")
        vencidas = pendientes[fechas.notna() & (fechas < hoy)] if not pendientes.empty else pd.DataFrame()
        sin_responsable = pendientes[pendientes["responsable"].fillna("").astype(str).str.strip().eq("")] if not pendientes.empty else pd.DataFrame()
        datasets["Tareas vencidas"] = vencidas
        datasets["Tareas sin responsable"] = sin_responsable
        if not vencidas.empty:
            alertas.append({"nivel": "Alta", "alerta": "Tareas vencidas", "cantidad": len(vencidas), "acción": "Reasignar o cerrar tareas internas."})
        if not sin_responsable.empty:
            alertas.append({"nivel": "Media", "alerta": "Tareas sin responsable", "cantidad": len(sin_responsable), "acción": "Asignar responsable."})

    if not obligaciones.empty:
        pendientes_o = obligaciones[obligaciones["estado"].isin(["Pendiente", "En proceso"])]
        fechas_o = pd.to_datetime(pendientes_o["fecha_vencimiento"], errors="coerce") if not pendientes_o.empty else pd.Series(dtype="datetime64[ns]")
        vencidas_o = pendientes_o[fechas_o.notna() & (fechas_o < hoy)] if not pendientes_o.empty else pd.DataFrame()
        sin_fecha = obligaciones[pd.to_datetime(obligaciones["fecha_vencimiento"], errors="coerce").isna()]
        datasets["Obligaciones vencidas"] = vencidas_o
        datasets["Obligaciones sin fecha"] = sin_fecha
        if not vencidas_o.empty:
            alertas.append({"nivel": "Alta", "alerta": "Obligaciones vencidas", "cantidad": len(vencidas_o), "acción": "Pagar, renovar o cerrar obligación."})
        if not sin_fecha.empty:
            alertas.append({"nivel": "Media", "alerta": "Obligaciones sin fecha", "cantidad": len(sin_fecha), "acción": "Agregar fecha de vencimiento."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas", len(alertas))
    c2.metric("Tareas vencidas", len(datasets.get("Tareas vencidas", pd.DataFrame())))
    c3.metric("Obligaciones vencidas", len(datasets.get("Obligaciones vencidas", pd.DataFrame())))
    c4.metric("Sin responsable/fecha", len(datasets.get("Tareas sin responsable", pd.DataFrame())) + len(datasets.get("Obligaciones sin fecha", pd.DataFrame())))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas administrativas críticas.")

    if datasets:
        tabs = st.tabs(list(datasets.keys()))
        for tab, (nombre, df) in zip(tabs, datasets.items()):
            with tab:
                if df.empty:
                    st.success("Sin registros.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)


def render_administracion_hub(usuario: str = "Sistema") -> None:
    _ensure_tables()
    st.title("🗂️ Administración")
    st.caption("Centro administrativo: resumen, agenda, tareas, obligaciones, documentos, respaldo, seguridad, manuales, auditoría y diagnóstico.")

    secciones = {
        "📊 Resumen": lambda: _render_resumen(usuario),
        "📅 Agenda / Calendario": lambda: render_calendario_operativo(usuario),
        "✅ Tareas internas": lambda: _render_tareas(usuario),
        "📌 Obligaciones": lambda: _render_obligaciones(usuario),
        "📁 Documentos administrativos": lambda: render_area_empresarial("Administración", usuario, show_title=False),
        "🧰 Respaldo / Exportación": lambda: render_respaldo_datos(usuario),
        "🔐 Seguridad / Roles": lambda: render_seguridad_roles(usuario),
        "⚙️ Configuración": lambda: render_configuracion(usuario),
        "📘 Manuales / SOP": lambda: render_manuales_sop(usuario),
        "📊 Auditoría": lambda: render_auditoria(usuario),
        "🧠 Diagnóstico IA": lambda: render_diagnostico(usuario),
        "🧩 Módulos rescatados": lambda: render_modulos_rescatados(usuario),
        "🚨 Alertas administrativas": lambda: _render_alertas(usuario),
    }

    seccion = st.radio("Sección administrativa", list(secciones.keys()), horizontal=True, key="admin_seccion_activa")
    st.divider()
    secciones[seccion]()
