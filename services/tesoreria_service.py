from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from modules.common import as_positive, clean_text, money, require_text


TIPOS_TESORERIA = ("ingreso", "egreso")
ORIGENES_TESORERIA = (
    "venta",
    "cobro_cliente",
    "gasto",
    "pago_proveedor",
    "compra_inicial_pagada",
    "ajuste_manual",
    "cierre_caja",
)
ESTADOS_TESORERIA = ("confirmado", "cancelado")


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


def _get_table_columns(conn: Any, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row[1]) for row in rows}
    except Exception:
        return set()


def _pick_first_existing(columns: set[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _safe_read_sql(query: str, conn: Any, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    try:
        return pd.read_sql_query(query, conn, params=params or [])
    except Exception:
        return pd.DataFrame()


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
    monto_moneda_normalizado = money(
        monto if monto_moneda is None else as_positive(monto_moneda, "Monto en moneda", allow_zero=True)
    )
    metodo_pago_normalizado = clean_text(metodo_pago).lower() or "efectivo"
    fecha_normalizada = clean_text(fecha) or None
    fecha_control = fecha_normalizada or datetime.now().date().isoformat()

    from services.conciliacion_service import periodo_esta_cerrado

    if periodo_esta_cerrado(conn, fecha_movimiento=fecha_control, tipo_cierre="mensual"):
        raise ValueError(f"El período mensual de la fecha {fecha_control} está cerrado")

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
        (
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
            metadata
        )
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

    ingresos = (
        float(movimientos.loc[movimientos["tipo"] == "ingreso", "monto_usd"].sum())
        if not movimientos.empty
        else 0.0
    )
    egresos = (
        float(movimientos.loc[movimientos["tipo"] == "egreso", "monto_usd"].sum())
        if not movimientos.empty
        else 0.0
    )
    flujo_neto = round(ingresos - egresos, 2)

    saldos_metodo = obtener_saldos_por_metodo(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    saldo_por_cuentas = float(saldos_metodo["saldo_neto_usd"].sum()) if not saldos_metodo.empty else 0.0

    vencimientos = listar_vencimientos(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    cxp_df = vencimientos.get("cxp_proximas", pd.DataFrame())
    cxc_df = vencimientos.get("cxc_pendientes", pd.DataFrame())

    cxp_proximas = float(cxp_df["saldo_usd"].sum()) if not cxp_df.empty and "saldo_usd" in cxp_df.columns else 0.0
    cxc_pendientes = float(cxc_df["saldo_usd"].sum()) if not cxc_df.empty and "saldo_usd" in cxc_df.columns else 0.0

    return {
        "total_ingresos_usd": round(ingresos, 2),
        "total_egresos_usd": round(egresos, 2),
        "flujo_neto_usd": flujo_neto,
        "saldo_neto_periodo_usd": flujo_neto,
        "saldo_por_cuentas_usd": round(saldo_por_cuentas, 2),
        "cxp_proximas_usd": round(cxp_proximas, 2),
        "cxc_pendientes_usd": round(cxc_pendientes, 2),
        "cantidad_movimientos": int(len(movimientos.index)),
    }


def obtener_saldos_por_metodo(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado: str = "confirmado",
) -> pd.DataFrame:
    movimientos = listar_movimientos_tesoreria(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado=estado,
    )

    if movimientos.empty:
        return pd.DataFrame(columns=["metodo_pago", "ingresos_usd", "egresos_usd", "saldo_neto_usd"])

    df = movimientos.copy()
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir").astype(str)
    df["tipo"] = df["tipo"].fillna("").astype(str).str.lower()
    df["monto_usd"] = pd.to_numeric(df["monto_usd"], errors="coerce").fillna(0.0)

    resumen = (
        df.groupby(["metodo_pago", "tipo"], as_index=False)["monto_usd"]
        .sum()
        .pivot_table(index="metodo_pago", columns="tipo", values="monto_usd", aggfunc="sum", fill_value=0.0)
        .reset_index()
    )

    if "ingreso" not in resumen.columns:
        resumen["ingreso"] = 0.0
    if "egreso" not in resumen.columns:
        resumen["egreso"] = 0.0

    resumen = resumen.rename(
        columns={
            "ingreso": "ingresos_usd",
            "egreso": "egresos_usd",
        }
    )
    resumen["saldo_neto_usd"] = resumen["ingresos_usd"] - resumen["egresos_usd"]
    return resumen.sort_values("saldo_neto_usd", ascending=False).reset_index(drop=True)


def obtener_resumen_por_origen(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado: str = "confirmado",
) -> pd.DataFrame:
    movimientos = listar_movimientos_tesoreria(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado=estado,
    )

    if movimientos.empty:
        return pd.DataFrame(columns=["origen", "ingreso", "egreso", "flujo_neto"])

    df = movimientos.copy()
    df["origen"] = df["origen"].fillna("sin definir").astype(str)
    df["tipo"] = df["tipo"].fillna("").astype(str).str.lower()
    df["monto_usd"] = pd.to_numeric(df["monto_usd"], errors="coerce").fillna(0.0)

    resumen = (
        df.groupby(["origen", "tipo"], as_index=False)["monto_usd"]
        .sum()
        .pivot_table(index="origen", columns="tipo", values="monto_usd", aggfunc="sum", fill_value=0.0)
        .reset_index()
    )

    if "ingreso" not in resumen.columns:
        resumen["ingreso"] = 0.0
    if "egreso" not in resumen.columns:
        resumen["egreso"] = 0.0

    resumen["flujo_neto"] = resumen["ingreso"] - resumen["egreso"]
    return resumen.sort_values("flujo_neto", ascending=False).reset_index(drop=True)


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

    cxp_proximas = pd.DataFrame(
        columns=[
            "id",
            "fecha",
            "estado",
            "referencia_id",
            "tercero",
            "saldo_usd",
            "fecha_vencimiento",
            "origen",
        ]
    )
    cxc_pendientes = pd.DataFrame(
        columns=[
            "id",
            "fecha",
            "estado",
            "referencia_id",
            "tercero",
            "saldo_usd",
            "fecha_vencimiento",
            "origen",
        ]
    )

    if _table_exists(conn, "cuentas_por_pagar_proveedores"):
        cxp_cols = _get_table_columns(conn, "cuentas_por_pagar_proveedores")
        proveedor_cols = _get_table_columns(conn, "proveedores") if _table_exists(conn, "proveedores") else set()

        compra_col = _pick_first_existing(cxp_cols, "compra_id", "referencia_id")
        proveedor_fk_col = _pick_first_existing(cxp_cols, "proveedor_id")
        saldo_col = _pick_first_existing(cxp_cols, "saldo_usd")
        fecha_venc_col = _pick_first_existing(cxp_cols, "fecha_vencimiento")
        estado_col = _pick_first_existing(cxp_cols, "estado")
        fecha_col = _pick_first_existing(cxp_cols, "fecha")
        proveedor_nombre_col = _pick_first_existing(proveedor_cols, "nombre")

        if compra_col and saldo_col and fecha_venc_col and estado_col and fecha_col:
            if proveedor_fk_col and proveedor_nombre_col:
                query_cxp = f"""
                    SELECT
                        cxp.id,
                        cxp.{fecha_col} AS fecha,
                        cxp.{estado_col} AS estado,
                        cxp.{compra_col} AS referencia_id,
                        COALESCE(p.{proveedor_nombre_col}, 'Sin proveedor') AS tercero,
                        cxp.{saldo_col} AS saldo_usd,
                        cxp.{fecha_venc_col} AS fecha_vencimiento,
                        'cuenta_por_pagar' AS origen
                    FROM cuentas_por_pagar_proveedores cxp
                    LEFT JOIN proveedores p ON p.id = cxp.{proveedor_fk_col}
                    WHERE cxp.{estado_col} IN ('pendiente','parcial','vencida')
                      AND COALESCE(cxp.{saldo_col}, 0) > 0
                      AND cxp.{fecha_venc_col} IS NOT NULL
                      AND date(cxp.{fecha_venc_col}) BETWEEN date(?) AND date(?)
                    ORDER BY date(cxp.{fecha_venc_col}), cxp.id
                """
            else:
                query_cxp = f"""
                    SELECT
                        cxp.id,
                        cxp.{fecha_col} AS fecha,
                        cxp.{estado_col} AS estado,
                        cxp.{compra_col} AS referencia_id,
                        'Sin proveedor' AS tercero,
                        cxp.{saldo_col} AS saldo_usd,
                        cxp.{fecha_venc_col} AS fecha_vencimiento,
                        'cuenta_por_pagar' AS origen
                    FROM cuentas_por_pagar_proveedores cxp
                    WHERE cxp.{estado_col} IN ('pendiente','parcial','vencida')
                      AND COALESCE(cxp.{saldo_col}, 0) > 0
                      AND cxp.{fecha_venc_col} IS NOT NULL
                      AND date(cxp.{fecha_venc_col}) BETWEEN date(?) AND date(?)
                    ORDER BY date(cxp.{fecha_venc_col}), cxp.id
                """
            cxp_proximas = _safe_read_sql(query_cxp, conn, [desde, hasta])

    if _table_exists(conn, "cuentas_por_cobrar"):
        cxc_cols = _get_table_columns(conn, "cuentas_por_cobrar")
        cliente_cols = _get_table_columns(conn, "clientes") if _table_exists(conn, "clientes") else set()

        venta_col = _pick_first_existing(cxc_cols, "venta_id", "referencia_id")
        cliente_fk_col = _pick_first_existing(cxc_cols, "cliente_id")
        saldo_col = _pick_first_existing(cxc_cols, "saldo_usd")
        fecha_venc_col = _pick_first_existing(cxc_cols, "fecha_vencimiento")
        estado_col = _pick_first_existing(cxc_cols, "estado")
        fecha_col = _pick_first_existing(cxc_cols, "fecha")
        cliente_nombre_col = _pick_first_existing(cliente_cols, "nombre")

        if venta_col and saldo_col and fecha_venc_col and estado_col and fecha_col:
            if cliente_fk_col and cliente_nombre_col:
                query_cxc = f"""
                    SELECT
                        cxc.id,
                        cxc.{fecha_col} AS fecha,
                        cxc.{estado_col} AS estado,
                        cxc.{venta_col} AS referencia_id,
                        COALESCE(c.{cliente_nombre_col}, 'Sin cliente') AS tercero,
                        cxc.{saldo_col} AS saldo_usd,
                        cxc.{fecha_venc_col} AS fecha_vencimiento,
                        'cuenta_por_cobrar' AS origen
                    FROM cuentas_por_cobrar cxc
                    LEFT JOIN clientes c ON c.id = cxc.{cliente_fk_col}
                    WHERE cxc.{estado_col} IN ('pendiente','parcial','vencida')
                      AND COALESCE(cxc.{saldo_col}, 0) > 0
                    ORDER BY
                        CASE WHEN cxc.{fecha_venc_col} IS NULL THEN 1 ELSE 0 END,
                        date(cxc.{fecha_venc_col}),
                        cxc.id
                """
            else:
                query_cxc = f"""
                    SELECT
                        cxc.id,
                        cxc.{fecha_col} AS fecha,
                        cxc.{estado_col} AS estado,
                        cxc.{venta_col} AS referencia_id,
                        'Sin cliente' AS tercero,
                        cxc.{saldo_col} AS saldo_usd,
                        cxc.{fecha_venc_col} AS fecha_vencimiento,
                        'cuenta_por_cobrar' AS origen
                    FROM cuentas_por_cobrar cxc
                    WHERE cxc.{estado_col} IN ('pendiente','parcial','vencida')
                      AND COALESCE(cxc.{saldo_col}, 0) > 0
                    ORDER BY
                        CASE WHEN cxc.{fecha_venc_col} IS NULL THEN 1 ELSE 0 END,
                        date(cxc.{fecha_venc_col}),
                        cxc.id
                """
            cxc_pendientes = _safe_read_sql(query_cxc, conn)

    return {
        "cxp_proximas": cxp_proximas,
        "cxc_pendientes": cxc_pendientes,
    }


def proyectar_flujo_tesoreria(
    conn: Any,
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    dias_alerta: int = 15,
) -> pd.DataFrame:
    resumen = obtener_resumen_tesoreria(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    saldo_base = float(resumen.get("saldo_neto_periodo_usd", 0.0))

    vencimientos = listar_vencimientos(
        conn,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        dias_alerta=dias_alerta,
    )

    cxp = vencimientos.get("cxp_proximas", pd.DataFrame()).copy()
    cxc = vencimientos.get("cxc_pendientes", pd.DataFrame()).copy()

    frames: list[pd.DataFrame] = []

    if not cxc.empty and "fecha_vencimiento" in cxc.columns and "saldo_usd" in cxc.columns:
        cxc["fecha"] = pd.to_datetime(cxc["fecha_vencimiento"], errors="coerce")
        cxc["monto_usd"] = pd.to_numeric(cxc["saldo_usd"], errors="coerce").fillna(0.0)
        cxc["tipo"] = "ingreso_esperado"
        cxc["impacto_usd"] = cxc["monto_usd"]
        frames.append(cxc[["fecha", "tipo", "monto_usd", "impacto_usd"]])

    if not cxp.empty and "fecha_vencimiento" in cxp.columns and "saldo_usd" in cxp.columns:
        cxp["fecha"] = pd.to_datetime(cxp["fecha_vencimiento"], errors="coerce")
        cxp["monto_usd"] = pd.to_numeric(cxp["saldo_usd"], errors="coerce").fillna(0.0)
        cxp["tipo"] = "egreso_programado"
        cxp["impacto_usd"] = -cxp["monto_usd"]
        frames.append(cxp[["fecha", "tipo", "monto_usd", "impacto_usd"]])

    if not frames:
        return pd.DataFrame(columns=["fecha", "tipo", "monto_usd", "impacto_usd", "saldo_proyectado_usd"])

    proy = pd.concat(frames, ignore_index=True)
    proy = proy.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    proy["saldo_proyectado_usd"] = saldo_base + proy["impacto_usd"].cumsum()
    return proy
