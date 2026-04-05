from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text
from modules.integration_hub import render_module_inbox


TIPOS_MERMA = [
    "Desperdicio normal",
    "Desperdicio anormal",
    "Prueba / calibración",
    "Error humano",
    "Corte incorrecto",
    "Impresión fallida",
    "Daño por almacenamiento",
    "Rotura",
    "Vencimiento",
    "Sobrante no reutilizable",
    "Otro",
]

CAUSAS_MERMA = [
    "Error operativo",
    "Falla de máquina",
    "Falla de material",
    "Mala manipulación",
    "Calibración",
    "Transporte",
    "Almacenamiento",
    "Humedad / calor",
    "Vencimiento",
    "Prueba interna",
    "Otro",
]

AREAS_MERMA = [
    "Producción",
    "Corte",
    "Sublimación",
    "Impresión",
    "Acabado",
    "Almacén",
    "Despacho",
    "Administración",
    "Otro",
]

DESTINOS_RECUPERACION = [
    "No recuperable",
    "Reutilizable",
    "Reciclable",
    "Chatarra",
    "Devuelto a inventario",
]

UNIDADES_BASE = [
    "unidad",
    "und",
    "cm",
    "cm2",
    "ml",
    "gr",
    "kg",
    "m",
    "m2",
    "litro",
    "pliego",
    "paquete",
    "caja",
]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_mermas_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mermas_desperdicio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                inventario_id INTEGER,
                producto TEXT NOT NULL,
                sku TEXT,
                categoria TEXT,
                unidad TEXT DEFAULT 'unidad',
                cantidad REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                tipo_merma TEXT NOT NULL,
                causa TEXT NOT NULL,
                area TEXT,
                proceso TEXT,
                orden_produccion TEXT,
                maquina TEXT,
                operador TEXT,
                lote TEXT,
                cliente TEXT,
                observacion TEXT,
                recuperable INTEGER NOT NULL DEFAULT 0,
                cantidad_recuperada REAL NOT NULL DEFAULT 0,
                valor_recuperado_usd REAL NOT NULL DEFAULT 0,
                destino_recuperacion TEXT,
                evidencia_url TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            )
            """
        )

        cols = {r[1] for r in conn.execute("PRAGMA table_info(mermas_desperdicio)").fetchall()}

        extras = {
            "proceso": "TEXT",
            "orden_produccion": "TEXT",
            "maquina": "TEXT",
            "operador": "TEXT",
            "lote": "TEXT",
            "cliente": "TEXT",
            "evidencia_url": "TEXT",
            "destino_recuperacion": "TEXT",
            "cantidad_recuperada": "REAL NOT NULL DEFAULT 0",
            "valor_recuperado_usd": "REAL NOT NULL DEFAULT 0",
            "recuperable": "INTEGER NOT NULL DEFAULT 0",
            "estado": "TEXT NOT NULL DEFAULT 'activo'",
            "sku": "TEXT",
            "categoria": "TEXT",
            "unidad": "TEXT DEFAULT 'unidad'",
        }

        for col, sql_type in extras.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE mermas_desperdicio ADD COLUMN {col} {sql_type}")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_fecha ON mermas_desperdicio(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_tipo ON mermas_desperdicio(tipo_merma)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_causa ON mermas_desperdicio(causa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_area ON mermas_desperdicio(area)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_inventario ON mermas_desperdicio(inventario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_estado ON mermas_desperdicio(estado)")


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _sum_method(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _load_inventory_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                nombre,
                sku,
                categoria,
                unidad,
                stock_actual,
                costo_unitario_usd,
                precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY nombre ASC
            """
        ).fetchall()

    return pd.DataFrame(
        rows,
        columns=[
            "id",
            "nombre",
            "sku",
            "categoria",
            "unidad",
            "stock_actual",
            "costo_unitario_usd",
            "precio_venta_usd",
        ],
    )


def _load_mermas_df() -> pd.DataFrame:
    _ensure_mermas_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                inventario_id,
                producto,
                sku,
                categoria,
                unidad,
                cantidad,
                costo_unitario_usd,
                costo_total_usd,
                tipo_merma,
                causa,
                area,
                proceso,
                orden_produccion,
                maquina,
                operador,
                lote,
                cliente,
                observacion,
                recuperable,
                cantidad_recuperada,
                valor_recuperado_usd,
                destino_recuperacion,
                evidencia_url,
                estado
            FROM mermas_desperdicio
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )
    return df


def _filter_mermas(
    df: pd.DataFrame,
    buscar: str,
    tipo: str,
    causa: str,
    area: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    view = df.copy()

    if buscar:
        txt = clean_text(buscar)
        mask = (
            view["producto"].astype(str).str.contains(txt, case=False, na=False)
            | view["sku"].astype(str).str.contains(txt, case=False, na=False)
            | view["observacion"].astype(str).str.contains(txt, case=False, na=False)
            | view["orden_produccion"].astype(str).str.contains(txt, case=False, na=False)
            | view["operador"].astype(str).str.contains(txt, case=False, na=False)
            | view["maquina"].astype(str).str.contains(txt, case=False, na=False)
            | view["cliente"].astype(str).str.contains(txt, case=False, na=False)
        )
        view = view[mask]

    if tipo != "Todos":
        view = view[view["tipo_merma"].astype(str) == tipo]

    if causa != "Todas":
        view = view[view["causa"].astype(str) == causa]

    if area != "Todas":
        view = view[view["area"].astype(str) == area]

    return view


def _registrar_salida_inventario_por_merma(
    conn,
    usuario: str,
    inventario_id: int,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
) -> None:
    row = conn.execute(
        """
        SELECT stock_actual
        FROM inventario
        WHERE id=? AND COALESCE(estado,'activo')='activo'
        """,
        (int(inventario_id),),
    ).fetchone()

    if not row:
        raise ValueError("El producto de inventario no existe.")

    stock_actual = float(row["stock_actual"] or 0.0)
    if stock_actual < float(cantidad):
        raise ValueError("Stock insuficiente para registrar la merma.")

    conn.execute(
        """
        INSERT INTO movimientos_inventario(
            usuario,
            inventario_id,
            tipo,
            cantidad,
            costo_unitario_usd,
            referencia
        )
        VALUES (?, ?, 'salida', ?, ?, ?)
        """,
        (
            require_text(usuario, "Usuario"),
            int(inventario_id),
            -abs(float(cantidad)),
            max(0.0, float(costo_unitario_usd)),
            clean_text(referencia),
        ),
    )

    conn.execute(
        """
        UPDATE inventario
        SET stock_actual = stock_actual - ?
        WHERE id = ?
        """,
        (float(cantidad), int(inventario_id)),
    )


# ============================================================
# CORE
# ============================================================

def registrar_merma(
    usuario: str,
    inventario_id: int | None,
    producto: str,
    sku: str,
    categoria: str,
    unidad: str,
    cantidad: float,
    costo_unitario_usd: float,
    tipo_merma: str,
    causa: str,
    area: str,
    proceso: str = "",
    orden_produccion: str = "",
    maquina: str = "",
    operador: str = "",
    lote: str = "",
    cliente: str = "",
    observacion: str = "",
    recuperable: bool = False,
    cantidad_recuperada: float = 0.0,
    valor_recuperado_usd: float = 0.0,
    destino_recuperacion: str = "No recuperable",
    evidencia_url: str = "",
) -> int:
    producto = require_text(producto, "Producto")
    tipo_merma = require_text(tipo_merma, "Tipo de merma")
    causa = require_text(causa, "Causa")
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_unitario_usd = as_positive(costo_unitario_usd, "Costo unitario", allow_zero=True)
    cantidad_recuperada = as_positive(cantidad_recuperada, "Cantidad recuperada", allow_zero=True)
    valor_recuperado_usd = as_positive(valor_recuperado_usd, "Valor recuperado", allow_zero=True)

    if cantidad_recuperada > cantidad:
        raise ValueError("La cantidad recuperada no puede ser mayor a la cantidad perdida.")

    costo_total_usd = round(float(cantidad) * float(costo_unitario_usd), 4)

    referencia = (
        f"Merma registrada · {tipo_merma}"
        f"{' · ' + clean_text(orden_produccion) if clean_text(orden_produccion) else ''}"
        f"{' · ' + clean_text(proceso) if clean_text(proceso) else ''}"
    )

    with db_transaction() as conn:
        if inventario_id is not None:
            _registrar_salida_inventario_por_merma(
                conn=conn,
                usuario=usuario,
                inventario_id=int(inventario_id),
                cantidad=float(cantidad),
                costo_unitario_usd=float(costo_unitario_usd),
                referencia=referencia,
            )

        cur = conn.execute(
            """
            INSERT INTO mermas_desperdicio (
                usuario,
                inventario_id,
                producto,
                sku,
                categoria,
                unidad,
                cantidad,
                costo_unitario_usd,
                costo_total_usd,
                tipo_merma,
                causa,
                area,
                proceso,
                orden_produccion,
                maquina,
                operador,
                lote,
                cliente,
                observacion,
                recuperable,
                cantidad_recuperada,
                valor_recuperado_usd,
                destino_recuperacion,
                evidencia_url,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo')
            """,
            (
                usuario,
                int(inventario_id) if inventario_id is not None else None,
                clean_text(producto),
                clean_text(sku),
                clean_text(categoria),
                clean_text(unidad) or "unidad",
                float(cantidad),
                float(costo_unitario_usd),
                float(costo_total_usd),
                clean_text(tipo_merma),
                clean_text(causa),
                clean_text(area),
                clean_text(proceso),
                clean_text(orden_produccion),
                clean_text(maquina),
                clean_text(operador),
                clean_text(lote),
                clean_text(cliente),
                clean_text(observacion),
                1 if bool(recuperable) else 0,
                float(cantidad_recuperada),
                float(valor_recuperado_usd),
                clean_text(destino_recuperacion),
                clean_text(evidencia_url),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# UI
# ============================================================

def render_mermas(usuario: str) -> None:
    _ensure_mermas_tables()

    st.subheader("♻️ Mermas y desperdicio")
    st.caption(
        "Controla pérdidas de material, calcula su impacto económico, "
        "descuenta inventario y analiza causas para mejorar producción."
    )

    def _apply_inbox(inbox: dict) -> None:
        data = dict(inbox.get("payload_data", {}))
        if data.get("orden_id"):
            st.session_state["merma_op"] = str(data.get("orden_id"))
        if data.get("proceso"):
            st.session_state["merma_proceso"] = str(data.get("proceso"))
        if data.get("material"):
            st.session_state["merma_producto_manual"] = str(data.get("material"))
        if data.get("observaciones"):
            st.session_state["merma_observacion"] = str(data.get("observaciones"))
        if data.get("merma") is not None:
            try:
                st.session_state["merma_cantidad"] = float(data.get("merma"))
            except (TypeError, ValueError):
                pass

    render_module_inbox("mermas", apply_callback=_apply_inbox, clear_after_apply=False)

    tabs = st.tabs(
        [
            "📝 Registrar merma",
            "📜 Historial",
            "📊 Resumen",
        ]
    )

    with tabs[0]:
        _render_tab_registro(usuario)

    with tabs[1]:
        _render_tab_historial()

    with tabs[2]:
        _render_tab_resumen()





