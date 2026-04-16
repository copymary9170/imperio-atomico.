from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.integration_hub import (
    dispatch_to_module,
    render_module_inbox,
    render_send_buttons,
)


# ============================================================
# CONFIG
# ============================================================

TIPOS_PRODUCTO = [
    "Tela",
    "Taza",
    "Gorra",
    "Mousepad",
    "Rompecabezas",
    "Metal",
    "Madera",
    "Otro",
]

ESTADOS_LOTE = [
    "pendiente",
    "analizado",
    "aprobado",
    "en_proceso",
    "completado",
    "con_merma",
    "rechazado",
    "cancelado",
]

RESULTADOS_CALIDAD = [
    "aprobado",
    "reproceso",
    "rechazado",
]

PRESIONES = [
    "baja",
    "media",
    "alta",
]

MAQUINAS_DEFAULT = [
    "Plancha 1",
    "Plancha 2",
    "Horno",
    "Sublimadora automática",
]

CALIDADES_ACABADO = [
    "excelente",
    "buena",
    "regular",
    "rechazada",
]


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
        return int(float(value))
    except Exception:
        return int(default)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (str(table_name),),
    ).fetchone()
    return row is not None


def _get_table_columns(conn, table_name: str) -> list[str]:
    if not _table_exists(conn, table_name):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _filter_df(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    txt = _clean_text(query)
    if not txt or df.empty:
        return df

    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(txt, case=False, na=False)
    return df[mask]


def _safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _next_sublimacion_code() -> str:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT codigo FROM sublimacion_lotes ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row or not row["codigo"]:
        return "SUB-0001"

    last = str(row["codigo"]).split("-")[-1]
    n = _safe_int(last, 0) + 1
    return f"SUB-{n:04d}"


# ============================================================
# SCHEMA
# ============================================================

def _ensure_sublimacion_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,

                origen TEXT,
                referencia_origen TEXT,

                cliente TEXT,
                producto TEXT NOT NULL,
                tipo_producto TEXT DEFAULT 'Otro',
                diseno TEXT,

                ruta_id INTEGER,
                ruta_codigo TEXT,
                ruta_nombre TEXT,

                orden_produccion_id INTEGER,
                lote_codigo TEXT,

                material_base_id INTEGER,
                material_base_nombre TEXT,
                material_base_unidad TEXT DEFAULT 'unidad',

                tinta_inventario_id INTEGER,
                tinta_inventario_nombre TEXT,
                tinta_inventario_unidad TEXT DEFAULT 'ml',

                cantidad_programada REAL NOT NULL DEFAULT 0,
                cantidad_producida REAL NOT NULL DEFAULT 0,
                cantidad_aprobada REAL NOT NULL DEFAULT 0,
                cantidad_reproceso REAL NOT NULL DEFAULT 0,
                cantidad_merma REAL NOT NULL DEFAULT 0,
                cantidad_rechazada REAL NOT NULL DEFAULT 0,

                maquina TEXT,
                temperatura_c REAL DEFAULT 0,
                tiempo_seg REAL DEFAULT 0,
                presion TEXT,

                papel_tipo TEXT,
                tinta_tipo TEXT,

                area_estimada_cm2 REAL DEFAULT 0,
                consumo_tinta_estimado_ml REAL DEFAULT 0,
                consumo_material_estimado_unid REAL DEFAULT 0,

                consumo_tinta_real_ml REAL DEFAULT 0,
                consumo_material_real_unid REAL DEFAULT 0,

                capacidad_turno_unidades REAL DEFAULT 0,
                utilizacion_capacidad_pct REAL DEFAULT 0,

                tiempo_preparacion_min REAL DEFAULT 0,
                tiempo_impresion_min REAL DEFAULT 0,
                tiempo_transferencia_min REAL DEFAULT 0,
                tiempo_total_estimado_min REAL DEFAULT 0,
                tiempo_total_real_min REAL DEFAULT 0,

                calidad_acabado TEXT DEFAULT 'buena',

                costo_transfer_total REAL DEFAULT 0,
                costo_transfer_unit REAL DEFAULT 0,
                costo_tinta_unit REAL DEFAULT 0,
                costo_material_unit REAL DEFAULT 0,
                costo_energia_unit REAL DEFAULT 0,
                costo_mano_obra_unit REAL DEFAULT 0,
                costo_depreciacion_unit REAL DEFAULT 0,
                costo_indirecto_unit REAL DEFAULT 0,
                costo_unitario_final REAL DEFAULT 0,
                costo_total_final REAL DEFAULT 0,

                costo_tinta_real_total REAL DEFAULT 0,
                costo_material_real_total REAL DEFAULT 0,
                costo_mano_obra_real_total REAL DEFAULT 0,
                costo_total_real REAL DEFAULT 0,

                merma_pct REAL DEFAULT 0,
                observaciones TEXT,
                estado TEXT DEFAULT 'pendiente'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_control_calidad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                color_correcto INTEGER DEFAULT 1,
                transferencia_completa INTEGER DEFAULT 1,
                sin_manchas INTEGER DEFAULT 1,
                sin_ghosting INTEGER DEFAULT 1,
                sin_quemado INTEGER DEFAULT 1,
                observaciones TEXT,
                resultado TEXT DEFAULT 'aprobado',
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_mermas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                tipo_falla TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                costo_estimado_usd REAL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                accion TEXT,
                detalle TEXT,
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_consumos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                inventario_id INTEGER,
                item_nombre TEXT,
                tipo_consumo TEXT NOT NULL DEFAULT 'material',
                cantidad REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        cols = {r[1] for r in conn.execute("PRAGMA table_info(sublimacion_lotes)").fetchall()}
        missing = {
            "codigo": "ALTER TABLE sublimacion_lotes ADD COLUMN codigo TEXT",
            "ruta_id": "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_id INTEGER",
            "ruta_codigo": "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_codigo TEXT",
            "ruta_nombre": "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_nombre TEXT",
            "orden_produccion_id": "ALTER TABLE sublimacion_lotes ADD COLUMN orden_produccion_id INTEGER",
            "lote_codigo": "ALTER TABLE sublimacion_lotes ADD COLUMN lote_codigo TEXT",
            "material_base_id": "ALTER TABLE sublimacion_lotes ADD COLUMN material_base_id INTEGER",
            "material_base_nombre": "ALTER TABLE sublimacion_lotes ADD COLUMN material_base_nombre TEXT",
            "material_base_unidad": "ALTER TABLE sublimacion_lotes ADD COLUMN material_base_unidad TEXT DEFAULT 'unidad'",
            "tinta_inventario_id": "ALTER TABLE sublimacion_lotes ADD COLUMN tinta_inventario_id INTEGER",
            "tinta_inventario_nombre": "ALTER TABLE sublimacion_lotes ADD COLUMN tinta_inventario_nombre TEXT",
            "tinta_inventario_unidad": "ALTER TABLE sublimacion_lotes ADD COLUMN tinta_inventario_unidad TEXT DEFAULT 'ml'",
            "area_estimada_cm2": "ALTER TABLE sublimacion_lotes ADD COLUMN area_estimada_cm2 REAL DEFAULT 0",
            "consumo_tinta_estimado_ml": "ALTER TABLE sublimacion_lotes ADD COLUMN consumo_tinta_estimado_ml REAL DEFAULT 0",
            "consumo_material_estimado_unid": "ALTER TABLE sublimacion_lotes ADD COLUMN consumo_material_estimado_unid REAL DEFAULT 0",
            "consumo_tinta_real_ml": "ALTER TABLE sublimacion_lotes ADD COLUMN consumo_tinta_real_ml REAL DEFAULT 0",
            "consumo_material_real_unid": "ALTER TABLE sublimacion_lotes ADD COLUMN consumo_material_real_unid REAL DEFAULT 0",
            "capacidad_turno_unidades": "ALTER TABLE sublimacion_lotes ADD COLUMN capacidad_turno_unidades REAL DEFAULT 0",
            "utilizacion_capacidad_pct": "ALTER TABLE sublimacion_lotes ADD COLUMN utilizacion_capacidad_pct REAL DEFAULT 0",
            "tiempo_preparacion_min": "ALTER TABLE sublimacion_lotes ADD COLUMN tiempo_preparacion_min REAL DEFAULT 0",
            "tiempo_impresion_min": "ALTER TABLE sublimacion_lotes ADD COLUMN tiempo_impresion_min REAL DEFAULT 0",
            "tiempo_transferencia_min": "ALTER TABLE sublimacion_lotes ADD COLUMN tiempo_transferencia_min REAL DEFAULT 0",
            "tiempo_total_estimado_min": "ALTER TABLE sublimacion_lotes ADD COLUMN tiempo_total_estimado_min REAL DEFAULT 0",
            "tiempo_total_real_min": "ALTER TABLE sublimacion_lotes ADD COLUMN tiempo_total_real_min REAL DEFAULT 0",
            "calidad_acabado": "ALTER TABLE sublimacion_lotes ADD COLUMN calidad_acabado TEXT DEFAULT 'buena'",
            "costo_tinta_unit": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_tinta_unit REAL DEFAULT 0",
            "costo_material_unit": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_material_unit REAL DEFAULT 0",
            "costo_tinta_real_total": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_tinta_real_total REAL DEFAULT 0",
            "costo_material_real_total": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_material_real_total REAL DEFAULT 0",
            "costo_mano_obra_real_total": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_mano_obra_real_total REAL DEFAULT 0",
            "costo_total_real": "ALTER TABLE sublimacion_lotes ADD COLUMN costo_total_real REAL DEFAULT 0",
        }
        for col, sql in missing.items():
            if col in cols:
                continue
            try:
                conn.execute(sql)
                cols.add(col)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    cols.add(col)
                    continue
                raise

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_fecha ON sublimacion_lotes(fecha)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_estado ON sublimacion_lotes(estado)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_codigo ON sublimacion_lotes(codigo)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_ruta ON sublimacion_lotes(ruta_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_qc_lote ON sublimacion_control_calidad(lote_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_mermas_lote ON sublimacion_mermas(lote_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_historial_lote ON sublimacion_historial(lote_id, fecha)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_consumos_lote ON sublimacion_consumos(lote_id, fecha)"
        )

        rows = conn.execute(
            "SELECT id, codigo FROM sublimacion_lotes WHERE codigo IS NULL OR TRIM(codigo) = '' ORDER BY id ASC"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE sublimacion_lotes SET codigo = ? WHERE id = ?",
                (f"SUB-{int(row['id']):04d}", int(row["id"])),
            )


# ============================================================
# HISTORIAL
# ============================================================
def _load_queue_df() -> pd.DataFrame:
    cola = st.session_state.get("cola_sublimacion", [])
    if not cola:
        return pd.DataFrame()

    df = pd.DataFrame(cola).copy()

    if "cantidad" not in df.columns:
        df["cantidad"] = 0.0
    if "costo_transfer_total" not in df.columns:
        df["costo_transfer_total"] = 0.0
    if "producto" not in df.columns:
        if "nombre" in df.columns:
            df["producto"] = df["nombre"]
        elif "descripcion" in df.columns:
            df["producto"] = df["descripcion"]
        else:
            df["producto"] = "Trabajo sin nombre"

    if "cliente" not in df.columns:
        df["cliente"] = ""
    if "diseno" not in df.columns:
        df["diseno"] = ""
    if "tipo_producto" not in df.columns:
        df["tipo_producto"] = "Otro"

    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0.0)
    df["costo_transfer_total"] = pd.to_numeric(df["costo_transfer_total"], errors="coerce").fillna(0.0)
    return df


def _load_rutas_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "rutas_produccion"):
            return pd.DataFrame(columns=["id", "codigo", "nombre", "tiempo_total_min", "costo_base_usd"])

        return pd.read_sql_query(
            """
            SELECT
                id,
                codigo,
                nombre,
                producto_tipo,
                tiempo_total_min,
                costo_base_usd,
                estado
            FROM rutas_produccion
            WHERE COALESCE(estado, 'activa') = 'activa'
            ORDER BY codigo ASC, nombre ASC
            """,
            conn,
        )


def _load_inventario_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _get_table_columns(conn, "inventario")
        if not cols:
            return pd.DataFrame(columns=["id", "nombre", "categoria", "unidad", "stock", "costo_ref"])

        name_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
        stock_col = "stock_actual" if "stock_actual" in cols else "cantidad" if "cantidad" in cols else None
        unidad_col = "unidad" if "unidad" in cols else None
        cost_col = "costo_unitario_usd" if "costo_unitario_usd" in cols else "precio_venta_usd" if "precio_venta_usd" in cols else None
        categoria_col = "categoria" if "categoria" in cols else None
        active_col = "estado" if "estado" in cols else "activo" if "activo" in cols else None

        if not name_col:
            return pd.DataFrame(columns=["id", "nombre", "categoria", "unidad", "stock", "costo_ref"])

        query = f"SELECT id, {name_col} AS nombre"
        query += f", COALESCE({categoria_col}, '') AS categoria" if categoria_col else ", '' AS categoria"
        query += f", COALESCE({unidad_col}, 'unidad') AS unidad" if unidad_col else ", 'unidad' AS unidad"
        query += f", COALESCE({stock_col}, 0) AS stock" if stock_col else ", 0 AS stock"
        query += f", COALESCE({cost_col}, 0) AS costo_ref" if cost_col else ", 0 AS costo_ref"
        query += " FROM inventario"

        conditions: list[str] = []
        if active_col == "estado":
            conditions.append("COALESCE(estado,'activo')='activo'")
        elif active_col == "activo":
            conditions.append("COALESCE(activo,1)=1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY nombre ASC"
        rows = conn.execute(query).fetchall()

    return pd.DataFrame(rows, columns=["id", "nombre", "categoria", "unidad", "stock", "costo_ref"])


def _load_materiales_df() -> pd.DataFrame:
    df = _load_inventario_df()
    if df.empty:
        return df

    filtered = df[
        df["categoria"].astype(str).str.contains(
            "papel|tela|taza|gorra|mousepad|rompecabezas|metal|madera|sustrato|material|blank",
            case=False,
            na=False,
        )
    ]
    return filtered if not filtered.empty else df


def _load_tintas_df() -> pd.DataFrame:
    df = _load_inventario_df()
    if df.empty:
        return df

    filtered = df[
        df["nombre"].astype(str).str.contains("tinta", case=False, na=False)
        | df["categoria"].astype(str).str.contains("tinta", case=False, na=False)
    ]
    return filtered if not filtered.empty else pd.DataFrame(columns=df.columns)


def _load_lotes_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                codigo,
                fecha,
                usuario,
                cliente,
                producto,
                tipo_producto,
                diseno,
                ruta_codigo,
                ruta_nombre,
                orden_produccion_id,
                lote_codigo,
                material_base_nombre,
                tinta_inventario_nombre,
                cantidad_programada,
                cantidad_producida,
                cantidad_aprobada,
                cantidad_reproceso,
                cantidad_merma,
                cantidad_rechazada,
                maquina,
                temperatura_c,
                tiempo_seg,
                presion,
                papel_tipo,
                tinta_tipo,
                area_estimada_cm2,
                consumo_tinta_estimado_ml,
                consumo_material_estimado_unid,
                consumo_tinta_real_ml,
                consumo_material_real_unid,
                capacidad_turno_unidades,
                utilizacion_capacidad_pct,
                tiempo_preparacion_min,
                tiempo_impresion_min,
                tiempo_transferencia_min,
                tiempo_total_estimado_min,
                tiempo_total_real_min,
                calidad_acabado,
                costo_transfer_total,
                costo_transfer_unit,
                costo_tinta_unit,
                costo_material_unit,
                costo_energia_unit,
                costo_mano_obra_unit,
                costo_depreciacion_unit,
                costo_indirecto_unit,
                costo_unitario_final,
                costo_total_final,
                costo_tinta_real_total,
                costo_material_real_total,
                costo_mano_obra_real_total,
                costo_total_real,
                merma_pct,
                estado,
                observaciones
            FROM sublimacion_lotes
            ORDER BY id DESC
            """,
            conn,
        )


def _load_qc_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                qc.id,
                qc.fecha,
                qc.lote_id,
                l.codigo,
                l.producto,
                l.cliente,
                qc.usuario,
                qc.color_correcto,
                qc.transferencia_completa,
                qc.sin_manchas,
                qc.sin_ghosting,
                qc.sin_quemado,
                qc.resultado,
                qc.observaciones
            FROM sublimacion_control_calidad qc
            JOIN sublimacion_lotes l ON l.id = qc.lote_id
            ORDER BY qc.id DESC
            """,
            conn,
        )


def _load_mermas_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                m.id,
                m.fecha,
                m.lote_id,
                l.codigo,
                l.producto,
                l.cliente,
                m.usuario,
                m.tipo_falla,
                m.cantidad,
                m.costo_estimado_usd,
                m.observaciones
            FROM sublimacion_mermas m
            JOIN sublimacion_lotes l ON l.id = m.lote_id
            ORDER BY m.id DESC
            """,
            conn,
        )


def _load_historial_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                h.id,
                h.fecha,
                h.lote_id,
                l.codigo,
                l.producto,
                h.usuario,
                h.accion,
                h.detalle
            FROM sublimacion_historial h
            JOIN sublimacion_lotes l ON l.id = h.lote_id
            ORDER BY h.id DESC
            """,
            conn,
        )


def _load_consumos_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                c.id,
                c.fecha,
                c.lote_id,
                l.codigo,
                l.producto,
                c.usuario,
                c.item_nombre,
                c.tipo_consumo,
                c.cantidad,
                c.unidad,
                c.costo_unitario_usd,
                c.costo_total_usd,
                c.observaciones
            FROM sublimacion_consumos c
            JOIN sublimacion_lotes l ON l.id = c.lote_id
            ORDER BY c.id DESC
            """,
            conn,
        )


# ============================================================
# INVENTARIO
# ============================================================

def _descontar_inventario(conn, inventario_id: int, cantidad: float) -> tuple[str, str, float]:
    cols = _get_table_columns(conn, "inventario")
    if not cols:
        raise ValueError("La tabla inventario no existe.")

    stock_col = "stock_actual" if "stock_actual" in cols else "cantidad" if "cantidad" in cols else None
    name_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
    unidad_col = "unidad" if "unidad" in cols else None
    costo_col = "costo_unitario_usd" if "costo_unitario_usd" in cols else "precio_venta_usd" if "precio_venta_usd" in cols else None

    if not stock_col or not name_col:
        raise ValueError("La tabla inventario no tiene columnas compatibles.")

    row = conn.execute(
        f"""
        SELECT
            {name_col} AS nombre,
            COALESCE({stock_col}, 0) AS stock,
            COALESCE({unidad_col}, 'unidad') AS unidad,
            COALESCE({costo_col}, 0) AS costo_ref
        FROM inventario
        WHERE id = ?
        """,
        (int(inventario_id),),
    ).fetchone()

    if not row:
        raise ValueError("Item no encontrado en inventario.")

    stock_actual = float(row["stock"] or 0.0)
    cantidad = float(cantidad or 0.0)

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    if stock_actual < cantidad:
        raise ValueError(f"Inventario insuficiente para {row['nombre']}.")

    conn.execute(
        f"UPDATE inventario SET {stock_col} = COALESCE({stock_col}, 0) - ? WHERE id = ?",
        (float(cantidad), int(inventario_id)),
    )

    return str(row["nombre"]), str(row["unidad"]), float(row["costo_ref"] or 0.0)


def _registrar_consumo(
    conn,
    lote_id: int,
    usuario: str,
    inventario_id: int | None,
    item_nombre: str,
    tipo_consumo: str,
    cantidad: float,
    unidad: str,
    costo_unitario_usd: float,
    observaciones: str = "",
) -> None:
    costo_total = round(float(cantidad or 0.0) * float(costo_unitario_usd or 0.0), 4)
    conn.execute(
        """
        INSERT INTO sublimacion_consumos (
            lote_id, usuario, inventario_id, item_nombre, tipo_consumo, cantidad, unidad,
            costo_unitario_usd, costo_total_usd, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(lote_id),
            _clean_text(usuario),
            int(inventario_id) if inventario_id else None,
            _clean_text(item_nombre),
            _clean_text(tipo_consumo),
            float(cantidad),
            _clean_text(unidad),
            float(costo_unitario_usd),
            float(costo_total),
            _clean_text(observaciones),
        ),
    )


# ============================================================
# COSTEO / ANALISIS
# ============================================================

def _calc_costs(
    cantidad_total: float,
    costo_transfer_total: float,
    potencia_kw: float,
    minutos_unidad: float,
    costo_kwh: float,
    salario_hora: float,
    unidades_hora: float,
    valor_maquina: float,
    vida_horas: float,
    costo_indirecto_unit: float,
    costo_tinta_unit: float,
    costo_material_unit: float,
) -> dict[str, float]:
    qty = max(float(cantidad_total or 0.0), 0.0001)

    costo_transfer_unit = float(costo_transfer_total or 0.0) / qty
    costo_energia_unit = (float(potencia_kw or 0.0) * (float(minutos_unidad or 0.0) / 60.0)) * float(costo_kwh or 0.0)
    costo_mano_obra_unit = float(salario_hora or 0.0) / max(float(unidades_hora or 1.0), 0.0001)
    costo_depreciacion_unit = (float(valor_maquina or 0.0) / max(float(vida_horas or 1.0), 0.0001)) / max(float(unidades_hora or 1.0), 0.0001)
    costo_indirecto_unit = float(costo_indirecto_unit or 0.0)
    costo_tinta_unit = float(costo_tinta_unit or 0.0)
    costo_material_unit = float(costo_material_unit or 0.0)

    costo_unitario_final = (
        costo_transfer_unit
        + costo_tinta_unit
        + costo_material_unit
        + costo_energia_unit
        + costo_mano_obra_unit
        + costo_depreciacion_unit
        + costo_indirecto_unit
    )
    costo_total_final = costo_unitario_final * qty

    return {
        "costo_transfer_unit": round(costo_transfer_unit, 6),
        "costo_tinta_unit": round(costo_tinta_unit, 6),
        "costo_material_unit": round(costo_material_unit, 6),
        "costo_energia_unit": round(costo_energia_unit, 6),
        "costo_mano_obra_unit": round(costo_mano_obra_unit, 6),
        "costo_depreciacion_unit": round(costo_depreciacion_unit, 6),
        "costo_indirecto_unit": round(costo_indirecto_unit, 6),
        "costo_unitario_final": round(costo_unitario_final, 6),
        "costo_total_final": round(costo_total_final, 4),
    }


def _calc_operacion(
    cantidad_total: float,
    minutos_unidad: float,
    ancho_cm: float,
    alto_cm: float,
    tinta_ml_unidad: float,
    capacidad_turno_horas: float = 8.0,
) -> dict[str, float]:
    qty = max(float(cantidad_total or 0.0), 0.0)
    area_estimada_cm2 = max(float(ancho_cm or 0.0), 0.0) * max(float(alto_cm or 0.0), 0.0) * qty
    consumo_tinta_estimado_ml = max(float(tinta_ml_unidad or 0.0), 0.0) * qty
    consumo_material_estimado_unid = qty

    tiempo_preparacion_min = 10.0 if qty > 0 else 0.0
    tiempo_impresion_min = max(float(minutos_unidad or 0.0), 0.0) * qty
    tiempo_transferencia_min = round(qty * 0.75, 2)
    tiempo_total_estimado_min = round(tiempo_preparacion_min + tiempo_impresion_min + tiempo_transferencia_min, 2)

    capacidad_turno_unidades = 0.0
    if float(minutos_unidad or 0.0) > 0:
        capacidad_turno_unidades = (float(capacidad_turno_horas) * 60.0) / float(minutos_unidad)

    utilizacion_capacidad_pct = 0.0
    if capacidad_turno_unidades > 0:
        utilizacion_capacidad_pct = (qty / capacidad_turno_unidades) * 100.0

    return {
        "area_estimada_cm2": round(area_estimada_cm2, 2),
        "consumo_tinta_estimado_ml": round(consumo_tinta_estimado_ml, 4),
        "consumo_material_estimado_unid": round(consumo_material_estimado_unid, 4),
        "tiempo_preparacion_min": round(tiempo_preparacion_min, 2),
        "tiempo_impresion_min": round(tiempo_impresion_min, 2),
        "tiempo_transferencia_min": round(tiempo_transferencia_min, 2),
        "tiempo_total_estimado_min": round(tiempo_total_estimado_min, 2),
        "capacidad_turno_unidades": round(capacidad_turno_unidades, 2),
        "utilizacion_capacidad_pct": round(utilizacion_capacidad_pct, 2),
    }


# ============================================================
# SERVICIOS
# ============================================================

def _registrar_lote(
    usuario: str,
    producto: str,
    cliente: str,
    tipo_producto: str,
    diseno: str,
    cantidad_programada: float,
    maquina: str,
    temperatura_c: float,
    tiempo_seg: float,
    presion: str,
    papel_tipo: str,
    tinta_tipo: str,
    observaciones: str,
    costo_transfer_total: float,
    costos: dict[str, float],
    operacion: dict[str, float],
    origen: str = "manual",
    referencia_origen: str = "",
    ruta_id: int | None = None,
    ruta_codigo: str = "",
    ruta_nombre: str = "",
    orden_produccion_id: int | None = None,
    lote_codigo: str = "",
    material_base_id: int | None = None,
    material_base_nombre: str = "",
    material_base_unidad: str = "unidad",
    tinta_inventario_id: int | None = None,
    tinta_inventario_nombre: str = "",
    tinta_inventario_unidad: str = "ml",
) -> int:
    _ensure_sublimacion_tables()
    codigo = _next_sublimacion_code()

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO sublimacion_lotes (
                codigo, usuario, origen, referencia_origen, cliente, producto, tipo_producto, diseno,
                ruta_id, ruta_codigo, ruta_nombre, orden_produccion_id, lote_codigo,
                material_base_id, material_base_nombre, material_base_unidad,
                tinta_inventario_id, tinta_inventario_nombre, tinta_inventario_unidad,
                cantidad_programada, cantidad_producida, cantidad_aprobada, cantidad_reproceso,
                cantidad_merma, cantidad_rechazada,
                maquina, temperatura_c, tiempo_seg, presion, papel_tipo, tinta_tipo,
                area_estimada_cm2, consumo_tinta_estimado_ml, consumo_material_estimado_unid,
                consumo_tinta_real_ml, consumo_material_real_unid,
                capacidad_turno_unidades, utilizacion_capacidad_pct,
                tiempo_preparacion_min, tiempo_impresion_min, tiempo_transferencia_min, tiempo_total_estimado_min,
                tiempo_total_real_min, calidad_acabado,
                observaciones,
                costo_transfer_total, costo_transfer_unit, costo_tinta_unit, costo_material_unit, costo_energia_unit,
                costo_mano_obra_unit, costo_depreciacion_unit, costo_indirecto_unit,
                costo_unitario_final, costo_total_final,
                costo_tinta_real_total, costo_material_real_total, costo_mano_obra_real_total, costo_total_real,
                merma_pct, estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, 0, 'buena', ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 'analizado')
            """,
            (
                codigo,
                usuario,
                origen,
                referencia_origen,
                cliente,
                producto,
                tipo_producto,
                diseno,
                int(ruta_id) if ruta_id else None,
                ruta_codigo,
                ruta_nombre,
                int(orden_produccion_id) if orden_produccion_id else None,
                lote_codigo,
                int(material_base_id) if material_base_id else None,
                material_base_nombre,
                material_base_unidad,
                int(tinta_inventario_id) if tinta_inventario_id else None,
                tinta_inventario_nombre,
                tinta_inventario_unidad,
                float(cantidad_programada),
                maquina,
                float(temperatura_c),
                float(tiempo_seg),
                presion,
                papel_tipo,
                tinta_tipo,
                float(operacion["area_estimada_cm2"]),
                float(operacion["consumo_tinta_estimado_ml"]),
                float(operacion["consumo_material_estimado_unid"]),
                float(operacion["capacidad_turno_unidades"]),
                float(operacion["utilizacion_capacidad_pct"]),
                float(operacion["tiempo_preparacion_min"]),
                float(operacion["tiempo_impresion_min"]),
                float(operacion["tiempo_transferencia_min"]),
                float(operacion["tiempo_total_estimado_min"]),
                observaciones,
                float(costo_transfer_total),
                float(costos["costo_transfer_unit"]),
                float(costos["costo_tinta_unit"]),
                float(costos["costo_material_unit"]),
                float(costos["costo_energia_unit"]),
                float(costos["costo_mano_obra_unit"]),
                float(costos["costo_depreciacion_unit"]),
                float(costos["costo_indirecto_unit"]),
                float(costos["costo_unitario_final"]),
                float(costos["costo_total_final"]),
            ),
        )
        lote_id = int(cur.lastrowid)

    _log_sublimacion(lote_id, usuario, "crear_lote", f"Lote creado: {codigo}")
    return lote_id


def _actualizar_resultado_lote(
    lote_id: int,
    usuario: str,
    producida: float,
    aprobada: float,
    reproceso: float,
    merma: float,
    rechazada: float,
    consumo_tinta_real_ml: float,
    consumo_material_real_unid: float,
    tiempo_total_real_min: float,
    calidad_acabado: str,
    observaciones: str,
    descontar_inventario_real: bool = False,
) -> None:
    merma_pct = (float(merma or 0.0) / max(float(producida or 0.0), 0.0001)) * 100.0 if producida > 0 else 0.0

    if rechazada > 0 and aprobada <= 0:
        estado = "rechazado"
    elif merma > 0:
        estado = "con_merma"
    elif aprobada > 0:
        estado = "completado"
    else:
        estado = "en_proceso"

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                codigo,
                material_base_id,
                tinta_inventario_id,
                costo_tinta_unit,
                costo_material_unit,
                costo_mano_obra_unit
            FROM sublimacion_lotes
            WHERE id = ?
            """,
            (int(lote_id),),
        ).fetchone()

        if not row:
            raise ValueError("Lote no encontrado.")

        costo_tinta_unit = float(row["costo_tinta_unit"] or 0.0)
        costo_material_unit = float(row["costo_material_unit"] or 0.0)
        costo_mano_obra_unit = float(row["costo_mano_obra_unit"] or 0.0)

        if descontar_inventario_real:
            if row["material_base_id"] and float(consumo_material_real_unid or 0.0) > 0:
                nombre, unidad, costo_ref = _descontar_inventario(
                    conn,
                    inventario_id=int(row["material_base_id"]),
                    cantidad=float(consumo_material_real_unid),
                )
                _registrar_consumo(
                    conn=conn,
                    lote_id=int(lote_id),
                    usuario=usuario,
                    inventario_id=int(row["material_base_id"]),
                    item_nombre=nombre,
                    tipo_consumo="material",
                    cantidad=float(consumo_material_real_unid),
                    unidad=unidad,
                    costo_unitario_usd=float(costo_ref or costo_material_unit),
                    observaciones=f"Consumo real de material lote {row['codigo']}",
                )

            if row["tinta_inventario_id"] and float(consumo_tinta_real_ml or 0.0) > 0:
                nombre_t, unidad_t, costo_ref_t = _descontar_inventario(
                    conn,
                    inventario_id=int(row["tinta_inventario_id"]),
                    cantidad=float(consumo_tinta_real_ml),
                )
                _registrar_consumo(
                    conn=conn,
                    lote_id=int(lote_id),
                    usuario=usuario,
                    inventario_id=int(row["tinta_inventario_id"]),
                    item_nombre=nombre_t,
                    tipo_consumo="tinta",
                    cantidad=float(consumo_tinta_real_ml),
                    unidad=unidad_t,
                    costo_unitario_usd=float(costo_ref_t or costo_tinta_unit),
                    observaciones=f"Consumo real de tinta lote {row['codigo']}",
                )

        costo_tinta_real_total = round(float(consumo_tinta_real_ml or 0.0) * costo_tinta_unit, 4)
        costo_material_real_total = round(float(consumo_material_real_unid or 0.0) * costo_material_unit, 4)
        costo_mano_obra_real_total = round(float(producida or 0.0) * costo_mano_obra_unit, 4)
        costo_total_real = round(costo_tinta_real_total + costo_material_real_total + costo_mano_obra_real_total, 4)

        conn.execute(
            """
            UPDATE sublimacion_lotes
            SET cantidad_producida=?,
                cantidad_aprobada=?,
                cantidad_reproceso=?,
                cantidad_merma=?,
                cantidad_rechazada=?,
                consumo_tinta_real_ml=?,
                consumo_material_real_unid=?,
                tiempo_total_real_min=?,
                calidad_acabado=?,
                merma_pct=?,
                observaciones=?,
                costo_tinta_real_total=?,
                costo_material_real_total=?,
                costo_mano_obra_real_total=?,
                costo_total_real=?,
                estado=?,
                actualizado_en=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                float(producida),
                float(aprobada),
                float(reproceso),
                float(merma),
                float(rechazada),
                float(consumo_tinta_real_ml),
                float(consumo_material_real_unid),
                float(tiempo_total_real_min),
                _clean_text(calidad_acabado) or "buena",
                round(merma_pct, 4),
                _clean_text(observaciones),
                float(costo_tinta_real_total),
                float(costo_material_real_total),
                float(costo_mano_obra_real_total),
                float(costo_total_real),
                estado,
                int(lote_id),
            ),
        )

    _log_sublimacion(lote_id, usuario, "actualizar_produccion", f"Producción actualizada. Estado: {estado}")


def _registrar_control_calidad(
    lote_id: int,
    usuario: str,
    color_correcto: bool,
    transferencia_completa: bool,
    sin_manchas: bool,
    sin_ghosting: bool,
    sin_quemado: bool,
    observaciones: str,
    resultado: str,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO sublimacion_control_calidad (
                lote_id, usuario, color_correcto, transferencia_completa,
                sin_manchas, sin_ghosting, sin_quemado, observaciones, resultado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(lote_id),
                usuario,
                1 if color_correcto else 0,
                1 if transferencia_completa else 0,
                1 if sin_manchas else 0,
                1 if sin_ghosting else 0,
                1 if sin_quemado else 0,
                _clean_text(observaciones),
                resultado,
            ),
        )

    _log_sublimacion(lote_id, usuario, "control_calidad", f"Resultado QC: {resultado}")


def _registrar_merma(
    lote_id: int,
    usuario: str,
    tipo_falla: str,
    cantidad: float,
    costo_estimado_usd: float,
    observaciones: str,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO sublimacion_mermas (
                lote_id, usuario, tipo_falla, cantidad, costo_estimado_usd, observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(lote_id),
                usuario,
                _clean_text(tipo_falla),
                float(cantidad),
                float(costo_estimado_usd),
                _clean_text(observaciones),
            ),
        )

    _log_sublimacion(lote_id, usuario, "registrar_merma", f"Merma: {tipo_falla} ({cantidad})")


# ============================================================
# UI
# ============================================================

def _render_cola() -> None:
    st.subheader("📥 Cola recibida desde CMYK")
    df_cola = _load_queue_df()

    if df_cola.empty:
        st.info("No hay trabajos pendientes en cola.")
        return

    total_transfer = float(df_cola["costo_transfer_total"].sum())
    total_unidades = float(df_cola["cantidad"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Trabajos en cola", len(df_cola))
    c2.metric("Unidades pendientes", f"{total_unidades:,.2f}")
    c3.metric("Costo transfer total", f"$ {total_transfer:,.2f}")

    st.dataframe(df_cola, use_container_width=True, hide_index=True)

    if st.button("🧹 Vaciar cola de sublimación", use_container_width=True):
        st.session_state["cola_sublimacion"] = []
        st.success("Cola vaciada.")
        st.rerun()


def _render_registro(usuario: str) -> None:
    st.subheader("⚙️ Registrar lote de sublimación")

    df_cola = _load_queue_df()
    df_rutas = _load_rutas_df()
    df_tintas = _load_tintas_df()
    df_materiales = _load_materiales_df()

    usar_cola = st.checkbox("Usar datos desde la cola de CMYK", value=not df_cola.empty)

    trabajo_sel = None
    if usar_cola and not df_cola.empty:
        opciones = df_cola.index.tolist()
        idx = st.selectbox(
            "Trabajo en cola",
            options=opciones,
            format_func=lambda i: f"{df_cola.loc[i, 'producto']} · {df_cola.loc[i, 'cantidad']} uds",
        )
        trabajo_sel = df_cola.loc[idx]

    c1, c2, c3 = st.columns(3)
    producto = c1.text_input("Producto", value=_clean_text(trabajo_sel["producto"]) if trabajo_sel is not None else "")
    cliente = c2.text_input("Cliente", value=_clean_text(trabajo_sel["cliente"]) if trabajo_sel is not None else "")
    tipo_producto = c3.selectbox(
        "Tipo de producto",
        TIPOS_PRODUCTO,
        index=TIPOS_PRODUCTO.index(_clean_text(trabajo_sel["tipo_producto"])) if trabajo_sel is not None and _clean_text(trabajo_sel["tipo_producto"]) in TIPOS_PRODUCTO else len(TIPOS_PRODUCTO) - 1,
    )

    c4, c5, c6 = st.columns(3)
    diseno = c4.text_input("Diseño / referencia", value=_clean_text(trabajo_sel["diseno"]) if trabajo_sel is not None else "")
    cantidad_programada = c5.number_input(
        "Cantidad programada",
        min_value=1.0,
        value=float(_safe_float(trabajo_sel["cantidad"], 1.0)) if trabajo_sel is not None else 1.0,
        step=1.0,
    )
    lote_codigo = c6.text_input("Código de lote", value="")

    st.markdown("### Integración")
    i1, i2 = st.columns(2)

    if not df_rutas.empty:
        ruta_idx = i1.selectbox(
            "Ruta de producción (opcional)",
            options=[None] + df_rutas.index.tolist(),
            format_func=lambda i: "Sin ruta" if i is None else f"{df_rutas.loc[i, 'codigo']} · {df_rutas.loc[i, 'nombre']}",
        )
        ruta_sel = df_rutas.loc[ruta_idx] if ruta_idx is not None else None
    else:
        ruta_sel = None
        i1.caption("No hay rutas activas.")

    orden_produccion_id = i2.number_input("Orden de producción ID (opcional)", min_value=0, value=0, step=1)

    st.markdown("### Inventario vinculado")
    v1, v2 = st.columns(2)

    if not df_materiales.empty:
        material_idx = v1.selectbox(
            "Material base",
            options=[None] + df_materiales.index.tolist(),
            format_func=lambda i: "Sin material vinculado" if i is None else f"{df_materiales.loc[i, 'nombre']} · stock {df_materiales.loc[i, 'stock']} {df_materiales.loc[i, 'unidad']}",
        )
        material_sel = df_materiales.loc[material_idx] if material_idx is not None else None
    else:
        material_sel = None
        v1.caption("No hay materiales disponibles.")

    if not df_tintas.empty:
        tinta_idx = v2.selectbox(
            "Tinta base inventario",
            options=[None] + df_tintas.index.tolist(),
            format_func=lambda i: "Manual" if i is None else f"{df_tintas.loc[i, 'nombre']} · stock {df_tintas.loc[i, 'stock']} {df_tintas.loc[i, 'unidad']}",
        )
        tinta_sel = df_tintas.loc[tinta_idx] if tinta_idx is not None else None
    else:
        tinta_sel = None
        v2.caption("No hay tintas en inventario.")

    st.markdown("### Parámetros de sublimación")
    p1, p2, p3, p4 = st.columns(4)
    maquina = p1.selectbox("Máquina", MAQUINAS_DEFAULT + ["Otra"])
    temperatura_c = p2.number_input("Temperatura (°C)", min_value=0.0, value=180.0, step=1.0)
    tiempo_seg = p3.number_input("Tiempo (seg)", min_value=0.0, value=60.0, step=1.0)
    presion = p4.selectbox("Presión", PRESIONES, index=1)

    p5, p6 = st.columns(2)
    papel_tipo = p5.text_input("Tipo de papel", value="Papel sublimación")
    tinta_tipo = p6.text_input(
        "Tipo de tinta",
        value=str(tinta_sel["nombre"]) if tinta_sel is not None else "Tinta sublimación",
    )

    st.markdown("### Operación y capacidad")
    o1, o2, o3, o4 = st.columns(4)
    ancho_cm = o1.number_input("Ancho diseño (cm)", min_value=0.0, value=10.0, format="%.2f")
    alto_cm = o2.number_input("Alto diseño (cm)", min_value=0.0, value=10.0, format="%.2f")
    tinta_ml_unidad = o3.number_input("Tinta estimada por unidad (ml)", min_value=0.0, value=1.5, format="%.4f")
    minutos_unidad = o4.number_input("Minutos por unidad", min_value=0.0, value=5.0, format="%.4f")

    st.markdown("### Costos del lote")
    total_transfer_default = float(_safe_float(trabajo_sel["costo_transfer_total"], 0.0)) if trabajo_sel is not None else 0.0
    k1, k2, k3 = st.columns(3)
    costo_transfer_total = k1.number_input("Costo transfer total USD", min_value=0.0, value=total_transfer_default, format="%.4f")
    potencia_kw = k2.number_input("Potencia máquina (kW)", min_value=0.0, value=1.5, format="%.4f")
    costo_kwh = k3.number_input("Costo kWh USD", min_value=0.0, value=0.15, format="%.4f")

    k4, k5, k6, k7 = st.columns(4)
    salario_hora = k4.number_input("Salario/hora operador", min_value=0.0, value=3.0, format="%.4f")
    unidades_hora = k5.number_input("Unidades por hora", min_value=0.1, value=12.0, format="%.4f")
    valor_maquina = k6.number_input("Valor máquina USD", min_value=0.0, value=1500.0, format="%.2f")
    vida_horas = k7.number_input("Vida útil máquina (horas)", min_value=1.0, value=5000.0, format="%.2f")

    costo_material_unit = float(material_sel["costo_ref"]) if material_sel is not None else 0.0
    costo_tinta_unit = float(tinta_sel["costo_ref"]) if tinta_sel is not None else 0.0

    k8, k9, k10 = st.columns(3)
    costo_indirecto_unit = k8.number_input("Costo indirecto unitario USD", min_value=0.0, value=0.0, format="%.4f")
    costo_material_unit_input = k9.number_input("Costo material unitario USD", min_value=0.0, value=float(costo_material_unit), format="%.4f")
    costo_tinta_unit_input = k10.number_input("Costo tinta unitario USD", min_value=0.0, value=float(costo_tinta_unit), format="%.4f")

    operacion = _calc_operacion(
        cantidad_total=float(cantidad_programada),
        minutos_unidad=float(minutos_unidad),
        ancho_cm=float(ancho_cm),
        alto_cm=float(alto_cm),
        tinta_ml_unidad=float(tinta_ml_unidad),
    )

    costos = _calc_costs(
        cantidad_total=float(cantidad_programada),
        costo_transfer_total=float(costo_transfer_total),
        potencia_kw=float(potencia_kw),
        minutos_unidad=float(minutos_unidad),
        costo_kwh=float(costo_kwh),
        salario_hora=float(salario_hora),
        unidades_hora=float(unidades_hora),
        valor_maquina=float(valor_maquina),
        vida_horas=float(vida_horas),
        costo_indirecto_unit=float(costo_indirecto_unit),
        costo_tinta_unit=float(costo_tinta_unit_input),
        costo_material_unit=float(costo_material_unit_input),
    )

    st.markdown("### Resumen técnico")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Área estimada", f"{operacion['area_estimada_cm2']:,.2f} cm²")
    t2.metric("Tinta estimada", f"{operacion['consumo_tinta_estimado_ml']:,.2f} ml")
    t3.metric("Tiempo total", f"{operacion['tiempo_total_estimado_min']:,.2f} min")
    t4.metric("Uso de capacidad", f"{operacion['utilizacion_capacidad_pct']:,.2f}%")

    st.markdown("### Resumen de costo")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Transfer unitario", f"$ {costos['costo_transfer_unit']:.4f}")
    m2.metric("Tinta unitaria", f"$ {costos['costo_tinta_unit']:.4f}")
    m3.metric("Material unitario", f"$ {costos['costo_material_unit']:.4f}")
    m4.metric("Energía unitaria", f"$ {costos['costo_energia_unit']:.4f}")

    m5, m6, m7 = st.columns(3)
    m5.metric("Mano de obra unitaria", f"$ {costos['costo_mano_obra_unit']:.4f}")
    m6.metric("Costo unitario final", f"$ {costos['costo_unitario_final']:.4f}")
    m7.metric("Costo total final", f"$ {costos['costo_total_final']:.2f}")

    observaciones = st.text_area("Observaciones del lote")

    if st.button("✅ Registrar lote de sublimación", use_container_width=True):
        if not _clean_text(producto):
            st.error("Debes indicar el producto.")
            return

        lote_id = _registrar_lote(
            usuario=usuario,
            producto=producto,
            cliente=cliente,
            tipo_producto=tipo_producto,
            diseno=diseno,
            cantidad_programada=float(cantidad_programada),
            maquina=maquina,
            temperatura_c=float(temperatura_c),
            tiempo_seg=float(tiempo_seg),
            presion=presion,
            papel_tipo=papel_tipo,
            tinta_tipo=tinta_tipo,
            observaciones=observaciones,
            costo_transfer_total=float(costo_transfer_total),
            costos=costos,
            operacion=operacion,
            origen="cola_cmyk" if trabajo_sel is not None else "manual",
            referencia_origen=str(trabajo_sel.name) if trabajo_sel is not None else "",
            ruta_id=int(ruta_sel["id"]) if ruta_sel is not None else None,
            ruta_codigo=str(ruta_sel["codigo"]) if ruta_sel is not None else "",
            ruta_nombre=str(ruta_sel["nombre"]) if ruta_sel is not None else "",
            orden_produccion_id=int(orden_produccion_id) if int(orden_produccion_id) > 0 else None,
            lote_codigo=lote_codigo,
            material_base_id=int(material_sel["id"]) if material_sel is not None else None,
            material_base_nombre=str(material_sel["nombre"]) if material_sel is not None else "",
            material_base_unidad=str(material_sel["unidad"]) if material_sel is not None else "unidad",
            tinta_inventario_id=int(tinta_sel["id"]) if tinta_sel is not None else None,
            tinta_inventario_nombre=str(tinta_sel["nombre"]) if tinta_sel is not None else "",
            tinta_inventario_unidad=str(tinta_sel["unidad"]) if tinta_sel is not None else "ml",
        )

        st.success(f"Lote registrado correctamente. ID #{lote_id}")
        st.rerun()


def _render_control_produccion(usuario: str) -> None:
    st.subheader("🧪 Producción, calidad y merma")

    df_lotes = _load_lotes_df()
    if df_lotes.empty:
        st.info("No hay lotes registrados.")
        return

    lote_id = st.selectbox(
        "Selecciona lote",
        options=df_lotes["id"].tolist(),
        format_func=lambda x: f"{df_lotes.loc[df_lotes['id'] == x, 'codigo'].iloc[0]} · {df_lotes.loc[df_lotes['id'] == x, 'producto'].iloc[0]}",
    )

    row = df_lotes[df_lotes["id"] == lote_id].iloc[0]

    st.markdown("### Datos del lote")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Programada", f"{float(row['cantidad_programada']):,.2f}")
    a2.metric("Costo unitario", f"$ {float(row['costo_unitario_final']):,.4f}")
    a3.metric("Estado", str(row["estado"]).title())
    a4.metric("Merma actual", f"{float(row['merma_pct']):,.2f}%")

    st.markdown("### Resultado de producción")
    r1, r2, r3, r4 = st.columns(4)
    producida = r1.number_input("Cantidad producida", min_value=0.0, value=float(row["cantidad_programada"] or 0.0), step=1.0)
    aprobada = r2.number_input("Cantidad aprobada", min_value=0.0, value=float(row["cantidad_aprobada"] or 0.0), step=1.0)
    reproceso = r3.number_input("Cantidad reproceso", min_value=0.0, value=float(row["cantidad_reproceso"] or 0.0), step=1.0)
    rechazada = r4.number_input("Cantidad rechazada", min_value=0.0, value=float(row["cantidad_rechazada"] or 0.0), step=1.0)

    rr1, rr2, rr3, rr4 = st.columns(4)
    consumo_tinta_real_ml = rr1.number_input(
        "Consumo real tinta (ml)",
        min_value=0.0,
        value=float(row["consumo_tinta_estimado_ml"] or 0.0),
        format="%.4f",
    )
    consumo_material_real_unid = rr2.number_input(
        "Consumo real material",
        min_value=0.0,
        value=float(row["consumo_material_estimado_unid"] or 0.0),
        format="%.4f",
    )
    tiempo_total_real_min = rr3.number_input(
        "Tiempo real total (min)",
        min_value=0.0,
        value=float(row["tiempo_total_estimado_min"] or 0.0),
        format="%.2f",
    )
    calidad_acabado = rr4.selectbox(
        "Calidad del acabado",
        CALIDADES_ACABADO,
        index=CALIDADES_ACABADO.index(str(row["calidad_acabado"]).lower()) if str(row["calidad_acabado"]).lower() in CALIDADES_ACABADO else 1,
    )

    merma = max(float(producida) - float(aprobada) - float(reproceso), 0.0)
    st.caption(f"Merma calculada sugerida: {merma:,.2f} unidades")

    descontar_inventario_real = st.checkbox("Descontar consumo real desde inventario", value=False)
    prod_obs = st.text_area("Observaciones de producción", value=_clean_text(row["observaciones"]), key="sub_prod_obs")

    if st.button("💾 Guardar resultado de producción", use_container_width=True):
        _actualizar_resultado_lote(
            lote_id=int(lote_id),
            usuario=usuario,
            producida=float(producida),
            aprobada=float(aprobada),
            reproceso=float(reproceso),
            merma=float(merma),
            rechazada=float(rechazada),
            consumo_tinta_real_ml=float(consumo_tinta_real_ml),
            consumo_material_real_unid=float(consumo_material_real_unid),
            tiempo_total_real_min=float(tiempo_total_real_min),
            calidad_acabado=calidad_acabado,
            observaciones=prod_obs,
            descontar_inventario_real=bool(descontar_inventario_real),
        )
        st.success("Resultado de producción actualizado.")
        st.rerun()

    st.divider()
    st.markdown("### Control de calidad")

    q1, q2, q3, q4, q5 = st.columns(5)
    color_correcto = q1.checkbox("Color correcto", value=True)
    transferencia_completa = q2.checkbox("Transferencia completa", value=True)
    sin_manchas = q3.checkbox("Sin manchas", value=True)
    sin_ghosting = q4.checkbox("Sin ghosting", value=True)
    sin_quemado = q5.checkbox("Sin quemado", value=True)

    qc_resultado = st.selectbox("Resultado calidad", RESULTADOS_CALIDAD)
    qc_obs = st.text_area("Observaciones calidad", key="sub_qc_obs")

    if st.button("✅ Registrar control de calidad", use_container_width=True):
        _registrar_control_calidad(
            lote_id=int(lote_id),
            usuario=usuario,
            color_correcto=bool(color_correcto),
            transferencia_completa=bool(transferencia_completa),
            sin_manchas=bool(sin_manchas),
            sin_ghosting=bool(sin_ghosting),
            sin_quemado=bool(sin_quemado),
            observaciones=qc_obs,
            resultado=qc_resultado,
        )
        st.success("Control de calidad registrado.")
        st.rerun()

    st.divider()
    st.markdown("### Registrar merma / desperdicio")

    mm1, mm2 = st.columns(2)
    tipo_falla = mm1.text_input("Tipo de falla", value="Falla de calor")
    cantidad_merma = mm2.number_input("Cantidad dañada", min_value=0.0, value=0.0, step=1.0)

    costo_estimado = float(cantidad_merma) * float(_safe_float(row["costo_unitario_final"], 0.0))
    st.metric("Costo estimado merma", f"$ {costo_estimado:,.2f}")

    merma_obs = st.text_area("Observaciones merma", key="sub_merma_obs")
    if st.button("♻️ Registrar merma", use_container_width=True):
        if float(cantidad_merma) <= 0:
            st.error("La cantidad de merma debe ser mayor a cero.")
            return

        _registrar_merma(
            lote_id=int(lote_id),
            usuario=usuario,
            tipo_falla=tipo_falla,
            cantidad=float(cantidad_merma),
            costo_estimado_usd=float(costo_estimado),
            observaciones=merma_obs,
        )
        st.success("Merma registrada.")
        st.rerun()

    st.divider()
    st.markdown("### 🔗 Interoperabilidad del lote")

    current_row = _load_lotes_df()
    current_row = current_row[current_row["id"] == lote_id].iloc[0]

    def _build_to_costeo():
        return (
            "sublimacion_costeo",
            {
                "referencia": current_row["codigo"],
                "producto": current_row["producto"],
                "cantidad": current_row["cantidad_programada"],
                "costo_estimado": current_row["costo_total_final"],
                "costo_real": current_row["costo_total_real"],
                "tipo_proceso": "sublimacion",
            },
        )

    def _build_to_calidad():
        return (
            "sublimacion_calidad",
            {
                "lote": current_row["codigo"],
                "producto": current_row["producto"],
                "cliente": current_row["cliente"],
                "acabado": current_row["calidad_acabado"],
                "cantidad": current_row["cantidad_programada"],
            },
        )

    def _build_to_mermas():
        return (
            "sublimacion_mermas",
            {
                "lote": current_row["codigo"],
                "producto": current_row["producto"],
                "cantidad_merma": current_row["cantidad_merma"],
                "merma_pct": current_row["merma_pct"],
                "costo_merma": current_row["costo_total_real"],
            },
        )

    render_send_buttons(
        source_module="sublimación",
        payload_builders={
            "costeo industrial": _build_to_costeo,
            "control de calidad": _build_to_calidad,
            "mermas y desperdicio": _build_to_mermas,
        },
    )


def _render_historial() -> None:
    st.subheader("📚 Historial de sublimación")

    df_lotes = _load_lotes_df()
    if df_lotes.empty:
        st.info("No hay historial todavía.")
        return

    b1, b2 = st.columns(2)
    buscar = b1.text_input("Buscar producto / cliente")
    estado = b2.selectbox("Estado", ["Todos"] + ESTADOS_LOTE)

    view = df_lotes.copy()
    if buscar:
        mask = (
            view["producto"].astype(str).str.contains(buscar, case=False, na=False)
            | view["cliente"].astype(str).str.contains(buscar, case=False, na=False)
            | view["diseno"].astype(str).str.contains(buscar, case=False, na=False)
            | view["codigo"].astype(str).str.contains(buscar, case=False, na=False)
        )
        view = view[mask]

    if estado != "Todos":
        view = view[view["estado"].astype(str).str.lower() == estado.lower()]

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad_programada": st.column_config.NumberColumn("Programada", format="%.2f"),
            "cantidad_producida": st.column_config.NumberColumn("Producida", format="%.2f"),
            "cantidad_aprobada": st.column_config.NumberColumn("Aprobada", format="%.2f"),
            "cantidad_reproceso": st.column_config.NumberColumn("Reproceso", format="%.2f"),
            "cantidad_merma": st.column_config.NumberColumn("Merma", format="%.2f"),
            "consumo_tinta_estimado_ml": st.column_config.NumberColumn("Tinta est. ml", format="%.2f"),
            "consumo_tinta_real_ml": st.column_config.NumberColumn("Tinta real ml", format="%.2f"),
            "costo_unitario_final": st.column_config.NumberColumn("Costo unitario", format="%.4f"),
            "costo_total_final": st.column_config.NumberColumn("Costo total est.", format="%.2f"),
            "costo_total_real": st.column_config.NumberColumn("Costo total real", format="%.2f"),
            "merma_pct": st.column_config.NumberColumn("Merma %", format="%.2f"),
        },
    )

    df_qc = _load_qc_df()
    if not df_qc.empty:
        st.markdown("### Controles de calidad")
        st.dataframe(df_qc, use_container_width=True, hide_index=True)

    df_mermas = _load_mermas_df()
    if not df_mermas.empty:
        st.markdown("### Mermas registradas")
        st.dataframe(df_mermas, use_container_width=True, hide_index=True)

    df_consumos = _load_consumos_df()
    if not df_consumos.empty:
        st.markdown("### Consumos registrados")
        st.dataframe(df_consumos, use_container_width=True, hide_index=True)

    df_hist = _load_historial_df()
    if not df_hist.empty:
        st.markdown("### Bitácora")
        st.dataframe(df_hist, use_container_width=True, hide_index=True)


def _render_metricas() -> None:
    st.subheader("📊 Métricas de sublimación")

    df_lotes = _load_lotes_df()
    df_mermas = _load_mermas_df()
    df_qc = _load_qc_df()

    if df_lotes.empty:
        st.info("No hay datos para métricas.")
        return

    total_lotes = len(df_lotes)
    total_programado = _safe_sum(df_lotes, "cantidad_programada")
    total_aprobado = _safe_sum(df_lotes, "cantidad_aprobada")
    total_merma = _safe_sum(df_lotes, "cantidad_merma")
    costo_total_est = _safe_sum(df_lotes, "costo_total_final")
    costo_total_real = _safe_sum(df_lotes, "costo_total_real")
    tinta_total_est = _safe_sum(df_lotes, "consumo_tinta_estimado_ml")
    tinta_total_real = _safe_sum(df_lotes, "consumo_tinta_real_ml")
    merma_pct_global = (total_merma / max(total_programado, 0.0001)) * 100.0 if total_programado > 0 else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Lotes", total_lotes)
    m2.metric("Unidades programadas", f"{total_programado:,.2f}")
    m3.metric("Unidades aprobadas", f"{total_aprobado:,.2f}")
    m4.metric("Merma global", f"{merma_pct_global:,.2f}%")
    m5.metric("Costo real total", f"$ {costo_total_real:,.2f}")

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Tinta estimada total", f"{tinta_total_est:,.2f} ml")
    n2.metric("Tinta real total", f"{tinta_total_real:,.2f} ml")
    n3.metric("Costo estimado total", f"$ {costo_total_est:,.2f}")
    n4.metric("Desviación costo", f"$ {(costo_total_real - costo_total_est):,.2f}")

    por_producto = (
        df_lotes.groupby("producto", as_index=False)[
            [
                "cantidad_programada",
                "cantidad_aprobada",
                "cantidad_merma",
                "consumo_tinta_real_ml",
                "costo_total_real",
            ]
        ]
        .sum()
        .sort_values("costo_total_real", ascending=False)
    )
    st.markdown("### Producción por producto")
    st.dataframe(por_producto, use_container_width=True, hide_index=True)

    if not df_mermas.empty:
        st.markdown("### Mermas por tipo de falla")
        por_falla = (
            df_mermas.groupby("tipo_falla", as_index=False)[["cantidad", "costo_estimado_usd"]]
            .sum()
            .sort_values("costo_estimado_usd", ascending=False)
        )
        st.dataframe(por_falla, use_container_width=True, hide_index=True)

    if not df_qc.empty:
        st.markdown("### Resultados de calidad")
        resumen_qc = (
            df_qc.groupby("resultado", as_index=False)["id"]
            .count()
            .rename(columns={"id": "cantidad"})
            .sort_values("cantidad", ascending=False)
        )
        st.dataframe(resumen_qc, use_container_width=True, hide_index=True)

    capacidad = (
        df_lotes.groupby("maquina", as_index=False)[["cantidad_programada", "capacidad_turno_unidades", "utilizacion_capacidad_pct"]]
        .sum()
        .sort_values("utilizacion_capacidad_pct", ascending=False)
    )
    if not capacidad.empty:
        st.markdown("### Capacidad instalada por máquina")
        st.dataframe(capacidad, use_container_width=True, hide_index=True)


# ============================================================
# ENTRYPOINT
# ============================================================

def render_sublimacion(usuario: str) -> None:
    _ensure_sublimacion_tables()

    st.title("🔥 Sublimación Industrial PRO")
    st.caption(
        "Consumo de tinta y material, capacidad instalada, tiempos, reprocesos y calidad del acabado."
    )

    def _apply_inbox(inbox: dict) -> None:
        payload_data = dict(inbox.get("payload_data", {}))
        cola = st.session_state.get("cola_sublimacion", [])
        cola.append(payload_data)
        st.session_state["cola_sublimacion"] = cola

    render_module_inbox("sublimación", apply_callback=_apply_inbox, clear_after_apply=False)

    tabs = st.tabs(
        [
            "📥 Cola",
            "⚙️ Registro de lote",
            "🧪 Producción / Calidad / Merma",
            "📚 Historial",
            "📊 Métricas",
        ]
    )

    with tabs[0]:
        _render_cola()

    with tabs[1]:
        _render_registro(usuario)

    with tabs[2]:
        _render_control_produccion(usuario)

    with tabs[3]:
        _render_historial()

    with tabs[4]:
        _render_metricas()

    st.divider()
    st.markdown("### 🔗 Interoperabilidad del módulo")

    def _build_to_costeo_mod():
        return (
            "sublimacion_resumen_costeo",
            {
                "modulo": "sublimacion",
                "fecha": _today_iso(),
            },
        )

    def _build_to_rutas_mod():
        return (
            "sublimacion_rutas",
            {
                "modulo": "sublimacion",
                "fecha": _today_iso(),
            },
        )

    render_send_buttons(
        source_module="sublimación",
        payload_builders={
            "costeo industrial": _build_to_costeo_mod,
            "rutas de producción": _build_to_rutas_mod,
        },
    )
