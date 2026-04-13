from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, require_text


ESTADOS_RUTA = (
    "activa",
    "inactiva",
)

TIPOS_RECURSO = (
    "maquina",
    "operario",
    "insumo",
    "control_calidad",
    "transporte",
    "otro",
)


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _filter_df(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df

    q = clean_text(query)
    if not q:
        return df

    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(q, case=False, na=False)
    return df[mask]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_rutas_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rutas_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                producto_tipo TEXT,
                descripcion TEXT,
                estado TEXT NOT NULL DEFAULT 'activa',
                tiempo_total_min REAL NOT NULL DEFAULT 0,
                costo_base_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rutas_produccion_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ruta_id INTEGER NOT NULL,
                secuencia INTEGER NOT NULL DEFAULT 1,
                proceso TEXT NOT NULL,
                centro_trabajo TEXT,
                maquina TEXT,
                operario TEXT,
                insumo_principal TEXT,
                tiempo_estimado_min REAL NOT NULL DEFAULT 0,
                costo_estimado_usd REAL NOT NULL DEFAULT 0,
                punto_control INTEGER NOT NULL DEFAULT 0,
                requiere_mantenimiento INTEGER NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (ruta_id) REFERENCES rutas_produccion(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rutas_produccion_recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ruta_id INTEGER NOT NULL,
                detalle_id INTEGER,
                tipo_recurso TEXT NOT NULL DEFAULT 'otro',
                nombre TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 1,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (ruta_id) REFERENCES rutas_produccion(id),
                FOREIGN KEY (detalle_id) REFERENCES rutas_produccion_detalle(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rutas_produccion_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                ruta_id INTEGER NOT NULL,
                accion TEXT NOT NULL,
                detalle TEXT,
                FOREIGN KEY (ruta_id) REFERENCES rutas_produccion(id)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_rutas_codigo ON rutas_produccion(codigo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rutas_estado ON rutas_produccion(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rutas_detalle_ruta ON rutas_produccion_detalle(ruta_id, secuencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rutas_recursos_ruta ON rutas_produccion_recursos(ruta_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rutas_historial_ruta ON rutas_produccion_historial(ruta_id, fecha)")


# ============================================================
# CORE
# ============================================================

def _recalcular_ruta(conn, ruta_id: int) -> None:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(tiempo_estimado_min), 0) AS tiempo_total,
            COALESCE(SUM(costo_estimado_usd), 0) AS costo_total
        FROM rutas_produccion_detalle
        WHERE ruta_id = ?
        """,
        (int(ruta_id),),
    ).fetchone()

    tiempo_total = float(row["tiempo_total"] or 0.0) if row else 0.0
    costo_total = float(row["costo_total"] or 0.0) if row else 0.0

    conn.execute(
        """
        UPDATE rutas_produccion
        SET tiempo_total_min = ?,
            costo_base_usd = ?,
            actualizado_en = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (tiempo_total, costo_total, int(ruta_id)),
    )


def _log_ruta(conn, usuario: str, ruta_id: int, accion: str, detalle: str = "") -> None:
    conn.execute(
        """
        INSERT INTO rutas_produccion_historial (usuario, ruta_id, accion, detalle)
        VALUES (?, ?, ?, ?)
        """,
        (
            clean_text(usuario) or "Sistema",
            int(ruta_id),
            clean_text(accion) or "actualizacion",
            clean_text(detalle),
        ),
    )


def crear_ruta_produccion(
    usuario: str,
    codigo: str,
    nombre: str,
    producto_tipo: str = "",
    descripcion: str = "",
    estado: str = "activa",
    observaciones: str = "",
) -> int:
    _ensure_rutas_tables()

    codigo = require_text(codigo, "Código")
    nombre = require_text(nombre, "Nombre")
    estado = clean_text(estado).lower() or "activa"
    if estado not in ESTADOS_RUTA:
        estado = "activa"

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO rutas_produccion (
                usuario,
                codigo,
                nombre,
                producto_tipo,
                descripcion,
                estado,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_text(usuario) or "Sistema",
                codigo,
                nombre,
                clean_text(producto_tipo),
                clean_text(descripcion),
                estado,
                clean_text(observaciones),
            ),
        )
        ruta_id = int(cur.lastrowid)
        _log_ruta(conn, usuario, ruta_id, "crear_ruta", f"Ruta creada: {codigo} - {nombre}")
        return ruta_id


def actualizar_ruta_produccion(
    usuario: str,
    ruta_id: int,
    codigo: str,
    nombre: str,
    producto_tipo: str,
    descripcion: str,
    estado: str,
    observaciones: str,
) -> None:
    _ensure_rutas_tables()

    codigo = require_text(codigo, "Código")
    nombre = require_text(nombre, "Nombre")
    estado = clean_text(estado).lower() or "activa"
    if estado not in ESTADOS_RUTA:
        estado = "activa"

    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE rutas_produccion
            SET codigo = ?,
                nombre = ?,
                producto_tipo = ?,
                descripcion = ?,
                estado = ?,
                observaciones = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                codigo,
                nombre,
                clean_text(producto_tipo),
                clean_text(descripcion),
                estado,
                clean_text(observaciones),
                int(ruta_id),
            ),
        )
        _log_ruta(conn, usuario, ruta_id, "actualizar_ruta", f"Ruta actualizada: {codigo}")


def agregar_paso_ruta(
    usuario: str,
    ruta_id: int,
    secuencia: int,
    proceso: str,
    centro_trabajo: str = "",
    maquina: str = "",
    operario: str = "",
    insumo_principal: str = "",
    tiempo_estimado_min: float = 0.0,
    costo_estimado_usd: float = 0.0,
    punto_control: bool = False,
    requiere_mantenimiento: bool = False,
    observaciones: str = "",
) -> int:
    _ensure_rutas_tables()

    proceso = require_text(proceso, "Proceso")
    secuencia = max(1, int(secuencia))
    tiempo_estimado_min = max(0.0, float(tiempo_estimado_min or 0.0))
    costo_estimado_usd = max(0.0, float(costo_estimado_usd or 0.0))

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO rutas_produccion_detalle (
                ruta_id,
                secuencia,
                proceso,
                centro_trabajo,
                maquina,
                operario,
                insumo_principal,
                tiempo_estimado_min,
                costo_estimado_usd,
                punto_control,
                requiere_mantenimiento,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(ruta_id),
                int(secuencia),
                proceso,
                clean_text(centro_trabajo),
                clean_text(maquina),
                clean_text(operario),
                clean_text(insumo_principal),
                float(tiempo_estimado_min),
                float(costo_estimado_usd),
                1 if punto_control else 0,
                1 if requiere_mantenimiento else 0,
                clean_text(observaciones),
            ),
        )
        detalle_id = int(cur.lastrowid)
        _recalcular_ruta(conn, int(ruta_id))
        _log_ruta(conn, usuario, ruta_id, "agregar_paso", f"Paso {secuencia}: {proceso}")
        return detalle_id


def actualizar_paso_ruta(
    usuario: str,
    detalle_id: int,
    secuencia: int,
    proceso: str,
    centro_trabajo: str,
    maquina: str,
    operario: str,
    insumo_principal: str,
    tiempo_estimado_min: float,
    costo_estimado_usd: float,
    punto_control: bool,
    requiere_mantenimiento: bool,
    observaciones: str,
) -> None:
    _ensure_rutas_tables()

    proceso = require_text(proceso, "Proceso")

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT ruta_id FROM rutas_produccion_detalle WHERE id = ?",
            (int(detalle_id),),
        ).fetchone()
        if not row:
            raise ValueError("Paso no encontrado.")

        ruta_id = int(row["ruta_id"])

        conn.execute(
            """
            UPDATE rutas_produccion_detalle
            SET secuencia = ?,
                proceso = ?,
                centro_trabajo = ?,
                maquina = ?,
                operario = ?,
                insumo_principal = ?,
                tiempo_estimado_min = ?,
                costo_estimado_usd = ?,
                punto_control = ?,
                requiere_mantenimiento = ?,
                observaciones = ?
            WHERE id = ?
            """,
            (
                max(1, int(secuencia)),
                proceso,
                clean_text(centro_trabajo),
                clean_text(maquina),
                clean_text(operario),
                clean_text(insumo_principal),
                max(0.0, float(tiempo_estimado_min or 0.0)),
                max(0.0, float(costo_estimado_usd or 0.0)),
                1 if punto_control else 0,
                1 if requiere_mantenimiento else 0,
                clean_text(observaciones),
                int(detalle_id),
            ),
        )

        _recalcular_ruta(conn, ruta_id)
        _log_ruta(conn, usuario, ruta_id, "actualizar_paso", f"Paso actualizado #{detalle_id}")


def eliminar_paso_ruta(usuario: str, detalle_id: int) -> None:
    _ensure_rutas_tables()

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT ruta_id, proceso FROM rutas_produccion_detalle WHERE id = ?",
            (int(detalle_id),),
        ).fetchone()
        if not row:
            raise ValueError("Paso no encontrado.")

        ruta_id = int(row["ruta_id"])
        proceso = str(row["proceso"] or "")

        conn.execute("DELETE FROM rutas_produccion_recursos WHERE detalle_id = ?", (int(detalle_id),))
        conn.execute("DELETE FROM rutas_produccion_detalle WHERE id = ?", (int(detalle_id),))

        _recalcular_ruta(conn, ruta_id)
        _log_ruta(conn, usuario, ruta_id, "eliminar_paso", f"Paso eliminado: {proceso}")


def agregar_recurso_ruta(
    ruta_id: int,
    detalle_id: int | None,
    tipo_recurso: str,
    nombre: str,
    cantidad: float = 1.0,
    unidad: str = "unidad",
    costo_unitario_usd: float = 0.0,
    observaciones: str = "",
) -> int:
    _ensure_rutas_tables()

    tipo_recurso = clean_text(tipo_recurso).lower() or "otro"
    if tipo_recurso not in TIPOS_RECURSO:
        tipo_recurso = "otro"

    nombre = require_text(nombre, "Nombre del recurso")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO rutas_produccion_recursos (
                ruta_id,
                detalle_id,
                tipo_recurso,
                nombre,
                cantidad,
                unidad,
                costo_unitario_usd,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(ruta_id),
                int(detalle_id) if detalle_id else None,
                tipo_recurso,
                nombre,
                max(0.0, float(cantidad or 0.0)),
                clean_text(unidad) or "unidad",
                max(0.0, float(costo_unitario_usd or 0.0)),
                clean_text(observaciones),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# LOADERS
# ============================================================

def _load_rutas_df() -> pd.DataFrame:
    _ensure_rutas_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                actualizado_en,
                usuario,
                codigo,
                nombre,
                producto_tipo,
                descripcion,
                estado,
                tiempo_total_min,
                costo_base_usd,
                observaciones
            FROM rutas_produccion
            ORDER BY actualizado_en DESC, id DESC
            """,
            conn,
        )


def _load_ruta_detalle_df(ruta_id: int) -> pd.DataFrame:
    _ensure_rutas_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                ruta_id,
                secuencia,
                proceso,
                centro_trabajo,
                maquina,
                operario,
                insumo_principal,
                tiempo_estimado_min,
                costo_estimado_usd,
                punto_control,
                requiere_mantenimiento,
                observaciones
            FROM rutas_produccion_detalle
            WHERE ruta_id = ?
            ORDER BY secuencia ASC, id ASC
            """,
            conn,
            params=(int(ruta_id),),
        )


def _load_ruta_recursos_df(ruta_id: int) -> pd.DataFrame:
    _ensure_rutas_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                ruta_id,
                detalle_id,
                tipo_recurso,
                nombre,
                cantidad,
                unidad,
                costo_unitario_usd,
                observaciones
            FROM rutas_produccion_recursos
            WHERE ruta_id = ?
            ORDER BY tipo_recurso ASC, nombre ASC, id ASC
            """,
            conn,
            params=(int(ruta_id),),
        )


def _load_ruta_historial_df(ruta_id: int) -> pd.DataFrame:
    _ensure_rutas_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                accion,
                detalle
            FROM rutas_produccion_historial
            WHERE ruta_id = ?
            ORDER BY fecha DESC, id DESC
            """,
            conn,
            params=(int(ruta_id),),
        )


# ============================================================
# UI
# ============================================================

def _render_dashboard() -> None:
    st.subheader("📊 Resumen de rutas")

    df = _load_rutas_df()
    if df.empty:
        st.info("No hay rutas de producción registradas.")
        return

    activas = int((df["estado"].astype(str).str.lower() == "activa").sum())
    inactivas = int((df["estado"].astype(str).str.lower() == "inactiva").sum())
    tiempo_total = float(pd.to_numeric(df["tiempo_total_min"], errors="coerce").fillna(0).sum())
    costo_total = float(pd.to_numeric(df["costo_base_usd"], errors="coerce").fillna(0).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rutas", len(df))
    c2.metric("Activas", activas)
    c3.metric("Tiempo total min", f"{tiempo_total:,.0f}")
    c4.metric("Costo base USD", f"$ {costo_total:,.2f}")

    estado_df = df.groupby("estado", as_index=False)["id"].count().rename(columns={"id": "cantidad"})
    if not estado_df.empty:
        st.markdown("#### Estado de rutas")
        st.bar_chart(estado_df.set_index("estado")["cantidad"])

    top = df.sort_values("tiempo_total_min", ascending=False).head(10)
    st.markdown("#### Rutas con mayor tiempo estimado")
    st.dataframe(
        top[["codigo", "nombre", "producto_tipo", "estado", "tiempo_total_min", "costo_base_usd"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "tiempo_total_min": st.column_config.NumberColumn("Tiempo min", format="%.2f"),
            "costo_base_usd": st.column_config.NumberColumn("Costo base USD", format="%.2f"),
        },
    )


def _render_rutas(usuario: str) -> None:
    st.subheader("🧭 Rutas de producción")

    df = _load_rutas_df()

    if not df.empty:
        q1, q2 = st.columns([2, 1])
        buscar = q1.text_input("Buscar ruta", key="ruta_buscar")
        estado = q2.selectbox("Estado", ["todos", "activa", "inactiva"], key="ruta_estado")

        view = _filter_df(df.copy(), buscar, ["codigo", "nombre", "producto_tipo", "descripcion", "observaciones"])
        if estado != "todos":
            view = view[view["estado"].astype(str).str.lower() == estado]

        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "tiempo_total_min": st.column_config.NumberColumn("Tiempo min", format="%.2f"),
                "costo_base_usd": st.column_config.NumberColumn("Costo base USD", format="%.2f"),
            },
        )
    else:
        st.info("No hay rutas registradas todavía.")

    st.divider()
    st.subheader("➕ Registrar / Editar ruta")

    ruta_existente = None
    if not df.empty:
        ruta_sel = st.selectbox(
            "Editar ruta existente (opcional)",
            options=[None] + df["id"].tolist(),
            format_func=lambda x: "Nueva ruta" if x is None else f"{df[df['id'] == x]['codigo'].iloc[0]} · {df[df['id'] == x]['nombre'].iloc[0]}",
            key="ruta_edit_sel",
        )
        if ruta_sel is not None:
            ruta_existente = df[df["id"] == ruta_sel].iloc[0]

    with st.form("form_ruta_produccion"):
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código", value="" if ruta_existente is None else str(ruta_existente["codigo"]))
        nombre = c2.text_input("Nombre", value="" if ruta_existente is None else str(ruta_existente["nombre"]))
        producto_tipo = c3.text_input(
            "Tipo de producto",
            value="" if ruta_existente is None else str(ruta_existente["producto_tipo"]),
        )

        descripcion = st.text_area(
            "Descripción",
            value="" if ruta_existente is None else str(ruta_existente["descripcion"]),
        )

        c4, c5 = st.columns(2)
        estado_ruta = c4.selectbox(
            "Estado",
            ESTADOS_RUTA,
            index=ESTADOS_RUTA.index(str(ruta_existente["estado"]).lower()) if ruta_existente is not None and str(ruta_existente["estado"]).lower() in ESTADOS_RUTA else 0,
        )
        observaciones = c5.text_input(
            "Observaciones",
            value="" if ruta_existente is None else str(ruta_existente["observaciones"]),
        )

        guardar = st.form_submit_button("💾 Guardar ruta", use_container_width=True)

    if guardar:
        try:
            if ruta_existente is None:
                rid = crear_ruta_produccion(
                    usuario=usuario,
                    codigo=codigo,
                    nombre=nombre,
                    producto_tipo=producto_tipo,
                    descripcion=descripcion,
                    estado=estado_ruta,
                    observaciones=observaciones,
                )
                st.success(f"Ruta creada correctamente. ID #{rid}")
            else:
                actualizar_ruta_produccion(
                    usuario=usuario,
                    ruta_id=int(ruta_existente["id"]),
                    codigo=codigo,
                    nombre=nombre,
                    producto_tipo=producto_tipo,
                    descripcion=descripcion,
                    estado=estado_ruta,
                    observaciones=observaciones,
                )
                st.success("Ruta actualizada correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar la ruta: {exc}")


def _render_pasos(usuario: str) -> None:
    st.subheader("🪜 Pasos de la ruta")

    df_rutas = _load_rutas_df()
    if df_rutas.empty:
        st.info("Primero debes crear una ruta.")
        return

    ruta_id = st.selectbox(
        "Ruta",
        df_rutas["id"].tolist(),
        format_func=lambda x: f"{df_rutas[df_rutas['id'] == x]['codigo'].iloc[0]} · {df_rutas[df_rutas['id'] == x]['nombre'].iloc[0]}",
        key="ruta_pasos_ruta_id",
    )

    df_det = _load_ruta_detalle_df(int(ruta_id))

    with st.form("form_paso_ruta"):
        c1, c2, c3 = st.columns(3)
        secuencia = c1.number_input("Secuencia", min_value=1, value=int(len(df_det) + 1), step=1)
        proceso = c2.text_input("Proceso")
        centro_trabajo = c3.text_input("Centro de trabajo")

        c4, c5, c6 = st.columns(3)
        maquina = c4.text_input("Máquina")
        operario = c5.text_input("Operario")
        insumo_principal = c6.text_input("Insumo principal")

        c7, c8, c9 = st.columns(3)
        tiempo = c7.number_input("Tiempo estimado (min)", min_value=0.0, value=0.0, format="%.2f")
        costo = c8.number_input("Costo estimado USD", min_value=0.0, value=0.0, format="%.2f")
        punto_control = c9.checkbox("Punto de control")

        requiere_mantenimiento = st.checkbox("Requiere validación de mantenimiento")
        observaciones = st.text_area("Observaciones del paso")

        guardar_paso = st.form_submit_button("➕ Agregar paso", use_container_width=True)

    if guardar_paso:
        try:
            agregar_paso_ruta(
                usuario=usuario,
                ruta_id=int(ruta_id),
                secuencia=int(secuencia),
                proceso=proceso,
                centro_trabajo=centro_trabajo,
                maquina=maquina,
                operario=operario,
                insumo_principal=insumo_principal,
                tiempo_estimado_min=float(tiempo),
                costo_estimado_usd=float(costo),
                punto_control=bool(punto_control),
                requiere_mantenimiento=bool(requiere_mantenimiento),
                observaciones=observaciones,
            )
            st.success("Paso agregado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo agregar el paso: {exc}")

    if df_det.empty:
        st.caption("Esta ruta aún no tiene pasos.")
        return

    st.markdown("### Detalle de pasos")
    st.dataframe(
        df_det,
        use_container_width=True,
        hide_index=True,
        column_config={
            "tiempo_estimado_min": st.column_config.NumberColumn("Tiempo min", format="%.2f"),
            "costo_estimado_usd": st.column_config.NumberColumn("Costo USD", format="%.2f"),
        },
    )

    st.markdown("### ✏️ Editar / eliminar paso")
    paso_id = st.selectbox(
        "Paso",
        df_det["id"].tolist(),
        format_func=lambda x: f"Paso #{x} · {df_det[df_det['id'] == x]['proceso'].iloc[0]}",
        key="ruta_paso_edit_id",
    )
    paso = df_det[df_det["id"] == paso_id].iloc[0]

    p1, p2, p3 = st.columns(3)
    secuencia_n = p1.number_input("Secuencia ", min_value=1, value=int(_safe_int(paso["secuencia"], 1)), step=1)
    proceso_n = p2.text_input("Proceso ", value=str(paso["proceso"] or ""))
    centro_n = p3.text_input("Centro trabajo ", value=str(paso["centro_trabajo"] or ""))

    p4, p5, p6 = st.columns(3)
    maquina_n = p4.text_input("Máquina ", value=str(paso["maquina"] or ""))
    operario_n = p5.text_input("Operario ", value=str(paso["operario"] or ""))
    insumo_n = p6.text_input("Insumo principal ", value=str(paso["insumo_principal"] or ""))

    p7, p8 = st.columns(2)
    tiempo_n = p7.number_input("Tiempo min ", min_value=0.0, value=float(_safe_float(paso["tiempo_estimado_min"])), format="%.2f")
    costo_n = p8.number_input("Costo USD ", min_value=0.0, value=float(_safe_float(paso["costo_estimado_usd"])), format="%.2f")

    p9, p10 = st.columns(2)
    punto_n = p9.checkbox("Punto control ", value=bool(_safe_int(paso["punto_control"], 0)))
    mant_n = p10.checkbox("Requiere mantenimiento ", value=bool(_safe_int(paso["requiere_mantenimiento"], 0)))

    obs_n = st.text_area("Observaciones ", value=str(paso["observaciones"] or ""))

    b1, b2 = st.columns(2)
    if b1.button("💾 Actualizar paso", use_container_width=True):
        try:
            actualizar_paso_ruta(
                usuario=usuario,
                detalle_id=int(paso_id),
                secuencia=int(secuencia_n),
                proceso=proceso_n,
                centro_trabajo=centro_n,
                maquina=maquina_n,
                operario=operario_n,
                insumo_principal=insumo_n,
                tiempo_estimado_min=float(tiempo_n),
                costo_estimado_usd=float(costo_n),
                punto_control=bool(punto_n),
                requiere_mantenimiento=bool(mant_n),
                observaciones=obs_n,
            )
            st.success("Paso actualizado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar el paso: {exc}")

    if b2.button("🗑 Eliminar paso", use_container_width=True):
        try:
            eliminar_paso_ruta(usuario=usuario, detalle_id=int(paso_id))
            st.success("Paso eliminado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo eliminar el paso: {exc}")


def _render_recursos() -> None:
    st.subheader("🧰 Recursos por ruta")

    df_rutas = _load_rutas_df()
    if df_rutas.empty:
        st.info("Primero debes crear una ruta.")
        return

    ruta_id = st.selectbox(
        "Ruta de recursos",
        df_rutas["id"].tolist(),
        format_func=lambda x: f"{df_rutas[df_rutas['id'] == x]['codigo'].iloc[0]} · {df_rutas[df_rutas['id'] == x]['nombre'].iloc[0]}",
        key="ruta_recursos_ruta_id",
    )

    df_det = _load_ruta_detalle_df(int(ruta_id))
    df_rec = _load_ruta_recursos_df(int(ruta_id))

    with st.form("form_recurso_ruta"):
        c1, c2, c3 = st.columns(3)
        detalle_id = c1.selectbox(
            "Paso asociado (opcional)",
            options=[None] + df_det["id"].tolist(),
            format_func=lambda x: "General de la ruta" if x is None else f"#{x} · {df_det[df_det['id'] == x]['proceso'].iloc[0]}",
        )
        tipo_recurso = c2.selectbox("Tipo de recurso", TIPOS_RECURSO)
        nombre = c3.text_input("Nombre del recurso")

        c4, c5, c6 = st.columns(3)
        cantidad = c4.number_input("Cantidad", min_value=0.0, value=1.0, format="%.2f")
        unidad = c5.text_input("Unidad", value="unidad")
        costo_u = c6.number_input("Costo unitario USD", min_value=0.0, value=0.0, format="%.2f")

        observaciones = st.text_input("Observaciones")
        guardar = st.form_submit_button("➕ Agregar recurso", use_container_width=True)

    if guardar:
        try:
            agregar_recurso_ruta(
                ruta_id=int(ruta_id),
                detalle_id=int(detalle_id) if detalle_id else None,
                tipo_recurso=tipo_recurso,
                nombre=nombre,
                cantidad=float(cantidad),
                unidad=unidad,
                costo_unitario_usd=float(costo_u),
                observaciones=observaciones,
            )
            st.success("Recurso agregado.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo agregar el recurso: {exc}")

    if df_rec.empty:
        st.caption("No hay recursos cargados para esta ruta.")
    else:
        st.dataframe(
            df_rec,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
                "costo_unitario_usd": st.column_config.NumberColumn("Costo USD", format="%.2f"),
            },
        )


def _render_historial() -> None:
    st.subheader("🕓 Historial de cambios")

    df_rutas = _load_rutas_df()
    if df_rutas.empty:
        st.info("No hay rutas registradas.")
        return

    ruta_id = st.selectbox(
        "Ruta para historial",
        df_rutas["id"].tolist(),
        format_func=lambda x: f"{df_rutas[df_rutas['id'] == x]['codigo'].iloc[0]} · {df_rutas[df_rutas['id'] == x]['nombre'].iloc[0]}",
        key="ruta_hist_ruta_id",
    )

    df_hist = _load_ruta_historial_df(int(ruta_id))
    if df_hist.empty:
        st.info("No hay historial registrado para esta ruta.")
    else:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)


def render_rutas_produccion(usuario: str) -> None:
    _ensure_rutas_tables()

    st.subheader("🧭 Rutas de producción")
    st.caption(
        "Define secuencias, tiempos, máquinas, operarios, insumos y puntos de control para cada ruta."
    )

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "🧭 Rutas",
            "🪜 Pasos",
            "🧰 Recursos",
            "🕓 Historial",
        ]
    )

    with tabs[0]:
        _render_dashboard()

    with tabs[1]:
        _render_rutas(usuario)

    with tabs[2]:
        _render_pasos(usuario)

    with tabs[3]:
        _render_recursos()

    with tabs[4]:
        _render_historial()
