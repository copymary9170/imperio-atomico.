from __future__ import annotations

import json
from typing import Any

from database.connection import db_transaction


def _scalar(conn, query: str, params: tuple[Any, ...] = ()) -> float:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return 0.0
    value = row[0]
    return float(value or 0)


def calcular_metricas_ejecutivas(periodo: str = "diario") -> dict[str, Any]:
    """Calcula metricas base para el panel ejecutivo usando tablas transaccionales."""
    filtro_fecha = "date(fecha) = date('now', 'localtime')" if periodo == "diario" else "date(fecha) >= date('now', 'start of month')"

    with db_transaction() as conn:
        ventas_usd = _scalar(conn, f"SELECT COALESCE(SUM(total_usd), 0) FROM ventas WHERE estado != 'anulado' AND {filtro_fecha}")
        gastos_usd = _scalar(conn, f"SELECT COALESCE(SUM(monto_usd), 0) FROM gastos WHERE estado != 'anulado' AND {filtro_fecha}")
        costo_ventas_usd = _scalar(
            conn,
            f"""
            SELECT COALESCE(SUM(cantidad * costo_unitario_usd), 0)
            FROM ventas_detalle
            WHERE estado != 'anulado' AND {filtro_fecha}
            """,
        )
        cxc_usd = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd), 0) FROM cuentas_por_cobrar WHERE estado IN ('pendiente','parcial','vencida')")
        cxp_usd = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd), 0) FROM cuentas_por_pagar_proveedores WHERE estado IN ('pendiente','parcial','vencida')")
        stock_critico = int(_scalar(conn, "SELECT COUNT(*) FROM inventario WHERE estado = 'activo' AND stock_actual <= stock_minimo"))
        trabajos_pendientes = int(_scalar(conn, "SELECT COUNT(*) FROM ordenes_produccion WHERE estado IN ('pendiente','en_proceso')"))
        alertas_criticas = int(_scalar(conn, "SELECT COUNT(*) FROM eventos_transaccionales WHERE estado = 'fallido' OR severidad = 'critica'"))

    utilidad_estimada_usd = round(ventas_usd - costo_ventas_usd - gastos_usd, 4)
    return {
        "periodo": periodo,
        "ventas_usd": round(ventas_usd, 4),
        "utilidad_estimada_usd": utilidad_estimada_usd,
        "gastos_usd": round(gastos_usd, 4),
        "cuentas_por_cobrar_usd": round(cxc_usd, 4),
        "cuentas_por_pagar_usd": round(cxp_usd, 4),
        "stock_critico": stock_critico,
        "trabajos_pendientes": trabajos_pendientes,
        "alertas_criticas": alertas_criticas,
    }


def guardar_snapshot_metricas(periodo: str = "diario") -> int:
    metricas = calcular_metricas_ejecutivas(periodo=periodo)
    metadata = {k: v for k, v in metricas.items() if k not in {"periodo"}}
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO metricas_dashboard_snapshot (
                periodo, ventas_usd, utilidad_estimada_usd, gastos_usd,
                cuentas_por_cobrar_usd, cuentas_por_pagar_usd, stock_critico,
                trabajos_pendientes, alertas_criticas, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metricas["periodo"],
                metricas["ventas_usd"],
                metricas["utilidad_estimada_usd"],
                metricas["gastos_usd"],
                metricas["cuentas_por_cobrar_usd"],
                metricas["cuentas_por_pagar_usd"],
                metricas["stock_critico"],
                metricas["trabajos_pendientes"],
                metricas["alertas_criticas"],
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        return int(cur.lastrowid)
