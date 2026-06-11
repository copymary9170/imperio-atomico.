from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, money, require_text


TIPOS_CONSUMIBLE = [
    "tinta",
    "cartucho",
    "toner",
    "cabezal",
    "rollo termico",
    "cinta termica",
    "ribbon",
    "papel especial",
    "mantenimiento",
    "otro",
]

COLORES_CONSUMIBLE = [
    "K / Negro",
    "C / Cyan",
    "M / Magenta",
    "Y / Amarillo",
    "Tricolor",
    "Monocromatico",
    "Termico / No usa tinta",
    "No aplica",
]

UNIDADES_CARGA_CONSUMIBLE = [
    "ml",
    "gramos",
    "unidad",
    "cartucho",
    "toner",
    "botella",
    "litro",
    "rollo",
    "metro",
    "hoja",
    "cinta",
    "no aplica",
]


def listar_impresoras_activas() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                equipo,
                modelo,
                unidad,
                categoria,
                tipo_detalle,
                estado,
                inversion
            FROM activos
            WHERE COALESCE(estado, 'activo') <> 'inactivo'
              AND lower(COALESCE(unidad, '')) = 'impresora'
            ORDER BY equipo, modelo, id
            """,
            conn,
        )


def listar_consumibles_inventario() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                sku,
                nombre,
                categoria,
                unidad,
                stock_actual,
                costo_unitario_usd,
                precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY categoria, nombre, sku, id
            """,
            conn,
        )


def listar_consumibles_por_impresora(activo_id: int | None = None) -> pd.DataFrame:
    filtros = ["ic.activo = 1"]
    params: list[Any] = []
    if activo_id:
        filtros.append("ic.activo_id = ?")
        params.append(int(activo_id))

    with db_transaction() as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                ic.id,
                ic.fecha_creacion,
                ic.activo_id,
                a.equipo AS impresora,
                a.modelo AS modelo_impresora,
                ic.inventario_id,
                i.sku,
                i.nombre AS consumible,
                i.categoria AS categoria_consumible,
                i.unidad,
                i.stock_actual,
                i.costo_unitario_usd,
                ic.tipo_consumible,
                ic.color,
                ic.rendimiento_paginas,
                ic.cobertura_referencia,
                ic.costo_estimado_hoja_usd,
                COALESCE(ic.capacidad_maquina_ml, 0) AS capacidad_maquina_ml,
                COALESCE(ic.cantidad_en_maquina_ml, 0) AS cantidad_en_maquina_ml,
                COALESCE(ic.unidad_carga, 'ml') AS unidad_carga,
                COALESCE(ic.descontar_de_inventario, 1) AS descontar_de_inventario,
                ic.notas
            FROM impresora_consumibles ic
            JOIN activos a ON a.id = ic.activo_id
            JOIN inventario i ON i.id = ic.inventario_id
            WHERE {' AND '.join(filtros)}
            ORDER BY a.equipo, a.modelo, ic.color, i.nombre
            """,
            conn,
            params=params,
        )


def asignar_consumible_impresora(
    *,
    activo_id: int,
    inventario_id: int,
    tipo_consumible: str,
    color: str,
    rendimiento_paginas: float = 0.0,
    cobertura_referencia: str | None = None,
    costo_estimado_hoja_usd: float = 0.0,
    capacidad_maquina_ml: float = 0.0,
    cantidad_en_maquina_ml: float = 0.0,
    unidad_carga: str = "ml",
    descontar_de_inventario: bool = True,
    notas: str | None = None,
) -> int:
    activo_ok = int(activo_id)
    inventario_ok = int(inventario_id)
    tipo_ok = clean_text(tipo_consumible).lower() or "tinta"
    color_ok = require_text(color, "Color")
    rendimiento = max(0.0, float(rendimiento_paginas or 0.0))
    costo_hoja = max(0.0, float(costo_estimado_hoja_usd or 0.0))
    capacidad = max(0.0, float(capacidad_maquina_ml or 0.0))
    cantidad_maquina = max(0.0, float(cantidad_en_maquina_ml or 0.0))
    unidad_ok = clean_text(unidad_carga) or "ml"
    descuenta = 1 if bool(descontar_de_inventario) else 0

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM impresora_consumibles
            WHERE activo_id = ? AND inventario_id = ? AND color = ?
            """,
            (activo_ok, inventario_ok, color_ok),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE impresora_consumibles
                SET tipo_consumible = ?,
                    rendimiento_paginas = ?,
                    cobertura_referencia = ?,
                    costo_estimado_hoja_usd = ?,
                    capacidad_maquina_ml = ?,
                    cantidad_en_maquina_ml = ?,
                    unidad_carga = ?,
                    descontar_de_inventario = ?,
                    notas = ?,
                    activo = 1
                WHERE id = ?
                """,
                (
                    tipo_ok,
                    rendimiento,
                    clean_text(cobertura_referencia),
                    money(costo_hoja),
                    capacidad,
                    cantidad_maquina,
                    unidad_ok,
                    descuenta,
                    clean_text(notas),
                    int(row["id"]),
                ),
            )
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO impresora_consumibles (
                activo_id,
                inventario_id,
                tipo_consumible,
                color,
                rendimiento_paginas,
                cobertura_referencia,
                costo_estimado_hoja_usd,
                capacidad_maquina_ml,
                cantidad_en_maquina_ml,
                unidad_carga,
                descontar_de_inventario,
                notas,
                activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                activo_ok,
                inventario_ok,
                tipo_ok,
                color_ok,
                rendimiento,
                clean_text(cobertura_referencia),
                money(costo_hoja),
                capacidad,
                cantidad_maquina,
                unidad_ok,
                descuenta,
                clean_text(notas),
            ),
        )
        return int(cur.lastrowid)


def desactivar_consumible_impresora(relacion_id: int) -> None:
    with db_transaction() as conn:
        conn.execute("UPDATE impresora_consumibles SET activo = 0 WHERE id = ?", (int(relacion_id),))
