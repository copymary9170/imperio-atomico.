from __future__ import annotations

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text


CATEGORIAS_PRESUPUESTO = [
    "ventas",
    "compras",
    "gastos fijos",
    "gastos variables",
    "inversion",
    "ahorro",
    "otro",
]


def ensure_presupuesto_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS presupuesto_mensual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                periodo TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'otro',
                concepto TEXT NOT NULL,
                monto_estimado_usd REAL NOT NULL DEFAULT 0,
                monto_real_usd REAL NOT NULL DEFAULT 0,
                notas TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metas_equilibrio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                periodo TEXT NOT NULL,
                gastos_fijos_usd REAL NOT NULL DEFAULT 0,
                gastos_variables_usd REAL NOT NULL DEFAULT 0,
                margen_promedio_pct REAL NOT NULL DEFAULT 40,
                ganancia_objetivo_usd REAL NOT NULL DEFAULT 0,
                notas TEXT
            )
            """
        )


def guardar_presupuesto_linea(*, usuario: str, periodo: str, categoria: str, concepto: str, monto_estimado_usd: float, monto_real_usd: float = 0.0, notas: str = "") -> int:
    ensure_presupuesto_tables()
    periodo_ok = require_text(periodo, "Periodo")
    concepto_ok = require_text(concepto, "Concepto")
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO presupuesto_mensual
            (usuario, periodo, categoria, concepto, monto_estimado_usd, monto_real_usd, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"),
                periodo_ok,
                clean_text(categoria) or "otro",
                concepto_ok,
                round(float(monto_estimado_usd or 0.0), 4),
                round(float(monto_real_usd or 0.0), 4),
                clean_text(notas),
            ),
        )
        return int(cur.lastrowid)


def listar_presupuesto(periodo: str = "") -> pd.DataFrame:
    ensure_presupuesto_tables()
    with db_transaction() as conn:
        if clean_text(periodo):
            return pd.read_sql_query(
                """
                SELECT id, fecha_creacion, periodo, categoria, concepto, monto_estimado_usd, monto_real_usd,
                       (monto_real_usd - monto_estimado_usd) AS diferencia_usd, notas
                FROM presupuesto_mensual
                WHERE periodo = ?
                ORDER BY categoria, concepto, id DESC
                """,
                conn,
                params=(clean_text(periodo),),
            )
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, periodo, categoria, concepto, monto_estimado_usd, monto_real_usd,
                   (monto_real_usd - monto_estimado_usd) AS diferencia_usd, notas
            FROM presupuesto_mensual
            ORDER BY periodo DESC, categoria, concepto, id DESC
            LIMIT 300
            """,
            conn,
        )


def resumen_presupuesto(periodo: str = "") -> dict:
    df = listar_presupuesto(periodo)
    if df.empty:
        return {
            "estimado_ingresos": 0.0,
            "estimado_egresos": 0.0,
            "real_ingresos": 0.0,
            "real_egresos": 0.0,
            "resultado_estimado": 0.0,
            "resultado_real": 0.0,
        }
    ventas = df[df["categoria"].astype(str).str.lower().eq("ventas")]
    egresos = df[~df["categoria"].astype(str).str.lower().eq("ventas")]
    estimado_ingresos = float(ventas["monto_estimado_usd"].sum())
    real_ingresos = float(ventas["monto_real_usd"].sum())
    estimado_egresos = float(egresos["monto_estimado_usd"].sum())
    real_egresos = float(egresos["monto_real_usd"].sum())
    return {
        "estimado_ingresos": round(estimado_ingresos, 4),
        "estimado_egresos": round(estimado_egresos, 4),
        "real_ingresos": round(real_ingresos, 4),
        "real_egresos": round(real_egresos, 4),
        "resultado_estimado": round(estimado_ingresos - estimado_egresos, 4),
        "resultado_real": round(real_ingresos - real_egresos, 4),
    }


def guardar_meta_equilibrio(*, usuario: str, periodo: str, gastos_fijos_usd: float, gastos_variables_usd: float, margen_promedio_pct: float, ganancia_objetivo_usd: float = 0.0, notas: str = "") -> int:
    ensure_presupuesto_tables()
    periodo_ok = require_text(periodo, "Periodo")
    margen = max(0.01, float(margen_promedio_pct or 0.0))
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO metas_equilibrio
            (usuario, periodo, gastos_fijos_usd, gastos_variables_usd, margen_promedio_pct, ganancia_objetivo_usd, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"),
                periodo_ok,
                round(float(gastos_fijos_usd or 0.0), 4),
                round(float(gastos_variables_usd or 0.0), 4),
                round(margen, 4),
                round(float(ganancia_objetivo_usd or 0.0), 4),
                clean_text(notas),
            ),
        )
        return int(cur.lastrowid)


def calcular_punto_equilibrio(gastos_fijos_usd: float, gastos_variables_usd: float, margen_promedio_pct: float, ganancia_objetivo_usd: float = 0.0) -> dict:
    fijos = max(0.0, float(gastos_fijos_usd or 0.0))
    variables = max(0.0, float(gastos_variables_usd or 0.0))
    objetivo = max(0.0, float(ganancia_objetivo_usd or 0.0))
    margen = max(0.01, float(margen_promedio_pct or 0.0)) / 100.0
    ventas_equilibrio = (fijos + variables) / margen
    ventas_meta = (fijos + variables + objetivo) / margen
    return {
        "gastos_totales_usd": round(fijos + variables, 4),
        "margen_decimal": round(margen, 6),
        "ventas_equilibrio_usd": round(ventas_equilibrio, 4),
        "ventas_meta_usd": round(ventas_meta, 4),
        "ganancia_objetivo_usd": round(objetivo, 4),
    }


def listar_metas_equilibrio(limit: int = 100) -> pd.DataFrame:
    ensure_presupuesto_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, periodo, gastos_fijos_usd, gastos_variables_usd, margen_promedio_pct, ganancia_objetivo_usd, notas
            FROM metas_equilibrio
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )
