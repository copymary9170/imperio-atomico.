rom __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


ESTADOS_PRODUCCION = (
    "planificada",
    "en_proceso",
    "pausada",
    "terminada",
    "entregada",
    "cancelada",
)

PRIORIDADES_PRODUCCION = (
    "baja",
    "media",
    "alta",
    "urgente",
)

ETAPAS_BASE_PRODUCCION = (
    "Diseño",
    "Preparación",
    "Producción",
    "Acabado",
    "Empaque",
    "Entrega",
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


def _safe_text(value: Any, default: str = "") -> str:
    txt = clean_text(value)
    return txt if txt else default


def _safe_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _filter_df(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    txt = clean_text(query)
    if not txt:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(txt, case=False, na=False)
    return df[mask]


def _priority_rank(value: str) -> int:
    m = {
        "urgente": 0,
        "alta": 1,
        "media": 2,
        "baja": 3,
    }
    return m.get(str(value).lower(), 99)


def _state_rank(value: str) -> int:
    m = {
        "en_proceso": 0,
        "planificada": 1,
        "pausada": 2,
        "terminada": 3,
        "entregada": 4,
        "cancelada": 5,
    }
    return m.get(str(value).lower(), 99)


# ============================================================
# SCHEMA
# ============================================================

def _ensure_produccion_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS produccion_ordenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                cliente_id INTEGER,
                venta_id INTEGER,
                cotizacion_id INTEGER,
                titulo TEXT NOT NULL,
                producto TEXT NOT NULL,
                descripcion TEXT,
                cantidad REAL NOT NULL DEFAULT 1,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                fecha_inicio TEXT,
                fecha_entrega TEXT,
                prioridad TEXT NOT NULL DEFAULT 'media',
                estado TEXT NOT NULL DEFAULT 'planificada',
                responsable TEXT,
                equipo TEXT,
                costo_materiales_usd REAL NOT NULL DEFAULT 0,
                costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
                costo_indirecto_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                porcentaje_avance REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                FOREIGN KEY (venta_id) REFERENCES ventas(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS produccion_materiales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                inventario_id INTEGER,
                material TEXT NOT NULL,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                cantidad_requerida REAL NOT NULL DEFAULT 0,
                cantidad_consumida REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                observaciones TEXT,
                FOREIGN KEY (orden_id) REFERENCES produccion_ordenes(id),
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS produccion_etapas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                responsable TEXT,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                fecha_inicio TEXT,
                fecha_fin TEXT,
                porcentaje REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                orden INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (orden_id) REFERENCES produccion_ordenes(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS produccion_incidencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                tipo TEXT NOT NULL DEFAULT 'observacion',
                detalle TEXT NOT NULL,
                impacto TEXT,
                accion_tomada TEXT,
                FOREIGN KEY (orden_id) REFERENCES produccion_ordenes(id)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_orden_estado ON produccion_ordenes(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_orden_fecha_entrega ON produccion_ordenes(fecha_entrega)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_orden_prioridad ON produccion_ordenes(prioridad)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_mat_orden ON produccion_materiales(orden_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_etapas_orden ON produccion_etapas(orden_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_inc_orden ON produccion_incidencias(orden_id)")


# ============================================================
# LOADERS
# ============================================================

def _load_clientes_df() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, nombre
                FROM clientes
                WHERE COALESCE(estado, 'activo')='activo'
                ORDER BY nombre ASC
                """
            ).fetchall()
        return pd.DataFrame(rows, columns=["id", "nombre"])
    except Exception:
        return pd.DataFrame(columns=["id", "nombre"])


def _load_ventas_df() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, fecha, total_usd
                FROM ventas
                WHERE COALESCE(estado, 'registrada')='registrada'
                ORDER BY fecha DESC, id DESC
                LIMIT 500
                """
            ).fetchall()
        return pd.DataFrame(rows, columns=["id", "fecha", "total_usd"])
    except Exception:
        return pd.DataFrame(columns=["id", "fecha", "total_usd"])


def _load_inventario_df() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    sku,
                    nombre,
                    unidad,
                    stock_actual,
                    costo_unitario_usd,
                    precio_venta_usd
                FROM inventario
                WHERE COALESCE(estado, 'activo')='activo'
                ORDER BY nombre ASC
                """
            ).fetchall()
        return pd.DataFrame(
            rows,
            columns=[
                "id",
                "sku",
                "nombre",
                "unidad",
                "stock_actual",
                "costo_unitario_usd",
                "precio_venta_usd",
            ],
        )
    except Exception:
        return pd.DataFrame(
            columns=[
                "id",
                "sku",
                "nombre",
                "unidad",
                "stock_actual",
                "costo_unitario_usd",
                "precio_venta_usd",
            ]
        )


def _load_ordenes_df() -> pd.DataFrame:
    _ensure_produccion_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                o.id,
                o.fecha,
                o.actualizado_en,
                o.usuario,
                o.cliente_id,
                o.venta_id,
                o.cotizacion_id,
                o.titulo,
                o.producto,
                o.descripcion,
                o.cantidad,
                o.unidad,
                o.fecha_inicio,
                o.fecha_entrega,
                o.prioridad,
                o.estado,
                o.responsable,
                o.equipo,
                o.costo_materiales_usd,
                o.costo_mano_obra_usd,
                o.costo_indirecto_usd,
                o.costo_total_usd,
                o.porcentaje_avance,
                o.observaciones,
                COALESCE(c.nombre, '') AS cliente
            FROM produccion_ordenes o
            LEFT JOIN clientes c ON c.id = o.cliente_id
            ORDER BY o.id DESC
            """,
            conn,
        )

    if df.empty:
        return df

    num_cols = [
        "cantidad",
        "costo_materiales_usd",
        "costo_mano_obra_usd",
        "costo_indirecto_usd",
        "costo_total_usd",
        "porcentaje_avance",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def _load_materiales_df(orden_id: int | None = None) -> pd.DataFrame:
    _ensure_produccion_tables()
    sql = """
        SELECT
            m.id,
            m.orden_id,
            o.titulo,
            o.producto,
            m.inventario_id,
            COALESCE(i.sku, '') AS sku,
            m.material,
            m.unidad,
            m.cantidad_requerida,
            m.cantidad_consumida,
            m.costo_unitario_usd,
            m.costo_total_usd,
            m.estado,
            m.observaciones,
            COALESCE(i.stock_actual, 0) AS stock_actual
        FROM produccion_materiales m
        JOIN produccion_ordenes o ON o.id = m.orden_id
        LEFT JOIN inventario i ON i.id = m.inventario_id
    """
    params: tuple[Any, ...] = ()
    if orden_id is not None:
        sql += " WHERE m.orden_id = ?"
        params = (int(orden_id),)
    sql += " ORDER BY m.id DESC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "orden_id",
            "titulo",
            "producto",
            "inventario_id",
            "sku",
            "material",
            "unidad",
            "cantidad_requerida",
            "cantidad_consumida",
            "costo_unitario_usd",
            "costo_total_usd",
            "estado",
            "observaciones",
            "stock_actual",
        ],
    )

    if not df.empty:
        for col in ["cantidad_requerida", "cantidad_consumida", "costo_unitario_usd", "costo_total_usd", "stock_actual"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def _load_etapas_df(orden_id: int | None = None) -> pd.DataFrame:
    _ensure_produccion_tables()
    sql = """
        SELECT
            e.id,
            e.orden_id,
            o.titulo,
            o.producto,
            e.nombre,
            e.responsable,
            e.estado,
            e.fecha_inicio,
            e.fecha_fin,
            e.porcentaje,
            e.observaciones,
            e.orden
        FROM produccion_etapas e
        JOIN produccion_ordenes o ON o.id = e.orden_id
    """
    params: tuple[Any, ...] = ()
    if orden_id is not None:
        sql += " WHERE e.orden_id = ?"
        params = (int(orden_id),)
    sql += " ORDER BY e.orden ASC, e.id ASC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "orden_id",
            "titulo",
            "producto",
            "nombre",
            "responsable",
            "estado",
            "fecha_inicio",
            "fecha_fin",
            "porcentaje",
            "observaciones",
            "orden",
        ],
    )

    if not df.empty:
        df["porcentaje"] = pd.to_numeric(df["porcentaje"], errors="coerce").fillna(0.0)

    return df


def _load_incidencias_df(orden_id: int | None = None) -> pd.DataFrame:
    _ensure_produccion_tables()
    sql = """
        SELECT
            i.id,
            i.orden_id,
            o.titulo,
            i.fecha,
            i.usuario,
            i.tipo,
            i.detalle,
            i.impacto,
            i.accion_tomada
        FROM produccion_incidencias i
        JOIN produccion_ordenes o ON o.id = i.orden_id
    """
    params: tuple[Any, ...] = ()
    if orden_id is not None:
        sql += " WHERE i.orden_id = ?"
        params = (int(orden_id),)
    sql += " ORDER BY i.fecha DESC, i.id DESC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    return pd.DataFrame(
        rows,
        columns=[
            "id",
            "orden_id",
            "titulo",
            "fecha",
            "usuario",
            "tipo",
            "detalle",
            "impacto",
            "accion_tomada",
        ],
    )


# ============================================================
# CORE
# ============================================================

def _recalcular_costos_y_avance(conn, orden_id: int) -> None:
    row_mat = conn.execute(
        """
        SELECT COALESCE(SUM(costo_total_usd), 0) AS total_materiales
        FROM produccion_materiales
        WHERE orden_id = ?
        """,
        (int(orden_id),),
    ).fetchone()
    total_materiales = float(row_mat["total_materiales"] or 0.0)

    row_orden = conn.execute(
        """
        SELECT costo_mano_obra_usd, costo_indirecto_usd
        FROM produccion_ordenes
        WHERE id = ?
        """,
        (int(orden_id),),
    ).fetchone()

    mano_obra = float(row_orden["costo_mano_obra_usd"] or 0.0) if row_orden else 0.0
    indirecto = float(row_orden["costo_indirecto_usd"] or 0.0) if row_orden else 0.0
    total = money(total_materiales + mano_obra + indirecto)

    etapas = conn.execute(
        """
        SELECT porcentaje
        FROM produccion_etapas
        WHERE orden_id = ?
        """,
        (int(orden_id),),
    ).fetchall()

    if etapas:
        avance = round(sum(float(r["porcentaje"] or 0.0) for r in etapas) / len(etapas), 2)
    else:
        avance = 0.0

    conn.execute(
        """
        UPDATE produccion_ordenes
        SET costo_materiales_usd=?,
            costo_total_usd=?,
            porcentaje_avance=?,
            actualizado_en=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (money(total_materiales), total, avance, int(orden_id)),
    )


def crear_orden_produccion(
    usuario: str,
    titulo: str,
    producto: str,
    cantidad: float,
    unidad: str,
    fecha_inicio: str | None = None,
    fecha_entrega: str | None = None,
    prioridad: str = "media",
    cliente_id: int | None = None,
    venta_id: int | None = None,
    cotizacion_id: int | None = None,
    descripcion: str = "",
    responsable: str = "",
    equipo: str = "",
    costo_mano_obra_usd: float = 0.0,
    costo_indirecto_usd: float = 0.0,
    observaciones: str = "",
    crear_etapas_base: bool = True,
) -> int:
    _ensure_produccion_tables()

    titulo = require_text(titulo, "Título")
    producto = require_text(producto, "Producto")
    unidad = require_text(unidad, "Unidad")
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_mano_obra_usd = as_positive(costo_mano_obra_usd, "Costo mano de obra", allow_zero=True)
    costo_indirecto_usd = as_positive(costo_indirecto_usd, "Costo indirecto", allow_zero=True)

    prioridad = clean_text(prioridad).lower() or "media"
    if prioridad not in PRIORIDADES_PRODUCCION:
        prioridad = "media"

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO produccion_ordenes (
                usuario,
                cliente_id,
                venta_id,
                cotizacion_id,
                titulo,
                producto,
                descripcion,
                cantidad,
                unidad,
                fecha_inicio,
                fecha_entrega,
                prioridad,
                estado,
                responsable,
                equipo,
                costo_materiales_usd,
                costo_mano_obra_usd,
                costo_indirecto_usd,
                costo_total_usd,
                porcentaje_avance,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'planificada', ?, ?, 0, ?, ?, ?, 0, ?)
            """,
            (
                usuario,
                int(cliente_id) if cliente_id else None,
                int(venta_id) if venta_id else None,
                int(cotizacion_id) if cotizacion_id else None,
                titulo,
                producto,
                clean_text(descripcion),
                float(cantidad),
                unidad,
                clean_text(fecha_inicio),
                clean_text(fecha_entrega),
                prioridad,
                clean_text(responsable),
                clean_text(equipo),
                money(costo_mano_obra_usd),
                money(costo_indirecto_usd),
                money(costo_mano_obra_usd + costo_indirecto_usd),
                clean_text(observaciones),
            ),
        )
        orden_id = int(cur.lastrowid)

        if crear_etapas_base:
            for idx, nombre in enumerate(ETAPAS_BASE_PRODUCCION, start=1):
                conn.execute(
                    """
                    INSERT INTO produccion_etapas (
                        orden_id, nombre, responsable, estado, porcentaje, orden
                    )
                    VALUES (?, ?, '', 'pendiente', 0, ?)
                    """,
                    (int(orden_id), str(nombre), int(idx)),
                )

        _recalcular_costos_y_avance(conn, int(orden_id))
        return int(orden_id)


def agregar_material_orden(
    orden_id: int,
    material: str,
    cantidad_requerida: float,
    unidad: str = "unidad",
    inventario_id: int | None = None,
    costo_unitario_usd: float = 0.0,
    observaciones: str = "",
) -> int:
    _ensure_produccion_tables()

    material = require_text(material, "Material")
    unidad = require_text(unidad, "Unidad")
    cantidad_requerida = as_positive(cantidad_requerida, "Cantidad requerida", allow_zero=False)
    costo_unitario_usd = as_positive(costo_unitario_usd, "Costo unitario", allow_zero=True)

    with db_transaction() as conn:
        if inventario_id:
            row = conn.execute(
                """
                SELECT nombre, unidad, costo_unitario_usd
                FROM inventario
                WHERE id = ? AND COALESCE(estado, 'activo')='activo'
                """,
                (int(inventario_id),),
            ).fetchone()
            if row:
                material = str(row["nombre"])
                unidad = str(row["unidad"] or unidad)
                costo_unitario_usd = float(row["costo_unitario_usd"] or costo_unitario_usd)

        cur = conn.execute(
            """
            INSERT INTO produccion_materiales (
                orden_id,
                inventario_id,
                material,
                unidad,
                cantidad_requerida,
                cantidad_consumida,
                costo_unitario_usd,
                costo_total_usd,
                estado,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'pendiente', ?)
            """,
            (
                int(orden_id),
                int(inventario_id) if inventario_id else None,
                material,
                unidad,
                float(cantidad_requerida),
                money(costo_unitario_usd),
                money(float(cantidad_requerida) * float(costo_unitario_usd)),
                clean_text(observaciones),
            ),
        )
        mat_id = int(cur.lastrowid)
        _recalcular_costos_y_avance(conn, int(orden_id))
        return mat_id


def consumir_material_orden(
    usuario: str,
    material_id: int,
    cantidad_consumida: float,
    descontar_inventario: bool = True,
) -> None:
    _ensure_produccion_tables()
    cantidad_consumida = as_positive(cantidad_consumida, "Cantidad consumida", allow_zero=False)

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                m.id,
                m.orden_id,
                m.inventario_id,
                m.material,
                m.cantidad_requerida,
                m.cantidad_consumida,
                m.costo_unitario_usd,
                m.unidad
            FROM produccion_materiales m
            WHERE m.id = ?
            """,
            (int(material_id),),
        ).fetchone()

        if not row:
            raise ValueError("Material no encontrado")

        acumulado = float(row["cantidad_consumida"] or 0.0) + float(cantidad_consumida)
        estado = "consumido" if acumulado >= float(row["cantidad_requerida"] or 0.0) else "parcial"

        if descontar_inventario and row["inventario_id"]:
            inv = conn.execute(
                "SELECT stock_actual FROM inventario WHERE id=? AND COALESCE(estado, 'activo')='activo'",
                (int(row["inventario_id"]),),
            ).fetchone()
            if not inv:
                raise ValueError("Ítem de inventario no encontrado")
            if float(inv["stock_actual"] or 0.0) < float(cantidad_consumida):
                raise ValueError("Stock insuficiente para consumir material")

            conn.execute(
                "UPDATE inventario SET stock_actual = stock_actual - ? WHERE id=?",
                (float(cantidad_consumida), int(row["inventario_id"])),
            )

            conn.execute(
                """
                INSERT INTO movimientos_inventario (
                    usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia
                )
                VALUES (?, ?, 'salida', ?, ?, ?)
                """,
                (
                    usuario,
                    int(row["inventario_id"]),
                    -abs(float(cantidad_consumida)),
                    float(row["costo_unitario_usd"] or 0.0),
                    f"Consumo producción · Orden #{int(row['orden_id'])} · {row['material']}",
                ),
            )

        conn.execute(
            """
            UPDATE produccion_materiales
            SET cantidad_consumida=?,
                estado=?,
                costo_total_usd=?,
                observaciones=COALESCE(observaciones, '')
            WHERE id=?
            """,
            (
                float(acumulado),
                estado,
                money(float(row["cantidad_requerida"] or 0.0) * float(row["costo_unitario_usd"] or 0.0)),
                int(material_id),
            ),
        )

        _recalcular_costos_y_avance(conn, int(row["orden_id"]))


def actualizar_etapa_produccion(
    etapa_id: int,
    estado: str,
    porcentaje: float,
    responsable: str = "",
    fecha_inicio: str = "",
    fecha_fin: str = "",
    observaciones: str = "",
) -> None:
    _ensure_produccion_tables()
    porcentaje = max(0.0, min(float(porcentaje or 0.0), 100.0))

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT orden_id FROM produccion_etapas WHERE id=?",
            (int(etapa_id),),
        ).fetchone()
        if not row:
            raise ValueError("Etapa no encontrada")

        conn.execute(
            """
            UPDATE produccion_etapas
            SET estado=?,
                porcentaje=?,
                responsable=?,
                fecha_inicio=?,
                fecha_fin=?,
                observaciones=?
            WHERE id=?
            """,
            (
                clean_text(estado),
                float(porcentaje),
                clean_text(responsable),
                clean_text(fecha_inicio),
                clean_text(fecha_fin),
                clean_text(observaciones),
                int(etapa_id),
            ),
        )

        orden_id = int(row["orden_id"])
        _recalcular_costos_y_avance(conn, orden_id)

        etapas = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN LOWER(COALESCE(estado,''))='terminada' OR porcentaje >= 100 THEN 1 ELSE 0 END) AS hechas
            FROM produccion_etapas
            WHERE orden_id=?
            """,
            (orden_id,),
        ).fetchone()

        total_etapas = int(etapas["total"] or 0)
        hechas = int(etapas["hechas"] or 0)

        nuevo_estado = None
        if total_etapas > 0 and hechas == total_etapas:
            nuevo_estado = "terminada"
        elif porcentaje > 0:
            nuevo_estado = "en_proceso"

        if nuevo_estado:
            conn.execute(
                """
                UPDATE produccion_ordenes
                SET estado=?, actualizado_en=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (nuevo_estado, orden_id),
            )


def actualizar_orden_produccion(
    orden_id: int,
    estado: str,
    prioridad: str,
    responsable: str,
    equipo: str,
    fecha_inicio: str,
    fecha_entrega: str,
    costo_mano_obra_usd: float,
    costo_indirecto_usd: float,
    observaciones: str,
) -> None:
    _ensure_produccion_tables()

    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE produccion_ordenes
            SET estado=?,
                prioridad=?,
                responsable=?,
                equipo=?,
                fecha_inicio=?,
                fecha_entrega=?,
                costo_mano_obra_usd=?,
                costo_indirecto_usd=?,
                observaciones=?,
                actualizado_en=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                clean_text(estado).lower(),
                clean_text(prioridad).lower(),
                clean_text(responsable),
                clean_text(equipo),
                clean_text(fecha_inicio),
                clean_text(fecha_entrega),
                money(costo_mano_obra_usd),
                money(costo_indirecto_usd),
                clean_text(observaciones),
                int(orden_id),
            ),
        )
        _recalcular_costos_y_avance(conn, int(orden_id))


def registrar_incidencia_produccion(
    usuario: str,
    orden_id: int,
    tipo: str,
    detalle: str,
    impacto: str = "",
    accion_tomada: str = "",
) -> int:
    _ensure_produccion_tables()
    detalle = require_text(detalle, "Detalle")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO produccion_incidencias (
                orden_id, usuario, tipo, detalle, impacto, accion_tomada
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(orden_id),
                clean_text(usuario),
                clean_text(tipo) or "observacion",
                detalle,
                clean_text(impacto),
                clean_text(accion_tomada),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# UI HELPERS
# ============================================================

def _render_dashboard(df: pd.DataFrame) -> None:
    st.subheader("📊 Dashboard de producción")

    if df.empty:
        st.info("No hay órdenes de producción registradas.")
        return

    activas = df[df["estado"].isin(["planificada", "en_proceso", "pausada"])].copy()
    vencidas = df[
        (df["fecha_entrega"].fillna("").astype(str) != "")
        & (df["estado"].isin(["planificada", "en_proceso", "pausada"]))
        & (pd.to_datetime(df["fecha_entrega"], errors="coerce").dt.date < date.today())
    ].copy()

    total_ordenes = int(len(df))
    activas_n = int(len(activas))
    terminadas = int((df["estado"] == "terminada").sum())
    entregadas = int((df["estado"] == "entregada").sum())
    costo_total = float(df["costo_total_usd"].sum())
    avance_prom = float(df["porcentaje_avance"].mean()) if not df.empty else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Órdenes", total_ordenes)
    c2.metric("Activas", activas_n)
    c3.metric("Terminadas", terminadas)
    c4.metric("Entregadas", entregadas)
    c5.metric("Vencidas", int(len(vencidas)))
    c6.metric("Costo total", f"$ {costo_total:,.2f}")

    st.progress(min(max(avance_prom / 100.0, 0.0), 1.0))
    st.caption(f"Avance promedio general: {avance_prom:.1f}%")

    g1, g2 = st.columns(2)

    with g1:
        estado_df = df.groupby("estado", as_index=False)["id"].count().rename(columns={"id": "cantidad"})
        st.markdown("#### Órdenes por estado")
        if not estado_df.empty:
            st.bar_chart(estado_df.set_index("estado")["cantidad"])

    with g2:
        prioridad_df = df.groupby("prioridad", as_index=False)["id"].count().rename(columns={"id": "cantidad"})
        if not prioridad_df.empty:
            prioridad_df["rank"] = prioridad_df["prioridad"].apply(_priority_rank)
            prioridad_df = prioridad_df.sort_values("rank")
            st.markdown("#### Órdenes por prioridad")
            st.bar_chart(prioridad_df.set_index("prioridad")["cantidad"])

    pendientes = activas.copy()
    if not pendientes.empty:
        pendientes["rank_estado"] = pendientes["estado"].apply(_state_rank)
        pendientes["rank_prioridad"] = pendientes["prioridad"].apply(_priority_rank)
        pendientes = pendientes.sort_values(["rank_prioridad", "fecha_entrega", "rank_estado", "id"])
        st.markdown("#### Prioridades operativas")
        st.dataframe(
            pendientes[
                [
                    "id",
                    "titulo",
                    "producto",
                    "cliente",
                    "cantidad",
                    "unidad",
                    "fecha_inicio",
                    "fecha_entrega",
                    "prioridad",
                    "estado",
                    "responsable",
                    "porcentaje_avance",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "porcentaje_avance": st.column_config.NumberColumn("Avance %", format="%.2f"),
                "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
            },
        )


def _render_nueva_orden(usuario: str) -> None:
    st.subheader("📝 Nueva orden de producción")

    df_clientes = _load_clientes_df()
    df_ventas = _load_ventas_df()

    with st.form("form_nueva_orden_produccion", clear_on_submit=False):
        a1, a2, a3 = st.columns(3)
        titulo = a1.text_input("Título de la orden")
        producto = a2.text_input("Producto / trabajo")
        cantidad = a3.number_input("Cantidad", min_value=0.01, value=1.0, format="%.2f")

        b1, b2, b3 = st.columns(3)
        unidad = b1.text_input("Unidad", value="unidad")
        prioridad = b2.selectbox("Prioridad", PRIORIDADES_PRODUCCION, index=1)
        responsable = b3.text_input("Responsable")

        c1, c2, c3 = st.columns(3)
        fecha_inicio = c1.date_input("Fecha inicio", value=date.today())
        fecha_entrega = c2.date_input("Fecha entrega", value=date.today() + timedelta(days=3))
        equipo = c3.text_input("Equipo / máquina")

        d1, d2, d3 = st.columns(3)
        costo_mano = d1.number_input("Costo mano de obra USD", min_value=0.0, value=0.0, format="%.2f")
        costo_indirecto = d2.number_input("Costo indirecto USD", min_value=0.0, value=0.0, format="%.2f")
        cliente_sel = d3.selectbox(
            "Cliente (opcional)",
            options=[None] + df_clientes["id"].tolist() if not df_clientes.empty else [None],
            format_func=lambda x: "Sin cliente" if x is None else str(df_clientes[df_clientes["id"] == x]["nombre"].iloc[0]),
        )

        venta_sel = st.selectbox(
            "Venta relacionada (opcional)",
            options=[None] + df_ventas["id"].tolist() if not df_ventas.empty else [None],
            format_func=lambda x: "Sin venta" if x is None else f"Venta #{x}",
        )

        descripcion = st.text_area("Descripción / especificaciones")
        observaciones = st.text_area("Observaciones internas")
        crear_base = st.checkbox("Crear etapas base automáticamente", value=True)

        submit = st.form_submit_button("✅ Crear orden", use_container_width=True)

    if submit:
        try:
            oid = crear_orden_produccion(
                usuario=usuario,
                titulo=titulo,
                producto=producto,
                cantidad=float(cantidad),
                unidad=unidad,
                fecha_inicio=fecha_inicio.isoformat() if fecha_inicio else "",
                fecha_entrega=fecha_entrega.isoformat() if fecha_entrega else "",
                prioridad=prioridad,
                cliente_id=cliente_sel,
                venta_id=venta_sel,
                descripcion=descripcion,
                responsable=responsable,
                equipo=equipo,
                costo_mano_obra_usd=float(costo_mano),
                costo_indirecto_usd=float(costo_indirecto),
                observaciones=observaciones,
                crear_etapas_base=bool(crear_base),
            )
            st.success(f"Orden de producción #{oid} creada correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo crear la orden: {exc}")


def _render_ordenes() -> None:
    st.subheader("📋 Órdenes de producción")

    df = _load_ordenes_df()
    if df.empty:
        st.info("No hay órdenes registradas.")
        return

    f1, f2, f3 = st.columns([2, 1, 1])
    buscar = f1.text_input("Buscar orden", key="prod_buscar_orden")
    estado = f2.selectbox("Estado", ["todos"] + list(ESTADOS_PRODUCCION), key="prod_estado_orden")
    prioridad = f3.selectbox("Prioridad", ["todas"] + list(PRIORIDADES_PRODUCCION), key="prod_prioridad_orden")

    view = _filter_df(df.copy(), buscar, ["titulo", "producto", "cliente", "responsable", "equipo", "observaciones"])

    if estado != "todos":
        view = view[view["estado"] == estado]
    if prioridad != "todas":
        view = view[view["prioridad"] == prioridad]

    view["rank_prioridad"] = view["prioridad"].apply(_priority_rank)
    view["rank_estado"] = view["estado"].apply(_state_rank)
    view = view.sort_values(["rank_prioridad", "fecha_entrega", "rank_estado", "id"])

    st.dataframe(
        view[
            [
                "id",
                "fecha",
                "titulo",
                "producto",
                "cliente",
                "cantidad",
                "unidad",
                "fecha_inicio",
                "fecha_entrega",
                "prioridad",
                "estado",
                "responsable",
                "equipo",
                "costo_materiales_usd",
                "costo_mano_obra_usd",
                "costo_indirecto_usd",
                "costo_total_usd",
                "porcentaje_avance",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.2f"),
            "costo_materiales_usd": st.column_config.NumberColumn("Mat. USD", format="%.2f"),
            "costo_mano_obra_usd": st.column_config.NumberColumn("M.O. USD", format="%.2f"),
            "costo_indirecto_usd": st.column_config.NumberColumn("Indirecto USD", format="%.2f"),
            "costo_total_usd": st.column_config.NumberColumn("Costo total USD", format="%.2f"),
            "porcentaje_avance": st.column_config.NumberColumn("Avance %", format="%.2f"),
        },
    )

    st.divider()
    st.markdown("### ✏️ Actualizar orden")

    orden_id = st.selectbox(
        "Selecciona una orden",
        options=df["id"].tolist(),
        format_func=lambda x: f"#{x} · {df[df['id'] == x]['titulo'].iloc[0]}",
        key="prod_edit_orden_id",
    )

    row = df[df["id"] == orden_id].iloc[0]

    e1, e2, e3 = st.columns(3)
    estado_n = e1.selectbox("Estado", ESTADOS_PRODUCCION, index=list(ESTADOS_PRODUCCION).index(str(row["estado"])))
    prioridad_n = e2.selectbox("Prioridad", PRIORIDADES_PRODUCCION, index=list(PRIORIDADES_PRODUCCION).index(str(row["prioridad"])))
    responsable_n = e3.text_input("Responsable", value=str(row["responsable"] or ""))

    e4, e5, e6 = st.columns(3)
    equipo_n = e4.text_input("Equipo", value=str(row["equipo"] or ""))
    fecha_inicio_n = e5.text_input("Fecha inicio", value=str(row["fecha_inicio"] or ""))
    fecha_entrega_n = e6.text_input("Fecha entrega", value=str(row["fecha_entrega"] or ""))

    e7, e8 = st.columns(2)
    mano_n = e7.number_input("Costo mano de obra USD", min_value=0.0, value=float(row["costo_mano_obra_usd"] or 0.0), format="%.2f")
    indirecto_n = e8.number_input("Costo indirecto USD", min_value=0.0, value=float(row["costo_indirecto_usd"] or 0.0), format="%.2f")

    observ_n = st.text_area("Observaciones", value=str(row["observaciones"] or ""))

    if st.button("💾 Guardar cambios de la orden", use_container_width=True):
        try:
            actualizar_orden_produccion(
                orden_id=int(orden_id),
                estado=estado_n,
                prioridad=prioridad_n,
                responsable=responsable_n,
                equipo=equipo_n,
                fecha_inicio=fecha_inicio_n,
                fecha_entrega=fecha_entrega_n,
                costo_mano_obra_usd=float(mano_n),
                costo_indirecto_usd=float(indirecto_n),
                observaciones=observ_n,
            )
            st.success("Orden actualizada.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar: {exc}")


def _render_materiales(usuario: str) -> None:
    st.subheader("🧱 Materiales de producción")

    df_ordenes = _load_ordenes_df()
    df_inv = _load_inventario_df()

    if df_ordenes.empty:
        st.info("Primero crea una orden de producción.")
        return

    tab1, tab2 = st.tabs(["Agregar material", "Consumir material"])

    with tab1:
        orden_id = st.selectbox(
            "Orden",
            options=df_ordenes["id"].tolist(),
            format_func=lambda x: f"#{x} · {df_ordenes[df_ordenes['id'] == x]['titulo'].iloc[0]}",
            key="prod_material_orden",
        )

        modo = st.radio("Origen del material", ["Inventario existente", "Manual"], horizontal=True, key="prod_material_modo")

        inv_id = None
        material = ""
        unidad = "unidad"
        costo_u = 0.0

        if modo == "Inventario existente" and not df_inv.empty:
            inv_id = st.selectbox(
                "Ítem de inventario",
                options=df_inv["id"].tolist(),
                format_func=lambda x: (
                    f"{df_inv[df_inv['id'] == x]['nombre'].iloc[0]} "
                    f"({df_inv[df_inv['id'] == x]['sku'].iloc[0]})"
                ),
                key="prod_material_inv_id",
            )
            inv_row = df_inv[df_inv["id"] == inv_id].iloc[0]
            material = str(inv_row["nombre"])
            unidad = str(inv_row["unidad"] or "unidad")
            costo_u = float(inv_row["costo_unitario_usd"] or 0.0)
            st.caption(
                f"Stock actual: {float(inv_row['stock_actual'] or 0.0):,.2f} {unidad} | "
                f"Costo unitario: $ {costo_u:,.4f}"
            )
        else:
            m1, m2, m3 = st.columns(3)
            material = m1.text_input("Material")
            unidad = m2.text_input("Unidad", value="unidad")
            costo_u = m3.number_input("Costo unitario USD", min_value=0.0, value=0.0, format="%.4f")

        c1, c2 = st.columns(2)
        cantidad_req = c1.number_input("Cantidad requerida", min_value=0.0001, value=1.0, format="%.4f")
        obs = c2.text_input("Observaciones")

        costo_total_prev = float(cantidad_req) * float(costo_u)
        st.metric("Costo total estimado", f"$ {costo_total_prev:,.2f}")

        if st.button("➕ Agregar material", use_container_width=True):
            try:
                agregar_material_orden(
                    orden_id=int(orden_id),
                    material=material,
                    cantidad_requerida=float(cantidad_req),
                    unidad=unidad,
                    inventario_id=int(inv_id) if inv_id else None,
                    costo_unitario_usd=float(costo_u),
                    observaciones=obs,
                )
                st.success("Material agregado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo agregar el material: {exc}")

    with tab2:
        df_mat = _load_materiales_df()
        if df_mat.empty:
            st.caption("No hay materiales cargados.")
        else:
            st.dataframe(
                df_mat[
                    [
                        "id",
                        "orden_id",
                        "titulo",
                        "material",
                        "unidad",
                        "cantidad_requerida",
                        "cantidad_consumida",
                        "stock_actual",
                        "estado",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "cantidad_requerida": st.column_config.NumberColumn("Req.", format="%.4f"),
                    "cantidad_consumida": st.column_config.NumberColumn("Consumida", format="%.4f"),
                    "stock_actual": st.column_config.NumberColumn("Stock", format="%.4f"),
                },
            )

            material_id = st.selectbox(
                "Material a consumir",
                options=df_mat["id"].tolist(),
                format_func=lambda x: f"#{x} · {df_mat[df_mat['id'] == x]['material'].iloc[0]} · Orden #{df_mat[df_mat['id'] == x]['orden_id'].iloc[0]}",
                key="prod_consumir_material_id",
            )
            row = df_mat[df_mat["id"] == material_id].iloc[0]
            cons = st.number_input(
                "Cantidad a consumir",
                min_value=0.0001,
                value=1.0,
                format="%.4f",
                key="prod_consumir_cantidad",
            )
            descontar = st.checkbox(
                "Descontar del inventario",
                value=bool(row["inventario_id"]) if "inventario_id" in row.index else True,
                key="prod_consumir_desc_inv",
            )

            if st.button("📦 Registrar consumo", use_container_width=True):
                try:
                    consumir_material_orden(
                        usuario=usuario,
                        material_id=int(material_id),
                        cantidad_consumida=float(cons),
                        descontar_inventario=bool(descontar),
                    )
                    st.success("Consumo registrado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar el consumo: {exc}")


def _render_etapas() -> None:
    st.subheader("🧩 Etapas de producción")

    df_ordenes = _load_ordenes_df()
    df_etapas = _load_etapas_df()

    if df_ordenes.empty:
        st.info("No hay órdenes disponibles.")
        return

    if df_etapas.empty:
        st.info("No hay etapas registradas.")
        return

    orden_id = st.selectbox(
        "Filtrar por orden",
        options=df_ordenes["id"].tolist(),
        format_func=lambda x: f"#{x} · {df_ordenes[df_ordenes['id'] == x]['titulo'].iloc[0]}",
        key="prod_etapa_orden_id",
    )

    view = df_etapas[df_etapas["orden_id"] == orden_id].copy()
    st.dataframe(
        view[
            [
                "id",
                "nombre",
                "responsable",
                "estado",
                "fecha_inicio",
                "fecha_fin",
                "porcentaje",
                "observaciones",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "porcentaje": st.column_config.NumberColumn("Avance %", format="%.2f"),
        },
    )

    st.divider()
    etapa_id = st.selectbox(
        "Selecciona una etapa",
        options=view["id"].tolist(),
        format_func=lambda x: f"#{x} · {view[view['id'] == x]['nombre'].iloc[0]}",
        key="prod_edit_etapa_id",
    )

    row = view[view["id"] == etapa_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    estado = c1.selectbox("Estado", ["pendiente", "en_proceso", "pausada", "terminada"], index=["pendiente", "en_proceso", "pausada", "terminada"].index(str(row["estado"] or "pendiente")))
    porcentaje = c2.slider("Avance %", 0, 100, int(float(row["porcentaje"] or 0.0)))
    responsable = c3.text_input("Responsable", value=str(row["responsable"] or ""))

    c4, c5 = st.columns(2)
    fecha_inicio = c4.text_input("Fecha inicio", value=str(row["fecha_inicio"] or ""))
    fecha_fin = c5.text_input("Fecha fin", value=str(row["fecha_fin"] or ""))

    observ = st.text_area("Observaciones", value=str(row["observaciones"] or ""))

    if st.button("💾 Actualizar etapa", use_container_width=True):
        try:
            actualizar_etapa_produccion(
                etapa_id=int(etapa_id),
                estado=estado,
                porcentaje=float(porcentaje),
                responsable=responsable,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                observaciones=observ,
            )
            st.success("Etapa actualizada.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar la etapa: {exc}")


def _render_incidencias(usuario: str) -> None:
    st.subheader("⚠️ Incidencias y observaciones")

    df_ordenes = _load_ordenes_df()
    if df_ordenes.empty:
        st.info("No hay órdenes registradas.")
        return

    orden_id = st.selectbox(
        "Orden",
        options=df_ordenes["id"].tolist(),
        format_func=lambda x: f"#{x} · {df_ordenes[df_ordenes['id'] == x]['titulo'].iloc[0]}",
        key="prod_incidencia_orden_id",
    )

    c1, c2 = st.columns(2)
    tipo = c1.selectbox("Tipo", ["observacion", "retraso", "falla", "merma", "cliente", "calidad"])
    impacto = c2.text_input("Impacto")

    detalle = st.text_area("Detalle")
    accion = st.text_area("Acción tomada")

    if st.button("📝 Registrar incidencia", use_container_width=True):
        try:
            registrar_incidencia_produccion(
                usuario=usuario,
                orden_id=int(orden_id),
                tipo=tipo,
                detalle=detalle,
                impacto=impacto,
                accion_tomada=accion,
            )
            st.success("Incidencia registrada.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar la incidencia: {exc}")

    df_inc = _load_incidencias_df(int(orden_id))
    if df_inc.empty:
        st.caption("Sin incidencias para esta orden.")
    else:
        st.dataframe(df_inc, use_container_width=True, hide_index=True)


def _render_calendario(df: pd.DataFrame) -> None:
    st.subheader("🗓️ Calendario de entregas")

    if df.empty:
        st.info("No hay órdenes registradas.")
        return

    view = df.copy()
    view["fecha_entrega_date"] = view["fecha_entrega"].apply(_safe_date)
    view = view.dropna(subset=["fecha_entrega_date"])

    if view.empty:
        st.info("No hay fechas de entrega válidas.")
        return

    hoy = date.today()
    anios = sorted(view["fecha_entrega_date"].apply(lambda x: x.year).unique().tolist())
    anio_default = hoy.year if hoy.year in anios else anios[0]

    c1, c2 = st.columns(2)
    anio = c1.selectbox("Año", anios, index=anios.index(anio_default), key="prod_cal_anio")
    mes = c2.selectbox(
        "Mes",
        list(range(1, 13)),
        index=hoy.month - 1,
        format_func=lambda m: calendar.month_name[m],
        key="prod_cal_mes",
    )

    df_mes = view[
        (view["fecha_entrega_date"].apply(lambda x: x.year) == anio)
        & (view["fecha_entrega_date"].apply(lambda x: x.month) == mes)
    ].copy()

    eventos_por_dia: dict[int, list[dict[str, Any]]] = {}
    for _, row in df_mes.iterrows():
        eventos_por_dia.setdefault(int(row["fecha_entrega_date"].day), []).append(dict(row))

    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    hdr = st.columns(7)
    for i, d in enumerate(dias_semana):
        hdr[i].markdown(f"**{d}**")

    cal = calendar.monthcalendar(anio, mes)
    for semana in cal:
        cols = st.columns(7)
        for idx, dia in enumerate(semana):
            with cols[idx]:
                if dia == 0:
                    st.markdown(" ")
                    continue

                eventos = eventos_por_dia.get(dia, [])
                fecha_actual = date(anio, mes, dia)

                if fecha_actual < hoy:
                    color = "#fde2e2"
                elif fecha_actual == hoy:
                    color = "#fff3cd"
                else:
                    color = "#e8f5e9"

                html = f"""
                <div style="
                    border:1px solid #ddd;
                    border-radius:10px;
                    padding:8px;
                    min-height:120px;
                    background:{color};
                    margin-bottom:8px;
                ">
                    <div style="font-weight:700; margin-bottom:6px;">{dia}</div>
                """

                if not eventos:
                    html += '<div style="font-size:12px; color:#777;">Sin entregas</div>'
                else:
                    for ev in eventos[:3]:
                        html += f"""
                        <div style="font-size:12px; margin-bottom:6px; padding:4px; border-radius:6px; background:white;">
                            <b>#{int(ev.get('id', 0))}</b> {ev.get('titulo', '')}<br>
                            {ev.get('prioridad', '').upper()} · {ev.get('estado', '')}<br>
                            Avance: {float(ev.get('porcentaje_avance', 0.0)):.0f}%
                        </div>
                        """
                    if len(eventos) > 3:
                        html += f'<div style="font-size:11px; color:#555;">+{len(eventos)-3} más</div>'

                html += "</div>"
                st.markdown(html, unsafe_allow_html=True)

    st.markdown("### Próximas entregas")
    proximas = view[
        (view["estado"].isin(["planificada", "en_proceso", "pausada"]))
        & (view["fecha_entrega_date"] >= hoy)
    ].sort_values(["fecha_entrega_date", "prioridad"])

    if proximas.empty:
        st.success("No hay entregas próximas.")
    else:
        st.dataframe(
            proximas[
                [
                    "id",
                    "titulo",
                    "producto",
                    "cliente",
                    "fecha_entrega",
                    "prioridad",
                    "estado",
                    "porcentaje_avance",
                    "responsable",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "porcentaje_avance": st.column_config.NumberColumn("Avance %", format="%.2f"),
            },
        )


def _render_resumen_costos(df_ordenes: pd.DataFrame) -> None:
    st.subheader("💵 Resumen de costos")

    if df_ordenes.empty:
        st.info("No hay órdenes registradas.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Materiales", f"$ {float(df_ordenes['costo_materiales_usd'].sum()):,.2f}")
    c2.metric("Mano de obra", f"$ {float(df_ordenes['costo_mano_obra_usd'].sum()):,.2f}")
    c3.metric("Indirectos", f"$ {float(df_ordenes['costo_indirecto_usd'].sum()):,.2f}")
    c4.metric("Costo total", f"$ {float(df_ordenes['costo_total_usd'].sum()):,.2f}")

    costo_estado = (
        df_ordenes.groupby("estado", as_index=False)["costo_total_usd"]
        .sum()
        .sort_values("costo_total_usd", ascending=False)
    )
    if not costo_estado.empty:
        st.markdown("#### Costo por estado")
        st.bar_chart(costo_estado.set_index("estado")["costo_total_usd"])

    top = df_ordenes.sort_values("costo_total_usd", ascending=False).head(10)
    st.markdown("#### Órdenes más costosas")
    st.dataframe(
        top[
            [
                "id",
                "titulo",
                "producto",
                "cliente",
                "estado",
                "prioridad",
                "costo_materiales_usd",
                "costo_mano_obra_usd",
                "costo_indirecto_usd",
                "costo_total_usd",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "costo_materiales_usd": st.column_config.NumberColumn("Materiales", format="%.2f"),
            "costo_mano_obra_usd": st.column_config.NumberColumn("M.O.", format="%.2f"),
            "costo_indirecto_usd": st.column_config.NumberColumn("Indirectos", format="%.2f"),
            "costo_total_usd": st.column_config.NumberColumn("Total", format="%.2f"),
        },
    )


# ============================================================
# UI
# ============================================================

def render_produccion(usuario: str) -> None:
    _ensure_produccion_tables()

    st.subheader("🏭 Planificación de producción")
    st.caption(
        "Órdenes, materiales, etapas, incidencias, calendario de entregas y control de costos."
    )

    df_ordenes = _load_ordenes_df()

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "📝 Nueva orden",
            "📋 Órdenes",
            "🧱 Materiales",
            "🧩 Etapas",
            "⚠️ Incidencias",
            "🗓️ Calendario",
            "💵 Costos",
        ]
    )

    with tabs[0]:
        _render_dashboard(df_ordenes)

    with tabs[1]:
        _render_nueva_orden(usuario)

    with tabs[2]:
        _render_ordenes()

    with tabs[3]:
        _render_materiales(usuario)

    with tabs[4]:
        _render_etapas()

    with tabs[5]:
        _render_incidencias(usuario)

    with tabs[6]:
        _render_calendario(df_ordenes)

    with tabs[7]:
        _render_resumen_costos(df_ordenes)









