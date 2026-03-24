from __future__ import annotations

import json
from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


DEFAULT_PARAMETROS = {
    "factor_imprevistos_pct": 5.0,
    "factor_indirecto_pct": 10.0,
    "margen_objetivo_pct": 35.0,
}


def _parse_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def obtener_parametros_costeo(conn: Any | None = None) -> dict[str, float]:
    def _load(connection: Any) -> dict[str, float]:
        rows = connection.execute(
            """
            SELECT clave, valor_num
            FROM parametros_costeo
            WHERE estado = 'activo'
            """
        ).fetchall()
        params = dict(DEFAULT_PARAMETROS)
        for row in rows:
            if row["clave"] in params and row["valor_num"] is not None:
                params[row["clave"]] = float(row["valor_num"])
        return params

    if conn is not None:
        return _load(conn)

    with db_transaction() as tmp_conn:
        return _load(tmp_conn)


def calcular_costo_servicio(
    *,
    tipo_proceso: str,
    cantidad: float,
    costo_materiales_usd: float,
    costo_mano_obra_usd: float,
    costo_indirecto_usd: float = 0.0,
    parametros_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    tipo_normalizado = require_text(tipo_proceso, "Tipo de proceso")
    cantidad_val = as_positive(cantidad, "Cantidad", allow_zero=False)

    materiales = as_positive(costo_materiales_usd, "Costo materiales")
    mano_obra = as_positive(costo_mano_obra_usd, "Costo mano de obra")
    indirecto_input = as_positive(costo_indirecto_usd, "Costo indirecto")

    parametros = dict(DEFAULT_PARAMETROS)
    parametros.update({k: float(v) for k, v in (parametros_override or {}).items() if k in parametros})

    subtotal_base = money(materiales + mano_obra + indirecto_input)
    imprevistos_pct = as_positive(parametros.get("factor_imprevistos_pct", 0), "Imprevistos %")
    indirecto_pct = as_positive(parametros.get("factor_indirecto_pct", 0), "Indirecto %")

    costo_imprevistos = money(subtotal_base * (imprevistos_pct / 100))
    costo_indirecto_factor = money(subtotal_base * (indirecto_pct / 100))
    costo_total = money(subtotal_base + costo_imprevistos + costo_indirecto_factor)
    costo_unitario = money(costo_total / cantidad_val)

    return {
        "tipo_proceso": tipo_normalizado,
        "cantidad": float(cantidad_val),
        "componentes": {
            "materiales_usd": money(materiales),
            "mano_obra_usd": money(mano_obra),
            "indirecto_directo_usd": money(indirecto_input),
            "imprevistos_usd": costo_imprevistos,
            "indirecto_factor_usd": costo_indirecto_factor,
        },
        "parametros": {
            "factor_imprevistos_pct": imprevistos_pct,
            "factor_indirecto_pct": indirecto_pct,
        },
        "costo_total_usd": costo_total,
        "costo_unitario_usd": costo_unitario,
    }


def calcular_margen_estimado(
    *,
    costo_total_usd: float,
    margen_pct: float | None = None,
    precio_venta_usd: float | None = None,
) -> dict[str, float]:
    costo_total = as_positive(costo_total_usd, "Costo total", allow_zero=False)

    if precio_venta_usd is not None:
        precio = as_positive(precio_venta_usd, "Precio de venta", allow_zero=False)
        utilidad = money(precio - costo_total)
        margen_real = money((utilidad / precio) * 100) if precio else 0.0
        markup = money((utilidad / costo_total) * 100) if costo_total else 0.0
        return {
            "costo_total_usd": money(costo_total),
            "precio_sugerido_usd": money(precio),
            "utilidad_esperada_usd": utilidad,
            "margen_estimado_pct": margen_real,
            "markup_pct": markup,
        }

    margen = as_positive(margen_pct if margen_pct is not None else 0.0, "Margen %")
    precio = money(costo_total * (1 + margen / 100))
    utilidad = money(precio - costo_total)

    return {
        "costo_total_usd": money(costo_total),
        "precio_sugerido_usd": precio,
        "utilidad_esperada_usd": utilidad,
        "margen_estimado_pct": money((utilidad / precio) * 100) if precio else 0.0,
        "markup_pct": money((utilidad / costo_total) * 100),
    }


def guardar_costeo(
    *,
    usuario: str,
    tipo_proceso: str,
    descripcion: str,
    cantidad: float,
    costo_materiales_usd: float,
    costo_mano_obra_usd: float,
    costo_indirecto_usd: float,
    margen_pct: float,
    precio_sugerido_usd: float,
    origen: str = "manual",
    referencia_id: int | None = None,
    detalle: list[dict[str, Any]] | None = None,
) -> int:
    usuario_ok = require_text(usuario, "Usuario")
    tipo_ok = require_text(tipo_proceso, "Tipo de proceso")
    descripcion_ok = clean_text(descripcion) or "Costeo sin descripción"

    cantidad_ok = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_materiales_ok = as_positive(costo_materiales_usd, "Costo materiales")
    costo_mano_obra_ok = as_positive(costo_mano_obra_usd, "Costo mano de obra")
    costo_indirecto_ok = as_positive(costo_indirecto_usd, "Costo indirecto")
    margen_ok = as_positive(margen_pct, "Margen %")
    precio_ok = as_positive(precio_sugerido_usd, "Precio sugerido", allow_zero=False)

    costo_total = money(costo_materiales_ok + costo_mano_obra_ok + costo_indirecto_ok)

    rows_detalle = detalle or [
        {
            "categoria": "material",
            "concepto": "Materiales",
            "cantidad": 1,
            "costo_unitario_usd": money(costo_materiales_ok),
            "subtotal_usd": money(costo_materiales_ok),
        },
        {
            "categoria": "mano_obra",
            "concepto": "Mano de obra",
            "cantidad": 1,
            "costo_unitario_usd": money(costo_mano_obra_ok),
            "subtotal_usd": money(costo_mano_obra_ok),
        },
        {
            "categoria": "indirecto",
            "concepto": "Indirectos",
            "cantidad": 1,
            "costo_unitario_usd": money(costo_indirecto_ok),
            "subtotal_usd": money(costo_indirecto_ok),
        },
    ]

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO costeo_ordenes (
                usuario,
                tipo_proceso,
                descripcion,
                cantidad,
                costo_materiales_usd,
                costo_mano_obra_usd,
                costo_indirecto_usd,
                costo_total_usd,
                margen_pct,
                precio_sugerido_usd,
                origen,
                referencia_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario_ok,
                tipo_ok,
                descripcion_ok,
                float(cantidad_ok),
                money(costo_materiales_ok),
                money(costo_mano_obra_ok),
                money(costo_indirecto_ok),
                costo_total,
                money(margen_ok),
                money(precio_ok),
                clean_text(origen) or "manual",
                int(referencia_id) if referencia_id else None,
            ),
        )
        orden_id = int(cur.lastrowid)

        for item in rows_detalle:
            concepto = clean_text(item.get("concepto")) or "Sin concepto"
            categoria = clean_text(item.get("categoria")) or "general"
            cantidad_item = as_positive(item.get("cantidad", 1), "Cantidad detalle", allow_zero=False)
            costo_unitario_item = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario detalle")
            subtotal_item = as_positive(item.get("subtotal_usd", costo_unitario_item), "Subtotal detalle")
            metadata = item.get("metadata")

            conn.execute(
                """
                INSERT INTO costeo_detalle (
                    orden_id,
                    concepto,
                    categoria,
                    cantidad,
                    costo_unitario_usd,
                    subtotal_usd,
                    metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    orden_id,
                    concepto,
                    categoria,
                    float(cantidad_item),
                    money(costo_unitario_item),
                    money(subtotal_item),
                    json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                ),
            )

        return orden_id


def listar_costeos(
    *,
    limit: int = 100,
    tipo_proceso: str | None = None,
    origen: str | None = None,
) -> pd.DataFrame:
    limit_ok = max(1, min(int(limit), 500))

    filtros = ["1=1"]
    params: list[Any] = []

    if clean_text(tipo_proceso):
        filtros.append("tipo_proceso = ?")
        params.append(clean_text(tipo_proceso))

    if clean_text(origen):
        filtros.append("origen = ?")
        params.append(clean_text(origen))

    query = f"""
        SELECT
            id,
            fecha,
            usuario,
            tipo_proceso,
            descripcion,
            cantidad,
            costo_materiales_usd,
            costo_mano_obra_usd,
            costo_indirecto_usd,
            costo_total_usd,
            margen_pct,
            precio_sugerido_usd,
            origen,
            referencia_id,
            estado
        FROM costeo_ordenes
        WHERE {' AND '.join(filtros)}
        ORDER BY datetime(fecha) DESC, id DESC
        LIMIT ?
    """
    params.append(limit_ok)

    with db_transaction() as conn:
        return pd.read_sql_query(query, conn, params=params)


def obtener_detalle_costeo(orden_id: int) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                orden_id,
                concepto,
                categoria,
                cantidad,
                costo_unitario_usd,
                subtotal_usd,
                metadata
            FROM costeo_detalle
            WHERE orden_id = ?
            ORDER BY id ASC
            """,
            conn,
            params=[int(orden_id)],
        )
