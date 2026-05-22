from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.rrhh_service import RRHHService

ESTADO_SOLICITUD_OPCIONES = ["todos", "pendiente", "aprobado", "rechazado"]
ESTADOS_INCIDENCIA = ["Abierta", "En seguimiento", "Cerrada", "Cancelada"]
TIPOS_INCIDENCIA = ["Disciplina", "Ausencia", "Retraso", "Accidente", "Desempeño", "Conflicto", "Otro"]
ESTADOS_CAPACITACION = ["Pendiente", "En curso", "Completada", "Cancelada"]
TIPOS_DOCUMENTO = ["Contrato", "Documento identidad", "Certificado", "Evaluación", "Permiso", "Otro"]


def _format_empleado_option(emp: dict) -> str:
    return f"{emp['nombre']} - {emp['puesto']} ({emp['estado']})"


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_rrhh_extra_tables() -> None:
    RRHHService()
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rrhh_incidencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Abierta',
                responsable TEXT,
                accion_correctiva TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rrhh_capacitaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                tema TEXT NOT NULL,
                proveedor TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                costo_usd REAL NOT NULL DEFAULT 0,
                resultado TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rrhh_documentos_empleado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                referencia TEXT,
                fecha_vencimiento TEXT,
                estado TEXT NOT NULL DEFAULT 'Vigente',
                observaciones TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rrhh_incidencias_estado ON rrhh_incidencias(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rrhh_documentos_venc ON rrhh_documentos_empleado(fecha_vencimiento)")


def _read_table(table_name: str) -> pd.DataFrame:
    _ensure_rrhh_extra_tables()
    with db_transaction() as conn:
        if not _table_exists(conn, table_name):
            return pd.DataFrame()
        return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)


def _insert(table_name: str, data: dict) -> int:
    _ensure_rrhh_extra_tables()
    with db_transaction() as conn:
        cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        cur = conn.execute(
            f"INSERT INTO {table_name} ({','.join(keys)}) VALUES ({','.join(['?'] * len(keys))})",
            [payload[k] for k in keys],
        )
        return int(cur.lastrowid)


def _empleados_options(service: RRHHService, activos: bool = False) -> dict[str, dict]:
    empleados = service.listar_empleados("activo" if activos else None)
    return {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados}


def _empleados_df(service: RRHHService, estado: str | None = None) -> pd.DataFrame:
    return pd.DataFrame(service.listar_empleados(estado))


def _render_dashboard(service: RRHHService) -> None:
    st.subheader("📊 Panel de control RRHH")
    indicadores = service.indicadores()
    incidencias = _read_table("rrhh_incidencias")
    docs = _read_table("rrhh_documentos_empleado")
    cap = _read_table("rrhh_capacitaciones")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Empleados activos", indicadores["empleados_activos"])
    c2.metric("Asistencias del día", indicadores["asistencias_hoy"])
    c3.metric("Solicitudes pendientes", indicadores["solicitudes_pendientes"])
    c4.metric("Incidencias abiertas", len(incidencias[incidencias["estado"].isin(["Abierta", "En seguimiento"])]) if not incidencias.empty else 0)
    c5.metric("Capacitaciones activas", len(cap[cap["estado"].isin(["Pendiente", "En curso"])]) if not cap.empty else 0)
    if not docs.empty:
        st.markdown("#### Documentos recientes")
        st.dataframe(docs.head(10), use_container_width=True, hide_index=True)


def _render_empleados(service: RRHHService, usuario: str) -> None:
    st.subheader("👥 Empleados")
    st.caption("Fuente maestra de trabajadores. Nómina lee estos empleados; no los duplica.")

    with st.form("rrhh_crear_empleado", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre", placeholder="Ej. Ana Pérez")
        documento = c2.text_input("Documento", placeholder="Ej. 10203040")
        c3, c4 = st.columns(2)
        puesto = c3.text_input("Puesto", placeholder="Ej. Analista")
        area = c4.text_input("Área", placeholder="Ej. Operaciones")
        c5, c6 = st.columns(2)
        fecha_ingreso = c5.date_input("Fecha ingreso", value=date.today())
        estado = c6.selectbox("Estado", ["activo", "inactivo"], index=0)
        submitted = st.form_submit_button("Guardar empleado", type="primary")
        if submitted:
            try:
                empleado_id = service.crear_empleado(nombre=nombre, documento=documento, puesto=puesto, area=area, fecha_ingreso=fecha_ingreso, estado=estado, usuario=usuario)
                st.success(f"Empleado guardado (ID #{empleado_id})")
            except Exception as exc:
                st.error(str(exc))

    filtro_estado = st.selectbox("Filtrar por estado", ["todos", "activo", "inactivo"], key="rrhh_filtro_empleado")
    empleados = service.listar_empleados(None if filtro_estado == "todos" else filtro_estado)
    if not empleados:
        st.info("No hay empleados registrados")
        return
    st.dataframe(pd.DataFrame(empleados), use_container_width=True, hide_index=True)


def _render_asistencia(service: RRHHService, usuario: str) -> None:
    st.subheader("🕒 Asistencia")
    opciones = _empleados_options(service, activos=True)
    if not opciones:
        st.warning("No hay empleados activos para registrar asistencia")
        return

    with st.form("rrhh_registrar_asistencia"):
        c1, c2, c3, c4 = st.columns(4)
        empleado_label = c1.selectbox("Empleado", list(opciones.keys()))
        fecha = c2.date_input("Fecha", value=date.today(), disabled=True)
        entrada = c3.time_input("Entrada", value=None)
        salida = c4.time_input("Salida", value=None)
        submitted = st.form_submit_button("Guardar asistencia", type="primary")
        if submitted:
            try:
                asist_id = service.registrar_asistencia(empleado_id=opciones[empleado_label]["id"], fecha=fecha, hora_entrada=entrada, hora_salida=salida, usuario=usuario)
                st.success(f"Asistencia registrada (ID #{asist_id})")
            except Exception as exc:
                st.error(str(exc))

    c1, c2, c3 = st.columns(3)
    fecha_desde = c1.date_input("Desde", value=date.today().replace(day=1), key="rrhh_asist_desde")
    fecha_hasta = c2.date_input("Hasta", value=date.today(), key="rrhh_asist_hasta")
    filtro_empleados = {"Todos": None}
    filtro_empleados.update({f"#{emp['id']} - {emp['nombre']}": emp["id"] for emp in service.listar_empleados()})
    empleado_hist = c3.selectbox("Empleado", list(filtro_empleados.keys()), key="rrhh_asist_empleado_filtro")
    try:
        asistencias = service.listar_asistencia(fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, empleado_id=filtro_empleados[empleado_hist])
        st.dataframe(pd.DataFrame(asistencias), use_container_width=True, hide_index=True) if asistencias else st.info("No hay asistencias para los filtros seleccionados")
    except Exception as exc:
        st.error(str(exc))


def _render_solicitudes(service: RRHHService, usuario: str) -> None:
    st.subheader("📝 Solicitudes")
    opciones = _empleados_options(service, activos=True)
    if not opciones:
        st.warning("No hay empleados activos para crear solicitudes")
        return
    with st.form("rrhh_crear_solicitud", clear_on_submit=True):
        c1, c2 = st.columns(2)
        empleado_label = c1.selectbox("Empleado", list(opciones.keys()))
        tipo = c2.selectbox("Tipo", ["vacaciones", "permiso", "incapacidad"])
        motivo = st.text_area("Motivo")
        c3, c4 = st.columns(2)
        fecha_inicio = c3.date_input("Fecha inicio", value=date.today())
        fecha_fin = c4.date_input("Fecha fin", value=date.today())
        submitted = st.form_submit_button("Crear solicitud", type="primary")
        if submitted:
            try:
                solicitud_id = service.crear_solicitud(empleado_id=opciones[empleado_label]["id"], tipo=tipo, motivo=motivo, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, usuario=usuario)
                st.success(f"Solicitud creada (ID #{solicitud_id})")
            except Exception as exc:
                st.error(str(exc))

    c1, c2, c3 = st.columns(3)
    estado = c1.selectbox("Estado", ESTADO_SOLICITUD_OPCIONES)
    fecha_desde = c2.date_input("Desde", value=date.today().replace(day=1), key="rrhh_sol_desde")
    fecha_hasta = c3.date_input("Hasta", value=date.today(), key="rrhh_sol_hasta")
    try:
        solicitudes = service.listar_solicitudes(estado=None if estado == "todos" else estado, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        st.dataframe(pd.DataFrame(solicitudes), use_container_width=True, hide_index=True) if solicitudes else st.info("No hay solicitudes para los filtros seleccionados")
    except Exception as exc:
        st.error(str(exc))


def _render_aprobaciones(service: RRHHService, usuario: str) -> None:
    st.subheader("✅ Aprobaciones")
    pendientes = service.listar_solicitudes(estado="pendiente")
    if not pendientes:
        st.success("No hay solicitudes pendientes")
        return
    st.dataframe(pd.DataFrame(pendientes), use_container_width=True, hide_index=True)
    opciones = {f"#{sol['id']} - {sol['empleado']} ({sol['tipo']} | {sol['fecha_inicio']} a {sol['fecha_fin']})": sol for sol in pendientes}
    solicitud_label = st.selectbox("Solicitud pendiente", list(opciones.keys()), key="rrhh_aprob_sel")
    comentario = st.text_input("Comentario (opcional)", key="rrhh_aprob_comentario")
    c1, c2 = st.columns(2)
    if c1.button("✅ Aprobar", type="primary", use_container_width=True, key="rrhh_aprobar_btn"):
        try:
            service.resolver_solicitud(solicitud_id=opciones[solicitud_label]["id"], accion="aprobar", comentario=comentario, admin_usuario=usuario)
            st.success("Solicitud aprobada")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if c2.button("⛔ Rechazar", use_container_width=True, key="rrhh_rechazar_btn"):
        try:
            service.resolver_solicitud(solicitud_id=opciones[solicitud_label]["id"], accion="rechazar", comentario=comentario, admin_usuario=usuario)
            st.success("Solicitud rechazada")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_incidencias(service: RRHHService, usuario: str) -> None:
    st.subheader("⚠️ Incidencias laborales")
    opciones = _empleados_options(service)
    if not opciones:
        st.warning("No hay empleados registrados.")
        return
    with st.form("rrhh_incidencia_form"):
        a, b, c = st.columns(3)
        empleado_label = a.selectbox("Empleado", list(opciones.keys()))
        tipo = b.selectbox("Tipo", TIPOS_INCIDENCIA)
        fecha_inc = c.date_input("Fecha", value=date.today())
        descripcion = st.text_area("Descripción")
        d, e = st.columns(2)
        estado = d.selectbox("Estado", ESTADOS_INCIDENCIA)
        responsable = e.text_input("Responsable", value=usuario)
        accion = st.text_area("Acción correctiva / seguimiento")
        submitted = st.form_submit_button("Guardar incidencia", type="primary")
        if submitted:
            if not descripcion.strip():
                st.error("La descripción es obligatoria.")
            else:
                iid = _insert("rrhh_incidencias", {"empleado_id": opciones[empleado_label]["id"], "fecha": fecha_inc.isoformat(), "tipo": tipo, "descripcion": descripcion.strip(), "estado": estado, "responsable": responsable.strip() or usuario, "accion_correctiva": accion.strip(), "created_by": usuario})
                st.success(f"Incidencia #{iid} registrada.")
                st.rerun()
    df = _read_table("rrhh_incidencias")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay incidencias.")


def _render_capacitacion(service: RRHHService, usuario: str) -> None:
    st.subheader("🎓 Capacitación / Evaluaciones")
    opciones = _empleados_options(service)
    if not opciones:
        st.warning("No hay empleados registrados.")
        return
    with st.form("rrhh_capacitacion_form"):
        a, b, c = st.columns(3)
        empleado_label = a.selectbox("Empleado", list(opciones.keys()))
        tema = b.text_input("Tema")
        proveedor = c.text_input("Proveedor / instructor")
        d, e, f = st.columns(3)
        fecha_inicio = d.date_input("Fecha inicio", value=date.today())
        fecha_fin = e.date_input("Fecha fin", value=date.today())
        estado = f.selectbox("Estado", ESTADOS_CAPACITACION)
        costo = st.number_input("Costo USD", min_value=0.0, value=0.0, step=1.0)
        resultado = st.text_area("Resultado / evaluación")
        submitted = st.form_submit_button("Guardar capacitación", type="primary")
        if submitted:
            if not tema.strip():
                st.error("El tema es obligatorio.")
            else:
                cid = _insert("rrhh_capacitaciones", {"empleado_id": opciones[empleado_label]["id"], "tema": tema.strip(), "proveedor": proveedor.strip(), "fecha_inicio": fecha_inicio.isoformat(), "fecha_fin": fecha_fin.isoformat(), "estado": estado, "costo_usd": float(costo), "resultado": resultado.strip(), "created_by": usuario})
                st.success(f"Capacitación #{cid} registrada.")
                st.rerun()
    df = _read_table("rrhh_capacitaciones")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay capacitaciones registradas.")


def _render_documentos(service: RRHHService, usuario: str) -> None:
    st.subheader("📁 Documentos de empleados")
    opciones = _empleados_options(service)
    if not opciones:
        st.warning("No hay empleados registrados.")
        return
    with st.form("rrhh_documento_form"):
        a, b, c = st.columns(3)
        empleado_label = a.selectbox("Empleado", list(opciones.keys()))
        tipo = b.selectbox("Tipo", TIPOS_DOCUMENTO)
        nombre = c.text_input("Nombre documento")
        referencia = st.text_input("Referencia / link / ubicación")
        d, e = st.columns(2)
        fecha_venc = d.date_input("Fecha vencimiento", value=date.today())
        estado = e.selectbox("Estado", ["Vigente", "Pendiente", "Vencido", "No aplica"])
        observaciones = st.text_area("Observaciones")
        submitted = st.form_submit_button("Guardar documento", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre del documento es obligatorio.")
            else:
                did = _insert("rrhh_documentos_empleado", {"empleado_id": opciones[empleado_label]["id"], "tipo": tipo, "nombre": nombre.strip(), "referencia": referencia.strip(), "fecha_vencimiento": fecha_venc.isoformat(), "estado": estado, "observaciones": observaciones.strip(), "created_by": usuario})
                st.success(f"Documento #{did} registrado.")
                st.rerun()
    df = _read_table("rrhh_documentos_empleado")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay documentos registrados.")


def _render_alertas(service: RRHHService) -> None:
    st.subheader("🚨 Alertas RRHH")
    empleados = _empleados_df(service)
    activos = _empleados_df(service, "activo")
    indicadores = service.indicadores()
    incidencias = _read_table("rrhh_incidencias")
    documentos = _read_table("rrhh_documentos_empleado")
    alertas = []
    datasets: dict[str, pd.DataFrame] = {}

    if indicadores["solicitudes_pendientes"] > 0:
        alertas.append({"nivel": "Media", "alerta": "Solicitudes pendientes", "cantidad": indicadores["solicitudes_pendientes"], "acción": "Revisar aprobaciones."})

    if not activos.empty and indicadores["asistencias_hoy"] < len(activos):
        alertas.append({"nivel": "Media", "alerta": "Empleados activos sin asistencia hoy", "cantidad": len(activos) - indicadores["asistencias_hoy"], "acción": "Registrar entrada/salida o justificar ausencia."})

    if not empleados.empty:
        sin_doc = empleados[empleados["documento"].fillna("").astype(str).str.strip().eq("")]
        sin_area = empleados[empleados["area"].fillna("").astype(str).str.strip().eq("")]
        sin_puesto = empleados[empleados["puesto"].fillna("").astype(str).str.strip().eq("")]
        datasets["Sin documento"] = sin_doc
        datasets["Sin área"] = sin_area
        datasets["Sin puesto"] = sin_puesto
        if not sin_doc.empty:
            alertas.append({"nivel": "Alta", "alerta": "Empleados sin documento", "cantidad": len(sin_doc), "acción": "Completar identificación."})
        if not sin_area.empty:
            alertas.append({"nivel": "Media", "alerta": "Empleados sin área", "cantidad": len(sin_area), "acción": "Asignar área."})
        if not sin_puesto.empty:
            alertas.append({"nivel": "Media", "alerta": "Empleados sin puesto", "cantidad": len(sin_puesto), "acción": "Asignar puesto."})

    if not incidencias.empty:
        abiertas = incidencias[incidencias["estado"].isin(["Abierta", "En seguimiento"])]
        datasets["Incidencias abiertas"] = abiertas
        if not abiertas.empty:
            alertas.append({"nivel": "Alta", "alerta": "Incidencias abiertas", "cantidad": len(abiertas), "acción": "Dar seguimiento y cerrar."})

    if not documentos.empty:
        fechas = pd.to_datetime(documentos["fecha_vencimiento"], errors="coerce")
        vencidos = documentos[fechas.notna() & (fechas < pd.Timestamp.today().normalize()) & ~documentos["estado"].eq("No aplica")]
        datasets["Documentos vencidos"] = vencidos
        if not vencidos.empty:
            alertas.append({"nivel": "Alta", "alerta": "Documentos vencidos", "cantidad": len(vencidos), "acción": "Renovar documentos de empleados."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas", len(alertas))
    c2.metric("Solicitudes pendientes", indicadores["solicitudes_pendientes"])
    c3.metric("Incidencias abiertas", len(datasets.get("Incidencias abiertas", pd.DataFrame())))
    c4.metric("Docs vencidos", len(datasets.get("Documentos vencidos", pd.DataFrame())))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas RRHH críticas.")
    if datasets:
        tabs = st.tabs(list(datasets.keys()))
        for tab, (nombre, df) in zip(tabs, datasets.items()):
            with tab:
                st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("Sin registros.")


def render_rrhh(usuario: str) -> None:
    service = RRHHService()
    _ensure_rrhh_extra_tables()
    st.title("👨‍💼 RRHH")
    st.caption("Fuente maestra de empleados, asistencia, solicitudes, aprobaciones, documentos, capacitación, incidencias y alertas.")

    secciones = {
        "📊 Panel RRHH": lambda: _render_dashboard(service),
        "👥 Empleados": lambda: _render_empleados(service, usuario),
        "🕒 Asistencia": lambda: _render_asistencia(service, usuario),
        "📝 Solicitudes": lambda: _render_solicitudes(service, usuario),
        "✅ Aprobaciones": lambda: _render_aprobaciones(service, usuario),
        "📁 Documentos": lambda: _render_documentos(service, usuario),
        "🎓 Capacitación": lambda: _render_capacitacion(service, usuario),
        "⚠️ Incidencias": lambda: _render_incidencias(service, usuario),
        "🚨 Alertas RRHH": lambda: _render_alertas(service),
    }
    seccion = st.radio("Sección RRHH", list(secciones.keys()), horizontal=True, key="rrhh_seccion_activa")
    st.divider()
    secciones[seccion]()
