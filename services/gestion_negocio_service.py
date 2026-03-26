from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from database.connection import get_connection


@dataclass(frozen=True)
class DashboardFilters:
    fecha_desde: str
    fecha_hasta: str
    sucursal: str = "ALL"
    usuario: str = "ALL"
    tipo_negocio: str = "ALL"


def _today_iso() -> str:
    return date.today().isoformat()


def _default_since(days: int = 30) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def normalize_filters(raw: dict[str, str] | None = None) -> DashboardFilters:
    raw = raw or {}
    fecha_desde = raw.get("fecha_desde") or _default_since(30)
    fecha_hasta = raw.get("fecha_hasta") or _today_iso()
    return DashboardFilters(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        sucursal=(raw.get("sucursal") or "ALL").strip() or "ALL",
        usuario=(raw.get("usuario") or "ALL").strip() or "ALL",
        tipo_negocio=(raw.get("tipo_negocio") or "ALL").strip() or "ALL",
    )


def _where(filters: DashboardFilters, table_alias: str = "") -> tuple[str, list[Any]]:
    prefix = f"{table_alias}." if table_alias else ""
    clauses = [f"date({prefix}fecha) BETWEEN date(?) AND date(?)"]
    params: list[Any] = [filters.fecha_desde, filters.fecha_hasta]

    if filters.sucursal != "ALL":
        clauses.append(f"COALESCE({prefix}sucursal, 'Matriz') = ?")
        params.append(filters.sucursal)
    if filters.usuario != "ALL":
        clauses.append(f"COALESCE({prefix}usuario, 'Sistema') = ?")
        params.append(filters.usuario)
    if filters.tipo_negocio != "ALL":
        clauses.append(f"COALESCE({prefix}tipo_negocio, 'General') = ?")
        params.append(filters.tipo_negocio)

    return " AND ".join(clauses), params


def _fetch_one_dict(query: str, params: list[Any]) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else {}


def _fetch_all_dict(query: str, params: list[Any]) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def dashboard_kpis(filters: DashboardFilters) -> dict[str, Any]:
    where_v, params_v = _where(filters, "v")
    where_d, params_d = _where(filters, "v")
    where_g, params_g = _where(filters, "g")

    ventas = _fetch_one_dict(
        f"""
        SELECT
            COUNT(*) AS total_ventas,
            ROUND(COALESCE(SUM(v.total_usd), 0), 2) AS ingresos_usd,
            ROUND(COALESCE(AVG(v.total_usd), 0), 2) AS ticket_promedio_usd
        FROM ventas v
        WHERE {where_v}
        """,
        params_v,
    )

    costos = _fetch_one_dict(
        f"""
        SELECT ROUND(COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0), 2) AS costo_ventas_usd
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        WHERE {where_d}
        """,
        params_d,
    )

    gastos = _fetch_one_dict(
        f"""
        SELECT ROUND(COALESCE(SUM(g.monto_usd), 0), 2) AS gastos_operativos_usd
        FROM gastos g
        WHERE {where_g}
        """,
        params_g,
    )

    ingresos = float(ventas.get("ingresos_usd", 0) or 0)
    costo_ventas = float(costos.get("costo_ventas_usd", 0) or 0)
    gasto_ope = float(gastos.get("gastos_operativos_usd", 0) or 0)
    utilidad_bruta = round(ingresos - costo_ventas, 2)
    utilidad_neta = round(utilidad_bruta - gasto_ope, 2)
    margen_bruto_pct = round((utilidad_bruta / ingresos) * 100, 2) if ingresos > 0 else 0.0
    margen_neto_pct = round((utilidad_neta / ingresos) * 100, 2) if ingresos > 0 else 0.0

    cuentas = cuentas_por_cobrar_resumen(filters)
    pagos = cuentas_por_pagar_resumen(filters)
    pendientes = pedidos_pendientes(filters)

    return {
        "fecha_desde": filters.fecha_desde,
        "fecha_hasta": filters.fecha_hasta,
        "kpis": {
            "ingresos_usd": round(ingresos, 2),
            "costo_ventas_usd": round(costo_ventas, 2),
            "gastos_operativos_usd": round(gasto_ope, 2),
            "utilidad_bruta_usd": utilidad_bruta,
            "utilidad_neta_usd": utilidad_neta,
            "margen_bruto_pct": margen_bruto_pct,
            "margen_neto_pct": margen_neto_pct,
            "total_ventas": int(ventas.get("total_ventas", 0) or 0),
            "ticket_promedio_usd": float(ventas.get("ticket_promedio_usd", 0) or 0),
            "cxc_saldo_usd": float(cuentas["totales"].get("saldo_total_usd", 0) or 0),
            "cxp_saldo_usd": float(pagos["totales"].get("saldo_total_usd", 0) or 0),
            "pedidos_pendientes": len(pendientes["items"]),
        },
    }


def ventas_tiempo(filters: DashboardFilters, grano: str = "dia") -> dict[str, Any]:
    where, params = _where(filters, "v")
    if grano == "semana":
        bucket = "strftime('%Y-W%W', v.fecha)"
    elif grano == "mes":
        bucket = "strftime('%Y-%m', v.fecha)"
    else:
        bucket = "date(v.fecha)"
        grano = "dia"

    rows = _fetch_all_dict(
        f"""
        SELECT
            {bucket} AS periodo,
            ROUND(COALESCE(SUM(v.total_usd), 0), 2) AS ventas_usd,
            COUNT(*) AS transacciones
        FROM ventas v
        WHERE {where}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )
    return {"grano": grano, "series": rows}


def consolidado_sucursal(filters: DashboardFilters) -> dict[str, Any]:
    where, params = _where(filters, "v")
    rows = _fetch_all_dict(
        f"""
        SELECT
            COALESCE(v.sucursal, 'Matriz') AS sucursal,
            ROUND(COALESCE(SUM(v.total_usd), 0), 2) AS ingresos_usd,
            ROUND(COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0), 2) AS costo_ventas_usd,
            ROUND(COALESCE(SUM(v.total_usd), 0) - COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0), 2) AS utilidad_bruta_usd,
            COUNT(DISTINCT v.id) AS ventas
        FROM ventas v
        LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
        WHERE {where}
        GROUP BY COALESCE(v.sucursal, 'Matriz')
        ORDER BY ingresos_usd DESC
        """,
        params,
    )
    return {"items": rows}


def rentabilidad_linea_negocio(filters: DashboardFilters) -> dict[str, Any]:
    where, params = _where(filters, "v")
    rows = _fetch_all_dict(
        f"""
        SELECT
            COALESCE(v.tipo_negocio, 'General') AS tipo_negocio,
            ROUND(COALESCE(SUM(v.total_usd), 0), 2) AS ingresos_usd,
            ROUND(COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0), 2) AS costo_ventas_usd,
            ROUND(COALESCE(SUM(v.total_usd), 0) - COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0), 2) AS utilidad_bruta_usd,
            ROUND(
                CASE
                    WHEN COALESCE(SUM(v.total_usd), 0) > 0
                    THEN ((COALESCE(SUM(v.total_usd), 0) - COALESCE(SUM(vd.cantidad * vd.costo_unitario_usd), 0)) / COALESCE(SUM(v.total_usd), 0)) * 100
                    ELSE 0
                END,
                2
            ) AS margen_bruto_pct
        FROM ventas v
        LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
        WHERE {where}
        GROUP BY COALESCE(v.tipo_negocio, 'General')
        ORDER BY utilidad_bruta_usd DESC
        """,
        params,
    )
    return {"items": rows}


def productos_mas_vendidos(filters: DashboardFilters, limit: int = 10) -> dict[str, Any]:
    where, params = _where(filters, "v")
    rows = _fetch_all_dict(
        f"""
        SELECT
            vd.descripcion AS producto,
            ROUND(COALESCE(SUM(vd.cantidad), 0), 2) AS cantidad,
            ROUND(COALESCE(SUM(vd.subtotal_usd), 0), 2) AS venta_usd
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        WHERE {where}
        GROUP BY vd.descripcion
        ORDER BY cantidad DESC, venta_usd DESC
        LIMIT ?
        """,
        params + [int(limit)],
    )
    return {"items": rows}


def servicios_mas_rentables(filters: DashboardFilters, limit: int = 10) -> dict[str, Any]:
    where, params = _where(filters, "o")
    rows = _fetch_all_dict(
        f"""
        SELECT
            COALESCE(o.tipo_negocio, o.tipo_proceso, 'Servicio general') AS servicio,
            COUNT(*) AS ordenes,
            ROUND(COALESCE(SUM(o.precio_vendido_usd), 0), 2) AS ingresos_usd,
            ROUND(COALESCE(SUM(o.costo_real_usd), 0), 2) AS costo_real_usd,
            ROUND(COALESCE(SUM(o.precio_vendido_usd - o.costo_real_usd), 0), 2) AS utilidad_usd,
            ROUND(
                CASE WHEN COALESCE(SUM(o.precio_vendido_usd), 0) > 0
                    THEN (COALESCE(SUM(o.precio_vendido_usd - o.costo_real_usd), 0) / COALESCE(SUM(o.precio_vendido_usd), 0)) * 100
                    ELSE 0
                END,
            2) AS margen_pct
        FROM costeo_ordenes o
        WHERE {where}
          AND LOWER(COALESCE(o.estado, '')) IN ('ejecutado', 'cerrado')
        GROUP BY COALESCE(o.tipo_negocio, o.tipo_proceso, 'Servicio general')
        ORDER BY utilidad_usd DESC
        LIMIT ?
        """,
        params + [int(limit)],
    )
    return {"items": rows}


def pedidos_pendientes(filters: DashboardFilters) -> dict[str, Any]:
    where, params = _where(filters, "p")
    rows = _fetch_all_dict(
        f"""
        SELECT
            p.id,
            p.fecha,
            p.sucursal,
            p.usuario,
            p.tipo_negocio,
            p.cliente,
            p.descripcion,
            p.fecha_entrega,
            p.total_usd,
            p.estado,
            CAST(julianday(COALESCE(p.fecha_entrega, date('now'))) - julianday(date('now')) AS INTEGER) AS dias_para_entrega
        FROM pedidos_negocio p
        WHERE {where}
          AND LOWER(COALESCE(p.estado, 'pendiente')) IN ('pendiente', 'en_proceso')
        ORDER BY date(p.fecha_entrega) ASC, p.id DESC
        """,
        params,
    )
    return {"items": rows}


def cuentas_por_cobrar_resumen(filters: DashboardFilters) -> dict[str, Any]:
    where, params = _where(filters, "c")
    items = _fetch_all_dict(
        f"""
        SELECT
            c.id,
            c.fecha,
            COALESCE(cl.nombre, 'Cliente sin nombre') AS cliente,
            c.sucursal,
            c.tipo_negocio,
            c.saldo_usd,
            c.fecha_vencimiento,
            CASE
                WHEN c.fecha_vencimiento IS NULL THEN 0
                ELSE MAX(CAST(julianday(date('now')) - julianday(date(c.fecha_vencimiento)) AS INTEGER), 0)
            END AS dias_vencido,
            c.estado
        FROM cuentas_por_cobrar c
        LEFT JOIN clientes cl ON cl.id = c.cliente_id
        WHERE {where}
          AND LOWER(COALESCE(c.estado, 'pendiente')) IN ('pendiente', 'parcial', 'vencida')
        ORDER BY dias_vencido DESC, c.saldo_usd DESC
        """,
        params,
    )
    total = round(sum(float(i.get("saldo_usd") or 0) for i in items), 2)
    vencido = round(sum(float(i.get("saldo_usd") or 0) for i in items if int(i.get("dias_vencido") or 0) > 0), 2)
    return {"totales": {"saldo_total_usd": total, "saldo_vencido_usd": vencido}, "items": items}


def cuentas_por_pagar_resumen(filters: DashboardFilters) -> dict[str, Any]:
    where, params = _where(filters, "c")
    items = _fetch_all_dict(
        f"""
        SELECT
            c.id,
            c.fecha,
            c.sucursal,
            c.tipo_negocio,
            c.saldo_usd,
            c.fecha_vencimiento,
            CASE
                WHEN c.fecha_vencimiento IS NULL THEN 0
                ELSE MAX(CAST(julianday(date('now')) - julianday(date(c.fecha_vencimiento)) AS INTEGER), 0)
            END AS dias_vencido,
            c.estado
        FROM cuentas_por_pagar_proveedores c
        WHERE {where}
          AND LOWER(COALESCE(c.estado, 'pendiente')) IN ('pendiente', 'parcial', 'vencida')
        ORDER BY dias_vencido DESC, c.saldo_usd DESC
        """,
        params,
    )
    total = round(sum(float(i.get("saldo_usd") or 0) for i in items), 2)
    vencido = round(sum(float(i.get("saldo_usd") or 0) for i in items if int(i.get("dias_vencido") or 0) > 0), 2)
    return {"totales": {"saldo_total_usd": total, "saldo_vencido_usd": vencido}, "items": items}


def alertas_negocio(filters: DashboardFilters) -> dict[str, Any]:
    kpi = dashboard_kpis(filters)["kpis"]
    cuentas = cuentas_por_cobrar_resumen(filters)["totales"]
    pagos = cuentas_por_pagar_resumen(filters)["totales"]
    pendientes = pedidos_pendientes(filters)["items"]

    alerts: list[dict[str, Any]] = []
    if kpi["margen_neto_pct"] < 15:
        alerts.append({"codigo": "margen_bajo", "prioridad": "alta", "mensaje": "Margen neto por debajo de 15%."})
    if cuentas["saldo_vencido_usd"] > 0:
        alerts.append({"codigo": "cxc_vencida", "prioridad": "alta", "mensaje": f"CXC vencida por USD {cuentas['saldo_vencido_usd']:.2f}."})
    if pagos["saldo_vencido_usd"] > 0:
        alerts.append({"codigo": "cxp_vencida", "prioridad": "media", "mensaje": f"CXP vencida por USD {pagos['saldo_vencido_usd']:.2f}."})

    vencidos = [p for p in pendientes if int(p.get("dias_para_entrega") or 0) < 0]
    if vencidos:
        alerts.append({"codigo": "pedidos_atrasados", "prioridad": "alta", "mensaje": f"{len(vencidos)} pedido(s) con fecha de entrega vencida."})

    return {"items": alerts}


def dashboard_payload(raw_filters: dict[str, str] | None = None) -> dict[str, Any]:
    filters = normalize_filters(raw_filters)
    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "filters": {
            "fecha_desde": filters.fecha_desde,
            "fecha_hasta": filters.fecha_hasta,
            "sucursal": filters.sucursal,
            "usuario": filters.usuario,
            "tipo_negocio": filters.tipo_negocio,
        },
        "dashboard": {
            "resumen": dashboard_kpis(filters),
            "consolidado_sucursal": consolidado_sucursal(filters),
            "rentabilidad_linea": rentabilidad_linea_negocio(filters),
            "ventas_dia": ventas_tiempo(filters, "dia"),
            "ventas_semana": ventas_tiempo(filters, "semana"),
            "ventas_mes": ventas_tiempo(filters, "mes"),
            "productos_top": productos_mas_vendidos(filters, 10),
            "servicios_rentables": servicios_mas_rentables(filters, 10),
            "pedidos_pendientes": pedidos_pendientes(filters),
            "cuentas_por_cobrar": cuentas_por_cobrar_resumen(filters),
            "cuentas_por_pagar": cuentas_por_pagar_resumen(filters),
            "alertas": alertas_negocio(filters),
        },
    }
