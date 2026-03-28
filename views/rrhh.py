from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.rrhh_service import RRHHService

ESTADO_SOLICITUD_OPCIONES = ["todos", "pendiente", "aprobado", "rechazado"]


def _format_empleado_option(emp: dict) -> str:
    return f"{emp['nombre']} - {emp['puesto']} ({emp['estado']})"


def _render_dashboard(service: RRHHService) -> None:
    st.subheader("Dashboard RRHH")
    indicadores = service.indicadores()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Empleados activos", indicadores["empleados_activos"])
    c2.metric("Asistencias del día", indicadores["asistencias_hoy"])
    c3.metric("Solicitudes pendientes", indicadores["solicitudes_pendientes"])
    c4.metric("Aprobadas", indicadores["solicitudes_aprobadas"])
    c5.metric("Rechazadas", indicadores["solicitudes_rechazadas"])


def _render_empleados(service: RRHHService, usuario: str) -> None:
    st.subheader("Empleados")

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
                empleado_id = service.crear_empleado(
                    nombre=nombre,
                    documento=documento,
                    puesto=puesto,
                    area=area,
                    fecha_ingreso=fecha_ingreso,
                    estado=estado,
                    usuario=usuario,
                )
                st.success(f"Empleado guardado (ID #{empleado_id})")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    st.markdown("#### Listado")
    filtro_estado = st.selectbox("Filtrar por estado", ["todos", "activo", "inactivo"], key="rrhh_filtro_empleado")
    empleados = service.listar_empleados(None if filtro_estado == "todos" else filtro_estado)

    if not empleados:
        st.info("No hay empleados registrados")
        return

    st.dataframe(pd.DataFrame(empleados), use_container_width=True, hide_index=True)


def _render_asistencia(service: RRHHService, usuario: str) -> None:
    st.subheader("Asistencia")
    empleados_activos = service.listar_empleados("activo")
    if not empleados_activos:
        st.warning("No hay empleados activos para registrar asistencia")
        return

    opciones = {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados_activos}

    with st.form("rrhh_registrar_asistencia"):
        c1, c2, c3, c4 = st.columns(4)
        empleado_label = c1.selectbox("Empleado", list(opciones.keys()))
        fecha = c2.date_input("Fecha", value=date.today(), disabled=True)
        entrada = c3.time_input("Entrada", value=None)
        salida = c4.time_input("Salida", value=None)

        submitted = st.form_submit_button("Guardar asistencia", type="primary")
        if submitted:
            try:
                asist_id = service.registrar_asistencia(
                    empleado_id=opciones[empleado_label]["id"],
                    fecha=fecha,
                    hora_entrada=entrada,
                    hora_salida=salida,
                    usuario=usuario,
                )
                st.success(f"Asistencia registrada (ID #{asist_id})")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    st.markdown("#### Historial de asistencias")
    c1, c2, c3 = st.columns(3)
    fecha_desde = c1.date_input("Desde", value=date.today().replace(day=1), key="rrhh_asist_desde")
    fecha_hasta = c2.date_input("Hasta", value=date.today(), key="rrhh_asist_hasta")

    filtro_empleados = {"Todos": None}
    filtro_empleados.update({f"#{emp['id']} - {emp['nombre']}": emp["id"] for emp in service.listar_empleados()})
    empleado_hist = c3.selectbox("Empleado", list(filtro_empleados.keys()), key="rrhh_asist_empleado_filtro")

    try:
        asistencias = service.listar_asistencia(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            empleado_id=filtro_empleados[empleado_hist],
        )
        if asistencias:
            st.dataframe(pd.DataFrame(asistencias), use_container_width=True, hide_index=True)
        else:
            st.info("No hay asistencias para los filtros seleccionados")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))


def _render_solicitudes(service: RRHHService, usuario: str) -> None:
    st.subheader("Solicitudes")
    empleados_activos = service.listar_empleados("activo")
    if not empleados_activos:
        st.warning("No hay empleados activos para crear solicitudes")
        return

    opciones = {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados_activos}

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
                solicitud_id = service.crear_solicitud(
                    empleado_id=opciones[empleado_label]["id"],
                    tipo=tipo,
                    motivo=motivo,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    usuario=usuario,
                )
                st.success(f"Solicitud creada (ID #{solicitud_id})")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    st.markdown("#### Listado de solicitudes")
    c1, c2, c3 = st.columns(3)
    estado = c1.selectbox("Estado", ESTADO_SOLICITUD_OPCIONES)
    fecha_desde = c2.date_input("Desde", value=date.today().replace(day=1), key="rrhh_sol_desde")
    fecha_hasta = c3.date_input("Hasta", value=date.today(), key="rrhh_sol_hasta")

    try:
        solicitudes = service.listar_solicitudes(
            estado=None if estado == "todos" else estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        if solicitudes:
            st.dataframe(pd.DataFrame(solicitudes), use_container_width=True, hide_index=True)
        else:
            st.info("No hay solicitudes para los filtros seleccionados")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))


def _render_aprobaciones(service: RRHHService, usuario: str) -> None:
    st.subheader("Aprobaciones")
    pendientes = service.listar_solicitudes(estado="pendiente")
    if not pendientes:
        st.success("No hay solicitudes pendientes")
        return

    st.dataframe(pd.DataFrame(pendientes), use_container_width=True, hide_index=True)

    opciones = {
        f"#{sol['id']} - {sol['empleado']} ({sol['tipo']} | {sol['fecha_inicio']} a {sol['fecha_fin']})": sol
        for sol in pendientes
    }
    solicitud_label = st.selectbox("Solicitud pendiente", list(opciones.keys()), key="rrhh_aprob_sel")
    comentario = st.text_input("Comentario (opcional)", key="rrhh_aprob_comentario")

    c1, c2 = st.columns(2)
    if c1.button("✅ Aprobar", type="primary", use_container_width=True):
        try:
            service.resolver_solicitud(
                solicitud_id=opciones[solicitud_label]["id"],
                accion="aprobar",
                comentario=comentario,
                admin_usuario=usuario,
            )
            st.success("Solicitud aprobada")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    if c2.button("⛔ Rechazar", use_container_width=True):
        try:
            service.resolver_solicitud(
                solicitud_id=opciones[solicitud_label]["id"],
                accion="rechazar",
                comentario=comentario,
                admin_usuario=usuario,
            )
            st.success("Solicitud rechazada")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))


def render_rrhh(usuario: str) -> None:
    service = RRHHService()
    st.title("👨‍💼 RRHH")

    tabs = st.tabs([
        "Dashboard RRHH",
        "Empleados",
        "Asistencia",
        "Solicitudes",
        "Aprobaciones",
    ])

    with tabs[0]:
        _render_dashboard(service)
    with tabs[1]:
        _render_empleados(service, usuario)
    with tabs[2]:
        _render_asistencia(service, usuario)
    with tabs[3]:
        _render_solicitudes(service, usuario)
    with tabs[4]:
        _render_aprobaciones(service, usuario)
