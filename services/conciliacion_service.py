from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from modules.common import as_positive, clean_text, money, require_text

ESTADOS_CONCILIACION = ("pendiente", "conciliado", "con_diferencia")
TIPOS_CIERRE = ("diario", "mensual")
ESTADOS_CIERRE = ("abierto", "cerrado")


def _normalize_estado_conciliacion(estado: str) -> str:
    value = clean_text(estado).lower() or "pendiente"
    if value not in ESTADOS_CONCILIACION:
        raise ValueError("Estado de conciliación inválido")
    return value


def _normalize_tipo_cierre(tipo: str) -> str:
    value = clean_text(tipo).lower() or "mensual"
    if value not in TIPOS_CIERRE:
        raise ValueError("Tipo de cierre inválido")
    return value


def _normalize_estado_cierre(estado: str) -> str:
    value = clean_text(estado).lower() or "cerrado"
    if value not in ESTADOS_CIERRE:
        raise ValueError("Estado de cierre inválido")
    return value


def registrar_movimiento_bancario(
    conn: Any,
    *,
    fecha: str,
    descripcion: str,
    monto: float,
    tipo: str,
    cuenta_bancaria: str,
    usuario: str,
    referencia_banco: str | None = None,
    origen: str = "manual",
    moneda: str = "USD",
    saldo_reportado: float | None = None,
    estado_conciliacion: str = "pendiente",
) -> int:
    tipo_normalizado = clean_text(tipo).lower()
    if tipo_normalizado not in ("ingreso", "egreso"):
        raise ValueError("Tipo bancario inválido")

    cur = conn.execute(
        """
        INSERT INTO movimientos_bancarios
        (
            fecha,
            descripcion,
            monto,
            tipo,
            cuenta_bancaria,
            referencia_banco,
            origen,
            moneda,
            saldo_reportado,
            usuario,
            estado_conciliacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            require_text(fecha, "Fecha"),
            require_text(descripcion, "Descripción"),
            money(as_positive(monto, "Monto bancario", allow_zero=False)),
            tipo_normalizado,
            require_text(cuenta_bancaria, "Cuenta bancaria"),
            clean_text(referencia_banco) or None,
            clean_text(origen).lower() or "manual",
            clean_text(moneda).upper() or "USD",
            money(as_positive(saldo_reportado, "Saldo reportado", allow_zero=True)) if saldo_reportado is not None else None,
            require_text(usuario, "Usuario"),
            _normalize_estado_conciliacion(estado_conciliacion),
        ),
    )
    return int(cur.lastrowid)


def listar_movimientos_bancarios(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado_conciliacion: str | None = None,
    cuenta_bancaria: str | None = None,
) -> pd.DataFrame:
    filters: list[str] = ["1=1"]
    params: list[Any] = []

    if clean_text(fecha_desde):
        filters.append("date(mb.fecha) >= date(?)")
        params.append(clean_text(fecha_desde))
    if clean_text(fecha_hasta):
        filters.append("date(mb.fecha) <= date(?)")
        params.append(clean_text(fecha_hasta))
    if clean_text(estado_conciliacion):
        filters.append("mb.estado_conciliacion = ?")
        params.append(_normalize_estado_conciliacion(estado_conciliacion))
    if clean_text(cuenta_bancaria):
        filters.append("mb.cuenta_bancaria = ?")
        params.append(clean_text(cuenta_bancaria))

    query = f"""
        SELECT
            mb.id,
            mb.fecha,
            mb.descripcion,
            mb.monto,
            mb.tipo,
            mb.cuenta_bancaria,
            mb.referencia_banco,
            mb.origen,
            mb.moneda,
            mb.saldo_reportado,
            mb.estado_conciliacion,
            mb.usuario,
            mb.created_at,
            cb.tesoreria_movimiento_id,
            cb.estado_resultado,
            cb.diferencia_usd,
            cb.notas,
            cb.conciliado_en
        FROM movimientos_bancarios mb
        LEFT JOIN conciliaciones_bancarias cb ON cb.banco_movimiento_id = mb.id
        WHERE {' AND '.join(filters)}
        ORDER BY date(mb.fecha) DESC, mb.id DESC
    """
    return pd.read_sql_query(query, conn, params=params)


def listar_movimientos_tesoreria_pendientes(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> pd.DataFrame:
    filters = ["t.estado = 'confirmado'", "cb.id IS NULL"]
    params: list[Any] = []

    if clean_text(fecha_desde):
        filters.append("date(t.fecha) >= date(?)")
        params.append(clean_text(fecha_desde))
    if clean_text(fecha_hasta):
        filters.append("date(t.fecha) <= date(?)")
        params.append(clean_text(fecha_hasta))

    query = f"""
        SELECT
            t.id,
            t.fecha,
            t.tipo,
            t.origen,
            t.referencia_id,
            t.descripcion,
            t.monto_usd,
            t.metodo_pago,
            t.usuario
        FROM movimientos_tesoreria t
        LEFT JOIN conciliaciones_bancarias cb ON cb.tesoreria_movimiento_id = t.id
        WHERE {' AND '.join(filters)}
        ORDER BY date(t.fecha) DESC, t.id DESC
    """
    return pd.read_sql_query(query, conn, params=params)


def sugerir_cruces(
    conn: Any,
    *,
    tolerancia_dias: int = 3,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> pd.DataFrame:
    pendientes_banco = listar_movimientos_bancarios(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado_conciliacion="pendiente",
    )
    pendientes_tes = listar_movimientos_tesoreria_pendientes(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

    if pendientes_banco.empty or pendientes_tes.empty:
        return pd.DataFrame(
            columns=[
                "banco_movimiento_id",
                "tesoreria_movimiento_id",
                "fecha_banco",
                "fecha_tesoreria",
                "tipo",
                "monto_banco",
                "monto_tesoreria",
                "diferencia_usd",
                "desfase_dias",
                "score",
            ]
        )

    banco = pendientes_banco.copy()
    banco["fecha"] = pd.to_datetime(banco["fecha"], errors="coerce")
    tes = pendientes_tes.copy()
    tes["fecha"] = pd.to_datetime(tes["fecha"], errors="coerce")

    cruces: list[dict[str, Any]] = []
    for _, b in banco.iterrows():
        candidatos = tes[tes["tipo"] == b["tipo"]].copy()
        if candidatos.empty:
            continue
        candidatos["desfase_dias"] = (candidatos["fecha"] - b["fecha"]).dt.days.abs()
        candidatos = candidatos[candidatos["desfase_dias"] <= max(int(tolerancia_dias), 0)]
        if candidatos.empty:
            continue
        candidatos["diferencia_usd"] = (candidatos["monto_usd"] - float(b["monto"]))
        candidatos["score"] = candidatos["diferencia_usd"].abs() + (candidatos["desfase_dias"] * 0.01)
        mejor = candidatos.sort_values(["score", "id"], ascending=[True, True]).iloc[0]
        cruces.append(
            {
                "banco_movimiento_id": int(b["id"]),
                "tesoreria_movimiento_id": int(mejor["id"]),
                "fecha_banco": b["fecha"].date().isoformat() if pd.notna(b["fecha"]) else None,
                "fecha_tesoreria": mejor["fecha"].date().isoformat() if pd.notna(mejor["fecha"]) else None,
                "tipo": b["tipo"],
                "monto_banco": float(b["monto"]),
                "monto_tesoreria": float(mejor["monto_usd"]),
                "diferencia_usd": float(mejor["diferencia_usd"]),
                "desfase_dias": int(mejor["desfase_dias"]),
                "score": float(mejor["score"]),
            }
        )

    return pd.DataFrame(cruces).sort_values(["score", "banco_movimiento_id"], ascending=[True, True]) if cruces else pd.DataFrame()


def conciliar_movimientos(
    conn: Any,
    *,
    banco_movimiento_id: int,
    tesoreria_movimiento_id: int,
    usuario: str,
    notas: str | None = None,
) -> int:
    banco = conn.execute(
        """
        SELECT id, tipo, monto, estado_conciliacion
        FROM movimientos_bancarios
        WHERE id = ?
        """,
        (int(banco_movimiento_id),),
    ).fetchone()
    if not banco:
        raise ValueError("Movimiento bancario no existe")

    tes = conn.execute(
        """
        SELECT id, tipo, monto_usd, estado
        FROM movimientos_tesoreria
        WHERE id = ?
        """,
        (int(tesoreria_movimiento_id),),
    ).fetchone()
    if not tes:
        raise ValueError("Movimiento de tesorería no existe")
    if clean_text(tes["estado"]).lower() != "confirmado":
        raise ValueError("Solo se concilian movimientos de tesorería confirmados")

    existente = conn.execute(
        """
        SELECT id
        FROM conciliaciones_bancarias
        WHERE banco_movimiento_id = ? OR tesoreria_movimiento_id = ?
        LIMIT 1
        """,
        (int(banco_movimiento_id), int(tesoreria_movimiento_id)),
    ).fetchone()
    if existente:
        raise ValueError("Alguno de los movimientos ya fue conciliado")

    if clean_text(banco["tipo"]).lower() != clean_text(tes["tipo"]).lower():
        raise ValueError("No se puede conciliar ingreso con egreso")

    diferencia = money(float(tes["monto_usd"]) - float(banco["monto"]))
    estado_resultado = "conciliado" if abs(diferencia) < 0.01 else "con_diferencia"

    cur = conn.execute(
        """
        INSERT INTO conciliaciones_bancarias
        (
            banco_movimiento_id,
            tesoreria_movimiento_id,
            estado_resultado,
            diferencia_usd,
            notas,
            conciliado_por,
            conciliado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(banco_movimiento_id),
            int(tesoreria_movimiento_id),
            estado_resultado,
            diferencia,
            clean_text(notas) or None,
            require_text(usuario, "Usuario"),
        ),
    )

    conn.execute(
        "UPDATE movimientos_bancarios SET estado_conciliacion=? WHERE id=?",
        (estado_resultado, int(banco_movimiento_id)),
    )
    return int(cur.lastrowid)


def obtener_resumen_conciliacion(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict[str, float]:
    banco = listar_movimientos_bancarios(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    total = int(len(banco.index))
    conciliados = int((banco["estado_conciliacion"] == "conciliado").sum()) if not banco.empty else 0
    con_diferencia = int((banco["estado_conciliacion"] == "con_diferencia").sum()) if not banco.empty else 0
    pendientes = int((banco["estado_conciliacion"] == "pendiente").sum()) if not banco.empty else 0
    diferencia_total = float(banco.loc[banco["estado_conciliacion"] == "con_diferencia", "diferencia_usd"].sum()) if not banco.empty else 0.0

    return {
        "total_banco": total,
        "conciliados": conciliados,
        "con_diferencia": con_diferencia,
        "pendientes": pendientes,
        "diferencia_total_usd": round(diferencia_total, 2),
    }


def cerrar_periodo(
    conn: Any,
    *,
    periodo: str,
    tipo_cierre: str,
    fecha_desde: str,
    fecha_hasta: str,
    usuario: str,
    notas: str | None = None,
) -> int:
    periodo_normalizado = require_text(periodo, "Periodo")
    tipo = _normalize_tipo_cierre(tipo_cierre)

    abierto = conn.execute(
        """
        SELECT id
        FROM cierres_periodo
        WHERE periodo = ? AND tipo_cierre = ? AND estado = 'cerrado'
        LIMIT 1
        """,
        (periodo_normalizado, tipo),
    ).fetchone()
    if abierto:
        raise ValueError(f"El periodo {periodo_normalizado} ({tipo}) ya está cerrado")

    resumen = obtener_resumen_cierre_periodo(conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
    cur = conn.execute(
        """
        INSERT INTO cierres_periodo
        (
            periodo,
            tipo_cierre,
            fecha_desde,
            fecha_hasta,
            total_ingresos_usd,
            total_egresos_usd,
            saldo_neto_usd,
            no_conciliados_banco,
            no_conciliados_tesoreria,
            estado,
            cerrado_por,
            cerrado_en,
            notas
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'cerrado', ?, CURRENT_TIMESTAMP, ?)
        """,
        (
            periodo_normalizado,
            tipo,
            require_text(fecha_desde, "Fecha desde"),
            require_text(fecha_hasta, "Fecha hasta"),
            float(resumen["total_ingresos_usd"]),
            float(resumen["total_egresos_usd"]),
            float(resumen["saldo_neto_usd"]),
            int(resumen["movimientos_bancarios_pendientes"]),
            int(resumen["movimientos_tesoreria_pendientes"]),
            require_text(usuario, "Usuario"),
            clean_text(notas) or None,
        ),
    )
    return int(cur.lastrowid)


def periodo_esta_cerrado(conn: Any, *, fecha_movimiento: str, tipo_cierre: str = "mensual") -> bool:
    tipo = _normalize_tipo_cierre(tipo_cierre)
    row = conn.execute(
        """
        SELECT 1
        FROM cierres_periodo
        WHERE estado='cerrado'
          AND tipo_cierre=?
          AND date(?) BETWEEN date(fecha_desde) AND date(fecha_hasta)
        LIMIT 1
        """,
        (tipo, clean_text(fecha_movimiento) or date.today().isoformat()),
    ).fetchone()
    return bool(row)


def obtener_resumen_cierre_periodo(
    conn: Any,
    *,
    fecha_desde: str,
    fecha_hasta: str,
) -> dict[str, float | int]:
    mov_tes = pd.read_sql_query(
        """
        SELECT tipo, monto_usd
        FROM movimientos_tesoreria
        WHERE estado='confirmado'
          AND date(fecha) BETWEEN date(?) AND date(?)
        """,
        conn,
        params=[fecha_desde, fecha_hasta],
    )

    ingresos = float(mov_tes.loc[mov_tes["tipo"] == "ingreso", "monto_usd"].sum()) if not mov_tes.empty else 0.0
    egresos = float(mov_tes.loc[mov_tes["tipo"] == "egreso", "monto_usd"].sum()) if not mov_tes.empty else 0.0

    pendientes_banco = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM movimientos_bancarios
        WHERE estado_conciliacion='pendiente'
          AND date(fecha) BETWEEN date(?) AND date(?)
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()
    pendientes_tes = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM movimientos_tesoreria t
        LEFT JOIN conciliaciones_bancarias c ON c.tesoreria_movimiento_id = t.id
        WHERE t.estado='confirmado'
          AND c.id IS NULL
          AND date(t.fecha) BETWEEN date(?) AND date(?)
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()

    return {
        "total_ingresos_usd": round(ingresos, 2),
        "total_egresos_usd": round(egresos, 2),
        "saldo_neto_usd": round(ingresos - egresos, 2),
        "movimientos_bancarios_pendientes": int(pendientes_banco["total"] if pendientes_banco else 0),
        "movimientos_tesoreria_pendientes": int(pendientes_tes["total"] if pendientes_tes else 0),
    }


def listar_cierres_periodo(conn: Any, *, limit: int = 50) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            id,
            periodo,
            tipo_cierre,
            fecha_desde,
            fecha_hasta,
            total_ingresos_usd,
            total_egresos_usd,
            saldo_neto_usd,
            no_conciliados_banco,
            no_conciliados_tesoreria,
            estado,
            cerrado_por,
            cerrado_en,
            notas
        FROM cierres_periodo
        ORDER BY datetime(cerrado_en) DESC, id DESC
        LIMIT ?
        """,
        conn,
        params=[max(int(limit), 1)],
    )


def obtener_reporte_fiscal_simple(
    conn: Any,
    *,
    fecha_desde: str,
    fecha_hasta: str,
) -> pd.DataFrame:
    ventas = conn.execute(
        """
        SELECT
            COUNT(*) AS facturas,
            COALESCE(SUM(subtotal_usd), 0) AS base,
            COALESCE(SUM(impuesto_usd), 0) AS impuesto,
            COALESCE(SUM(total_usd), 0) AS total
        FROM ventas
        WHERE date(fecha) BETWEEN date(?) AND date(?)
          AND estado != 'anulada'
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()

    compras = conn.execute(
        """
        SELECT
            COUNT(*) AS docs,
            COALESCE(SUM(subtotal_usd), 0) AS base,
            COALESCE(SUM(impuesto_usd), 0) AS impuesto,
            COALESCE(SUM(monto_usd), 0) AS total
        FROM gastos
        WHERE date(fecha) BETWEEN date(?) AND date(?)
          AND estado != 'anulado'
        """,
        (fecha_desde, fecha_hasta),
    ).fetchone()

    data = [
        {
            "Concepto": "Ventas gravadas",
            "Documentos": int(ventas["facturas"] if ventas else 0),
            "Base USD": float(ventas["base"] if ventas else 0.0),
            "Impuesto USD": float(ventas["impuesto"] if ventas else 0.0),
            "Total USD": float(ventas["total"] if ventas else 0.0),
        },
        {
            "Concepto": "Gastos con impuesto",
            "Documentos": int(compras["docs"] if compras else 0),
            "Base USD": float(compras["base"] if compras else 0.0),
            "Impuesto USD": float(compras["impuesto"] if compras else 0.0),
            "Total USD": float(compras["total"] if compras else 0.0),
        },
    ]
    df = pd.DataFrame(data)
    df.loc[len(df.index)] = {
        "Concepto": "Impuesto estimado neto",
        "Documentos": None,
        "Base USD": None,
        "Impuesto USD": round(float(df.iloc[0]["Impuesto USD"]) - float(df.iloc[1]["Impuesto USD"]), 2),
        "Total USD": None,
    }
    return df


def periodo_desde_fecha(fecha_ref: date | None = None, tipo_cierre: str = "mensual") -> str:
    fecha_valida = fecha_ref or date.today()
    tipo = _normalize_tipo_cierre(tipo_cierre)
    if tipo == "diario":
        return fecha_valida.isoformat()
    return fecha_valida.strftime("%Y-%m")
