from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, require_text

ALLOWED_ROLES = {"Admin", "Administration", "Administracion"}
TIPOS_UNIDAD = [
    "Impresora",
    "Corte / Plotter (Cameo)",
    "Plancha de Sublimación",
    "Otro",
]
CATEGORIAS = ["Impresora", "Corte", "Sublimación", "Tinta", "Calor", "Mantenimiento", "Otro"]


# =========================================================
# CAPA DE DATOS
# =========================================================

def _ensure_activos_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            estado TEXT NOT NULL DEFAULT 'activo',
            equipo TEXT NOT NULL,
            modelo TEXT,
            categoria TEXT,
            inversion REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            desgaste REAL NOT NULL DEFAULT 0,
            costo_hora REAL NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activos_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            activo TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT,
            costo REAL NOT NULL DEFAULT 0,
            usuario TEXT
        )
        """
    )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(activos)").fetchall()}
    optional_cols = {
        "inversion": "ALTER TABLE activos ADD COLUMN inversion REAL NOT NULL DEFAULT 0",
        "unidad": "ALTER TABLE activos ADD COLUMN unidad TEXT",
        "desgaste": "ALTER TABLE activos ADD COLUMN desgaste REAL NOT NULL DEFAULT 0",
        "activo": "ALTER TABLE activos ADD COLUMN activo INTEGER NOT NULL DEFAULT 1",
        "modelo": "ALTER TABLE activos ADD COLUMN modelo TEXT",
        "costo_hora": "ALTER TABLE activos ADD COLUMN costo_hora REAL NOT NULL DEFAULT 0",
        "estado": "ALTER TABLE activos ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo'",
        "fecha": "ALTER TABLE activos ADD COLUMN fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "usuario": "ALTER TABLE activos ADD COLUMN usuario TEXT",
    }
    for col, alter_sql in optional_cols.items():
        if col not in cols:
            conn.execute(alter_sql)


def _load_activos_df() -> pd.DataFrame:
    query = """
        SELECT
            id,
            equipo,
            categoria,
            inversion,
            unidad,
            desgaste,
            modelo,
            costo_hora,
            fecha,
            COALESCE(activo, 1) AS activo
        FROM activos
        WHERE COALESCE(activo, 1) = 1
        ORDER BY id DESC
    """

    for _ in range(2):
        with db_transaction() as conn:
            _ensure_activos_schema(conn)
            try:
                rows = conn.execute(query).fetchall()
                break
            except sqlite3.OperationalError as exc:
                if "no such table: activos" not in str(exc).lower():
                    raise
    else:
        rows = []
    if not rows:
        return pd.DataFrame(
            columns=["id", "equipo", "categoria", "inversion", "unidad", "desgaste", "modelo", "costo_hora", "fecha", "activo"]
        )

    df = pd.DataFrame([dict(r) for r in rows])
    df["inversion"] = pd.to_numeric(df["inversion"], errors="coerce").fillna(0.0)
    df["desgaste"] = pd.to_numeric(df["desgaste"], errors="coerce").fillna(0.0)
    ranking_riesgo = df["desgaste"].rank(pct=True, method="average").fillna(0)
    df["riesgo"] = np.where(
        ranking_riesgo >= 0.80,
        "🔴 Alto",
        np.where(ranking_riesgo >= 0.50, "🟠 Medio", "🟢 Bajo"),
    )
    return df


def _crear_activo(
    usuario: str,
    equipo: str,
    tipo_unidad: str,
    categoria: str,
    inversion: float,
    vida_util: int,
    modelo: str,
) -> int:
    equipo = require_text(equipo, "Nombre del activo")
    categoria = require_text(categoria, "Categoría")
    tipo_unidad = require_text(tipo_unidad, "Tipo de equipo")
    inversion = as_positive(inversion, "Inversión", allow_zero=False)
    vida_util = max(1, int(vida_util or 1))
    desgaste_unitario = inversion / vida_util

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO activos
            (equipo, modelo, categoria, inversion, unidad, desgaste, costo_hora, usuario, activo, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'activo')
            """,
            (equipo, (modelo or "").strip() or None, categoria, inversion, tipo_unidad, desgaste_unitario, 0.0, usuario),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (equipo, "CREACIÓN", f"Registro inicial (vida útil: {vida_util})", inversion, usuario),
        )
        return int(cur.lastrowid)


def _actualizar_activo(
    usuario: str,
    activo_id: int,
    activo_nombre: str,
    nueva_inversion: float,
    nueva_vida: int,
    nueva_categoria: str,
    nuevo_modelo: str,
    nueva_unidad: str,
) -> None:
    nueva_inversion = as_positive(nueva_inversion, "Inversión")
    nueva_vida = max(1, int(nueva_vida or 1))
    nuevo_desgaste = (nueva_inversion / nueva_vida) if nueva_inversion > 0 else 0.0

    with db_transaction() as conn:
        _ensure_activos_schema(conn)
        conn.execute(
            """
            UPDATE activos
            SET inversion = ?, categoria = ?, desgaste = ?, modelo = ?, unidad = ?, usuario = ?
            WHERE id = ?
            """,
            (nueva_inversion, nueva_categoria, nuevo_desgaste, (nuevo_modelo or "").strip() or None, nueva_unidad, usuario, int(activo_id)),
        )
        conn.execute(
            """
            INSERT INTO activos_historial (activo, accion, detalle, costo, usuario)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                activo_nombre,
                "EDICIÓN",
                f"Actualización de valores (vida útil: {nueva_vida}, categoría: {nueva_categoria})",
                nueva_inversion,
                usuario,
            ),
        )


# =========================================================
# INTERFAZ ACTIVOS
# =========================================================

def render_activos(usuario: str):
    role = st.session_state.get("rol", "Admin")
    if role not in ALLOWED_ROLES:
        st.error("🚫 Acceso denegado. Solo Admin/Administración puede gestionar activos.")
        return

    st.title("🏗️ Gestión Integral de Activos")

    try:
        df = _load_activos_df()
    except Exception as e:
        st.error(f"Error al cargar activos: {e}")
        return

    if not df.empty:
        st.subheader("🧠 Salud de Activos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inversión instalada", f"$ {df['inversion'].sum():,.2f}")
        m2.metric("Desgaste promedio", f"$ {df['desgaste'].mean():.4f}/uso")
        m3.metric("Activos en riesgo alto", int((df["riesgo"] == "🔴 Alto").sum()))
        activo_critico = df.sort_values("desgaste", ascending=False).iloc[0]["equipo"]
        m4.metric("Activo más crítico", str(activo_critico))

        with st.expander("🔎 Activos con prioridad de mantenimiento", expanded=False):
            st.dataframe(
                df.sort_values("desgaste", ascending=False)[
                    ["equipo", "categoria", "unidad", "inversion", "desgaste", "riesgo"]
                ].head(10),
                use_container_width=True,
                hide_index=True,
            )
            fig_riesgo = px.histogram(
                df,
                x="riesgo",
                color="riesgo",
                title="Distribución de riesgo por desgaste",
                category_orders={"riesgo": ["🔴 Alto", "🟠 Medio", "🟢 Bajo"]},
            )
            st.plotly_chart(fig_riesgo, use_container_width=True)

    with st.expander("➕ Registrar Nuevo Activo"):
        with st.form("form_activos_pro"):
            c1, c2 = st.columns(2)
            nombre_eq = c1.text_input("Nombre del Activo")
            tipo_unidad = c2.selectbox("Tipo de Equipo", TIPOS_UNIDAD)

            c3, c4, c5 = st.columns(3)
            monto_inv = c3.number_input("Inversión ($)", min_value=0.0, step=10.0)
            vida_util = c4.number_input("Vida Útil (Usos)", min_value=1, value=1000, step=1)
            categoria = c5.selectbox("Categoría", CATEGORIAS)

            modelo = st.text_input("Modelo (opcional)")
            guardar = st.form_submit_button("🚀 Guardar Activo")

        if guardar:
            try:
                aid = _crear_activo(
                    usuario=usuario,
                    equipo=nombre_eq,
                    tipo_unidad=tipo_unidad,
                    categoria=categoria,
                    inversion=monto_inv,
                    vida_util=int(vida_util),
                    modelo=modelo,
                )
                st.success(f"✅ Activo registrado correctamente. ID #{aid}")
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar activo: {e}")

    st.divider()

    with st.expander("✏️ Editar Activo Existente"):
        if df.empty:
            st.info("No hay activos para editar.")
        else:
            opciones = {f"{row.equipo} · {row.unidad}": int(row.id) for row in df.itertuples()}
            label = st.selectbox("Seleccionar activo:", list(opciones.keys()))
            activo_id = opciones[label]
            datos = df[df["id"] == activo_id].iloc[0]

            vida_sugerida = int(max(1, round(datos["inversion"] / max(datos["desgaste"], 1e-9)))) if datos["inversion"] > 0 else 1000
            categoria_actual = str(datos.get("categoria") or "Otro")
            unidad_actual = str(datos.get("unidad") or "Otro")
            idx_categoria = CATEGORIAS.index(categoria_actual) if categoria_actual in CATEGORIAS else len(CATEGORIAS) - 1
            idx_unidad = TIPOS_UNIDAD.index(unidad_actual) if unidad_actual in TIPOS_UNIDAD else len(TIPOS_UNIDAD) - 1

            with st.form("editar_activo"):
                e1, e2, e3 = st.columns(3)
                nueva_inv = e1.number_input("Inversión ($)", min_value=0.0, value=float(datos["inversion"]), step=10.0)
                nueva_vida = e2.number_input("Vida útil", min_value=1, value=int(vida_sugerida), step=1)
                nueva_cat = e3.selectbox("Categoría", CATEGORIAS, index=idx_categoria)

                u1, u2 = st.columns(2)
                nueva_unidad = u1.selectbox("Tipo de Equipo", TIPOS_UNIDAD, index=idx_unidad)
                nuevo_modelo = u2.text_input("Modelo", value=str(datos.get("modelo") or ""))

                guardar_edicion = st.form_submit_button("💾 Guardar Cambios")

            if guardar_edicion:
                try:
                    _actualizar_activo(
                        usuario=usuario,
                        activo_id=activo_id,
                        activo_nombre=str(datos["equipo"]),
                        nueva_inversion=float(nueva_inv),
                        nueva_vida=int(nueva_vida),
                        nueva_categoria=nueva_cat,
                        nuevo_modelo=nuevo_modelo,
                        nueva_unidad=nueva_unidad,
                    )
                    st.success("✅ Activo actualizado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al actualizar activo: {e}")

    st.divider()

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "🖨️ Impresoras",
        "✂️ Corte / Plotter",
        "🔥 Planchas",
        "🧰 Otros",
        "📊 Resumen Global",
        "📜 Historial",
    ])

    if df.empty:
        with t1:
            st.info("No hay activos registrados todavía.")
        return

    with t1:
        st.subheader("Impresoras")
        df_imp = df[df["unidad"].fillna("").str.contains("Impresora", case=False)]
        st.dataframe(df_imp, use_container_width=True, hide_index=True)

    with t2:
        st.subheader("Corte / Plotter")
        df_corte = df[df["unidad"].fillna("").str.contains("Corte|Plotter|Cameo", case=False)]
        st.dataframe(df_corte, use_container_width=True, hide_index=True)

    with t3:
        st.subheader("Planchas de Sublimación")
        df_plancha = df[df["unidad"].fillna("").str.contains("Plancha|Sublim", case=False)]
        st.dataframe(df_plancha, use_container_width=True, hide_index=True)

    with t4:
        st.subheader("Otros equipos")
        mask_otro = ~df["unidad"].fillna("").str.contains("Impresora|Corte|Plotter|Cameo|Plancha|Sublim", case=False)
        st.dataframe(df[mask_otro], use_container_width=True, hide_index=True)

    with t5:
        c_inv, c_des, c_prom = st.columns(3)
        c_inv.metric("Inversión Total", f"$ {df['inversion'].sum():,.2f}")
        c_des.metric("Activos Registrados", len(df))
        c_prom.metric("Desgaste Promedio por Uso", f"$ {df['desgaste'].mean():.4f}")

        fig = px.bar(df, x="equipo", y="inversion", color="categoria", title="Distribución de Inversión por Activo")
        st.plotly_chart(fig, use_container_width=True)

    with t6:
        st.subheader("Historial de Movimientos de Activos")
        try:
            with db_transaction() as conn:
                _ensure_activos_schema(conn)
                hist = conn.execute(
                    """
                    SELECT activo, accion, detalle, costo, usuario, fecha
                    FROM activos_historial
                    ORDER BY fecha DESC, id DESC
                    """
                ).fetchall()
            df_hist = pd.DataFrame([dict(r) for r in hist])
            if df_hist.empty:
                st.info("No hay movimientos registrados aún.")
            else:
                st.dataframe(df_hist, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error cargando historial: {e}")
