rom __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, require_text


ESTADOS_CALIDAD = (
    "Pendiente",
    "Aprobado",
    "Aprobado con observación",
    "Rechazado",
    "En reproceso",
)

TIPOS_DEFECTO = (
    "Corte incorrecto",
    "Color incorrecto",
    "Medida incorrecta",
    "Acabado deficiente",
    "Material defectuoso",
    "Error de impresión",
    "Empaque incorrecto",
    "Daño por manipulación",
    "Falla de máquina",
    "Error humano",
    "Otro",
)

ACCIONES_CORRECTIVAS = (
    "Ninguna",
    "Reprocesar",
    "Desechar",
    "Ajustar máquina",
    "Capacitación",
    "Cambiar material",
    "Reinspeccionar",
    "Otro",
)

AREAS_CALIDAD = (
    "Producción",
    "Corte",
    "Sublimación",
    "Manual",
    "Despacho",
    "Inventario",
    "General",
)


# ============================================================
# SCHEMA
# ============================================================

def _ensure_control_calidad_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS control_calidad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                area TEXT,
                orden_produccion_id INTEGER,
                lote TEXT,
                producto TEXT NOT NULL,
                cliente TEXT,
                responsable TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                cantidad_producida REAL DEFAULT 0,
                cantidad_aprobada REAL DEFAULT 0,
                cantidad_rechazada REAL DEFAULT 0,
                cantidad_reproceso REAL DEFAULT 0,
                porcentaje_calidad REAL DEFAULT 0,
                color_ok INTEGER DEFAULT 1,
                medida_ok INTEGER DEFAULT 1,
                acabado_ok INTEGER DEFAULT 1,
                empaque_ok INTEGER DEFAULT 1,
                funcionamiento_ok INTEGER DEFAULT 1,
                observaciones TEXT,
                accion_correctiva TEXT DEFAULT 'Ninguna',
                fecha_compromiso TEXT,
                costo_no_calidad_usd REAL DEFAULT 0,
                estado_registro TEXT NOT NULL DEFAULT 'activo'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS control_calidad_defectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                control_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo_defecto TEXT NOT NULL,
                severidad TEXT DEFAULT 'Media',
                cantidad REAL DEFAULT 1,
                descripcion TEXT,
                responsable TEXT,
                requiere_merma INTEGER DEFAULT 0,
                requiere_reproceso INTEGER DEFAULT 0,
                costo_estimado_usd REAL DEFAULT 0,
                FOREIGN KEY (control_id) REFERENCES control_calidad(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS control_calidad_acciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                control_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                accion TEXT NOT NULL,
                responsable TEXT,
                fecha_compromiso TEXT,
                estado TEXT DEFAULT 'pendiente',
                comentario TEXT,
                FOREIGN KEY (control_id) REFERENCES control_calidad(id)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_fecha ON control_calidad(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_estado ON control_calidad(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_area ON control_calidad(area)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_producto ON control_calidad(producto)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_defectos_control ON control_calidad_defectos(control_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calidad_acciones_control ON control_calidad_acciones(control_id)")


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_text(value: Any) -> str:
    return clean_text("" if value is None else str(value))


def _safe_date_text(value: str) -> str | None:
    txt = clean_text(value)
    if not txt:
        return None
    try:
        return pd.to_datetime(txt).date().isoformat()
    except Exception:
        return None


def _porcentaje_calidad(producida: float, aprobada: float) -> float:
    producida = max(float(producida or 0.0), 0.0)
    aprobada = max(float(aprobada or 0.0), 0.0)
    if producida <= 0:
        return 0.0
    return round((aprobada / producida) * 100.0, 2)


def _clasificar_semaforo(pct: float) -> str:
    pct = float(pct or 0.0)
    if pct >= 95:
        return "Excelente"
    if pct >= 85:
        return "Aceptable"
    return "Crítico"


def _bool_to_int(value: bool) -> int:
    return 1 if bool(value) else 0


def _sum_ok_checks(row: pd.Series) -> int:
    checks = [
        int(row.get("color_ok", 0) or 0),
        int(row.get("medida_ok", 0) or 0),
        int(row.get("acabado_ok", 0) or 0),
        int(row.get("empaque_ok", 0) or 0),
        int(row.get("funcionamiento_ok", 0) or 0),
    ]
    return sum(checks)


def _load_production_orders() -> pd.DataFrame:
    """
    Intenta leer una tabla de planificación/producción si existe.
    Si no existe, retorna DataFrame vacío para no romper el módulo.
    """
    with db_transaction() as conn:
        tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
        table_names = {str(r["name"]) for r in tables}

        posibles = [
            "planificacion_produccion",
            "ordenes_produccion",
            "produccion_ordenes",
        ]
        tabla = next((t for t in posibles if t in table_names), None)

        if not tabla:
            return pd.DataFrame()

        try:
            return pd.read_sql_query(f"SELECT * FROM {tabla} ORDER BY id DESC", conn)
        except Exception:
            return pd.DataFrame()


def _try_register_merma_from_quality(
    usuario: str,
    producto: str,
    cantidad: float,
    motivo: str,
    costo_estimado_usd: float = 0.0,
) -> tuple[bool, str]:
    """
    Intenta registrar merma si existe una tabla compatible.
    No rompe el sistema si no existe.
    """
    cantidad = float(cantidad or 0.0)
    if cantidad <= 0:
        return False, "Cantidad de merma no válida."

    with db_transaction() as conn:
        tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """
        ).fetchall()
        table_names = {str(r["name"]) for r in tables}

        posibles = [
            "mermas_desperdicio",
            "mermas",
            "desperdicios",
        ]
        tabla = next((t for t in posibles if t in table_names), None)
        if not tabla:
            return False, "No existe tabla de mermas integrada."

        columnas = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
        cols = {str(c["name"]) if isinstance(c, dict) else str(c[1]) for c in columnas}

        payload: dict[str, Any] = {}
        if "usuario" in cols:
            payload["usuario"] = usuario
        if "producto" in cols:
            payload["producto"] = producto
        if "cantidad" in cols:
            payload["cantidad"] = cantidad
        if "motivo" in cols:
            payload["motivo"] = motivo
        if "descripcion" in cols:
            payload["descripcion"] = motivo
        if "tipo" in cols:
            payload["tipo"] = "Merma de calidad"
        if "costo_estimado_usd" in cols:
            payload["costo_estimado_usd"] = float(costo_estimado_usd or 0.0)
        if "fecha" in cols:
            payload["fecha"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if "estado" in cols:
            payload["estado"] = "activo"

        if not payload:
            return False, "La tabla de mermas existe pero no tiene columnas compatibles."

        fields = ", ".join(payload.keys())
        marks = ", ".join(["?"] * len(payload))
        conn.execute(
            f"INSERT INTO {tabla} ({fields}) VALUES ({marks})",
            tuple(payload.values()),
        )
        return True, "Merma registrada en módulo de mermas."


# ============================================================
# LOADERS
# ============================================================

def _load_control_calidad_df() -> pd.DataFrame:
    _ensure_control_calidad_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                actualizado_en,
                usuario,
                area,
                orden_produccion_id,
                lote,
                producto,
                cliente,
                responsable,
                estado,
                cantidad_producida,
                cantidad_aprobada,
                cantidad_rechazada,
                cantidad_reproceso,
                porcentaje_calidad,
                color_ok,
                medida_ok,
                acabado_ok,
                empaque_ok,
                funcionamiento_ok,
                observaciones,
                accion_correctiva,
                fecha_compromiso,
                costo_no_calidad_usd
            FROM control_calidad
            WHERE COALESCE(estado_registro, 'activo') = 'activo'
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )

    if df.empty:
        return df

    num_cols = [
        "cantidad_producida",
        "cantidad_aprobada",
        "cantidad_rechazada",
        "cantidad_reproceso",
        "porcentaje_calidad",
        "costo_no_calidad_usd",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    for col in ["color_ok", "medida_ok", "acabado_ok", "empaque_ok", "funcionamiento_ok"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["semaforo"] = df["porcentaje_calidad"].apply(_clasificar_semaforo)
    df["checks_ok"] = df.apply(_sum_ok_checks, axis=1)
    return df


def _load_defectos_df(control_id: int | None = None) -> pd.DataFrame:
    _ensure_control_calidad_tables()
    sql = """
        SELECT
            id,
            control_id,
            fecha,
            tipo_defecto,
            severidad,
            cantidad,
            descripcion,
            responsable,
            requiere_merma,
            requiere_reproceso,
            costo_estimado_usd
        FROM control_calidad_defectos
    """
    params: tuple[Any, ...] = ()
    if control_id is not None:
        sql += " WHERE control_id=?"
        params = (int(control_id),)
    sql += " ORDER BY fecha DESC, id DESC"

    with db_transaction() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        return df

    for col in ["cantidad", "costo_estimado_usd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _load_acciones_df(control_id: int | None = None) -> pd.DataFrame:
    _ensure_control_calidad_tables()
    sql = """
        SELECT
            id,
            control_id,
            fecha,
            accion,
            responsable,
            fecha_compromiso,
            estado,
            comentario
        FROM control_calidad_acciones
    """
    params: tuple[Any, ...] = ()
    if control_id is not None:
        sql += " WHERE control_id=?"
        params = (int(control_id),)
    sql += " ORDER BY fecha DESC, id DESC"

    with db_transaction() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    return df


# ============================================================
# REGISTRO
# ============================================================

def registrar_control_calidad(
    usuario: str,
    area: str,
    producto: str,
    cliente: str,
    responsable: str,
    estado: str,
    cantidad_producida: float,
    cantidad_aprobada: float,
    cantidad_rechazada: float,
    cantidad_reproceso: float,
    observaciones: str = "",
    accion_correctiva: str = "Ninguna",
    fecha_compromiso: str | None = None,
    costo_no_calidad_usd: float = 0.0,
    orden_produccion_id: int | None = None,
    lote: str = "",
    color_ok: bool = True,
    medida_ok: bool = True,
    acabado_ok: bool = True,
    empaque_ok: bool = True,
    funcionamiento_ok: bool = True,
) -> int:
    producto = require_text(producto, "Producto")
    area = require_text(area, "Área")
    estado = require_text(estado, "Estado")

    cantidad_producida = max(float(cantidad_producida or 0.0), 0.0)
    cantidad_aprobada = max(float(cantidad_aprobada or 0.0), 0.0)
    cantidad_rechazada = max(float(cantidad_rechazada or 0.0), 0.0)
    cantidad_reproceso = max(float(cantidad_reproceso or 0.0), 0.0)
    costo_no_calidad_usd = max(float(costo_no_calidad_usd or 0.0), 0.0)

    if cantidad_producida <= 0:
        raise ValueError("La cantidad producida debe ser mayor a cero.")

    if (cantidad_aprobada + cantidad_rechazada + cantidad_reproceso) > cantidad_producida + 0.0001:
        raise ValueError("La suma de aprobada + rechazada + reproceso no puede superar la cantidad producida.")

    porcentaje = _porcentaje_calidad(cantidad_producida, cantidad_aprobada)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO control_calidad (
                usuario,
                area,
                orden_produccion_id,
                lote,
                producto,
                cliente,
                responsable,
                estado,
                cantidad_producida,
                cantidad_aprobada,
                cantidad_rechazada,
                cantidad_reproceso,
                porcentaje_calidad,
                color_ok,
                medida_ok,
                acabado_ok,
                empaque_ok,
                funcionamiento_ok,
                observaciones,
                accion_correctiva,
                fecha_compromiso,
                costo_no_calidad_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                area,
                int(orden_produccion_id) if orden_produccion_id else None,
                clean_text(lote),
                producto,
                clean_text(cliente),
                clean_text(responsable),
                estado,
                cantidad_producida,
                cantidad_aprobada,
                cantidad_rechazada,
                cantidad_reproceso,
                porcentaje,
                _bool_to_int(color_ok),
                _bool_to_int(medida_ok),
                _bool_to_int(acabado_ok),
                _bool_to_int(empaque_ok),
                _bool_to_int(funcionamiento_ok),
                clean_text(observaciones),
                clean_text(accion_correctiva) or "Ninguna",
                fecha_compromiso,
                costo_no_calidad_usd,
            ),
        )
        return int(cur.lastrowid)


def registrar_defecto_calidad(
    control_id: int,
    tipo_defecto: str,
    severidad: str,
    cantidad: float,
    descripcion: str,
    responsable: str,
    requiere_merma: bool,
    requiere_reproceso: bool,
    costo_estimado_usd: float = 0.0,
    usuario: str = "Sistema",
    producto: str = "",
) -> int:
    tipo_defecto = require_text(tipo_defecto, "Tipo de defecto")
    severidad = clean_text(severidad) or "Media"
    cantidad = max(float(cantidad or 0.0), 0.0)
    costo_estimado_usd = max(float(costo_estimado_usd or 0.0), 0.0)

    if cantidad <= 0:
        raise ValueError("La cantidad del defecto debe ser mayor a cero.")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO control_calidad_defectos (
                control_id,
                tipo_defecto,
                severidad,
                cantidad,
                descripcion,
                responsable,
                requiere_merma,
                requiere_reproceso,
                costo_estimado_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(control_id),
                tipo_defecto,
                severidad,
                cantidad,
                clean_text(descripcion),
                clean_text(responsable),
                _bool_to_int(requiere_merma),
                _bool_to_int(requiere_reproceso),
                costo_estimado_usd,
            ),
        )
        defecto_id = int(cur.lastrowid)

    if requiere_merma and producto:
        _try_register_merma_from_quality(
            usuario=usuario,
            producto=producto,
            cantidad=cantidad,
            motivo=f"Merma por calidad · {tipo_defecto}",
            costo_estimado_usd=costo_estimado_usd,
        )

    return defecto_id


def registrar_accion_calidad(
    control_id: int,
    accion: str,
    responsable: str,
    fecha_compromiso: str | None,
    comentario: str,
) -> int:
    accion = require_text(accion, "Acción")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO control_calidad_acciones (
                control_id,
                accion,
                responsable,
                fecha_compromiso,
                estado,
                comentario
            )
            VALUES (?, ?, ?, ?, 'pendiente', ?)
            """,
            (
                int(control_id),
                accion,
                clean_text(responsable),
                fecha_compromiso,
                clean_text(comentario),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# DASHBOARD
# ============================================================

def _render_dashboard_calidad(df: pd.DataFrame, df_def: pd.DataFrame) -> None:
    st.subheader("📊 Dashboard de Calidad")

    if df.empty:
        st.info("No hay inspecciones de calidad registradas.")
        return

    total_registros = int(len(df))
    promedio_calidad = float(df["porcentaje_calidad"].mean()) if not df.empty else 0.0
    total_rechazado = float(df["cantidad_rechazada"].sum()) if not df.empty else 0.0
    costo_no_calidad = float(df["costo_no_calidad_usd"].sum()) if not df.empty else 0.0
    pendientes = int((df["estado"] == "Pendiente").sum()) if not df.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Inspecciones", total_registros)
    c2.metric("% calidad promedio", f"{promedio_calidad:,.2f}%")
    c3.metric("Rechazado total", f"{total_rechazado:,.2f}")
    c4.metric("Costo no calidad", f"$ {costo_no_calidad:,.2f}")
    c5.metric("Pendientes", pendientes)

    g1, g2 = st.columns(2)

    with g1:
        por_estado = df.groupby("estado", as_index=False)["id"].count().rename(columns={"id": "cantidad"})
        if not por_estado.empty:
            fig_estado = px.bar(
                por_estado,
                x="estado",
                y="cantidad",
                color="estado",
                title="Inspecciones por estado",
            )
            st.plotly_chart(fig_estado, use_container_width=True)

    with g2:
        por_area = df.groupby("area", as_index=False)["porcentaje_calidad"].mean()
        if not por_area.empty:
            fig_area = px.bar(
                por_area,
                x="area",
                y="porcentaje_calidad",
                color="area",
                title="Calidad promedio por área",
            )
            st.plotly_chart(fig_area, use_container_width=True)

    g3, g4 = st.columns(2)

    with g3:
        tendencia = (
            df.assign(dia=pd.to_datetime(df["fecha"], errors="coerce").dt.date)
            .groupby("dia", as_index=False)["porcentaje_calidad"]
            .mean()
            .sort_values("dia")
        )
        if not tendencia.empty:
            fig_tend = px.line(tendencia, x="dia", y="porcentaje_calidad", title="Tendencia de calidad")
            st.plotly_chart(fig_tend, use_container_width=True)

    with g4:
        if not df_def.empty:
            top_def = (
                df_def.groupby("tipo_defecto", as_index=False)["cantidad"]
                .sum()
                .sort_values("cantidad", ascending=False)
                .head(10)
            )
            if not top_def.empty:
                fig_def = px.bar(top_def, x="tipo_defecto", y="cantidad", color="tipo_defecto", title="Top defectos")
                st.plotly_chart(fig_def, use_container_width=True)

    st.markdown("### Resumen operativo")
    view = df[
        [
            "fecha",
            "area",
            "producto",
            "cliente",
            "estado",
            "cantidad_producida",
            "cantidad_aprobada",
            "cantidad_rechazada",
            "cantidad_reproceso",
            "porcentaje_calidad",
            "semaforo",
        ]
    ].copy()

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad_producida": st.column_config.NumberColumn("Producida", format="%.2f"),
            "cantidad_aprobada": st.column_config.NumberColumn("Aprobada", format="%.2f"),
            "cantidad_rechazada": st.column_config.NumberColumn("Rechazada", format="%.2f"),
            "cantidad_reproceso": st.column_config.NumberColumn("Reproceso", format="%.2f"),
            "porcentaje_calidad": st.column_config.NumberColumn("% Calidad", format="%.2f"),
        },
    )


# ============================================================
# REGISTRO UI
# ============================================================

def _render_registro_calidad(usuario: str) -> None:
    st.subheader("🧪 Registrar inspección de calidad")

    df_op = _load_production_orders()

    with st.form("form_control_calidad"):
        c1, c2, c3, c4 = st.columns(4)
        area = c1.selectbox("Área", AREAS_CALIDAD)
        producto = c2.text_input("Producto")
        cliente = c3.text_input("Cliente")
        responsable = c4.text_input("Responsable")

        o1, o2 = st.columns(2)
        if not df_op.empty and "id" in df_op.columns:
            orden_id = o1.selectbox(
                "Orden de producción (opcional)",
                options=[None] + df_op["id"].tolist(),
                format_func=lambda x: "Sin orden asociada" if x is None else f"Orden #{x}",
            )
        else:
            orden_id = None
            o1.caption("No hay órdenes de producción disponibles.")
        lote = o2.text_input("Lote")

        c5, c6, c7, c8 = st.columns(4)
        cantidad_producida = c5.number_input("Cantidad producida", min_value=0.0, value=1.0, format="%.2f")
        cantidad_aprobada = c6.number_input("Cantidad aprobada", min_value=0.0, value=1.0, format="%.2f")
        cantidad_rechazada = c7.number_input("Cantidad rechazada", min_value=0.0, value=0.0, format="%.2f")
        cantidad_reproceso = c8.number_input("Cantidad reproceso", min_value=0.0, value=0.0, format="%.2f")

        i1, i2, i3, i4, i5 = st.columns(5)
        color_ok = i1.checkbox("Color OK", value=True)
        medida_ok = i2.checkbox("Medida OK", value=True)
        acabado_ok = i3.checkbox("Acabado OK", value=True)
        empaque_ok = i4.checkbox("Empaque OK", value=True)
        funcionamiento_ok = i5.checkbox("Funcionamiento OK", value=True)

        p_calc = _porcentaje_calidad(cantidad_producida, cantidad_aprobada)
        st.caption(f"Calidad estimada: {p_calc:,.2f}% · Nivel: {_clasificar_semaforo(p_calc)}")

        c9, c10, c11 = st.columns(3)
        estado = c9.selectbox("Estado", ESTADOS_CALIDAD)
        accion_correctiva = c10.selectbox("Acción correctiva", ACCIONES_CORRECTIVAS)
        fecha_compromiso = c11.text_input("Fecha compromiso (YYYY-MM-DD)")

        c12, c13 = st.columns([2, 1])
        observaciones = c12.text_area("Observaciones")
        costo_no_calidad = c13.number_input("Costo no calidad USD", min_value=0.0, value=0.0, format="%.2f")

        guardar = st.form_submit_button("💾 Guardar inspección", use_container_width=True)

    if guardar:
        try:
            cid = registrar_control_calidad(
                usuario=usuario,
                area=area,
                producto=producto,
                cliente=cliente,
                responsable=responsable,
                estado=estado,
                cantidad_producida=float(cantidad_producida),
                cantidad_aprobada=float(cantidad_aprobada),
                cantidad_rechazada=float(cantidad_rechazada),
                cantidad_reproceso=float(cantidad_reproceso),
                observaciones=observaciones,
                accion_correctiva=accion_correctiva,
                fecha_compromiso=_safe_date_text(fecha_compromiso),
                costo_no_calidad_usd=float(costo_no_calidad),
                orden_produccion_id=int(orden_id) if orden_id else None,
                lote=lote,
                color_ok=color_ok,
                medida_ok=medida_ok,
                acabado_ok=acabado_ok,
                empaque_ok=empaque_ok,
                funcionamiento_ok=funcionamiento_ok,
            )
            st.success(f"Inspección registrada correctamente. ID #{cid}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar la inspección: {exc}")


# ============================================================
# DEFECTOS UI
# ============================================================

def _render_defectos_tab(usuario: str, df: pd.DataFrame) -> None:
    st.subheader("🚨 Defectos de calidad")

    if df.empty:
        st.info("Primero debes registrar una inspección de calidad.")
        return

    ids = df[["id", "producto", "fecha"]].copy()

    with st.form("form_defecto_calidad"):
        control_id = st.selectbox(
            "Inspección",
            options=ids["id"].tolist(),
            format_func=lambda x: (
                f"#{x} · {ids.loc[ids['id'] == x, 'producto'].iloc[0]} · "
                f"{ids.loc[ids['id'] == x, 'fecha'].iloc[0]}"
            ),
        )

        row_control = df[df["id"] == control_id].iloc[0]

        d1, d2, d3, d4 = st.columns(4)
        tipo_defecto = d1.selectbox("Tipo de defecto", TIPOS_DEFECTO)
        severidad = d2.selectbox("Severidad", ["Baja", "Media", "Alta", "Crítica"])
        cantidad = d3.number_input("Cantidad afectada", min_value=0.01, value=1.0, format="%.2f")
        costo_estimado = d4.number_input("Costo estimado USD", min_value=0.0, value=0.0, format="%.2f")

        d5, d6, d7 = st.columns(3)
        responsable = d5.text_input("Responsable")
        requiere_merma = d6.checkbox("Enviar a merma", value=False)
        requiere_reproceso = d7.checkbox("Enviar a reproceso", value=False)

        descripcion = st.text_area("Descripción del defecto")
        guardar = st.form_submit_button("➕ Registrar defecto", use_container_width=True)

    if guardar:
        try:
            did = registrar_defecto_calidad(
                control_id=int(control_id),
                tipo_defecto=tipo_defecto,
                severidad=severidad,
                cantidad=float(cantidad),
                descripcion=descripcion,
                responsable=responsable,
                requiere_merma=requiere_merma,
                requiere_reproceso=requiere_reproceso,
                costo_estimado_usd=float(costo_estimado),
                usuario=usuario,
                producto=str(row_control["producto"]),
            )
            st.success(f"Defecto registrado correctamente. ID #{did}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar el defecto: {exc}")

    st.markdown("### Historial de defectos")
    df_def = _load_defectos_df()
    if df_def.empty:
        st.caption("Sin defectos registrados.")
        return

    st.dataframe(
        df_def,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
            "costo_estimado_usd": st.column_config.NumberColumn("Costo estimado USD", format="%.2f"),
        },
    )


# ============================================================
# ACCIONES UI
# ============================================================

def _render_acciones_tab(df: pd.DataFrame) -> None:
    st.subheader("🛠️ Acciones correctivas")

    if df.empty:
        st.info("Primero registra una inspección.")
        return

    ids = df[["id", "producto"]].copy()

    with st.form("form_accion_calidad"):
        control_id = st.selectbox(
            "Inspección",
            options=ids["id"].tolist(),
            format_func=lambda x: f"#{x} · {ids.loc[ids['id'] == x, 'producto'].iloc[0]}",
            key="calidad_accion_control",
        )
        a1, a2, a3 = st.columns(3)
        accion = a1.selectbox("Acción", ACCIONES_CORRECTIVAS)
        responsable = a2.text_input("Responsable", key="calidad_accion_resp")
        fecha_compromiso = a3.text_input("Fecha compromiso (YYYY-MM-DD)", key="calidad_accion_fecha")
        comentario = st.text_area("Comentario", key="calidad_accion_coment")
        guardar = st.form_submit_button("💾 Registrar acción", use_container_width=True)

    if guardar:
        try:
            aid = registrar_accion_calidad(
                control_id=int(control_id),
                accion=accion,
                responsable=responsable,
                fecha_compromiso=_safe_date_text(fecha_compromiso),
                comentario=comentario,
            )
            st.success(f"Acción registrada. ID #{aid}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar la acción: {exc}")

    df_acc = _load_acciones_df()
    if df_acc.empty:
        st.caption("Sin acciones registradas.")
        return

    st.markdown("### Historial de acciones")
    st.dataframe(df_acc, use_container_width=True, hide_index=True)


# ============================================================
# HISTORIAL UI
# ============================================================

def _render_historial_tab(df: pd.DataFrame) -> None:
    st.subheader("📋 Historial de inspecciones")

    if df.empty:
        st.info("No hay inspecciones registradas.")
        return

    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    buscar = f1.text_input("Buscar producto / cliente / responsable", key="calidad_hist_buscar")
    area = f2.selectbox("Área", ["Todas"] + list(AREAS_CALIDAD), key="calidad_hist_area")
    estado = f3.selectbox("Estado", ["Todos"] + list(ESTADOS_CALIDAD), key="calidad_hist_estado")
    semaforo = f4.selectbox("Nivel", ["Todos", "Excelente", "Aceptable", "Crítico"], key="calidad_hist_semaforo")

    view = df.copy()

    if buscar:
        txt = clean_text(buscar)
        view = view[
            view["producto"].astype(str).str.contains(txt, case=False, na=False)
            | view["cliente"].astype(str).str.contains(txt, case=False, na=False)
            | view["responsable"].astype(str).str.contains(txt, case=False, na=False)
            | view["observaciones"].astype(str).str.contains(txt, case=False, na=False)
        ]

    if area != "Todas":
        view = view[view["area"].astype(str) == area]

    if estado != "Todos":
        view = view[view["estado"].astype(str) == estado]

    if semaforo != "Todos":
        view = view[view["semaforo"].astype(str) == semaforo]

    st.dataframe(
        view[
            [
                "id",
                "fecha",
                "area",
                "producto",
                "cliente",
                "responsable",
                "estado",
                "cantidad_producida",
                "cantidad_aprobada",
                "cantidad_rechazada",
                "cantidad_reproceso",
                "porcentaje_calidad",
                "checks_ok",
                "semaforo",
                "accion_correctiva",
                "costo_no_calidad_usd",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad_producida": st.column_config.NumberColumn("Producida", format="%.2f"),
            "cantidad_aprobada": st.column_config.NumberColumn("Aprobada", format="%.2f"),
            "cantidad_rechazada": st.column_config.NumberColumn("Rechazada", format="%.2f"),
            "cantidad_reproceso": st.column_config.NumberColumn("Reproceso", format="%.2f"),
            "porcentaje_calidad": st.column_config.NumberColumn("% Calidad", format="%.2f"),
            "costo_no_calidad_usd": st.column_config.NumberColumn("Costo no calidad", format="%.2f"),
        },
    )


# ============================================================
# REPORTES UI
# ============================================================

def _render_reportes_tab(df: pd.DataFrame, df_def: pd.DataFrame) -> None:
    st.subheader("📈 Reportes de calidad")

    if df.empty:
        st.info("No hay datos para reportar.")
        return

    r1, r2, r3 = st.columns(3)
    desde = r1.date_input("Desde", value=date.today() - timedelta(days=30), key="calidad_rep_desde")
    hasta = r2.date_input("Hasta", value=date.today(), key="calidad_rep_hasta")
    area = r3.selectbox("Área reporte", ["Todas"] + list(AREAS_CALIDAD), key="calidad_rep_area")

    view = df.copy()
    view["fecha_dt"] = pd.to_datetime(view["fecha"], errors="coerce").dt.date
    view = view[(view["fecha_dt"] >= desde) & (view["fecha_dt"] <= hasta)]

    if area != "Todas":
        view = view[view["area"] == area]

    if view.empty:
        st.warning("No hay datos en el rango seleccionado.")
        return

    st.metric("Calidad promedio del periodo", f"{float(view['porcentaje_calidad'].mean()):,.2f}%")

    export_df = view.copy()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name="ControlCalidad")
        if not df_def.empty:
            df_def.to_excel(writer, index=False, sheet_name="Defectos")

    st.download_button(
        "📥 Exportar reporte Excel",
        buffer.getvalue(),
        file_name=f"control_calidad_{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown("### Tabla exportable")
    st.dataframe(export_df, use_container_width=True, hide_index=True)


# ============================================================
# UI PRINCIPAL
# ============================================================

def render_control_calidad(usuario: str) -> None:
    _ensure_control_calidad_tables()

    st.subheader("✅ Control de calidad")
    st.caption(
        "Inspección, defectos, acciones correctivas, reproceso, costo de no calidad "
        "e integración opcional con mermas."
    )

    df = _load_control_calidad_df()
    df_def = _load_defectos_df()

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "🧪 Registrar inspección",
            "🚨 Defectos",
            "🛠️ Acciones",
            "📋 Historial",
            "📈 Reportes",
        ]
    )

    with tabs[0]:
        _render_dashboard_calidad(df, df_def)

    with tabs[1]:
        _render_registro_calidad(usuario)

    with tabs[2]:
        _render_defectos_tab(usuario, df)

    with tabs[3]:
        _render_acciones_tab(df)

    with tabs[4]:
        _render_historial_tab(df)

    with tabs[5]:
        _render_reportes_tab(df, df_def)





