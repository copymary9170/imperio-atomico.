from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


# ============================================================
# ESQUEMA
# ============================================================


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _ensure_planeacion_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS presupuesto_operativo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('ingreso', 'egreso')),
            monto_presupuestado_usd REAL NOT NULL DEFAULT 0,
            meta_kpi_usd REAL NOT NULL DEFAULT 0,
            notas TEXT,
            usuario TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_presupuesto_operativo_periodo
            ON presupuesto_operativo(periodo);

        CREATE INDEX IF NOT EXISTS idx_presupuesto_operativo_tipo
            ON presupuesto_operativo(tipo);
        """
    )


# ============================================================
# AUXILIARES
# ============================================================


def _safe_scalar(conn, query: str, params: tuple[Any, ...] = ()) -> float:
    try:
        row = conn.execute(query, params).fetchone()
        if not row:
            return 0.0
        return float(row[0] or 0.0)
    except Exception:
        return 0.0


def _safe_df(conn, query: str, params: tuple[Any, ...], columns: list[str]) -> pd.DataFrame:
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception:
        return pd.DataFrame(columns=columns)


def _period_bounds(periodo: str) -> tuple[str, str]:
    try:
        year, month = periodo.split("-")
        year_i = int(year)
        month_i = int(month)
        start = date(year_i, month_i, 1)
        if month_i == 12:
            end = date(year_i + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year_i, month_i + 1, 1) - timedelta(days=1)
        return start.isoformat(), end.isoformat()
    except Exception:
        today = date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        return start.isoformat(), end.isoformat()


def _ventas_reales_periodo(conn, fecha_desde: str, fecha_hasta: str) -> float:
    if not _table_exists(conn, "ventas"):
        return 0.0
    return _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(total_usd), 0)
        FROM ventas
        WHERE estado = 'registrada'
          AND DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """,
        (fecha_desde, fecha_hasta),
    )


def _gastos_reales_periodo(conn, fecha_desde: str, fecha_hasta: str) -> float:
    if not _table_exists(conn, "gastos"):
        return 0.0
    return _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(monto_usd), 0)
        FROM gastos
        WHERE estado = 'activo'
          AND DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """,
        (fecha_desde, fecha_hasta),
    )


def _cuentas_por_cobrar_en_horizonte(conn, horizonte_dias: int) -> float:
    if _table_exists(conn, "cuentas_por_cobrar"):
        return _safe_scalar(
            conn,
            """
            SELECT COALESCE(SUM(monto_usd), 0)
            FROM cuentas_por_cobrar
            WHERE estado IN ('pendiente', 'parcial')
              AND DATE(fecha_vencimiento) <= DATE('now', ?)
            """,
            (f"+{int(horizonte_dias)} day",),
        )

    if _table_exists(conn, "ventas"):
        # Fallback: proyecta cobros según promedio diario reciente
        base = _safe_scalar(
            conn,
            """
            SELECT COALESCE(SUM(total_usd), 0)
            FROM ventas
            WHERE estado = 'registrada'
              AND DATE(fecha) >= DATE('now', '-30 day')
            """,
        )
        promedio_diario = base / 30.0
        return promedio_diario * horizonte_dias

    return 0.0


def _cuentas_por_pagar_en_horizonte(conn, horizonte_dias: int) -> float:
    if _table_exists(conn, "cuentas_por_pagar"):
        return _safe_scalar(
            conn,
            """
            SELECT COALESCE(SUM(monto_usd), 0)
            FROM cuentas_por_pagar
            WHERE estado IN ('pendiente', 'parcial')
              AND DATE(fecha_vencimiento) <= DATE('now', ?)
            """,
            (f"+{int(horizonte_dias)} day",),
        )

    if _table_exists(conn, "gastos"):
        # Fallback: proyecta pagos según promedio diario reciente
        base = _safe_scalar(
            conn,
            """
            SELECT COALESCE(SUM(monto_usd), 0)
            FROM gastos
            WHERE estado = 'activo'
              AND DATE(fecha) >= DATE('now', '-30 day')
            """,
        )
        promedio_diario = base / 30.0
        return promedio_diario * horizonte_dias

    return 0.0


def _saldo_actual_estimado(conn) -> float:
    # Prioridad 1: caja/bancos
    if _table_exists(conn, "movimientos_financieros"):
        return _safe_scalar(
            conn,
            """
            SELECT COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(tipo) IN ('ingreso', 'entrada', 'credito') THEN monto_usd
                        WHEN LOWER(tipo) IN ('egreso', 'salida', 'debito') THEN -monto_usd
                        ELSE 0
                    END
                ),
                0
            )
            FROM movimientos_financieros
            """,
        )

    # Prioridad 2: si hay ventas/gastos, saldo simplificado
    ventas_total = 0.0
    gastos_total = 0.0

    if _table_exists(conn, "ventas"):
        ventas_total = _safe_scalar(
            conn,
            "SELECT COALESCE(SUM(total_usd), 0) FROM ventas WHERE estado = 'registrada'",
        )
    if _table_exists(conn, "gastos"):
        gastos_total = _safe_scalar(
            conn,
            "SELECT COALESCE(SUM(monto_usd), 0) FROM gastos WHERE estado = 'activo'",
        )

    return ventas_total - gastos_total


# ============================================================
# PRESUPUESTO OPERATIVO
# ============================================================


def guardar_presupuesto_operativo(
    conn,
    *,
    periodo: str,
    categoria: str,
    tipo: str,
    monto_presupuestado_usd: float,
    meta_kpi_usd: float,
    usuario: str,
    notas: str = "",
) -> int:
    _ensure_planeacion_schema(conn)

    if tipo not in {"ingreso", "egreso"}:
        raise ValueError("El tipo debe ser 'ingreso' o 'egreso'.")

    categoria_limpia = str(categoria or "").strip()
    if not categoria_limpia:
        raise ValueError("La categoría es obligatoria.")

    cur = conn.execute(
        """
        INSERT INTO presupuesto_operativo (
            periodo,
            categoria,
            tipo,
            monto_presupuestado_usd,
            meta_kpi_usd,
            notas,
            usuario
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(periodo).strip(),
            categoria_limpia,
            tipo,
            float(monto_presupuestado_usd or 0.0),
            float(meta_kpi_usd or 0.0),
            str(notas or "").strip(),
            str(usuario or "").strip(),
        ),
    )
    return int(cur.lastrowid)


def listar_presupuesto_operativo(conn, *, periodo: str) -> pd.DataFrame:
    _ensure_planeacion_schema(conn)
    return _safe_df(
        conn,
        """
        SELECT
            id,
            periodo,
            categoria,
            tipo,
            monto_presupuestado_usd,
            meta_kpi_usd,
            notas,
            usuario,
            created_at
        FROM presupuesto_operativo
        WHERE periodo = ?
        ORDER BY tipo ASC, categoria ASC, id DESC
        """,
        (periodo,),
        [
            "id",
            "periodo",
            "categoria",
            "tipo",
            "monto_presupuestado_usd",
            "meta_kpi_usd",
            "notas",
            "usuario",
            "created_at",
        ],
    )


def resumen_presupuesto_operativo(conn, *, periodo: str) -> dict[str, float]:
    _ensure_planeacion_schema(conn)
    fecha_desde, fecha_hasta = _period_bounds(periodo)

    ingresos_presupuestados = _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(monto_presupuestado_usd), 0)
        FROM presupuesto_operativo
        WHERE periodo = ? AND tipo = 'ingreso'
        """,
        (periodo,),
    )

    egresos_presupuestados = _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(monto_presupuestado_usd), 0)
        FROM presupuesto_operativo
        WHERE periodo = ? AND tipo = 'egreso'
        """,
        (periodo,),
    )

    meta_kpi_ingresos = _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(meta_kpi_usd), 0)
        FROM presupuesto_operativo
        WHERE periodo = ? AND tipo = 'ingreso'
        """,
        (periodo,),
    )

    meta_kpi_egresos = _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(meta_kpi_usd), 0)
        FROM presupuesto_operativo
        WHERE periodo = ? AND tipo = 'egreso'
        """,
        (periodo,),
    )

    ingresos_reales = _ventas_reales_periodo(conn, fecha_desde, fecha_hasta)
    egresos_reales = _gastos_reales_periodo(conn, fecha_desde, fecha_hasta)

    desviacion_ingresos = ingresos_reales - ingresos_presupuestados
    desviacion_egresos = egresos_reales - egresos_presupuestados

    utilidad_presupuestada = ingresos_presupuestados - egresos_presupuestados
    utilidad_real = ingresos_reales - egresos_reales

    cumplimiento_ingresos_pct = (
        (ingresos_reales / ingresos_presupuestados) * 100.0
        if ingresos_presupuestados > 0
        else 0.0
    )
    ejecucion_egresos_pct = (
        (egresos_reales / egresos_presupuestados) * 100.0
        if egresos_presupuestados > 0
        else 0.0
    )

    return {
        "ingresos_presupuestados_usd": float(ingresos_presupuestados),
        "egresos_presupuestados_usd": float(egresos_presupuestados),
        "meta_kpi_ingresos_usd": float(meta_kpi_ingresos),
        "meta_kpi_egresos_usd": float(meta_kpi_egresos),
        "ingresos_reales_usd": float(ingresos_reales),
        "egresos_reales_usd": float(egresos_reales),
        "desviacion_ingresos_usd": float(desviacion_ingresos),
        "desviacion_egresos_usd": float(desviacion_egresos),
        "utilidad_presupuestada_usd": float(utilidad_presupuestada),
        "utilidad_real_usd": float(utilidad_real),
        "cumplimiento_ingresos_pct": float(cumplimiento_ingresos_pct),
        "ejecucion_egresos_pct": float(ejecucion_egresos_pct),
    }


# ============================================================
# FLUJO DE CAJA PROYECTADO
# ============================================================


def calcular_flujo_caja_proyectado(conn) -> pd.DataFrame:
    _ensure_planeacion_schema(conn)

    saldo_actual = _saldo_actual_estimado(conn)
    rows: list[dict[str, float | int | str]] = []

    for horizonte in (7, 15, 30):
        cobros = _cuentas_por_cobrar_en_horizonte(conn, horizonte)
        pagos = _cuentas_por_pagar_en_horizonte(conn, horizonte)
        flujo = saldo_actual + cobros - pagos

        rows.append(
            {
                "fecha_corte": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "horizonte_dias": int(horizonte),
                "saldo_actual_usd": float(saldo_actual),
                "cobros_esperados_usd": float(cobros),
                "pagos_proximos_usd": float(pagos),
                "flujo_proyectado_usd": float(flujo),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# ALERTAS GERENCIALES
# ============================================================


def generar_alertas_gerenciales(conn, *, periodo: str) -> pd.DataFrame:
    _ensure_planeacion_schema(conn)

    resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
    flujo = calcular_flujo_caja_proyectado(conn)

    rows: list[dict[str, Any]] = []

    flujo_30 = 0.0
    if not flujo.empty:
        f30 = flujo[flujo["horizonte_dias"] == 30]
        if not f30.empty:
            flujo_30 = float(f30.iloc[-1]["flujo_proyectado_usd"])
        else:
            flujo_30 = float(flujo.iloc[-1]["flujo_proyectado_usd"])

    desviacion_egresos = float(resumen.get("desviacion_egresos_usd", 0.0))
    desviacion_ingresos = float(resumen.get("desviacion_ingresos_usd", 0.0))
    cumplimiento_ingresos = float(resumen.get("cumplimiento_ingresos_pct", 0.0))
    ejecucion_egresos = float(resumen.get("ejecucion_egresos_pct", 0.0))
    utilidad_real = float(resumen.get("utilidad_real_usd", 0.0))

    if flujo_30 < 0:
        rows.append(
            {
                "tipo": "flujo_caja",
                "severidad": "alta",
                "indicador": "Flujo proyectado 30 días",
                "valor_usd": flujo_30,
                "mensaje": "El flujo proyectado a 30 días es negativo. Requiere acción inmediata.",
            }
        )
    else:
        rows.append(
            {
                "tipo": "flujo_caja",
                "severidad": "info",
                "indicador": "Flujo proyectado 30 días",
                "valor_usd": flujo_30,
                "mensaje": "El flujo proyectado a 30 días se mantiene positivo.",
            }
        )

    if desviacion_egresos > 0:
        rows.append(
            {
                "tipo": "presupuesto",
                "severidad": "media",
                "indicador": "Desviación de egresos",
                "valor_usd": desviacion_egresos,
                "mensaje": "Los egresos reales están por encima del presupuesto.",
            }
        )

    if desviacion_ingresos < 0:
        rows.append(
            {
                "tipo": "presupuesto",
                "severidad": "media",
                "indicador": "Desviación de ingresos",
                "valor_usd": desviacion_ingresos,
                "mensaje": "Los ingresos reales están por debajo del presupuesto.",
            }
        )

    if cumplimiento_ingresos < 80 and resumen.get("ingresos_presupuestados_usd", 0.0) > 0:
        rows.append(
            {
                "tipo": "ingresos",
                "severidad": "media",
                "indicador": "Cumplimiento de ingresos",
                "valor_usd": cumplimiento_ingresos,
                "mensaje": "El cumplimiento de ingresos está por debajo del 80% de la meta.",
            }
        )

    if ejecucion_egresos > 110 and resumen.get("egresos_presupuestados_usd", 0.0) > 0:
        rows.append(
            {
                "tipo": "egresos",
                "severidad": "alta",
                "indicador": "Ejecución de egresos",
                "valor_usd": ejecucion_egresos,
                "mensaje": "La ejecución de egresos supera el 110% del presupuesto.",
            }
        )

    if utilidad_real < 0:
        rows.append(
            {
                "tipo": "rentabilidad",
                "severidad": "alta",
                "indicador": "Utilidad real",
                "valor_usd": utilidad_real,
                "mensaje": "La utilidad real del periodo es negativa.",
            }
        )

    if not rows:
        rows.append(
            {
                "tipo": "control",
                "severidad": "info",
                "indicador": "Estado general",
                "valor_usd": 0.0,
                "mensaje": "No se detectaron alertas financieras críticas para el periodo.",
            }
        )

    return pd.DataFrame(rows)
