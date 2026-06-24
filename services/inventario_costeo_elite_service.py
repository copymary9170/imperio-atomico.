from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from services.inventario_unificado_service import ensure_inventario_unificado_schema


UNIDADES_CONSUMO = ["unidad", "hoja", "pliego", "cm", "m", "cm²", "m²", "g", "kg", "ml", "L"]


def ensure_schema() -> None:
    ensure_inventario_unificado_schema()
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventario_costeo_elite (
                inventario_id INTEGER PRIMARY KEY,
                cantidad_comprada REAL NOT NULL DEFAULT 1,
                unidad_compra TEXT,
                piezas_por_compra REAL NOT NULL DEFAULT 1,
                ancho_cm REAL NOT NULL DEFAULT 0,
                alto_cm REAL NOT NULL DEFAULT 0,
                largo_cm REAL NOT NULL DEFAULT 0,
                peso_total_g REAL NOT NULL DEFAULT 0,
                volumen_total_ml REAL NOT NULL DEFAULT 0,
                costo_producto_usd REAL NOT NULL DEFAULT 0,
                delivery_usd REAL NOT NULL DEFAULT 0,
                impuestos_usd REAL NOT NULL DEFAULT 0,
                comision_usd REAL NOT NULL DEFAULT 0,
                otros_usd REAL NOT NULL DEFAULT 0,
                merma_pct REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
        """)


def guardar_costeo(
    inventario_id: int,
    *,
    cantidad_comprada: float,
    unidad_compra: str,
    piezas_por_compra: float,
    ancho_cm: float,
    alto_cm: float,
    largo_cm: float,
    peso_total_g: float,
    volumen_total_ml: float,
    costo_producto_usd: float,
    delivery_usd: float,
    impuestos_usd: float,
    comision_usd: float,
    otros_usd: float,
    merma_pct: float,
) -> None:
    ensure_schema()
    if cantidad_comprada <= 0:
        raise ValueError("La cantidad comprada debe ser mayor que cero.")
    if piezas_por_compra <= 0:
        raise ValueError("Las piezas o unidades contenidas deben ser mayores que cero.")
    if not 0 <= merma_pct < 100:
        raise ValueError("La merma debe estar entre 0% y menos de 100%.")
    valores = [ancho_cm, alto_cm, largo_cm, peso_total_g, volumen_total_ml, costo_producto_usd, delivery_usd, impuestos_usd, comision_usd, otros_usd]
    if any(float(v or 0) < 0 for v in valores):
        raise ValueError("Los valores no pueden ser negativos.")

    with db_transaction() as conn:
        conn.execute("""
            INSERT INTO inventario_costeo_elite(
                inventario_id,cantidad_comprada,unidad_compra,piezas_por_compra,
                ancho_cm,alto_cm,largo_cm,peso_total_g,volumen_total_ml,
                costo_producto_usd,delivery_usd,impuestos_usd,comision_usd,
                otros_usd,merma_pct,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(inventario_id) DO UPDATE SET
                cantidad_comprada=excluded.cantidad_comprada,
                unidad_compra=excluded.unidad_compra,
                piezas_por_compra=excluded.piezas_por_compra,
                ancho_cm=excluded.ancho_cm,
                alto_cm=excluded.alto_cm,
                largo_cm=excluded.largo_cm,
                peso_total_g=excluded.peso_total_g,
                volumen_total_ml=excluded.volumen_total_ml,
                costo_producto_usd=excluded.costo_producto_usd,
                delivery_usd=excluded.delivery_usd,
                impuestos_usd=excluded.impuestos_usd,
                comision_usd=excluded.comision_usd,
                otros_usd=excluded.otros_usd,
                merma_pct=excluded.merma_pct,
                updated_at=CURRENT_TIMESTAMP
        """, (
            int(inventario_id), float(cantidad_comprada), str(unidad_compra or "").strip(),
            float(piezas_por_compra), float(ancho_cm or 0), float(alto_cm or 0),
            float(largo_cm or 0), float(peso_total_g or 0), float(volumen_total_ml or 0),
            float(costo_producto_usd or 0), float(delivery_usd or 0),
            float(impuestos_usd or 0), float(comision_usd or 0), float(otros_usd or 0),
            float(merma_pct or 0),
        ))


def _calcular(row: pd.Series) -> pd.Series:
    cantidad_comprada = float(row.get("cantidad_comprada") or 1)
    piezas = float(row.get("piezas_por_compra") or 1)
    ancho = float(row.get("ancho_cm") or 0)
    alto = float(row.get("alto_cm") or 0)
    largo = float(row.get("largo_cm") or 0)
    peso = float(row.get("peso_total_g") or 0)
    volumen = float(row.get("volumen_total_ml") or 0)
    merma = float(row.get("merma_pct") or 0) / 100
    total = sum(float(row.get(campo) or 0) for campo in [
        "costo_producto_usd", "delivery_usd", "impuestos_usd", "comision_usd", "otros_usd"
    ])
    factor_util = max(1 - merma, 0.000001)
    piezas_totales = cantidad_comprada * piezas
    area_por_pieza = ancho * alto if ancho > 0 and alto > 0 else 0
    area_total = area_por_pieza * piezas_totales
    if largo > 0 and ancho > 0:
        area_total = ancho * largo * cantidad_comprada
    peso_total = peso * cantidad_comprada
    volumen_total = volumen * cantidad_comprada
    return pd.Series({
        "costo_puesto_usd": round(total, 6),
        "costo_por_unidad_usd": round(total / piezas_totales, 8) if piezas_totales else 0,
        "costo_por_unidad_util_usd": round(total / (piezas_totales * factor_util), 8) if piezas_totales else 0,
        "area_total_cm2": round(area_total, 4),
        "area_util_cm2": round(area_total * factor_util, 4),
        "costo_por_cm2_usd": round(total / (area_total * factor_util), 10) if area_total > 0 else 0,
        "peso_total_calculado_g": round(peso_total, 4),
        "costo_por_g_usd": round(total / (peso_total * factor_util), 10) if peso_total > 0 else 0,
        "volumen_total_calculado_ml": round(volumen_total, 4),
        "costo_por_ml_usd": round(total / (volumen_total * factor_util), 10) if volumen_total > 0 else 0,
    })


def listar_costeo_elite() -> pd.DataFrame:
    ensure_schema()
    with db_transaction() as conn:
        df = pd.read_sql_query("""
            SELECT i.id, i.sku, i.nombre, COALESCE(i.tipo_fisico,'unidad') AS tipo_fisico,
                   COALESCE(NULLIF(i.unidad_base,''),NULLIF(i.unidad,''),'unidad') AS unidad_base,
                   COALESCE(c.cantidad_comprada,1) AS cantidad_comprada,
                   COALESCE(c.unidad_compra,i.unidad_compra,'') AS unidad_compra,
                   COALESCE(c.piezas_por_compra,NULLIF(i.contenido_compra,0),1) AS piezas_por_compra,
                   COALESCE(c.ancho_cm,i.ancho_cm,0) AS ancho_cm,
                   COALESCE(c.alto_cm,i.alto_cm,0) AS alto_cm,
                   COALESCE(c.largo_cm,0) AS largo_cm,
                   COALESCE(c.peso_total_g,0) AS peso_total_g,
                   COALESCE(c.volumen_total_ml,0) AS volumen_total_ml,
                   COALESCE(c.costo_producto_usd,0) AS costo_producto_usd,
                   COALESCE(c.delivery_usd,0) AS delivery_usd,
                   COALESCE(c.impuestos_usd,0) AS impuestos_usd,
                   COALESCE(c.comision_usd,0) AS comision_usd,
                   COALESCE(c.otros_usd,0) AS otros_usd,
                   COALESCE(c.merma_pct,i.merma_base_pct,0) AS merma_pct
            FROM inventario i
            LEFT JOIN inventario_costeo_elite c ON c.inventario_id=i.id
            WHERE lower(COALESCE(i.estado,'activo'))='activo'
            ORDER BY i.nombre COLLATE NOCASE
        """, conn)
    if df.empty:
        return df
    calculos = df.apply(_calcular, axis=1)
    return pd.concat([df, calculos], axis=1)


def calcular_corte(
    *,
    ancho_material_cm: float,
    alto_material_cm: float,
    ancho_pieza_cm: float,
    alto_pieza_cm: float,
    separacion_cm: float,
    margen_cm: float,
) -> dict[str, float]:
    valores = [ancho_material_cm, alto_material_cm, ancho_pieza_cm, alto_pieza_cm]
    if any(float(v or 0) <= 0 for v in valores):
        raise ValueError("Las medidas del material y de la pieza deben ser mayores que cero.")
    ancho_util = max(float(ancho_material_cm) - 2 * float(margen_cm or 0), 0)
    alto_util = max(float(alto_material_cm) - 2 * float(margen_cm or 0), 0)
    paso_x = float(ancho_pieza_cm) + float(separacion_cm or 0)
    paso_y = float(alto_pieza_cm) + float(separacion_cm or 0)
    columnas = int((ancho_util + float(separacion_cm or 0)) // paso_x) if paso_x > 0 else 0
    filas = int((alto_util + float(separacion_cm or 0)) // paso_y) if paso_y > 0 else 0
    piezas = columnas * filas
    area_total = float(ancho_material_cm) * float(alto_material_cm)
    area_usada = piezas * float(ancho_pieza_cm) * float(alto_pieza_cm)
    merma = max(area_total - area_usada, 0)
    return {
        "columnas": columnas,
        "filas": filas,
        "piezas": piezas,
        "area_total_cm2": round(area_total, 4),
        "area_usada_cm2": round(area_usada, 4),
        "area_merma_cm2": round(merma, 4),
        "aprovechamiento_pct": round(area_usada / area_total * 100, 2) if area_total else 0,
    }
