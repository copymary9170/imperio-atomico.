from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, money

ESTADOS_RENTABILIDAD = ("ejecutado", "cerrado")


def _resolver_estado(estado: str | None) -> str | None:
    estado_ok = clean_text(estado or "")
    if not estado_ok:
        return None
    estado_ok = estado_ok.lower()
    if estado_ok not in ESTADOS_RENTABILIDAD:
        return None
    return estado_ok


def _base_where_clause(
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    tipo_proceso: str | None = None,
    estado: str | None = None,
    usuario: str | None = None,
) -> tuple[str, list[Any]]:
    filtros = ["LOWER(COALESCE(o.estado, '')) IN ('ejecutado', 'cerrado')"]
    params: list[Any] = []

    if fecha_desde:
        filtros.append("date(COALESCE(o.cerrado_en, o.ejecutado_en, o.fecha)) >= date(?)")
        params.append(fecha_desde)
    if fecha_hasta:
        filtros.append("date(COALESCE(o.cerrado_en, o.ejecutado_en, o.fecha)) <= date(?)")
        params.append(fecha_hasta)

    tipo_ok = clean_text(tipo_proceso or "")
    if tipo_ok:
        filtros.append("o.tipo_proceso = ?")
        params.append(tipo_ok)

    estado_ok = _resolver_estado(estado)
    if estado_ok:
        filtros.append("LOWER(o.estado) = ?")
        params.append(estado_ok)

    usuario_ok = clean_text(usuario or "")
    if usuario_ok:
        filtros.append("o.usuario = ?")
        params.append(usuario_ok)

    return " AND ".join(filtros), params


def obtener_opciones_filtro() -> dict[str, list[str]]:
    with db_transaction() as conn:
        tipos = pd.read_sql_query(
            """
            SELECT DISTINCT tipo_proceso
            FROM costeo_ordenes
            WHERE LOWER(COALESCE(estado, '')) IN ('ejecutado', 'cerrado')
            ORDER BY tipo_proceso
            """,
            conn,
        )
        usuarios = pd.read_sql_query(
            """
            SELECT DISTINCT usuario
            FROM costeo_ordenes
            WHERE LOWER(COALESCE(estado, '')) IN ('ejecutado', 'cerrado')
            ORDER BY usuario
            """,
            conn,
        )

    return {
        "tipos_proceso": [str(v) for v in tipos["tipo_proceso"].dropna().tolist()],
        "usuarios": [str(v) for v in usuarios["usuario"].dropna().tolist()],
        "estados": list(ESTADOS_RENTABILIDAD),
    }


def obtener_resumen_rentabilidad(
    *,
    fecha_desde: date | str | None = None,
    fecha_hasta: date | str | None = None,
    tipo_proceso: str | None = None,
    estado: str | None = None,
    usuario: str | None = None,
) -> dict[str, Any]:
    fecha_desde_iso = fecha_desde.isoformat() if isinstance(fecha_desde, date) else fecha_desde
    fecha_hasta_iso = fecha_hasta.isoformat() if isinstance(fecha_hasta, date) else fecha_hasta

    where_clause, params = _base_where_clause(
        fecha_desde=fecha_desde_iso,
        fecha_hasta=fecha_hasta_iso,
        tipo_proceso=tipo_proceso,
        estado=estado,
        usuario=usuario,
    )

    with db_transaction() as conn:
        metricas_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_trabajos,
                COALESCE(SUM(COALESCE(o.precio_vendido_usd, 0)), 0) AS ingreso_vendido_total_usd,
                COALESCE(SUM(COALESCE(o.costo_real_usd, 0)), 0) AS costo_real_total_usd,
                COALESCE(SUM(COALESCE(o.precio_vendido_usd, 0) - COALESCE(o.costo_real_usd, 0)), 0) AS utilidad_bruta_total_usd,
                COALESCE(AVG(COALESCE(o.margen_real_pct, 0)), 0) AS margen_promedio_real_pct,
                COALESCE(AVG(COALESCE(o.diferencia_vs_estimado_usd, 0)), 0) AS desviacion_promedio_vs_estimado_usd,
                COALESCE(SUM(COALESCE(o.precio_sugerido_usd, 0)), 0) AS ingreso_estimado_total_usd,
                COALESCE(SUM(COALESCE(o.costo_total_usd, 0)), 0) AS costo_estimado_total_usd,
                COALESCE(SUM(COALESCE(o.precio_sugerido_usd, 0) - COALESCE(o.costo_total_usd, 0)), 0) AS utilidad_estimada_total_usd,
                COALESCE(AVG(CASE
                    WHEN COALESCE(o.precio_sugerido_usd, 0) > 0
                    THEN ((COALESCE(o.precio_sugerido_usd, 0) - COALESCE(o.costo_total_usd, 0)) / o.precio_sugerido_usd) * 100
                    ELSE 0
                END), 0) AS margen_promedio_estimado_pct
            FROM costeo_ordenes o
            WHERE {where_clause}
            """,
            params,
        ).fetchone()

        rentabilidad_proceso = pd.read_sql_query(
            f"""
            SELECT
                o.tipo_proceso,
                COUNT(*) AS trabajos,
                SUM(COALESCE(o.precio_vendido_usd, 0)) AS ingreso_vendido_usd,
                SUM(COALESCE(o.costo_real_usd, 0)) AS costo_real_usd,
                SUM(COALESCE(o.precio_vendido_usd, 0) - COALESCE(o.costo_real_usd, 0)) AS utilidad_bruta_usd,
                AVG(COALESCE(o.margen_real_pct, 0)) AS margen_real_promedio_pct,
                AVG(COALESCE(o.diferencia_vs_estimado_usd, 0)) AS desviacion_promedio_usd
            FROM costeo_ordenes o
            WHERE {where_clause}
            GROUP BY o.tipo_proceso
            ORDER BY utilidad_bruta_usd DESC
            """,
            conn,
            params=params,
        )

        trabajos = pd.read_sql_query(
            f"""
            SELECT
                o.id,
                COALESCE(o.cerrado_en, o.ejecutado_en, o.fecha) AS fecha_ref,
                o.tipo_proceso,
                o.descripcion,
                o.usuario,
                o.estado,
                COALESCE(o.precio_sugerido_usd, 0) AS ingreso_estimado_usd,
                COALESCE(o.costo_total_usd, 0) AS costo_estimado_usd,
                COALESCE(o.precio_sugerido_usd, 0) - COALESCE(o.costo_total_usd, 0) AS utilidad_estimada_usd,
                CASE
                    WHEN COALESCE(o.precio_sugerido_usd, 0) > 0
                    THEN ((COALESCE(o.precio_sugerido_usd, 0) - COALESCE(o.costo_total_usd, 0)) / o.precio_sugerido_usd) * 100
                    ELSE 0
                END AS margen_estimado_pct,
                COALESCE(o.precio_vendido_usd, 0) AS ingreso_real_usd,
                COALESCE(o.costo_real_usd, 0) AS costo_real_usd,
                COALESCE(o.precio_vendido_usd, 0) - COALESCE(o.costo_real_usd, 0) AS utilidad_real_usd,
                COALESCE(o.margen_real_pct, 0) AS margen_real_pct,
                COALESCE(o.diferencia_vs_estimado_usd, 0) AS diferencia_vs_estimado_usd,
                (COALESCE(o.precio_vendido_usd, 0) - COALESCE(o.costo_real_usd, 0))
                    - (COALESCE(o.precio_sugerido_usd, 0) - COALESCE(o.costo_total_usd, 0))
                    AS diferencia_utilidad_vs_estimado_usd
            FROM costeo_ordenes o
            WHERE {where_clause}
            ORDER BY datetime(COALESCE(o.cerrado_en, o.ejecutado_en, o.fecha)) DESC, o.id DESC
            """,
            conn,
            params=params,
        )

        composicion_real = pd.read_sql_query(
            f"""
            SELECT
                o.tipo_proceso,
                COALESCE(d.categoria, 'sin_categoria') AS categoria,
                SUM(COALESCE(d.subtotal_usd, 0)) AS subtotal_real_usd,
                COUNT(*) AS registros
            FROM costeo_ordenes o
            LEFT JOIN costeo_detalle d ON d.orden_id = o.id AND d.tipo_registro = 'real'
            WHERE {where_clause}
            GROUP BY o.tipo_proceso, COALESCE(d.categoria, 'sin_categoria')
            ORDER BY subtotal_real_usd DESC
            """,
            conn,
            params=params,
        )

    metricas = {
        "total_trabajos": int(metricas_row["total_trabajos"] or 0),
        "ingreso_vendido_total_usd": money(metricas_row["ingreso_vendido_total_usd"] or 0),
        "costo_real_total_usd": money(metricas_row["costo_real_total_usd"] or 0),
        "utilidad_bruta_total_usd": money(metricas_row["utilidad_bruta_total_usd"] or 0),
        "margen_promedio_real_pct": money(metricas_row["margen_promedio_real_pct"] or 0),
        "desviacion_promedio_vs_estimado_usd": money(metricas_row["desviacion_promedio_vs_estimado_usd"] or 0),
        "ingreso_estimado_total_usd": money(metricas_row["ingreso_estimado_total_usd"] or 0),
        "costo_estimado_total_usd": money(metricas_row["costo_estimado_total_usd"] or 0),
        "utilidad_estimada_total_usd": money(metricas_row["utilidad_estimada_total_usd"] or 0),
        "margen_promedio_estimado_pct": money(metricas_row["margen_promedio_estimado_pct"] or 0),
    }

    mejores_trabajos = trabajos.sort_values(["utilidad_real_usd", "margen_real_pct"], ascending=[False, False]).head(10)
    peores_trabajos = trabajos.sort_values(["utilidad_real_usd", "margen_real_pct"], ascending=[True, True]).head(10)
    mayores_desviaciones = trabajos.assign(
        abs_desviacion=lambda df: df["diferencia_vs_estimado_usd"].abs()
    ).sort_values(["abs_desviacion", "diferencia_vs_estimado_usd"], ascending=[False, False]).head(10)

    return {
        "metricas": metricas,
        "rentabilidad_por_proceso": rentabilidad_proceso,
        "trabajos": trabajos,
        "trabajos_mas_rentables": mejores_trabajos,
        "trabajos_menos_rentables": peores_trabajos,
        "mayores_desviaciones": mayores_desviaciones,
        "composicion_real": composicion_real,
    }
