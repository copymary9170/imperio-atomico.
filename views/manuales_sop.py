from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission


MODULOS_ERP = [
    "Panel de control",
    "Inventario",
    "Kardex",
    "Activos",
    "Clientes",
    "CRM",
    "Ventas",
    "Cotizaciones",
    "Marketing / Ventas",
    "Fidelización",
    "Corte Industrial",
    "Sublimación",
    "Producción Manual",
    "Planificación de producción",
    "Rutas de producción",
    "Control de calidad",
    "Mermas y desperdicio",
    "Gastos",
    "Caja empresarial",
    "Tesorería",
    "Cuentas por pagar",
    "Contabilidad",
    "Conciliación bancaria",
    "Impuestos",
    "Rentabilidad",
    "Planeación financiera",
    "Auditoría",
    "Costeo",
    "Costeo industrial",
    "Calculadora",
    "RRHH",
    "Configuración",
    "Seguridad / Roles",
    "CMYK",
    "Diagnóstico IA",
    "Otros procesos",
    "Catálogo",
    "Mantenimiento",
]


def _ensure_manuales_table() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manuales_sop (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                creado_por TEXT NOT NULL DEFAULT 'Sistema',
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_por TEXT NOT NULL DEFAULT 'Sistema',
                estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo','borrador')),
                version TEXT NOT NULL DEFAULT '1.0',
                titulo TEXT NOT NULL,
                modulo TEXT NOT NULL,
                proceso TEXT NOT NULL,
                rol_responsable TEXT,
                objetivo TEXT,
                alcance TEXT,
                requisitos_previos TEXT,
                pasos TEXT,
                validaciones_previas TEXT,
                validaciones_posteriores TEXT,
                acciones_correctivas TEXT,
                casos_especiales TEXT,
                evidencia TEXT,
                notas TEXT
            )
            """
        )


def _get_manuales_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                titulo,
                modulo,
                proceso,
                version,
                rol_responsable,
                estado,
                actualizado_en,
                actualizado_por
            FROM manuales_sop
            ORDER BY id DESC
            """,
            conn,
        )


def _get_manual_by_id(manual_id: int):
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM manuales_sop
            WHERE id = ?
            """,
            (manual_id,),
        ).fetchone()
    return row


def _crear_manual(data: dict, usuario: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO manuales_sop (
                creado_por,
                actualizado_por,
                estado,
                version,
                titulo,
                modulo,
                proceso,
                rol_responsable,
                objetivo,
                alcance,
                requisitos_previos,
                pasos,
                validaciones_previas,
                validaciones_posteriores,
                acciones_correctivas,
                casos_especiales,
                evidencia,
                notas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                usuario,
                data["estado"],
                data["version"],
                data["titulo"],
                data["modulo"],
                data["proceso"],
                data["rol_responsable"],
                data["objetivo"],
                data["alcance"],
                data["requisitos_previos"],
                data["pasos"],
                data["validaciones_previas"],
                data["validaciones_posteriores"],
                data["acciones_correctivas"],
                data["casos_especiales"],
                data["evidencia"],
                data["notas"],
            ),
        )


def render_manuales_sop(usuario: str) -> None:
    if not require_permission("dashboard.view", "🚫 No tienes acceso al módulo Manuales / SOP."):
        return

    _ensure_manuales_table()

    puede_editar = has_permission("config.edit") or has_permission("security.edit")

    st.subheader("📘 Manuales / SOP")
    st.info("Documenta cómo operar cada módulo, qué validar y cómo corregir errores.")

    tab1, tab2, tab3 = st.tabs(["📚 Manuales", "➕ Nuevo SOP", "🔎 Consulta rápida"])

    with tab1:
        st.markdown("### Listado de manuales")
        try:
            df = _get_manuales_df()
            if df.empty:
                st.info("Aún no hay manuales registrados.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

                manual_id = st.number_input("Ver detalle por ID", min_value=1, step=1)
                if st.button("Ver manual", use_container_width=True):
                    manual = _get_manual_by_id(int(manual_id))
                    if not manual:
                        st.warning("No se encontró el manual.")
                    else:
                        st.markdown(f"## {manual['titulo']}")
                        st.write(f"**Módulo:** {manual['modulo']}")
                        st.write(f"**Proceso:** {manual['proceso']}")
                        st.write(f"**Versión:** {manual['version']}")
                        st.write(f"**Estado:** {manual['estado']}")
                        st.write(f"**Rol responsable:** {manual['rol_responsable'] or '-'}")

                        st.markdown("### Objetivo")
                        st.write(manual["objetivo"] or "-")

                        st.markdown("### Alcance")
                        st.write(manual["alcance"] or "-")

                        st.markdown("### Requisitos previos")
                        st.write(manual["requisitos_previos"] or "-")

                        st.markdown("### Pasos")
                        st.write(manual["pasos"] or "-")

                        st.markdown("### Validaciones previas")
                        st.write(manual["validaciones_previas"] or "-")

                        st.markdown("### Validaciones posteriores")
                        st.write(manual["validaciones_posteriores"] or "-")

                        st.markdown("### Acciones correctivas")
                        st.write(manual["acciones_correctivas"] or "-")

                        st.markdown("### Casos especiales")
                        st.write(manual["casos_especiales"] or "-")

                        st.markdown("### Evidencia / trazabilidad")
                        st.write(manual["evidencia"] or "-")

                        st.markdown("### Notas")
                        st.write(manual["notas"] or "-")
        except Exception as e:
            st.error("No se pudieron cargar los manuales.")
            st.exception(e)

    with tab2:
        st.markdown("### Crear nuevo SOP")

        if not puede_editar:
            st.warning("Modo solo lectura: no tienes permiso para crear manuales.")
        with st.form("form_manual_sop"):
            titulo = st.text_input("Título", disabled=not puede_editar)
            c1, c2, c3 = st.columns(3)
            modulo = c1.selectbox("Módulo", MODULOS_ERP, disabled=not puede_editar)
            proceso = c2.text_input("Proceso", disabled=not puede_editar)
            version = c3.text_input("Versión", value="1.0", disabled=not puede_editar)

            c4, c5 = st.columns(2)
            estado = c4.selectbox("Estado", ["activo", "inactivo", "borrador"], disabled=not puede_editar)
            rol_responsable = c5.text_input("Rol responsable", disabled=not puede_editar)

            objetivo = st.text_area("Objetivo", disabled=not puede_editar)
            alcance = st.text_area("Alcance", disabled=not puede_editar)
            requisitos_previos = st.text_area("Requisitos previos", disabled=not puede_editar)
            pasos = st.text_area("Pasos", help="Escribe el procedimiento paso a paso.", disabled=not puede_editar)
            validaciones_previas = st.text_area("Validaciones previas", disabled=not puede_editar)
            validaciones_posteriores = st.text_area("Validaciones posteriores", disabled=not puede_editar)
            acciones_correctivas = st.text_area("Acciones correctivas", disabled=not puede_editar)
            casos_especiales = st.text_area("Casos especiales", disabled=not puede_editar)
            evidencia = st.text_area("Evidencia / trazabilidad", disabled=not puede_editar)
            notas = st.text_area("Notas", disabled=not puede_editar)

            guardar = st.form_submit_button("💾 Guardar SOP", disabled=not puede_editar)

        if guardar:
            if not titulo.strip():
                st.warning("Debes indicar un título.")
            elif not proceso.strip():
                st.warning("Debes indicar un proceso.")
            else:
                try:
                    _crear_manual(
                        {
                            "estado": estado,
                            "version": version.strip() or "1.0",
                            "titulo": titulo.strip(),
                            "modulo": modulo,
                            "proceso": proceso.strip(),
                            "rol_responsable": rol_responsable.strip(),
                            "objetivo": objetivo.strip(),
                            "alcance": alcance.strip(),
                            "requisitos_previos": requisitos_previos.strip(),
                            "pasos": pasos.strip(),
                            "validaciones_previas": validaciones_previas.strip(),
                            "validaciones_posteriores": validaciones_posteriores.strip(),
                            "acciones_correctivas": acciones_correctivas.strip(),
                            "casos_especiales": casos_especiales.strip(),
                            "evidencia": evidencia.strip(),
                            "notas": notas.strip(),
                        },
                        usuario,
                    )
                    st.success("✅ SOP registrado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error("No se pudo guardar el SOP.")
                    st.exception(e)

    with tab3:
        st.markdown("### Consulta rápida")
        termino = st.text_input("Buscar por título, módulo o proceso")

        try:
            df = _get_manuales_df()
            if termino.strip():
                mask = (
                    df["titulo"].astype(str).str.contains(termino, case=False, na=False)
                    | df["modulo"].astype(str).str.contains(termino, case=False, na=False)
                    | df["proceso"].astype(str).str.contains(termino, case=False, na=False)
                )
                df = df[mask]

            if df.empty:
                st.info("No se encontraron manuales con ese criterio.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("No se pudo realizar la búsqueda.")
            st.exception(e)
