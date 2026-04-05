from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.integration_hub import dispatch_to_module, render_module_inbox, render_send_buttons


# ============================================================
# AUXILIARES
# ============================================================

def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


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


def _next_cut_code() -> str:
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT codigo FROM ordenes_corte ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row or not row["codigo"]:
        return "CUT-0001"
    last = str(row["codigo"]).split("-")[-1]
    n = _safe_int(last, 0) + 1
    return f"CUT-{n:04d}"


def _filter_df(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    txt = _clean_text(query)
    if not txt or df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(txt, case=False, na=False)
    return df[mask]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_corte_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_corte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                archivo_nombre TEXT,
                referencia TEXT,
                material_id INTEGER,
                material_nombre TEXT,
                equipo_id INTEGER,
                equipo_nombre TEXT,
                profundidad REAL NOT NULL DEFAULT 0,
                velocidad REAL NOT NULL DEFAULT 0,
                presion REAL NOT NULL DEFAULT 0,
                area_cm2_estimada REAL NOT NULL DEFAULT 0,
                cm_corte_estimado REAL NOT NULL DEFAULT 0,
                tiempo_estimado_min REAL NOT NULL DEFAULT 0,
                costo_estimado_usd REAL NOT NULL DEFAULT 0,
                cantidad_material_estimada REAL NOT NULL DEFAULT 0,
                desgaste_por_cm REAL NOT NULL DEFAULT 0,
                orden_produccion_id INTEGER,
                prioridad TEXT NOT NULL DEFAULT 'normal',
                estado TEXT NOT NULL DEFAULT 'analizado',
                observaciones TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ejecuciones_corte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_corte_id INTEGER NOT NULL,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                usuario TEXT NOT NULL,
                cm_corte_real REAL NOT NULL DEFAULT 0,
                tiempo_real_min REAL NOT NULL DEFAULT 0,
                material_real_usado REAL NOT NULL DEFAULT 0,
                merma REAL NOT NULL DEFAULT 0,
                retazo_reutilizable REAL NOT NULL DEFAULT 0,
                costo_real_usd REAL NOT NULL DEFAULT 0,
                desgaste_registrado REAL NOT NULL DEFAULT 0,
                incidencias TEXT,
                estado_final TEXT NOT NULL DEFAULT 'terminado',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movimientos_corte_material (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_corte_id INTEGER NOT NULL,
                inventario_id INTEGER,
                material_nombre TEXT,
                tipo TEXT NOT NULL DEFAULT 'salida',
                cantidad REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                referencia TEXT,
                usuario TEXT NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS retazos_corte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_corte_id INTEGER NOT NULL,
                inventario_id_origen INTEGER,
                material_nombre TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                reutilizable INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_ordenes_corte_estado ON ordenes_corte(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ordenes_corte_material ON ordenes_corte(material_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ejecuciones_corte_orden ON ejecuciones_corte(orden_corte_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_corte_orden ON movimientos_corte_material(orden_corte_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_retazos_corte_orden ON retazos_corte(orden_corte_id)")


# ============================================================
# LOADERS DINAMICOS
# ============================================================

def _load_materiales_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _get_table_columns(conn, "inventario")
        if not cols:
            return pd.DataFrame(columns=["id", "material", "stock", "unidad", "costo_ref"])

        id_col = "id"
        name_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
        stock_col = "stock_actual" if "stock_actual" in cols else "cantidad" if "cantidad" in cols else None
        unidad_col = "unidad" if "unidad" in cols else None
        cost_col = (
            "costo_unitario_usd"
            if "costo_unitario_usd" in cols
            else "precio_usd"
            if "precio_usd" in cols
            else None
        )
        active_col = "estado" if "estado" in cols else "activo" if "activo" in cols else None

        if not name_col:
            return pd.DataFrame(columns=["id", "material", "stock", "unidad", "costo_ref"])

        query = f"SELECT {id_col} AS id, {name_col} AS material"
        query += f", COALESCE({stock_col}, 0) AS stock" if stock_col else ", 0 AS stock"
        query += f", COALESCE({unidad_col}, 'unidad') AS unidad" if unidad_col else ", 'unidad' AS unidad"
        query += f", COALESCE({cost_col}, 0) AS costo_ref" if cost_col else ", 0 AS costo_ref"
        query += " FROM inventario"

        conditions: list[str] = []
        if active_col == "estado":
            conditions.append("COALESCE(estado,'activo')='activo'")
        elif active_col == "activo":
            conditions.append("COALESCE(activo,1)=1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY material ASC"

        rows = conn.execute(query).fetchall()

    return pd.DataFrame(rows, columns=["id", "material", "stock", "unidad", "costo_ref"])


def _load_equipos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _get_table_columns(conn, "activos")
        if not cols:
            return pd.DataFrame(columns=["id", "equipo", "categoria", "desgaste_por_cm", "desgaste_actual"])

        id_col = "id"
        equipo_col = "equipo" if "equipo" in cols else "nombre" if "nombre" in cols else None
        categoria_col = "categoria" if "categoria" in cols else None
        desgaste_cm_expr = (
            "COALESCE(desgaste_por_cm, desgaste_por_uso, 0)"
            if "desgaste_por_cm" in cols or "desgaste_por_uso" in cols
            else "0"
        )
        desgaste_actual_expr = (
            "COALESCE(desgaste, 0)"
            if "desgaste" in cols
            else "COALESCE(desgaste_por_uso, 0)"
            if "desgaste_por_uso" in cols
            else "0"
        )
        active_col = "activo" if "activo" in cols else "estado" if "estado" in cols else None

        if not equipo_col:
            return pd.DataFrame(columns=["id", "equipo", "categoria", "desgaste_por_cm", "desgaste_actual"])

        query = f"""
            SELECT
                {id_col} AS id,
                {equipo_col} AS equipo,
                {"COALESCE(" + categoria_col + ", '')" if categoria_col else "''"} AS categoria,
                {desgaste_cm_expr} AS desgaste_por_cm,
                {desgaste_actual_expr} AS desgaste_actual
            FROM activos
        """

        conditions: list[str] = []
        if active_col == "activo":
            conditions.append("COALESCE(activo,1)=1")
        elif active_col == "estado":
            conditions.append("COALESCE(estado,'activo')='activo'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY equipo ASC"

        rows = conn.execute(query).fetchall()

    df = pd.DataFrame(rows, columns=["id", "equipo", "categoria", "desgaste_por_cm", "desgaste_actual"])
    if df.empty:
        return df

    filtered = df[df["categoria"].astype(str).str.contains("Corte|Plotter|Cameo", case=False, na=False)]
    return filtered if not filtered.empty else df


def _load_ordenes_corte_df() -> pd.DataFrame:
    _ensure_corte_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                codigo,
                fecha,
                usuario,
                archivo_nombre,
                referencia,
                material_nombre,
                equipo_nombre,
                profundidad,
                velocidad,
                presion,
                area_cm2_estimada,
                cm_corte_estimado,
                tiempo_estimado_min,
                costo_estimado_usd,
                cantidad_material_estimada,
                prioridad,
                estado,
                observaciones,
                orden_produccion_id
            FROM ordenes_corte
            ORDER BY id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "codigo",
        "fecha",
        "usuario",
        "archivo_nombre",
        "referencia",
        "material_nombre",
        "equipo_nombre",
        "profundidad",
        "velocidad",
        "presion",
        "area_cm2_estimada",
        "cm_corte_estimado",
        "tiempo_estimado_min",
        "costo_estimado_usd",
        "cantidad_material_estimada",
        "prioridad",
        "estado",
        "observaciones",
        "orden_produccion_id",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_ejecuciones_corte_df() -> pd.DataFrame:
    _ensure_corte_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                e.id,
                e.orden_corte_id,
                o.codigo,
                o.material_nombre,
                o.equipo_nombre,
                e.fecha_inicio,
                e.fecha_fin,
                e.usuario,
                e.cm_corte_real,
                e.tiempo_real_min,
                e.material_real_usado,
                e.merma,
                e.retazo_reutilizable,
                e.costo_real_usd,
                e.desgaste_registrado,
                e.incidencias,
                e.estado_final
            FROM ejecuciones_corte e
            JOIN ordenes_corte o ON o.id = e.orden_corte_id
            ORDER BY e.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "orden_corte_id",
        "codigo",
        "material_nombre",
        "equipo_nombre",
        "fecha_inicio",
        "fecha_fin",
        "usuario",
        "cm_corte_real",
        "tiempo_real_min",
        "material_real_usado",
        "merma",
        "retazo_reutilizable",
        "costo_real_usd",
        "desgaste_registrado",
        "incidencias",
        "estado_final",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_movimientos_corte_df() -> pd.DataFrame:
    _ensure_corte_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.orden_corte_id,
                o.codigo,
                m.material_nombre,
                m.tipo,
                m.cantidad,
                m.unidad,
                m.referencia,
                m.usuario,
                m.fecha
            FROM movimientos_corte_material m
            JOIN ordenes_corte o ON o.id = m.orden_corte_id
            ORDER BY m.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "orden_corte_id",
        "codigo",
        "material_nombre",
        "tipo",
        "cantidad",
        "unidad",
        "referencia",
        "usuario",
        "fecha",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_retazos_df() -> pd.DataFrame:
    _ensure_corte_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                r.id,
                r.orden_corte_id,
                o.codigo,
                r.material_nombre,
                r.cantidad,
                r.unidad,
                r.reutilizable,
                r.observaciones,
                r.fecha
            FROM retazos_corte r
            JOIN ordenes_corte o ON o.id = r.orden_corte_id
            ORDER BY r.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "orden_corte_id",
        "codigo",
        "material_nombre",
        "cantidad",
        "unidad",
        "reutilizable",
        "observaciones",
        "fecha",
    ]
    return pd.DataFrame(rows, columns=cols)


# ============================================================
# SERVICIOS
# ============================================================

def _registrar_orden_produccion(
    usuario: str,
    tipo: str,
    referencia: str,
    costo_estimado: float,
    estado: str = "Pendiente",
) -> int:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ordenes_produccion (usuario, tipo, referencia, costo_estimado, estado)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(usuario), str(tipo), str(referencia), float(costo_estimado), str(estado)),
        )
        return int(cur.lastrowid)


def _crear_orden_corte(
    usuario: str,
    archivo_nombre: str,
    referencia: str,
    material_id: int,
    material_nombre: str,
    equipo_id: int,
    equipo_nombre: str,
    profundidad: float,
    velocidad: float,
    presion: float,
    area_cm2_estimada: float,
    cm_corte_estimado: float,
    tiempo_estimado_min: float,
    costo_estimado_usd: float,
    cantidad_material_estimada: float,
    desgaste_por_cm: float,
    prioridad: str = "normal",
    observaciones: str = "",
    orden_produccion_id: int | None = None,
) -> int:
    _ensure_corte_tables()
    codigo = _next_cut_code()

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ordenes_corte(
                codigo, fecha, usuario, archivo_nombre, referencia,
                material_id, material_nombre, equipo_id, equipo_nombre,
                profundidad, velocidad, presion,
                area_cm2_estimada, cm_corte_estimado, tiempo_estimado_min,
                costo_estimado_usd, cantidad_material_estimada, desgaste_por_cm,
                prioridad, estado, observaciones, orden_produccion_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                codigo,
                _today_iso(),
                str(usuario),
                _clean_text(archivo_nombre),
                _clean_text(referencia),
                int(material_id),
                _clean_text(material_nombre),
                int(equipo_id),
                _clean_text(equipo_nombre),
                float(profundidad),
                float(velocidad),
                float(presion),
                float(area_cm2_estimada),
                float(cm_corte_estimado),
                float(tiempo_estimado_min),
                float(costo_estimado_usd),
                float(cantidad_material_estimada),
                float(desgaste_por_cm),
                _clean_text(prioridad) or "normal",
                "analizado",
                _clean_text(observaciones),
                int(orden_produccion_id) if orden_produccion_id is not None else None,
            ),
        )
        return int(cur.lastrowid)


def _actualizar_estado_orden_corte(orden_id: int, estado: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE ordenes_corte SET estado=? WHERE id=?",
            (_clean_text(estado), int(orden_id)),
        )


def _descontar_inventario_material(
    conn,
    inventario_id: int,
    cantidad: float,
) -> tuple[str, str]:
    cols = _get_table_columns(conn, "inventario")
    if not cols:
        raise ValueError("La tabla inventario no existe.")

    stock_col = "stock_actual" if "stock_actual" in cols else "cantidad" if "cantidad" in cols else None
    name_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
    unidad_col = "unidad" if "unidad" in cols else None

    if not stock_col or not name_col:
        raise ValueError("La tabla inventario no tiene columnas compatibles para corte.")

    unidad_expr = f"COALESCE({unidad_col}, 'unidad')" if unidad_col else "'unidad'"
    row = conn.execute(
        f"SELECT {name_col} AS nombre, COALESCE({stock_col},0) AS stock, {unidad_expr} AS unidad "
        "FROM inventario WHERE id=?",
        (int(inventario_id),),
    ).fetchone()st.title("✂️ Corte Industrial – Cameo")

    if not row:
        raise ValueError("Material no encontrado en inventario.")

    stock_actual = float(row["stock"] or 0.0)
    cantidad = float(cantidad or 0.0)
    if cantidad <= 0:
        raise ValueError("La cantidad a descontar debe ser mayor a cero.")
    if stock_actual < cantidad:
        raise ValueError("Inventario insuficiente para descontar material.")

    conn.execute(
        f"UPDATE inventario SET {stock_col} = COALESCE({stock_col},0) - ? WHERE id=?",
        (float(cantidad), int(inventario_id)),
    )
    return str(row["nombre"]), str(row["unidad"])


def _registrar_movimiento_corte_material(
    conn,
    orden_corte_id: int,
    inventario_id: int,
    material_nombre: str,
    tipo: str,
    cantidad: float,
    unidad: str,
    referencia: str,
    usuario: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO movimientos_corte_material(
            orden_corte_id, inventario_id, material_nombre, tipo, cantidad, unidad, referencia, usuario, fecha
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            int(orden_corte_id),
            int(inventario_id),
            _clean_text(material_nombre),
            _clean_text(tipo) or "salida",
            float(cantidad),
            _clean_text(unidad) or "unidad",
            _clean_text(referencia),
            _clean_text(usuario),
            _now_iso(),
        ),
    )
    return int(cur.lastrowid)


def _registrar_retazo(
    conn,
    orden_corte_id: int,
    inventario_id_origen: int,
    material_nombre: str,
    cantidad: float,
    unidad: str,
    reutilizable: bool,
    observaciones: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO retazos_corte(
            orden_corte_id, inventario_id_origen, material_nombre, cantidad, unidad, reutilizable, observaciones, fecha
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            int(orden_corte_id),
            int(inventario_id_origen),
            _clean_text(material_nombre),
            float(cantidad),
            _clean_text(unidad) or "unidad",
            1 if reutilizable else 0,
            _clean_text(observaciones),
            _now_iso(),
        ),
    )
    return int(cur.lastrowid)


def _registrar_desgaste_equipo(conn, equipo_id: int, desgaste_inc: float) -> None:
    cols = _get_table_columns(conn, "activos")
    if not cols:
        return

    if "desgaste" in cols:
        conn.execute(
            "UPDATE activos SET desgaste = COALESCE(desgaste,0) + ? WHERE id=?",
            (float(desgaste_inc), int(equipo_id)),
        )
    elif "desgaste_por_uso" in cols:
        conn.execute(
            "UPDATE activos SET desgaste_por_uso = COALESCE(desgaste_por_uso,0) + ? WHERE id=?",
            (float(desgaste_inc), int(equipo_id)),
        )


def _ejecutar_corte(
    usuario: str,
    orden_corte_id: int,
    cm_corte_real: float,
    tiempo_real_min: float,
    material_real_usado: float,
    merma: float,
    retazo_reutilizable: float,
    incidencias: str = "",
) -> int:
    _ensure_corte_tables()

    with db_transaction() as conn:
        orden = conn.execute(
            """
            SELECT id, codigo, material_id, material_nombre, equipo_id, desgaste_por_cm, costo_estimado_usd
            FROM ordenes_corte
            WHERE id=?
            """,
            (int(orden_corte_id),),
        ).fetchone()
        if not orden:
            raise ValueError("La orden de corte no existe.")

        if str(
            conn.execute("SELECT estado FROM ordenes_corte WHERE id=?", (int(orden_corte_id),)).fetchone()["estado"]
        ).lower() in {"terminado", "cancelado"}:
            raise ValueError("La orden ya está cerrada o cancelada.")

        material_nombre, unidad = _descontar_inventario_material(
            conn,
            inventario_id=int(orden["material_id"]),
            cantidad=float(material_real_usado),
        )

        _registrar_movimiento_corte_material(
            conn=conn,
            orden_corte_id=int(orden_corte_id),
            inventario_id=int(orden["material_id"]),
            material_nombre=material_nombre,
            tipo="salida",
            cantidad=float(material_real_usado),
            unidad=unidad,
            referencia=f"Consumo por corte {orden['codigo']}",
            usuario=usuario,
        )

        if float(retazo_reutilizable or 0.0) > 0:
            _registrar_retazo(
                conn=conn,
                orden_corte_id=int(orden_corte_id),
                inventario_id_origen=int(orden["material_id"]),
                material_nombre=material_nombre,
                cantidad=float(retazo_reutilizable),
                unidad=unidad,
                reutilizable=True,
                observaciones="Retazo reutilizable generado en ejecución de corte",
            )

        desgaste_registrado = float(cm_corte_real or 0.0) * float(orden["desgaste_por_cm"] or 0.0)
        _registrar_desgaste_equipo(conn, int(orden["equipo_id"]), desgaste_registrado)

        costo_real = round(
            (_safe_float(orden["costo_estimado_usd"], 0.0) * 0.6)
            + (float(tiempo_real_min or 0.0) * 0.35)
            + (float(merma or 0.0) * 0.1),
            2,
        )

        cur = conn.execute(
            """
            INSERT INTO ejecuciones_corte(
                orden_corte_id, fecha_inicio, fecha_fin, usuario,
                cm_corte_real, tiempo_real_min, material_real_usado, merma,
                retazo_reutilizable, costo_real_usd, desgaste_registrado,
                incidencias, estado_final
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(orden_corte_id),
                _now_iso(),
                _now_iso(),
                _clean_text(usuario),
                float(cm_corte_real),
                float(tiempo_real_min),
                float(material_real_usado),
                float(merma),
                float(retazo_reutilizable),
                float(costo_real),
                float(desgaste_registrado),
                _clean_text(incidencias),
                "terminado",
            ),
        )

        conn.execute(
            "UPDATE ordenes_corte SET estado='terminado' WHERE id=?",
            (int(orden_corte_id),),
        )

        return int(cur.lastrowid)


# ============================================================
# ANALISIS
# ============================================================

def _analizar_diseno(
    archivo_bytes: bytes,
    presion: float,
    profundidad_cuchilla: float,
    velocidad: float,
    costo_material_ref: float,
    desgaste_por_cm: float,
) -> dict[str, Any]:
    size_kb = max(len(archivo_bytes) / 1024.0, 1.0)

    area_cm2 = round(size_kb * 6.2 * (1 + (presion / 100.0)), 2)
    cm_corte = round((area_cm2**0.5) * (2.0 + (profundidad_cuchilla / 10.0)) * 1.8, 2)
    complejidad = 1.0 + (presion / 80.0) + (profundidad_cuchilla / 20.0)
    tiempo_estimado_min = round((cm_corte / max(velocidad, 0.1)) * complejidad / 60.0, 2)

    costo_material_cm2 = float(costo_material_ref or 0.0) / 100.0
    costo_material = area_cm2 * costo_material_cm2
    costo_desgaste = cm_corte * float(desgaste_por_cm or 0.0)
    mano_obra = tiempo_estimado_min * 0.35
    costo_estimado = round(costo_material + costo_desgaste + mano_obra, 2)

    return {
        "area_cm2": float(area_cm2),
        "cm_corte": float(cm_corte),
        "tiempo_estimado_min": float(tiempo_estimado_min),
        "costo_estimado": float(costo_estimado),
        "cantidad_descuento_estimada": float(max(area_cm2 / 100.0, 0.01)),
        "costo_material": float(costo_material),
        "costo_desgaste": float(costo_desgaste),
        "mano_obra": float(mano_obra),
    }


# ============================================================
# UI
# ============================================================

def render_corte(usuario: str) -> None:
    _ensure_corte_tables()

    st.title("✂️ Corte Industrial – Cameo")
    st.caption("Análisis técnico, órdenes de corte, ejecución real, merma, retazos y trazabilidad.")

    def _apply_corte_inbox(inbox: dict) -> None:
        st.session_state["datos_corte_desde_cmyk"] = dict(inbox.get("payload_data", {}))

    render_module_inbox("corte industrial", apply_callback=_apply_corte_inbox, clear_after_apply=False)

    if "datos_corte_desde_cmyk" in st.session_state:
        cmyk_data = st.session_state.get("datos_corte_desde_cmyk", {})
        st.success(
            f"Trabajo recibido desde CMYK: {cmyk_data.get('trabajo', 'N/D')} ({cmyk_data.get('cantidad', 0)} uds)"
        )
        st.caption(f"Costo base de impresión recibido: $ {float(cmyk_data.get('costo_base', 0.0)):.2f}")
        if st.button("Limpiar envío CMYK (Corte)", key="btn_clear_cmyk_corte"):
            st.session_state.pop("datos_corte_desde_cmyk", None)
            st.rerun()

    df_materiales = _load_materiales_df()
    df_equipos = _load_equipos_df()
    df_ordenes = _load_ordenes_corte_df()
    df_ejec = _load_ejecuciones_corte_df()
    df_movs = _load_movimientos_corte_df()
    df_retazos = _load_retazos_df()

    total_ordenes = len(df_ordenes)
    abiertas = int(df_ordenes["estado"].astype(str).str.lower().isin(["analizado", "aprobado", "en_proceso"]).sum()) if not df_ordenes.empty else 0
    terminadas = int((df_ordenes["estado"].astype(str).str.lower() == "terminado").sum()) if not df_ordenes.empty else 0
    merma_total = float(df_ejec["merma"].sum()) if not df_ejec.empty else 0.0
    costo_total = float(df_ejec["costo_real_usd"].sum()) if not df_ejec.empty else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Órdenes", total_ordenes)
    m2.metric("Abiertas", abiertas)
    m3.metric("Terminadas", terminadas)
    m4.metric("Merma total", f"{merma_total:,.2f}")
    m5.metric("Costo real acumulado", f"$ {costo_total:,.2f}")

    tab_analisis, tab_ordenes, tab_ejecucion, tab_material, tab_historial = st.tabs(
        [
            "🔍 Analizar",
            "🧾 Órdenes",
            "⚙️ Ejecutar",
            "📦 Material / Merma",
            "📊 Historial",
        ]
    )

    with tab_analisis:
        with st.container(border=True):
            archivo = st.file_uploader(
                "Archivo de diseño",
                type=["svg", "dxf", "png", "jpg", "jpeg", "pdf"],
                key="corte_archivo",
            )

            if not df_materiales.empty:
                mat_idx = st.selectbox(
                    "Material",
                    df_materiales.index,
                    format_func=lambda i: (
                        f"{df_materiales.loc[i, 'material']} | "
                        f"Stock: {float(df_materiales.loc[i, 'stock'] or 0):,.2f} {df_materiales.loc[i, 'unidad']}"
                    ),
                    key="corte_material_idx",
                )
                material_row = df_materiales.loc[mat_idx]
            else:
                material_row = None
                st.warning("No hay materiales activos en inventario.")

            if not df_equipos.empty:
                equipo_idx = st.selectbox(
                    "Equipo",
                    df_equipos.index,
                    format_func=lambda i: (
                        f"{df_equipos.loc[i, 'equipo']} | desgaste/cm: "
                        f"{float(df_equipos.loc[i, 'desgaste_por_cm'] or 0):.6f}"
                    ),
                    key="corte_equipo_idx",
                )
                equipo_row = df_equipos.loc[equipo_idx]
            else:
                equipo_row = None
                st.warning("No hay equipos activos compatibles.")

            c1, c2, c3 = st.columns(3)
            profundidad_cuchilla = c1.number_input("Profundidad cuchilla", min_value=0.0, value=3.0, step=0.1)
            velocidad = c2.number_input("Velocidad", min_value=0.1, value=8.0, step=0.1)
            presion = c3.number_input("Presión", min_value=1.0, value=12.0, step=0.5)

            referencia = st.text_input("Referencia del trabajo", placeholder="Ej: Stickers cliente X")
            prioridad = st.selectbox("Prioridad", ["normal", "alta", "urgente"], key="corte_prioridad")
            observaciones = st.text_area("Observaciones")

        if "corte_resultado" not in st.session_state:
            st.session_state["corte_resultado"] = {}

        cbtn1, cbtn2, cbtn3 = st.columns(3)

        if cbtn1.button("🔍 Analizar diseño", use_container_width=True):
            if archivo is None:
                st.error("Debes subir un archivo para analizar.")
            elif material_row is None:
                st.error("Debes seleccionar un material válido.")
            elif equipo_row is None:
                st.error("Debes seleccionar un equipo válido.")
            else:
                analysis = _analizar_diseno(
                    archivo_bytes=archivo.getvalue(),
                    presion=float(presion),
                    profundidad_cuchilla=float(profundidad_cuchilla),
                    velocidad=float(velocidad),
                    costo_material_ref=float(material_row.get("costo_ref") or 0.0),
                    desgaste_por_cm=float(equipo_row.get("desgaste_por_cm") or 0.0),
                )

                st.session_state["corte_resultado"] = {
                    "archivo": archivo.name,
                    "referencia": _clean_text(referencia) or archivo.name,
                    "material": str(material_row.get("material")),
                    "material_id": int(material_row.get("id")),
                    "material_stock": float(material_row.get("stock") or 0.0),
                    "material_unidad": str(material_row.get("unidad") or "unidad"),
                    "equipo_id": int(equipo_row.get("id")),
                    "equipo": str(equipo_row.get("equipo")),
                    "profundidad": float(profundidad_cuchilla),
                    "velocidad": float(velocidad),
                    "presion": float(presion),
                    "prioridad": str(prioridad),
                    "observaciones": _clean_text(observaciones),
                    "desgaste_por_cm": float(equipo_row.get("desgaste_por_cm") or 0.0),
                    **analysis,
                }
                st.success("Análisis completado. Aún no se descontó material.")

        r = st.session_state.get("corte_resultado", {})
        if r:
            x1, x2, x3, x4 = st.columns(4)
            x1.metric("CM de corte", f"{r.get('cm_corte', 0):,.2f}")
            x2.metric("Área estimada", f"{r.get('area_cm2', 0):,.2f} cm²")
            x3.metric("Tiempo estimado", f"{r.get('tiempo_estimado_min', 0):,.2f} min")
            x4.metric("Costo estimado", f"$ {r.get('costo_estimado', 0):,.2f}")

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "archivo": r.get("archivo"),
                            "referencia": r.get("referencia"),
                            "material": r.get("material"),
                            "equipo": r.get("equipo"),
                            "cm_corte": r.get("cm_corte"),
                            "tiempo_estimado": r.get("tiempo_estimado_min"),
                            "costo_estimado": r.get("costo_estimado"),
                            "consumo_estimado": r.get("cantidad_descuento_estimada"),
                        }
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        if cbtn2.button("📤 Enviar a Cotización", use_container_width=True):
            if not r:
                st.error("Primero debes analizar el diseño.")
            else:
                payload_data = {
                    "tipo_produccion": "corte",
                    "archivo": r.get("archivo"),
                    "material": r.get("material"),
                    "cm_corte": r.get("cm_corte"),
                    "tiempo_estimado": r.get("tiempo_estimado_min"),
                    "costo_base": r.get("costo_estimado"),
                    "costo_estimado": r.get("costo_estimado"),
                    "referencia": r.get("referencia"),
                }
                st.session_state["datos_pre_cotizacion"] = payload_data
                dispatch_to_module(
                    source_module="corte industrial",
                    target_module="cotizaciones",
                    payload={
                        "source_module": "corte industrial",
                        "source_action": "analisis_corte",
                        "record_id": r.get("orden_id"),
                        "referencia": r.get("referencia"),
                        "timestamp": _now_iso(),
                        "usuario": usuario,
                        "payload_data": payload_data,
                    },
                    success_message="Datos enviados al módulo de cotización.",
                )

        if cbtn3.button("🧾 Crear Orden de Corte", use_container_width=True):
            if not r:
                st.error("Primero debes analizar el diseño.")
            else:
                try:
                    orden_prod_id = None
                    if _table_exists(next(iter([db_transaction().__enter__()])), "ordenes_produccion"):  # unsafe
                        pass
                except Exception:
                    orden_prod_id = None

                try:
                    try:
                        orden_prod_id = _registrar_orden_produccion(
                            usuario=usuario,
                            tipo="corte",
                            referencia=f"Corte industrial {r.get('archivo', 'Trabajo corte')}",
                            costo_estimado=float(r.get("costo_estimado", 0.0)),
                        )
                    except Exception:
                        orden_prod_id = None

                    oid = _crear_orden_corte(
                        usuario=usuario,
                        archivo_nombre=str(r.get("archivo")),
                        referencia=str(r.get("referencia")),
                        material_id=int(r.get("material_id")),
                        material_nombre=str(r.get("material")),
                        equipo_id=int(r.get("equipo_id")),
                        equipo_nombre=str(r.get("equipo")),
                        profundidad=float(r.get("profundidad", 0.0)),
                        velocidad=float(r.get("velocidad", 0.0)),
                        presion=float(r.get("presion", 0.0)),
                        area_cm2_estimada=float(r.get("area_cm2", 0.0)),
                        cm_corte_estimado=float(r.get("cm_corte", 0.0)),
                        tiempo_estimado_min=float(r.get("tiempo_estimado_min", 0.0)),
                        costo_estimado_usd=float(r.get("costo_estimado", 0.0)),
                        cantidad_material_estimada=float(r.get("cantidad_descuento_estimada", 0.0)),
                        desgaste_por_cm=float(r.get("desgaste_por_cm", 0.0)),
                        prioridad=str(r.get("prioridad", "normal")),
                        observaciones=str(r.get("observaciones", "")),
                        orden_produccion_id=orden_prod_id,
                    )
                    st.session_state["corte_resultado"]["orden_id"] = int(oid)
                    st.success(f"Orden de corte creada #{oid}")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo crear la orden: {e}")

        if r:
            st.markdown("#### 🔗 Interoperabilidad de corte")

            def _build_to_planificacion():
                return (
                    "orden_corte_analizada",
                    {
                        "orden": r.get("orden_id") or r.get("referencia"),
                        "analisis": r.get("referencia"),
                        "material": r.get("material"),
                        "equipo": r.get("equipo"),
                        "tiempos": r.get("tiempo_estimado_min"),
                        "costo": r.get("costo_estimado"),
                        "referencia": r.get("referencia"),
                    },
                )

            render_send_buttons(
                source_module="corte industrial",
                payload_builders={"planificación de producción": _build_to_planificacion},
            )

    with tab_ordenes:
        st.subheader("Órdenes de corte")
        if df_ordenes.empty:
            st.info("No hay órdenes de corte registradas.")
        else:
            f1, f2 = st.columns([2, 1])
            buscar = f1.text_input("Buscar orden", key="corte_buscar_orden")
            estado = f2.selectbox(
                "Estado",
                ["Todos", "analizado", "aprobado", "en_proceso", "terminado", "cancelado"],
                key="corte_estado_orden",
            )

            view = _filter_df(
                df_ordenes.copy(),
                buscar,
                ["codigo", "archivo_nombre", "referencia", "material_nombre", "equipo_nombre", "usuario", "estado"],
            )
            if estado != "Todos":
                view = view[view["estado"].astype(str).str.lower() == estado]

            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "area_cm2_estimada": st.column_config.NumberColumn("Área", format="%.2f"),
                    "cm_corte_estimado": st.column_config.NumberColumn("CM corte", format="%.2f"),
                    "tiempo_estimado_min": st.column_config.NumberColumn("Tiempo min", format="%.2f"),
                    "costo_estimado_usd": st.column_config.NumberColumn("Costo estimado", format="%.2f"),
                    "cantidad_material_estimada": st.column_config.NumberColumn("Consumo estimado", format="%.3f"),
                },
            )

            d1, d2 = st.columns(2)
            orden_sel = d1.selectbox(
                "Orden",
                options=df_ordenes["id"].tolist(),
                format_func=lambda i: f"{df_ordenes[df_ordenes['id'] == i]['codigo'].iloc[0]} · {df_ordenes[df_ordenes['id'] == i]['referencia'].iloc[0]}",
                key="corte_sel_orden_estado",
            )
            nuevo_estado = d2.selectbox(
                "Actualizar estado",
                ["analizado", "aprobado", "en_proceso", "terminado", "cancelado"],
                key="corte_nuevo_estado",
            )
            if st.button("💾 Guardar estado", use_container_width=True):
                try:
                    _actualizar_estado_orden_corte(int(orden_sel), str(nuevo_estado))
                    st.success("Estado actualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar el estado: {exc}")

    with tab_ejecucion:
        st.subheader("Ejecutar corte")
        if df_ordenes.empty:
            st.info("No hay órdenes para ejecutar.")
        else:
            ejecutables = df_ordenes[df_ordenes["estado"].astype(str).str.lower().isin(["analizado", "aprobado", "en_proceso"])].copy()
            if ejecutables.empty:
                st.success("No hay órdenes pendientes de ejecución.")
            else:
                orden_id = st.selectbox(
                    "Orden a ejecutar",
                    options=ejecutables["id"].tolist(),
                    format_func=lambda i: f"{ejecutables[ejecutables['id'] == i]['codigo'].iloc[0]} · {ejecutables[ejecutables['id'] == i]['material_nombre'].iloc[0]}",
                    key="corte_ejec_orden_id",
                )
                row = ejecutables[ejecutables["id"] == orden_id].iloc[0]

                p1, p2, p3 = st.columns(3)
                p1.metric("Consumo estimado", f"{float(row['cantidad_material_estimada'] or 0):,.3f}")
                p2.metric("Tiempo estimado", f"{float(row['tiempo_estimado_min'] or 0):,.2f} min")
                p3.metric("Costo estimado", f"$ {float(row['costo_estimado_usd'] or 0):,.2f}")

                e1, e2, e3 = st.columns(3)
                cm_corte_real = e1.number_input(
                    "CM corte real",
                    min_value=0.0,
                    value=float(row["cm_corte_estimado"] or 0.0),
                    format="%.2f",
                    key="corte_real_cm",
                )
                tiempo_real_min = e2.number_input(
                    "Tiempo real (min)",
                    min_value=0.0,
                    value=float(row["tiempo_estimado_min"] or 0.0),
                    format="%.2f",
                    key="corte_real_time",
                )
                material_real_usado = e3.number_input(
                    "Material real usado",
                    min_value=0.0,
                    value=float(row["cantidad_material_estimada"] or 0.0),
                    format="%.3f",
                    key="corte_real_material",
                )

                e4, e5 = st.columns(2)
                merma = e4.number_input("Merma", min_value=0.0, value=0.0, format="%.3f", key="corte_real_merma")
                retazo_reutilizable = e5.number_input(
                    "Retazo reutilizable",
                    min_value=0.0,
                    value=0.0,
                    format="%.3f",
                    key="corte_real_retazo",
                )

                incidencias = st.text_area("Incidencias", key="corte_real_incidencias")

                if st.button("⚙️ Ejecutar y cerrar orden", use_container_width=True):
                    try:
                        ejec_id = _ejecutar_corte(
                            usuario=usuario,
                            orden_corte_id=int(orden_id),
                            cm_corte_real=float(cm_corte_real),
                            tiempo_real_min=float(tiempo_real_min),
                            material_real_usado=float(material_real_usado),
                            merma=float(merma),
                            retazo_reutilizable=float(retazo_reutilizable),
                            incidencias=incidencias,
                        )
                        st.success(f"Ejecución registrada correctamente. ID #{ejec_id}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo ejecutar el corte: {exc}")

    with tab_material:
        st.subheader("Material / merma / retazos")

        mt1, mt2 = st.tabs(["Movimientos de material", "Retazos"])

        with mt1:
            if df_movs.empty:
                st.info("No hay movimientos de material registrados.")
            else:
                st.dataframe(
                    df_movs,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
                    },
                )

        with mt2:
            if df_retazos.empty:
                st.info("No hay retazos registrados.")
            else:
                st.dataframe(
                    df_retazos,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
                    },
                )

    with tab_historial:
        st.subheader("Historial de corte")

        ht1, ht2 = st.tabs(["Ejecuciones", "Resumen"])

        with ht1:
            if df_ejec.empty:
                st.info("No hay ejecuciones registradas.")
            else:
                st.dataframe(
                    df_ejec,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cm_corte_real": st.column_config.NumberColumn("CM reales", format="%.2f"),
                        "tiempo_real_min": st.column_config.NumberColumn("Tiempo real", format="%.2f"),
                        "material_real_usado": st.column_config.NumberColumn("Material real", format="%.3f"),
                        "merma": st.column_config.NumberColumn("Merma", format="%.3f"),
                        "retazo_reutilizable": st.column_config.NumberColumn("Retazo", format="%.3f"),
                        "costo_real_usd": st.column_config.NumberColumn("Costo real", format="%.2f"),
                        "desgaste_registrado": st.column_config.NumberColumn("Desgaste", format="%.6f"),
                    },
                )

        with ht2:
            if df_ordenes.empty:
                st.info("Sin datos aún.")
            else:
                eficiencia = 0.0
                if not df_ejec.empty:
                    total_material = float(df_ejec["material_real_usado"].sum() or 0.0)
                    total_merma = float(df_ejec["merma"].sum() or 0.0)
                    if total_material > 0:
                        eficiencia = ((total_material - total_merma) / total_material) * 100.0

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Órdenes totales", len(df_ordenes))
                s2.metric("Material usado", f"{float(df_ejec['material_real_usado'].sum()) if not df_ejec.empty else 0:,.3f}")
                s3.metric("Merma acumulada", f"{float(df_ejec['merma'].sum()) if not df_ejec.empty else 0:,.3f}")
                s4.metric("Eficiencia estimada", f"{eficiencia:.1f}%")

                if not df_ejec.empty:
                    resumen = (
                        df_ejec.groupby("material_nombre", as_index=False)[["material_real_usado", "merma", "retazo_reutilizable", "costo_real_usd"]]
                        .sum()
                        .sort_values("costo_real_usd", ascending=False)
                    )
                    st.markdown("### Resumen por material")
                    st.dataframe(
                        resumen,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "material_real_usado": st.column_config.NumberColumn("Usado", format="%.3f"),
                            "merma": st.column_config.NumberColumn("Merma", format="%.3f"),
                            "retazo_reutilizable": st.column_config.NumberColumn("Retazo", format="%.3f"),
                            "costo_real_usd": st.column_config.NumberColumn("Costo real", format="%.2f"),
                        },
                    )
