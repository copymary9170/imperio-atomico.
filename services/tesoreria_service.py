from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd

from modules.common import as_positive, clean_text, money, require_text


TIPOS_TESORERIA = ("ingreso", "egreso")
ORIGENES_TESORERIA = (
    "venta",
    "cobro_cliente",
    "gasto",
    "pago_proveedor",
    "compra_pago_inicial",
    "ajuste_manual",
    "cierre_caja",
)
ESTADOS_TESORERIA = ("confirmado", "anulado")


def _normalize_tipo(tipo: str) -> str:
    value = clean_text(tipo).lower()
    if value not in TIPOS_TESORERIA:
        raise ValueError("Tipo de tesorería inválido")
    return value


def _normalize_origen(origen: str) -> str:
    value = clean_text(origen).lower()
    if value not in ORIGENES_TESORERIA:
        raise ValueError("Origen de tesorería inválido")
    return value


def _normalize_estado(estado: str) -> str:
    value = clean_text(estado).lower() or "confirmado"
    if value not in ESTADOS_TESORERIA:
        raise ValueError("Estado de tesorería inválido")
    return value


def _serialize_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return bool(row)


def registrar_movimiento_tesoreria(
    conn: Any,
    *,
    tipo: str,
    origen: str,
    descripcion: str,
    monto_usd: float,
    usuario: str,
    referencia_id: int | None = None,
    fecha: str | None = None,
    moneda: str = "USD",
    monto_moneda: float | None = None,
    tasa_cambio: float = 1.0,
    metodo_pago: str = "efectivo",
    estado: str = "confirmado",
    metadata: dict[str, Any] | None = None,
    allow_duplicate: bool = False,
) -> int:
    tipo_normalizado = _normalize_tipo(tipo)
    origen_normalizado = _normalize_origen(origen)
    estado_normalizado = _normalize_estado(estado)
    descripcion_normalizada = require_text(descripcion, "Descripción")
    usuario_normalizado = require_text(usuario, "Usuario")
    monto = money(as_positive(monto_usd, "Monto tesorería", allow_zero=False))
    tasa = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    moneda_normalizada = clean_text(moneda).upper() or "USD"
    monto_moneda_normalizado = money(monto if monto_moneda is None else as_positive(monto_moneda, "Monto en moneda", allow_zero=True))
    metodo_pago_normalizado = clean_text(metodo_pago).lower() or "efectivo"
    fecha_normalizada = clean_text(fecha) or None

    if referencia_id is not None and not allow_duplicate:
        existing = conn.execute(
            """
            SELECT id
            FROM movimientos_tesoreria
            WHERE origen=? AND referencia_id=? AND tipo=? AND estado='confirmado'
            LIMIT 1
            """,
            (origen_normalizado, int(referencia_id), tipo_normalizado),
        ).fetchone()
        if existing:
            return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO movimientos_tesoreria
        (fecha, tipo, origen, referencia_id, descripcion, monto_usd, moneda, monto_moneda,
         tasa_cambio, metodo_pago, usuario, estado, metadata)
        VALUES (COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha_normalizada,
            tipo_normalizado,
            origen_normalizado,
            int(referencia_id) if referencia_id is not None else None,
            descripcion_normalizada,
            monto,
            moneda_normalizada,
            monto_moneda_normalizado,
            float(tasa),
            metodo_pago_normalizado,
            usuario_normalizado,
            estado_normalizado,
            _serialize_metadata(metadata),
        ),
    )
    return int(cur.lastrowid)


def registrar_ingreso(conn: Any, **kwargs: Any) -> int:
    return registrar_movimiento_tesoreria(conn, tipo="ingreso", **kwargs)


def registrar_egreso(conn: Any, **kwargs: Any) -> int:
    return registrar_movimiento_tesoreria(conn, tipo="egreso", **kwargs)


def listar_movimientos_tesoreria(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    tipo: str | None = None,
    origen: str | None = None,
    metodo_pago: str | None = None,
    estado: str = "confirmado",
) -> pd.DataFrame:
    filters: list[str] = ["estado = ?"]
    params: list[Any] = [_normalize_estado(estado)]

    if clean_text(fecha_desde):
        filters.append("date(fecha) >= date(?)")
        params.append(clean_text(fecha_desde))
    if clean_text(fecha_hasta):
        filters.append("date(fecha) <= date(?)")
        params.append(clean_text(fecha_hasta))
    if clean_text(tipo):
        filters.append("tipo = ?")
        params.append(_normalize_tipo(tipo))
    if clean_text(origen):
        filters.append("origen = ?")
        params.append(_normalize_origen(origen))
    if clean_text(metodo_pago):
        filters.append("metodo_pago = ?")
        params.append(clean_text(metodo_pago).lower())

    query = f"""
        SELECT
            id,
            fecha,
            tipo,
            origen,
            referencia_id,
            descripcion,
            monto_usd,
            moneda,
            monto_moneda,
            tasa_cambio,
            metodo_pago,
            usuario,
            estado,
            metadata,
            fecha_creacion
        FROM movimientos_tesoreria
        WHERE {' AND '.join(filters)}
        ORDER BY datetime(fecha) DESC, id DESC
    """
    return pd.read_sql_query(query, conn, params=params)


def obtener_resumen_tesoreria(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict[str, float]:
    movimientos = listar_movimientos_tesoreria(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    ingresos = float(movimientos.loc[movimientos["tipo"] == "ingreso", "monto_usd"].sum()) if not movimientos.empty else 0.0
    egresos = float(movimientos.loc[movimientos["tipo"] == "egreso", "monto_usd"].sum()) if not movimientos.empty else 0.0
    flujo_neto = round(ingresos - egresos, 2)

    vencimientos = listar_vencimientos(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    cxp_proximas = float(vencimientos.get("cxp_proximas", pd.DataFrame())["saldo_usd"].sum()) if not vencimientos.get("cxp_proximas", pd.DataFrame()).empty else 0.0
    cxc_pendientes = float(vencimientos.get("cxc_pendientes", pd.DataFrame())["saldo_usd"].sum()) if not vencimientos.get("cxc_pendientes", pd.DataFrame()).empty else 0.0

    return {
        "total_ingresos_usd": round(ingresos, 2),
        "total_egresos_usd": round(egresos, 2),
        "flujo_neto_usd": flujo_neto,
        "saldo_neto_periodo_usd": flujo_neto,
        "cxp_proximas_usd": round(cxp_proximas, 2),
        "cxc_pendientes_usd": round(cxc_pendientes, 2),
        "cantidad_movimientos": int(len(movimientos.index)),
    }


def listar_vencimientos(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    dias_alerta: int = 15,
) -> dict[str, pd.DataFrame]:
    hoy = date.today()
    desde = clean_text(fecha_desde) or hoy.isoformat()
    hasta = clean_text(fecha_hasta) or (hoy + timedelta(days=int(dias_alerta))).isoformat()

    if _table_exists(conn, "cuentas_por_pagar_proveedores"):
        if _table_exists(conn, "proveedores"):
            query_cxp = """
                SELECT
                    cxp.id,
                    cxp.fecha,
                    cxp.estado,
                    cxp.compra_id AS referencia_id,
                    COALESCE(p.nombre, 'Sin proveedor') AS tercero,
                    cxp.saldo_usd,
                    cxp.fecha_vencimiento,
                    'cuenta_por_pagar' AS origen
                FROM cuentas_por_pagar_proveedores cxp
                LEFT JOIN proveedores p ON p.id = cxp.proveedor_id
                WHERE cxp.estado IN ('pendiente','parcial','vencida')
                  AND COALESCE(cxp.saldo_usd, 0) > 0
                  AND cxp.fecha_vencimiento IS NOT NULL
                  AND date(cxp.fecha_vencimiento) BETWEEN date(?) AND date(?)
                ORDER BY date(cxp.fecha_vencimiento), cxp.id
            """
        else:
            query_cxp = """
                SELECT
                    cxp.id,
                    cxp.fecha,
                    cxp.estado,
                    cxp.compra_id AS referencia_id,
                    'Sin proveedor' AS tercero,
                    cxp.saldo_usd,
                    cxp.fecha_vencimiento,
                    'cuenta_por_pagar' AS origen
                FROM cuentas_por_pagar_proveedores cxp
                WHERE cxp.estado IN ('pendiente','parcial','vencida')
                  AND COALESCE(cxp.saldo_usd, 0) > 0
                  AND cxp.fecha_vencimiento IS NOT NULL
                  AND date(cxp.fecha_vencimiento) BETWEEN date(?) AND date(?)
                ORDER BY date(cxp.fecha_vencimiento), cxp.id
            """
        cxp_proximas = pd.read_sql_query(query_cxp, conn, params=[desde, hasta])
    else:
        cxp_proximas = pd.DataFrame(columns=["id", "fecha", "estado", "referencia_id", "tercero", "saldo_usd", "fecha_vencimiento", "origen"])

    if _table_exists(conn, "cuentas_por_cobrar") and _table_exists(conn, "clientes"):
        cxc_pendientes = pd.read_sql_query(
            """
            SELECT
                cxc.id,
                cxc.fecha,
                cxc.estado,
                cxc.venta_id AS referencia_id,
                COALESCE(c.nombre, 'Sin cliente') AS tercero,
                cxc.saldo_usd,
                cxc.fecha_vencimiento,
                'cuenta_por_cobrar' AS origen
            FROM cuentas_por_cobrar cxc
            LEFT JOIN clientes c ON c.id = cxc.cliente_id
            WHERE cxc.estado IN ('pendiente','parcial','vencida')
              AND COALESCE(cxc.saldo_usd, 0) > 0
            ORDER BY CASE WHEN cxc.fecha_vencimiento IS NULL THEN 1 ELSE 0 END, date(cxc.fecha_vencimiento), cxc.id
            """,
            conn,
        )
    else:
        cxc_pendientes = pd.DataFrame(columns=["id", "fecha", "estado", "referencia_id", "tercero", "saldo_usd", "fecha_vencimiento", "origen"])

    return {
        "cxp_proximas": cxp_proximas,
        "cxc_pendientes": cxc_pendientes,
    }
