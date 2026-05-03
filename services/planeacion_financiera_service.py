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

        CREATE UNIQUE INDEX IF NOT EXISTS uq_presupuesto_operativo_periodo_categoria_tipo
            ON presupuesto_operativo(periodo, categoria, tipo);
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


def _normalize_periodo(periodo: str) -> str:
    valor = str(periodo or "").strip()
    try:
        year, month = valor.split("-")
        year_i = int(year)
        month_i = int(month)
        if year_i < 2000 or month_i < 1 or month_i > 12:
            raise ValueError
        return f"{year_i:04d}-{month_i:02d}"
    except Exception as exc:
        raise ValueError("El período debe tener formato YYYY-MM.") from exc


def _period_bounds(periodo: str) -> tuple[str, str]:
    periodo_norm = _normalize_periodo(periodo)
    year, month = periodo_norm.split("-")
    year_i = int(year)
    month_i = int(month)

    start = date(year_i, month_i, 1)
    if month_i == 12:
        end = date(year_i + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year_i, month_i + 1, 1) - timedelta(days=1)

    return start.isoformat(), end.isoformat()


# ============================================================
# DATOS REALES (CORREGIDOS)
# ============================================================


def _ventas_reales_periodo(conn, fecha_desde: str, fecha_hasta: str) -> float:
    if not _table_exists(conn, "ventas"):
        return 0.0
    return _safe_scalar(
        conn,
        """
        SELECT COALESCE(SUM(total_usd), 0)
        FROM ventas
        WHERE estado IN ('registrado', 'registrada')
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
            SELECT COALESCE(SUM(saldo_usd), 0)
            FROM cuentas_por_cobrar
            WHERE estado IN ('pendiente', 'parcial')
              AND DATE(fecha_vencimiento) <= DATE('now', ?)
            """,
            (f"+{int(horizonte_dias)} day",),
        )

    return 0.0


def _cuentas_por_pagar_en_horizonte(conn, horizonte_dias: int) -> float:
    if _table_exists(conn, "cuentas_por_pagar_proveedores"):
        return _safe_scalar(
            conn,
            """
            SELECT COALESCE(SUM(saldo_usd), 0)
            FROM cuentas_por_pagar_proveedores
            WHERE estado IN ('pendiente', 'parcial')
              AND DATE(fecha_vencimiento) <= DATE('now', ?)
            """,
            (f"+{int(horizonte_dias)} day",),
        )

    return 0.0


def _saldo_actual_estimado(conn) -> float:
    if _table_exists(conn, "movimientos_tesoreria"):
        return _safe_scalar(
            conn,
            """
            SELECT COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(tipo) = 'ingreso' THEN monto_usd
                        WHEN LOWER(tipo) = 'egreso' THEN -monto_usd
                        ELSE 0
                    END
                ),
                0
            )
            FROM movimientos_tesoreria
            WHERE estado = 'confirmado'
            """,
        )

    return 0.0


# ============================================================
# PRESUPUESTO
# ============================================================


def resumen_presupuesto_operativo(conn, *, periodo: str) -> dict[str, float]:
    _ensure_planeacion_schema(conn)
    periodo_norm = _normalize_periodo(periodo)
    fecha_desde, fecha_hasta = _period_bounds(periodo_norm)

    ingresos_reales = _ventas_reales_periodo(conn, fecha_desde, fecha_hasta)
    egresos_reales = _gastos_reales_periodo(conn, fecha_desde, fecha_hasta)

    return {
        "ingresos_reales_usd": float(ingresos_reales),
        "egresos_reales_usd": float(egresos_reales),
        "utilidad_real_usd": float(ingresos_reales - egresos_reales),
    }


# ============================================================
# FLUJO DE CAJA
# ============================================================


def calcular_flujo_caja_proyectado(conn) -> pd.DataFrame:
    _ensure_planeacion_schema(conn)

    saldo_actual = _saldo_actual_estimado(conn)
    rows = []

    for horizonte in (7, 15, 30):
        cobros = _cuentas_por_cobrar_en_horizonte(conn, horizonte)
        pagos = _cuentas_por_pagar_en_horizonte(conn, horizonte)

        rows.append(
            {
                "horizonte_dias": horizonte,
                "saldo_actual_usd": saldo_actual,
                "cobros_esperados_usd": cobros,
                "pagos_proximos_usd": pagos,
                "flujo_proyectado_usd": saldo_actual + cobros - pagos,
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# ALERTAS / CRUD PRESUPUESTO
# ============================================================


def generar_alertas_gerenciales(conn, *, periodo: str) -> list[dict[str, str | float]]:
    resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
    flujo = calcular_flujo_caja_proyectado(conn)

    ingresos = float(resumen.get("ingresos_reales_usd", 0.0))
    egresos = float(resumen.get("egresos_reales_usd", 0.0))
    utilidad = float(resumen.get("utilidad_real_usd", 0.0))
    flujo_30 = 0.0
    if not flujo.empty and "horizonte_dias" in flujo.columns and "flujo_proyectado_usd" in flujo.columns:
        row30 = flujo[flujo["horizonte_dias"] == 30]
        if not row30.empty:
            flujo_30 = float(row30.iloc[-1]["flujo_proyectado_usd"] or 0.0)

    alertas: list[dict[str, str | float]] = []
    if ingresos <= 0:
        alertas.append({"nivel": "error", "mensaje": "No hay ingresos registrados para el período."})
    if utilidad < 0:
        alertas.append({"nivel": "error", "mensaje": "La utilidad del período es negativa."})
    if egresos > ingresos > 0:
        alertas.append({"nivel": "warning", "mensaje": "Los egresos superan a los ingresos del período."})
    if flujo_30 < 0:
        alertas.append({"nivel": "error", "mensaje": "El flujo proyectado a 30 días es negativo."})

    if not alertas:
        alertas.append({"nivel": "success", "mensaje": "Sin alertas críticas en la planeación financiera."})

    return alertas


def guardar_presupuesto_operativo(
    conn,
    *,
    periodo: str,
    categoria: str,
    tipo: str,
    monto_presupuestado_usd: float,
    meta_kpi_usd: float = 0.0,
    notas: str = "",
    usuario: str = "",

) -> int:
    _ensure_planeacion_schema(conn)
    periodo_norm = _normalize_periodo(periodo)
    tipo_norm = str(tipo).strip().lower()
    if tipo_norm not in {"ingreso", "egreso"}:
        raise ValueError("El tipo debe ser 'ingreso' o 'egreso'.")

    cur = conn.execute(
        """
        INSERT INTO presupuesto_operativo (
            periodo, categoria, tipo, monto_presupuestado_usd, meta_kpi_usd, notas, usuario
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(periodo, categoria, tipo)
        DO UPDATE SET
            monto_presupuestado_usd=excluded.monto_presupuestado_usd,
            meta_kpi_usd=excluded.meta_kpi_usd,
            notas=excluded.notas,
            usuario=excluded.usuario,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            periodo_norm,
            str(categoria or "Sin categoría").strip(),
            tipo_norm,
            float(monto_presupuestado_usd or 0.0),
            float(meta_kpi_usd or 0.0),
            str(notas or "").strip(),
            str(usuario or "").strip(),
        ),
    )
    return int(cur.lastrowid or 0)


def listar_presupuesto_operativo(conn, *, periodo: str) -> pd.DataFrame:
    _ensure_planeacion_schema(conn)
    periodo_norm = _normalize_periodo(periodo)
    return _safe_df(
        conn,
        """
        SELECT id, periodo, categoria, tipo, monto_presupuestado_usd, meta_kpi_usd, notas, usuario, created_at, updated_at
        FROM presupuesto_operativo
        WHERE periodo = ?
        ORDER BY tipo, categoria
        """,
        (periodo_norm,),
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
            "updated_at",
        ],
    )
