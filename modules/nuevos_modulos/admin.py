from __future__ import annotations

from datetime import date, datetime
from typing import Optional
import sqlite3
import pandas as pd
import streamlit as st

from .types import ModuleBlueprint

DB_PATH = "rrhh.db"

ADMIN_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="rrhh",
        name="Gestión de RRHH",
        icon="👥",
        category="Administración interna",
        summary="Centraliza ciclo de vida del personal, asistencia y solicitudes internas en un solo módulo.",
        capabilities=(
            "Alta/baja de colaboradores",
            "Control de asistencia",
            "Solicitudes de permisos e incapacidades",
            "Panel de indicadores de talento",
        ),
        integrations=("Producción", "Contabilidad", "Seguridad/Roles"),
        business_value="Mejora el control operativo del talento y reduce tiempos administrativos en procesos internos.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="seguridad_roles",
        name="Seguridad y roles",
        icon="🔐",
        category="Administración interna",
        summary="Define perfiles y permisos por área para proteger datos y asegurar trazabilidad de accesos.",
        capabilities=(
            "Roles por área",
            "Permisos por módulo",
            "Bitácora de accesos",
            "Gestión de usuarios activos/inactivos",
        ),
        integrations=("RRHH", "Auditoría", "Todos los módulos ERP"),
        business_value="Reduce riesgo operativo y fortalece gobernanza del ERP con control granular de acceso.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="auditoria",
        name="Auditoría operativa",
        icon="🕵️",
        category="Administración interna",
        summary="Registra eventos críticos para seguimiento de cambios, validación de procesos y cumplimiento interno.",
        capabilities=(
            "Bitácora de transacciones",
            "Trazabilidad de cambios",
            "Seguimiento de incidencias",
            "Reportes de control interno",
        ),
        integrations=("Seguridad/Roles", "Finanzas", "Producción", "Contabilidad"),
        business_value="Facilita investigaciones internas y control de cumplimiento con evidencia centralizada.",
        priority="Media-Alta",
    ),
)

# =========================
# DB LAYER
# =========================

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS empleados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        documento TEXT UNIQUE NOT NULL,
        puesto TEXT NOT NULL,
        area TEXT NOT NULL,
        fecha_ingreso TEXT NOT NULL,
        estado TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS asistencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER,
        fecha TEXT,
        hora_entrada TEXT,
        hora_salida TEXT,
        UNIQUE(empleado_id, fecha)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS solicitudes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empleado_id INTEGER,
        tipo TEXT,
        motivo TEXT,
        fecha_inicio TEXT,
        fecha_fin TEXT,
        estado TEXT DEFAULT 'pendiente',
        comentario_admin TEXT
    )
    """)

    conn.commit()
    conn.close()


# =========================
# SERVICE LAYER
# =========================

def crear_empleado(nombre, documento, puesto, area, fecha_ingreso, estado):
    if not nombre or not documento:
        raise ValueError("Nombre y documento obligatorios")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO empleados (nombre, documento, puesto, area, fecha_ingreso, estado)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (nombre, documento, puesto, area, fecha_ingreso, estado))
    conn.commit()
    conn.close()


def listar_empleados(estado: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()

    if estado and estado != "todos":
        cur.execute("SELECT * FROM empleados WHERE estado=?", (estado,))
    else:
        cur.execute("SELECT * FROM empleados")

    rows = cur.fetchall()
    conn.close()
    return rows


def registrar_asistencia(empleado_id, fecha, entrada, salida):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM asistencias WHERE empleado_id=? AND fecha=?", (empleado_id, fecha))
    existing = cur.fetchone()

    if existing:
        cur.execute("""
        UPDATE asistencias
        SET hora_entrada=COALESCE(?,hora_entrada),
            hora_salida=COALESCE(?,hora_salida)
        WHERE id=?
        """, (entrada, salida, existing[0]))
    else:
        cur.execute("""
        INSERT INTO asistencias (empleado_id, fecha, hora_entrada, hora_salida)
        VALUES (?, ?, ?, ?)
        """, (empleado_id, fecha, entrada, salida))

    conn.commit()
    conn.close()


def listar_asistencia():
    conn = get_conn()
    df = pd.read_sql_query("""
    SELECT a.id, a.fecha, a.hora_entrada, a.hora_salida,
           e.nombre
    FROM asistencias a
    JOIN empleados e ON e.id=a.empleado_id
    ORDER BY a.fecha DESC
    """, conn)
    conn.close()
    return df


def crear_solicitud(emp_id, tipo, motivo, fi, ff):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO solicitudes (empleado_id, tipo, motivo, fecha_inicio, fecha_fin)
    VALUES (?, ?, ?, ?, ?)
    """, (emp_id, tipo, motivo, fi, ff))

    conn.commit()
    conn.close()


def listar_solicitudes(estado=None):
    conn = get_conn()

    if estado and estado != "todos":
        df = pd.read_sql_query("""
        SELECT s.*, e.nombre FROM solicitudes s
        JOIN empleados e ON e.id=s.empleado_id
        WHERE estado=?
        """, conn, params=(estado,))
    else:
        df = pd.read_sql_query("""
        SELECT s.*, e.nombre FROM solicitudes s
        JOIN empleados e ON e.id=s.empleado_id
        """, conn)

    conn.close()
    return df


def resolver_solicitud(sol_id, estado, comentario):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE solicitudes
    SET estado=?, comentario_admin=?
    WHERE id=?
    """, (estado, comentario, sol_id))

    conn.commit()
    conn.close()


def indicadores():
    conn = get_conn()
    cur = conn.cursor()

    today = date.today().isoformat()

    activos = cur.execute("SELECT COUNT(*) FROM empleados WHERE estado='activo'").fetchone()[0]
    asistencias = cur.execute("SELECT COUNT(*) FROM asistencias WHERE fecha=?", (today,)).fetchone()[0]
    pendientes = cur.execute("SELECT COUNT(*) FROM solicitudes WHERE estado='pendiente'").fetchone()[0]
    aprobadas = cur.execute("SELECT COUNT(*) FROM solicitudes WHERE estado='aprobado'").fetchone()[0]
    rechazadas = cur.execute("SELECT COUNT(*) FROM solicitudes WHERE estado='rechazado'").fetchone()[0]

    conn.close()

    return activos, asistencias, pendientes, aprobadas, rechazadas


# =========================
# UI LAYER
# =========================

def render_rrhh(usuario: str):
    init_db()
    st.title("👨‍💼 RRHH")

    tabs = st.tabs([
        "Panel de control",
        "Empleados",
        "Asistencia",
        "Solicitudes",
        "Aprobaciones"
    ])

    # =========================
    # PANEL DE CONTROL
    # =========================
    with tabs[0]:
        a, b, c, d, e = indicadores()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Activos", a)
        c2.metric("Asistencias hoy", b)
        c3.metric("Pendientes", c)
        c4.metric("Aprobadas", d)
        c5.metric("Rechazadas", e)

    # =========================
    # EMPLEADOS
    # =========================
    with tabs[1]:
        st.subheader("Crear empleado")

        with st.form("emp"):
            nombre = st.text_input("Nombre")
            doc = st.text_input("Documento")
            puesto = st.text_input("Puesto")
            area = st.text_input("Área")
            fecha = st.date_input("Ingreso")
            estado = st.selectbox("Estado", ["activo", "inactivo"])

            if st.form_submit_button("Guardar"):
                try:
                    crear_empleado(nombre, doc, puesto, area, fecha.isoformat(), estado)
                    st.success("Guardado")
                except Exception as e:
                    st.error(str(e))

        filtro = st.selectbox("Filtro", ["todos", "activo", "inactivo"])
        data = listar_empleados(filtro)
        st.dataframe(data)

    # =========================
    # ASISTENCIA
    # =========================
    with tabs[2]:
        empleados = listar_empleados("activo")
        if not empleados:
            st.warning("No hay empleados")
        else:
            opciones = {f"{e[0]} - {e[1]}": e[0] for e in empleados}

            emp = st.selectbox("Empleado", list(opciones.keys()))
            entrada = st.time_input("Entrada")
            salida = st.time_input("Salida")

            if st.button("Registrar"):
                registrar_asistencia(
                    opciones[emp],
                    date.today().isoformat(),
                    entrada.strftime("%H:%M") if entrada else None,
                    salida.strftime("%H:%M") if salida else None
                )
                st.success("Registrado")

        st.dataframe(listar_asistencia())

    # =========================
    # SOLICITUDES
    # =========================
    with tabs[3]:
        empleados = listar_empleados("activo")
        if empleados:
            opciones = {f"{e[0]} - {e[1]}": e[0] for e in empleados}

            emp = st.selectbox("Empleado", list(opciones.keys()))
            tipo = st.selectbox("Tipo", ["vacaciones", "permiso", "incapacidad"])
            motivo = st.text_area("Motivo")
            fi = st.date_input("Inicio")
            ff = st.date_input("Fin")

            if st.button("Crear solicitud"):
                crear_solicitud(opciones[emp], tipo, motivo, fi.isoformat(), ff.isoformat())
                st.success("Creada")

        estado = st.selectbox("Estado", ["todos", "pendiente", "aprobado", "rechazado"])
        st.dataframe(listar_solicitudes(estado))

    # =========================
    # APROBACIONES
    # =========================
    with tabs[4]:
        df = listar_solicitudes("pendiente")

        if df.empty:
            st.success("No hay pendientes")
        else:
            st.dataframe(df)

            opciones = {f"{row['id']} - {row['nombre']}": row['id'] for _, row in df.iterrows()}
            sel = st.selectbox("Seleccionar", list(opciones.keys()))
            comentario = st.text_input("Comentario")

            c1, c2 = st.columns(2)

            if c1.button("Aprobar"):
                resolver_solicitud(opciones[sel], "aprobado", comentario)
                st.success("Aprobado")
                st.rerun()

            if c2.button("Rechazar"):
                resolver_solicitud(opciones[sel], "rechazado", comentario)
                st.success("Rechazado")
                st.rerun()
