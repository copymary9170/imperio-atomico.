from __future__ import annotations

import json
from typing import Any

import pandas as pd

from database.connection import db_transaction


def guardar_costeo_impresion_real(
    *,
    usuario: str,
    activo_id: int,
    impresora_label: str,
    paginas: float,
    costo_consumibles_usd: float,
    costo_cabezales_usd: float,
    costo_papel_usd: float,
    costo_merma_usd: float,
    otros_materiales_usd: float,
    electricidad_usd: float,
    internet_usd: float,
    mano_obra_usd: float,
    depreciacion_usd: float,
    costo_total_usd: float,
    margen_pct: float,
    precio_sugerido_usd: float,
    precio_unitario_usd: float,
    ganancia_usd: float,
    detalle: list[dict[str, Any]] | None = None,
    estado: str = "borrador",
) -> int:
    """Guarda un costeo real por impresora en historial."""
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO costeos_impresion_real
            (
                usuario, activo_id, impresora_label, paginas,
                costo_consumibles_usd, costo_cabezales_usd, costo_papel_usd,
                costo_merma_usd, otros_materiales_usd, electricidad_usd,
                internet_usd, mano_obra_usd, depreciacion_usd,
                costo_total_usd, margen_pct, precio_sugerido_usd,
                precio_unitario_usd, ganancia_usd, detalle_json, estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"),
                int(activo_id),
                str(impresora_label or ""),
                float(paginas or 0.0),
                float(costo_consumibles_usd or 0.0),
                float(costo_cabezales_usd or 0.0),
                float(costo_papel_usd or 0.0),
                float(costo_merma_usd or 0.0),
                float(otros_materiales_usd or 0.0),
                float(electricidad_usd or 0.0),
                float(internet_usd or 0.0),
                float(mano_obra_usd or 0.0),
                float(depreciacion_usd or 0.0),
                float(costo_total_usd or 0.0),
                float(margen_pct or 0.0),
                float(precio_sugerido_usd or 0.0),
                float(precio_unitario_usd or 0.0),
                float(ganancia_usd or 0.0),
                json.dumps(detalle or [], ensure_ascii=False),
                str(estado or "borrador"),
            ),
        )
        return int(cur.lastrowid)


def listar_costeos_impresion_real(limit: int = 50) -> pd.DataFrame:
    """Lista los costeos reales guardados más recientes."""
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, fecha, usuario, impresora_label, paginas,
                costo_total_usd, margen_pct, precio_sugerido_usd,
                precio_unitario_usd, ganancia_usd, estado
            FROM costeos_impresion_real
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )
