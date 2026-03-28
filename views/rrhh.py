from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.rrhh_service import RRHHService


ESTADO_SOLICITUD_OPCIONES = ["todos", "pendiente", "aprobado", "rechazado"]


def _format_empleado_option(emp: dict) -> str:
    return f"{emp['nombre']} ({emp['puesto']}) [{emp['estado']}]"


def _render_indicadores(service: RRHHService) -> None:
    indicadores = service.indicadores()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total empleados", indicadores["total_empleados"])
    c2.metric("Asistencias de hoy", indicadores["asistencias_hoy"])
    c3.metric("Solicitudes pendientes", indicadores["solicitudes_pendientes"])


def _render_empleados(service: RRHHService, usuario: str) -> None:
    st.subheader("1) Gestión de empleados")
    with st.form("rrhh_crear_empleado", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Nombre completo", placeholder="Ej. Ana Pérez")
        puesto = c2.text_input("Puesto", placeholder="Ej. Operador de producción")
        fecha_ingreso = c3.date_input("Fecha de ingreso", value=date.today())
        submitted = st.form_submit_button("Crear empleado", type="primary")
        if submitted:
            try:
                empleado_id = service.crear_empleado(
                    nombre=nombre,
                    puesto=puesto,
                    fecha_ingreso=fecha_ingreso,
                    usuario=usuario,
                )
                st.success(f"Empleado creado con ID #{empleado_id}")
            except ValueError as exc:
                st.error(str(exc))

    filtro_estado = st.selectbox("Filtrar empleados por estado", ["todos", "activo", "inactivo"], key="rrhh_empleados_estado")
    empleados = service.listar_empleados(None if filtro_estado == "todos" else filtro_estado)

    if not empleados:
        st.info("No hay empleados registrados todavía.")
        return

    employee_df = pd.DataFrame(empleados)
    st.dataframe(employee_df, use_container_width=True, hide_index=True)

    with st.expander("Cambiar estado activo/inactivo"):
        empleados_dict = {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados}
        selected = st.selectbox("Empleado", list(empleados_dict.keys()), key="rrhh_estado_emp")
        nuevo_estado = st.radio("Nuevo estado", ["activo", "inactivo"], horizontal=True, key="rrhh_nuevo_estado")
        if st.button("Actualizar estado", key="rrhh_btn_estado"):
            service.cambiar_estado_empleado(empleado_id=empleados_dict[selected]["id"], estado=nuevo_estado)
            st.success("Estado actualizado")
            st.rerun()


def _render_asistencia(service: RRHHService, usuario: str) -> None:
    st.subheader("2) Registro de asistencia")
    empleados_activos = service.listar_empleados("activo")
    if not empleados_activos:
        st.warning("Necesitas al menos un empleado activo para registrar asistencia.")
        return

    opciones = {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados_activos}

    with st.form("rrhh_registrar_asistencia"):
        c1, c2, c3, c4 = st.columns(4)
        empleado_label = c1.selectbox("Empleado", list(opciones.keys()))
        fecha = c2.date_input("Fecha", value=date.today(), key="rrhh_asist_fecha")
        entrada = c3.time_input("Hora entrada", value=None, key="rrhh_asist_entrada")
        salida = c4.time_input("Hora salida", value=None, key="rrhh_asist_salida")
        submitted = st.form_submit_button("Guardar asistencia", type="primary")
        if submitted:
            try:
                record_id = service.registrar_asistencia(
                    empleado_id=opciones[empleado_label]["id"],
                    fecha=fecha,
                    hora_entrada=entrada,
                    hora_salida=salida,
                    usuario=usuario,
                )
                st.success(f"Asistencia guardada (registro #{record_id})")
            except ValueError as exc:
                st.error(str(exc))

    st.markdown("**Listado de asistencias por fecha**")
    c1, c2 = st.columns(2)
    fecha_desde = c1.date_input("Desde", value=date.today(), key="rrhh_lista_asist_desde")
    fecha_hasta = c2.date_input("Hasta", value=date.today(), key="rrhh_lista_asist_hasta")
    try:
        asistencias = service.listar_asistencia(fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    except ValueError as exc:
        st.error(str(exc))
        return

    if asistencias:
        st.dataframe(pd.DataFrame(asistencias), use_container_width=True, hide_index=True)
    else:
        st.info("No hay asistencias en el rango seleccionado.")


def _render_solicitudes(service: RRHHService, usuario: str, rol_usuario: str | None) -> None:
    st.subheader("3) Solicitudes (vacaciones/permisos)")
    empleados = service.listar_empleados("activo")
    if not empleados:
        st.warning("Necesitas empleados activos para crear solicitudes.")
        return

    opciones = {f"#{emp['id']} - {_format_empleado_option(emp)}": emp for emp in empleados}

    with st.form("rrhh_crear_solicitud", clear_on_submit=True):
        c1, c2 = st.columns(2)
        empleado_label = c1.selectbox("Empleado", list(opciones.keys()), key="rrhh_sol_emp")
        tipo = c2.selectbox("Tipo", ["vacaciones", "permiso"], key="rrhh_sol_tipo")
        motivo = st.text_area("Motivo", key="rrhh_sol_motivo")
        f1, f2 = st.columns(2)
        fecha_inicio = f1.date_input("Fecha inicio", value=date.today(), key="rrhh_sol_ini")
        fecha_fin = f2.date_input("Fecha fin", value=date.today(), key="rrhh_sol_fin")
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
                st.success(f"Solicitud creada con ID #{solicitud_id}")
            except ValueError as exc:
                st.error(str(exc))

    st.markdown("**Listado de solicitudes**")
    c1, c2, c3 = st.columns(3)
    estado = c1.selectbox("Estado", ESTADO_SOLICITUD_OPCIONES, key="rrhh_sol_estado_filtro")
    fecha_desde = c2.date_input("Desde", value=date.today().replace(day=1), key="rrhh_sol_desde")
    fecha_hasta = c3.date_input("Hasta", value=date.today(), key="rrhh_sol_hasta")
    solicitudes = service.listar_solicitudes(
        estado=None if estado == "todos" else estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    if solicitudes:
        st.dataframe(pd.DataFrame(solicitudes), use_container_width=True, hide_index=True)
    else:
        st.info("No hay solicitudes con los filtros seleccionados.")

    st.subheader("4) Acción clave: aprobación/rechazo de solicitudes")
    pendientes = [s for s in service.listar_solicitudes(estado="pendiente")]
    if not pendientes:
        st.success("No hay solicitudes pendientes por resolver.")
        return

    if (rol_usuario or "").lower() not in {"admin", "administration"}:
        st.warning("Solo el rol administrador puede aprobar o rechazar solicitudes.")
        return

    opciones_pendientes = {
        f"#{s['id']} - {s['empleado']} ({s['tipo']}: {s['fecha_inicio']} → {s['fecha_fin']})": s
        for s in pendientes
    }
    solicitud_label = st.selectbox("Solicitud pendiente", list(opciones_pendientes.keys()), key="rrhh_apr_sol")
    comentario = st.text_input("Comentario admin (opcional)", key="rrhh_apr_coment")
    a1, a2 = st.columns(2)
    if a1.button("✅ Aprobar", key="rrhh_btn_aprobar", use_container_width=True):
        try:
            service.resolver_solicitud(
                solicitud_id=opciones_pendientes[solicitud_label]["id"],
                accion="aprobar",
                comentario=comentario,
                admin_usuario=usuario,
                rol_usuario=rol_usuario,
            )
            st.success("Solicitud aprobada")
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))

    if a2.button("⛔ Rechazar", key="rrhh_btn_rechazar", use_container_width=True):
        try:
            service.resolver_solicitud(
                solicitud_id=opciones_pendientes[solicitud_label]["id"],
                accion="rechazar",
                comentario=comentario,
                admin_usuario=usuario,
                rol_usuario=rol_usuario,
            )
            st.success("Solicitud rechazada")
            st.rerun()
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))


def render_rrhh(usuario):
    st.title("👨‍💼 RRHH")
    st.caption("Módulo operativo mínimo funcional")

    service = RRHHService()
    rol_usuario = st.session_state.get("rol")

    _render_indicadores(service)
    st.divider()
    _render_empleados(service, usuario)
    st.divider()
    _render_asistencia(service, usuario)
    st.divider()
    _render_solicitudes(service, usuario, rol_usuario)
