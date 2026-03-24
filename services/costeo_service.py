from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


DEFAULT_PARAMETROS = {
    "factor_imprevistos_pct": 5.0,
    "factor_indirecto_pct": 10.0,
    "margen_objetivo_pct": 35.0,
}

COSTEO_ESTADOS = ("borrador", "cotizado", "aprobado", "ejecutado", "cerrado")


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
        params = dict(DEFAULT_PARAMETROS)
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(parametros_costeo)").fetchall()}
            if not columns:
                return params

            where_clause = " WHERE COALESCE(estado, 'activo') = 'activo'" if "estado" in columns else ""
            rows = connection.execute(
                f"""
                SELECT clave, valor_num
                FROM parametros_costeo
                {where_clause}
                """
            ).fetchall()
            for row in rows:
                if row["clave"] in params and row["valor_num"] is not None:
                    params[row["clave"]] = float(row["valor_num"])
        except sqlite3.OperationalError:
            return params
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


def _normalizar_estado_costeo(estado: str | None) -> str:
    estado_ok = clean_text(estado or "") or "borrador"
    estado_ok = estado_ok.lower()
    if estado_ok not in COSTEO_ESTADOS:
        raise ValueError(f"Estado de costeo inválido: {estado}")
    return estado_ok


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
    cotizacion_id: int | None = None,
    venta_id: int | None = None,
    orden_produccion_id: int | None = None,
    estado: str = "borrador",
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
    estado_ok = _normalizar_estado_costeo(estado)

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
                referencia_id,
                cotizacion_id,
                venta_id,
                orden_produccion_id,
                estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                int(cotizacion_id) if cotizacion_id else None,
                int(venta_id) if venta_id else None,
                int(orden_produccion_id) if orden_produccion_id else None,
                estado_ok,
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
                    metadata,
                    tipo_registro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    orden_id,
                    concepto,
                    categoria,
                    float(cantidad_item),
                    money(costo_unitario_item),
                    money(subtotal_item),
                    json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                    "estimado",
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
            cotizacion_id,
            venta_id,
            orden_produccion_id,
            costo_real_usd,
            precio_vendido_usd,
            margen_real_pct,
            diferencia_vs_estimado_usd,
            ejecutado_en,
            cerrado_en,
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
                metadata,
                tipo_registro
            FROM costeo_detalle
            WHERE orden_id = ?
            ORDER BY id ASC
            """,
            conn,
            params=[int(orden_id)],
        )


def actualizar_vinculos_costeo(
    *,
    orden_id: int,
    cotizacion_id: int | None = None,
    venta_id: int | None = None,
    orden_produccion_id: int | None = None,
    estado: str | None = None,
) -> None:
    campos = []
    params: list[Any] = []

    if cotizacion_id is not None:
        campos.append("cotizacion_id = ?")
        params.append(int(cotizacion_id))
    if venta_id is not None:
        campos.append("venta_id = ?")
        params.append(int(venta_id))
    if orden_produccion_id is not None:
        campos.append("orden_produccion_id = ?")
        params.append(int(orden_produccion_id))
    if estado is not None:
        campos.append("estado = ?")
        params.append(_normalizar_estado_costeo(estado))

    if not campos:
        return

    params.append(int(orden_id))
    with db_transaction() as conn:
        conn.execute(
            f"UPDATE costeo_ordenes SET {', '.join(campos)} WHERE id = ?",
            params,
        )


def registrar_costeo_real(
    *,
    orden_id: int,
    usuario: str,
    materiales_consumidos_usd: float,
    merma_usd: float,
    mano_obra_real_usd: float,
    tiempo_real_horas: float,
    energia_indirectos_reales_usd: float,
    ajustes_manual_usd: float,
    precio_vendido_usd: float | None = None,
    venta_id: int | None = None,
    orden_produccion_id: int | None = None,
    cerrar: bool = False,
) -> dict[str, float]:
    orden_id_ok = int(orden_id)
    usuario_ok = require_text(usuario, "Usuario")
    costo_materiales = as_positive(materiales_consumidos_usd, "Materiales consumidos")
    costo_merma = as_positive(merma_usd, "Merma")
    costo_mo = as_positive(mano_obra_real_usd, "Mano de obra real")
    horas_reales = as_positive(tiempo_real_horas, "Tiempo real")
    costo_indirectos = as_positive(energia_indirectos_reales_usd, "Energía/indirectos reales")
    costo_ajustes = float(ajustes_manual_usd or 0.0)

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT costo_total_usd, precio_sugerido_usd
            FROM costeo_ordenes
            WHERE id = ?
            """,
            (orden_id_ok,),
        ).fetchone()
        if not row:
            raise ValueError(f"Costeo #{orden_id_ok} no existe")

        costo_estimado = money(float(row["costo_total_usd"] or 0.0))
        precio_referencia = money(float(row["precio_sugerido_usd"] or 0.0))
        precio_vendido = money(float(precio_vendido_usd)) if precio_vendido_usd is not None else precio_referencia

        costo_real = money(costo_materiales + costo_merma + costo_mo + costo_indirectos + costo_ajustes)
        diferencia = money(costo_real - costo_estimado)
        utilidad_real = money(precio_vendido - costo_real)
        margen_real = money((utilidad_real / precio_vendido) * 100) if precio_vendido > 0 else 0.0

        detalle_real = [
            ("Materiales consumidos", "material_real", costo_materiales, {"usuario": usuario_ok}),
            ("Merma", "merma_real", costo_merma, {"usuario": usuario_ok}),
            ("Mano de obra real", "mano_obra_real", costo_mo, {"usuario": usuario_ok, "horas": horas_reales}),
            ("Energía/indirectos reales", "indirecto_real", costo_indirectos, {"usuario": usuario_ok}),
            ("Ajustes manuales", "ajuste_real", costo_ajustes, {"usuario": usuario_ok}),
        ]
        for concepto, categoria, subtotal, metadata in detalle_real:
            conn.execute(
                """
                INSERT INTO costeo_detalle (
                    orden_id, concepto, categoria, cantidad, costo_unitario_usd, subtotal_usd, metadata, tipo_registro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    orden_id_ok,
                    concepto,
                    categoria,
                    1.0,
                    money(subtotal),
                    money(subtotal),
                    json.dumps(metadata, ensure_ascii=False),
                    "real",
                ),
            )

        nuevo_estado = "cerrado" if cerrar else "ejecutado"
        conn.execute(
            """
            UPDATE costeo_ordenes
            SET costo_real_usd = ?,
                precio_vendido_usd = ?,
                margen_real_pct = ?,
                diferencia_vs_estimado_usd = ?,
                venta_id = COALESCE(?, venta_id),
                orden_produccion_id = COALESCE(?, orden_produccion_id),
                estado = ?,
                ejecutado_en = COALESCE(ejecutado_en, CURRENT_TIMESTAMP),
                cerrado_en = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE cerrado_en END
            WHERE id = ?
            """,
            (
                costo_real,
                precio_vendido,
                margen_real,
                diferencia,
                int(venta_id) if venta_id else None,
                int(orden_produccion_id) if orden_produccion_id else None,
                nuevo_estado,
                1 if cerrar else 0,
                orden_id_ok,
            ),
        )

    return {
        "costo_estimado_usd": costo_estimado,
        "costo_real_usd": costo_real,
        "precio_vendido_usd": precio_vendido,
        "margen_real_pct": margen_real,
        "diferencia_vs_estimado_usd": diferencia,
    }
