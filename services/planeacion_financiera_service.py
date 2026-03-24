from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd


VENTANAS_PROYECCION = (7, 15, 30)


def _periodo_actual() -> str:
    hoy = date.today()
    return f"{hoy.year:04d}-{hoy.month:02d}"


def guardar_presupuesto_operativo(
    conn: Any,
    *,
    periodo: str,
    categoria: str,
    tipo: str,
    monto_presupuestado_usd: float,
    usuario: str,
    meta_kpi_usd: float = 0.0,
    notas: str | None = None,
) -> int:
    tipo_norm = (tipo or "").strip().lower()
    if tipo_norm not in {"ingreso", "egreso"}:
        raise ValueError("Tipo de presupuesto inválido")

    periodo_norm = (periodo or "").strip() or _periodo_actual()
    if len(periodo_norm) != 7 or "-" not in periodo_norm:
        raise ValueError("El período debe usar formato YYYY-MM")

    conn.execute(
        """
        INSERT INTO presupuesto_operativo
        (periodo, categoria, tipo, monto_presupuestado_usd, meta_kpi_usd, usuario, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(periodo, categoria, tipo) DO UPDATE SET
            monto_presupuestado_usd = excluded.monto_presupuestado_usd,
            meta_kpi_usd = excluded.meta_kpi_usd,
            usuario = excluded.usuario,
            notas = excluded.notas,
            actualizado_en = CURRENT_TIMESTAMP
        """,
        (
            periodo_norm,
            (categoria or "").strip() or "general",
            tipo_norm,
            float(monto_presupuestado_usd or 0),
            float(meta_kpi_usd or 0),
            str(usuario or "Sistema"),
            (notas or "").strip() or None,
        ),
    )
    row = conn.execute(
        """
        SELECT id
        FROM presupuesto_operativo
        WHERE periodo=? AND categoria=? AND tipo=?
        LIMIT 1
        """,
        (periodo_norm, (categoria or "").strip() or "general", tipo_norm),
    ).fetchone()
    return int(row["id"]) if row else 0


def listar_presupuesto_operativo(conn: Any, *, periodo: str | None = None) -> pd.DataFrame:
    periodo_norm = (periodo or "").strip() or _periodo_actual()
    return pd.read_sql_query(
        """
        SELECT
            id,
            periodo,
            categoria,
            tipo,
            monto_presupuestado_usd,
            meta_kpi_usd,
            usuario,
            notas,
            actualizado_en
        FROM presupuesto_operativo
        WHERE periodo = ?
        ORDER BY tipo, categoria
        """,
        conn,
        params=[periodo_norm],
    )


def _saldo_actual_tesoreria(conn: Any) -> float:
    row = conn.execute(
        """
        SELECT
            ROUND(
                COALESCE(SUM(CASE WHEN tipo='ingreso' AND estado='confirmado' THEN monto_usd END), 0)
                -
                COALESCE(SUM(CASE WHEN tipo='egreso' AND estado='confirmado' THEN monto_usd END), 0),
                2
            ) AS saldo_actual
        FROM movimientos_tesoreria
        """
    ).fetchone()
    return float(row["saldo_actual"] if row and row["saldo_actual"] is not None else 0.0)


def _sumatoria_cxc_hasta(conn: Any, fecha_hasta: str) -> float:
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(saldo_usd), 0), 2) AS total
        FROM cuentas_por_cobrar
        WHERE estado IN ('pendiente', 'parcial', 'vencida')
          AND COALESCE(saldo_usd, 0) > 0
          AND fecha_vencimiento IS NOT NULL
          AND date(fecha_vencimiento) BETWEEN date('now') AND date(?)
        """,
        (fecha_hasta,),
    ).fetchone()
    return float(row["total"] if row and row["total"] is not None else 0.0)


def _sumatoria_cxp_hasta(conn: Any, fecha_hasta: str) -> float:
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(saldo_usd), 0), 2) AS total
        FROM cuentas_por_pagar_proveedores
        WHERE estado IN ('pendiente', 'parcial', 'vencida')
          AND COALESCE(saldo_usd, 0) > 0
          AND fecha_vencimiento IS NOT NULL
          AND date(fecha_vencimiento) BETWEEN date('now') AND date(?)
        """,
        (fecha_hasta,),
    ).fetchone()
    return float(row["total"] if row and row["total"] is not None else 0.0)


def _sumatoria_gastos_esperados(conn: Any, dias: int) -> float:
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(monto_usd), 0), 2) AS total
        FROM gastos
        WHERE estado='activo'
          AND date(fecha) >= date('now', '-30 day')
        """
    ).fetchone()
    gastos_30 = float(row["total"] if row and row["total"] is not None else 0.0)
    if gastos_30 <= 0:
        return 0.0
    return round((gastos_30 / 30.0) * float(dias), 2)


def calcular_flujo_caja_proyectado(conn: Any, *, ventanas: tuple[int, ...] = VENTANAS_PROYECCION) -> pd.DataFrame:
    saldo_actual = _saldo_actual_tesoreria(conn)
    filas: list[dict[str, float | int | str]] = []

    for dias in ventanas:
        fecha_hasta = (date.today() + timedelta(days=int(dias))).isoformat()
        cobros = _sumatoria_cxc_hasta(conn, fecha_hasta)
        pagos = _sumatoria_cxp_hasta(conn, fecha_hasta)
        gastos = _sumatoria_gastos_esperados(conn, dias)

        flujo = round(cobros - pagos - gastos, 2)
        saldo_proyectado = round(saldo_actual + flujo, 2)

        filas.append(
            {
                "horizonte_dias": int(dias),
                "fecha_corte": fecha_hasta,
                "saldo_actual_usd": saldo_actual,
                "cobros_esperados_usd": cobros,
                "pagos_proximos_usd": pagos,
                "gastos_estimados_usd": gastos,
                "flujo_proyectado_usd": flujo,
                "saldo_proyectado_usd": saldo_proyectado,
            }
        )

    return pd.DataFrame(filas)


def resumen_presupuesto_operativo(conn: Any, *, periodo: str | None = None) -> dict[str, float | str]:
    periodo_norm = (periodo or "").strip() or _periodo_actual()
    fecha_desde = f"{periodo_norm}-01"
    fecha_hasta = f"{periodo_norm}-31"

    presupuesto = conn.execute(
        """
        SELECT
            ROUND(COALESCE(SUM(CASE WHEN tipo='ingreso' THEN monto_presupuestado_usd END), 0), 2) AS ingresos_pres,
            ROUND(COALESCE(SUM(CASE WHEN tipo='egreso' THEN monto_presupuestado_usd END), 0), 2) AS egresos_pres
        FROM presupuesto_operativo
        WHERE periodo=?
        """,
        (periodo_norm,),
    ).fetchone()

    ejecutado = conn.execute(
        """
        SELECT
            ROUND(COALESCE((SELECT SUM(total_usd) FROM ventas WHERE date(fecha) BETWEEN date(?) AND date(?) AND estado='registrada'), 0), 2) AS ingresos_real,
            ROUND(COALESCE((SELECT SUM(monto_usd) FROM gastos WHERE date(fecha) BETWEEN date(?) AND date(?) AND estado='activo'), 0), 2) AS egresos_real
        """,
        (fecha_desde, fecha_hasta, fecha_desde, fecha_hasta),
    ).fetchone()

    ingresos_pres = float(presupuesto["ingresos_pres"] if presupuesto else 0.0)
    egresos_pres = float(presupuesto["egresos_pres"] if presupuesto else 0.0)
    ingresos_real = float(ejecutado["ingresos_real"] if ejecutado else 0.0)
    egresos_real = float(ejecutado["egresos_real"] if ejecutado else 0.0)

    return {
        "periodo": periodo_norm,
        "ingresos_presupuestados_usd": ingresos_pres,
        "egresos_presupuestados_usd": egresos_pres,
        "ingresos_ejecutados_usd": ingresos_real,
        "egresos_ejecutados_usd": egresos_real,
        "desviacion_ingresos_usd": round(ingresos_real - ingresos_pres, 2),
        "desviacion_egresos_usd": round(egresos_real - egresos_pres, 2),
    }


def generar_alertas_gerenciales(conn: Any, *, periodo: str | None = None) -> pd.DataFrame:
    periodo_norm = (periodo or "").strip() or _periodo_actual()
    flujo = calcular_flujo_caja_proyectado(conn)
    resumen = resumen_presupuesto_operativo(conn, periodo=periodo_norm)

    alertas: list[dict[str, str | float | int]] = []

    for row in flujo.itertuples():
        if float(row.saldo_proyectado_usd) < 0:
            alertas.append(
                {
                    "tipo_alerta": "faltante_caja",
                    "prioridad": "alta",
                    "horizonte_dias": int(row.horizonte_dias),
                    "mensaje": f"Saldo proyectado negativo en {int(row.horizonte_dias)} días.",
                    "valor_usd": float(row.saldo_proyectado_usd),
                }
            )

    if resumen["egresos_presupuestados_usd"] > 0 and resumen["egresos_ejecutados_usd"] > resumen["egresos_presupuestados_usd"] * 1.05:
        alertas.append(
            {
                "tipo_alerta": "exceso_gasto",
                "prioridad": "media",
                "horizonte_dias": 30,
                "mensaje": "Egresos del período superan presupuesto en más de 5%.",
                "valor_usd": float(resumen["desviacion_egresos_usd"]),
            }
        )

    if resumen["ingresos_presupuestados_usd"] > 0 and resumen["ingresos_ejecutados_usd"] < resumen["ingresos_presupuestados_usd"] * 0.8:
        alertas.append(
            {
                "tipo_alerta": "baja_cobranza",
                "prioridad": "media",
                "horizonte_dias": 30,
                "mensaje": "Ingresos ejecutados por debajo del 80% del presupuesto.",
                "valor_usd": float(resumen["desviacion_ingresos_usd"]),
            }
        )

    vencidos = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(saldo_usd), 0), 2) AS total
        FROM cuentas_por_pagar_proveedores
        WHERE estado IN ('pendiente', 'parcial', 'vencida')
          AND COALESCE(saldo_usd, 0) > 0
          AND fecha_vencimiento IS NOT NULL
          AND date(fecha_vencimiento) < date('now')
        """
    ).fetchone()
    total_vencido = float(vencidos["total"] if vencidos and vencidos["total"] is not None else 0.0)
    if total_vencido > 0:
        alertas.append(
            {
                "tipo_alerta": "vencimientos_criticos",
                "prioridad": "alta",
                "horizonte_dias": 0,
                "mensaje": "Existen cuentas por pagar vencidas.",
                "valor_usd": total_vencido,
            }
        )

    if not alertas:
        alertas.append(
            {
                "tipo_alerta": "sin_alertas",
                "prioridad": "baja",
                "horizonte_dias": 30,
                "mensaje": "Sin alertas críticas con la información actual.",
                "valor_usd": 0.0,
            }
        )

    return pd.DataFrame(alertas).sort_values(["prioridad", "horizonte_dias"], ascending=[True, True]).reset_index(drop=True)
