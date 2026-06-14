from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _read_table(table: str, order: str = "id DESC", limit: int = 500) -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return pd.DataFrame()
        try:
            return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY {order} LIMIT {int(limit)}", conn)
        except Exception:
            return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {int(limit)}", conn)


def _read_query(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _insert_provider(data: dict[str, Any]) -> None:
    with db_transaction() as conn:
        cols = _columns(conn, "proveedores")
        if not cols:
            st.error("No existe la tabla proveedores.")
            return
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        placeholders = ",".join(["?"] * len(keys))
        conn.execute(
            f"INSERT INTO proveedores ({','.join(keys)}) VALUES ({placeholders})",
            [payload[k] for k in keys],
        )


def _safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def _provider_key(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    return " ".join(text.strip().lower().split())


def _filter_provider(df: pd.DataFrame, proveedor: str, column: str = "proveedor") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    key = _provider_key(proveedor)
    return df[df[column].apply(_provider_key).eq(key)].copy()


def _add_vencimiento_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "fecha_vencimiento" not in df.columns:
        return df.copy()
    out = df.copy()
    hoy = pd.Timestamp.today().normalize()
    vencimiento = pd.to_datetime(out["fecha_vencimiento"], errors="coerce")
    out["dias_para_vencer"] = (vencimiento - hoy).dt.days
    out["estado_vencimiento"] = "Sin vencimiento"
    out.loc[vencimiento.notna() & (out["dias_para_vencer"] < 0), "estado_vencimiento"] = "Vencida"
    out.loc[vencimiento.notna() & out["dias_para_vencer"].between(0, 7, inclusive="both"), "estado_vencimiento"] = "Vence en 7 días"
    out.loc[vencimiento.notna() & (out["dias_para_vencer"] > 7), "estado_vencimiento"] = "Vigente"
    out["dias_para_vencer"] = out["dias_para_vencer"].astype("Int64")
    return out


def _get_rates() -> tuple[float, float]:
    try:
        from modules.configuracion import DEFAULT_CONFIG, get_current_config
        config = get_current_config()
        tasa_bcv_default = float(DEFAULT_CONFIG.get("tasa_bcv", 36.5))
        tasa_binance_default = float(DEFAULT_CONFIG.get("tasa_binance", 38.0))
        tasa_bcv = float(config.get("tasa_bcv", st.session_state.get("tasa_bcv", tasa_bcv_default)) or tasa_bcv_default)
        tasa_binance = float(config.get("tasa_binance", st.session_state.get("tasa_binance", tasa_binance_default)) or tasa_binance_default)
        return tasa_bcv, tasa_binance
    except Exception:
        return 36.5, 38.0


def _inventory_module():
    try:
        from modules import inventario as inv_module
        inv_module._ensure_inventory_support_tables()
        inv_module._ensure_config_defaults()
        return inv_module
    except Exception as exc:
        st.error("No se pudo cargar la función avanzada del inventario.")
        st.exception(exc)
        return None


def _render_internal(section: str, callback_name: str, *args) -> None:
    inv_module = _inventory_module()
    if inv_module is None:
        return
    callback = getattr(inv_module, callback_name, None)
    if callback is None:
        st.warning(f"La sección {section} no está disponible en el módulo interno.")
        return
    try:
        callback(*args)
    except Exception as exc:
        st.error(f"No se pudo cargar {section}.")
        st.exception(exc)


def _facturas_compra_cxp() -> pd.DataFrame:
    return _read_query(
        """
        SELECT
            id,
            proveedor,
            numero_factura,
            fecha_factura,
            fecha_vencimiento,
            total_usd,
            pagado_usd,
            pendiente_usd,
            estado,
            metodo_pago,
            tipo_pago
        FROM facturas_compra
        WHERE pendiente_usd > 0.0001 OR estado IN ('pendiente', 'parcial')
        ORDER BY proveedor, date(fecha_vencimiento), id DESC
        """
    )


def _abonos_facturas_compra() -> pd.DataFrame:
    return _read_query(
        """
        SELECT
            a.id,
            a.fecha,
            f.proveedor,
            f.numero_factura,
            a.factura_id,
            a.monto_usd,
            a.metodo_pago,
            a.referencia,
            a.notas,
            a.movimiento_tesoreria_id
        FROM abonos_facturas_compra a
        LEFT JOIN facturas_compra f ON f.id = a.factura_id
        ORDER BY a.id DESC
        LIMIT 500
        """
    )


def _resumen_cxp_por_proveedor(cxp: pd.DataFrame) -> pd.DataFrame:
    if cxp.empty:
        return pd.DataFrame()
    df = cxp.copy()
    df["proveedor"] = df["proveedor"].fillna("Proveedor N/D").astype(str)
    df["fecha_vencimiento_dt"] = pd.to_datetime(df["fecha_vencimiento"], errors="coerce")
    hoy = pd.Timestamp.today().normalize()
    df["vencida"] = df["fecha_vencimiento_dt"].notna() & (df["fecha_vencimiento_dt"] < hoy)
    df["vence_pronto"] = df["fecha_vencimiento_dt"].notna() & df["fecha_vencimiento_dt"].between(hoy, hoy + pd.Timedelta(days=7), inclusive="both")
    resumen = df.groupby("proveedor", as_index=False).agg(
        facturas_pendientes=("id", "count"),
        total_pendiente_usd=("pendiente_usd", "sum"),
        total_facturado_usd=("total_usd", "sum"),
        facturas_vencidas=("vencida", "sum"),
        vencen_7_dias=("vence_pronto", "sum"),
    )
    return resumen.sort_values("total_pendiente_usd", ascending=False)
