from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text
from services.contabilidad_service import contabilizar_compra
from services.conciliacion_service import periodo_esta_cerrado
from services.cxp_proveedores_service import (
    CompraFinancialInput,
    crear_cuenta_por_pagar_desde_compra,
    validar_condicion_compra,
)
from services.tesoreria_service import registrar_egreso


# ============================================================
# AUXILIARES
# ============================================================

def _rate_from_label(label: str, tasa_bcv: float, tasa_binance: float) -> float:
    if "BCV" in str(label):
        return float(tasa_bcv or 1.0)
    if "Binance" in str(label):
        return float(tasa_binance or 1.0)
    return 1.0


def _slug(text: str) -> str:
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", clean_text(text).lower()).strip("-")
    return txt or "item"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _filter_df_by_query(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    txt = clean_text(query)
    if not txt or df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.contains(txt, case=False, na=False)
    return df[mask]


def _select_inventory_item(df: pd.DataFrame, label: str, key: str) -> int:
    return int(
        st.selectbox(
            label,
            df["id"].tolist(),
            format_func=lambda i: f"{df.loc[df['id'] == i, 'nombre'].iloc[0]} ({df.loc[df['id'] == i, 'sku'].iloc[0]})",
            key=key,
        )
    )


def _extract_supplier_tags(df_prov: pd.DataFrame) -> list[str]:
    tags: set[str] = set()
    if df_prov.empty or "especialidades" not in df_prov.columns:
        return []
    for txt in df_prov["especialidades"].fillna("").astype(str):
        for tag in [clean_text(x) for x in txt.split(",") if clean_text(x)]:
            tags.add(tag)
    return sorted(tags)


def _resolve_due_date_from_installments(cuotas: list[dict[str, Any]]) -> str | None:
    if not cuotas:
        return None
    fechas = []
    for cuota in cuotas:
        fecha = str(cuota.get("fecha_vencimiento") or "").strip()
        if fecha:
            fechas.append(fecha)
    return max(fechas) if fechas else None


# ============================================================
# SCHEMA / CONFIG
# ============================================================

def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                telefono TEXT,
                rif TEXT,
                contacto TEXT,
                observaciones TEXT,
                especialidades TEXT,
                activo INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        prov_cols = [r[1] for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()]
        if "especialidades" not in prov_cols:
            conn.execute("ALTER TABLE proveedores ADD COLUMN especialidades TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                inventario_id INTEGER,
                proveedor_id INTEGER,
                item TEXT,
                cantidad REAL,
                unidad TEXT,
                costo_total_usd REAL,
                costo_unit_usd REAL,
                impuestos REAL DEFAULT 0,
                delivery REAL DEFAULT 0,
                tasa_usada REAL DEFAULT 1,
                moneda_pago TEXT,
                activo INTEGER DEFAULT 1
            )
            """
        )

        compra_cols = {r[1] for r in conn.execute("PRAGMA table_info(historial_compras)").fetchall()}
        if "tipo_pago" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN tipo_pago TEXT DEFAULT 'contado'")
        if "monto_pagado_inicial_usd" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN monto_pagado_inicial_usd REAL DEFAULT 0")
        if "saldo_pendiente_usd" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN saldo_pendiente_usd REAL DEFAULT 0")
        if "fecha_vencimiento" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN fecha_vencimiento TEXT")
        if "fiscal_tipo" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN fiscal_tipo TEXT DEFAULT 'gravada'")
        if "fiscal_tasa_iva" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN fiscal_tasa_iva REAL DEFAULT 0.16")
        if "fiscal_iva_credito_usd" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN fiscal_iva_credito_usd REAL DEFAULT 0")
        if "fiscal_credito_iva_deducible" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN fiscal_credito_iva_deducible INTEGER DEFAULT 1")
        if "metodo_pago" not in compra_cols:
            conn.execute("ALTER TABLE historial_compras ADD COLUMN metodo_pago TEXT DEFAULT 'efectivo'")

        conn.execute(
            """
            UPDATE historial_compras
            SET tipo_pago = COALESCE(NULLIF(tipo_pago, ''), 'contado'),
                monto_pagado_inicial_usd = CASE
                    WHEN COALESCE(tipo_pago, 'contado') = 'contado'
                         AND COALESCE(monto_pagado_inicial_usd, 0) = 0
                        THEN COALESCE(costo_total_usd, 0)
                    ELSE COALESCE(monto_pagado_inicial_usd, 0)
                END,
                saldo_pendiente_usd = COALESCE(saldo_pendiente_usd, 0),
                fiscal_tipo = CASE
                    WHEN LOWER(COALESCE(fiscal_tipo, '')) IN ('gravada','exenta','no_sujeta') THEN LOWER(fiscal_tipo)
                    WHEN COALESCE(impuestos, 0) > 0 THEN 'gravada'
                    ELSE 'exenta'
                END,
                fiscal_tasa_iva = CASE
                    WHEN COALESCE(fiscal_tasa_iva, 0) <= 0 THEN 0.16
                    ELSE fiscal_tasa_iva
                END,
                fiscal_iva_credito_usd = CASE
                    WHEN COALESCE(fiscal_credito_iva_deducible, 1) = 1
                        THEN ROUND(COALESCE(costo_total_usd, 0) * (COALESCE(impuestos, 0) / 100.0), 4)
                    ELSE 0
                END,
                fiscal_credito_iva_deducible = CASE
                    WHEN COALESCE(fiscal_credito_iva_deducible, 1) IN (0,1)
                        THEN COALESCE(fiscal_credito_iva_deducible, 1)
                    ELSE 1
                END,
                metodo_pago = COALESCE(NULLIF(metodo_pago, ''), 'efectivo')
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cuentas_por_pagar_proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                proveedor_id INTEGER,
                compra_id INTEGER NOT NULL,
                tipo_documento TEXT NOT NULL DEFAULT 'compra',
                monto_original_usd REAL NOT NULL,
                monto_pagado_usd REAL NOT NULL DEFAULT 0,
                saldo_usd REAL NOT NULL,
                fecha_vencimiento TEXT,
                notas TEXT,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
                FOREIGN KEY (compra_id) REFERENCES historial_compras(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos_proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cuenta_por_pagar_id INTEGER NOT NULL,
                proveedor_id INTEGER,
                monto_usd REAL NOT NULL,
                moneda_pago TEXT NOT NULL DEFAULT 'USD',
                monto_moneda_pago REAL NOT NULL DEFAULT 0,
                tasa_cambio REAL NOT NULL DEFAULT 1,
                referencia TEXT,
                observaciones TEXT,
                FOREIGN KEY (cuenta_por_pagar_id) REFERENCES cuentas_por_pagar_proveedores(id),
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cuotas_compra_proveedor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                proveedor_id INTEGER,
                numero_cuota INTEGER NOT NULL,
                fecha_vencimiento TEXT NOT NULL,
                monto_base_usd REAL NOT NULL,
                impuesto_pct REAL NOT NULL DEFAULT 0,
                impuesto_usd REAL NOT NULL DEFAULT 0,
                monto_total_usd REAL NOT NULL,
                metodo_pago TEXT,
                moneda_pago TEXT NOT NULL DEFAULT 'USD',
                tasa_cambio REAL NOT NULL DEFAULT 1,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                fecha_pago TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (compra_id) REFERENCES historial_compras(id),
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventario_variantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventario_id INTEGER NOT NULL,
                color TEXT NOT NULL,
                sku_variante TEXT,
                stock_actual REAL DEFAULT 0,
                stock_minimo REAL DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_variante_unica_color
            ON inventario_variantes(inventario_id, color)
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_compra ON cuotas_compra_proveedor(compra_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_fecha ON cuotas_compra_proveedor(fecha_vencimiento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_estado ON cuotas_compra_proveedor(estado)")


def _ensure_config_defaults() -> None:
    defaults = {
        "inv_alerta_dias": 14,
        "inv_impuesto_default": 16.0,
        "inv_delivery_default": 0.0,
    }
    with db_transaction() as conn:
        for k, v in defaults.items():
            found = conn.execute("SELECT 1 FROM configuracion WHERE parametro=?", (k,)).fetchone()
            if not found:
                conn.execute("INSERT INTO configuracion(parametro, valor) VALUES(?,?)", (k, str(v)))


# ============================================================
# INPUT HELPERS
# ============================================================

def _calc_stock_by_unit_type(tipo_unidad: str) -> tuple[float, str, str]:
    if tipo_unidad == "Área (cm²)":
        c1, c2, c3 = st.columns(3)
        ancho = c1.number_input("Ancho (cm)", min_value=0.1, value=1.0, key="inv_area_ancho")
        alto = c2.number_input("Alto (cm)", min_value=0.1, value=1.0, key="inv_area_alto")
        pliegos = c3.number_input("Cantidad de pliegos", min_value=0.001, value=1.0, key="inv_area_pliegos")
        area_por_pliego = ancho * alto
        area_total = area_por_pliego * pliegos
        st.caption(f"Referencia: {area_por_pliego:,.2f} cm²/pliego | Área total: {area_total:,.2f} cm²")
        return float(pliegos), "pliegos", f"area_ref={area_por_pliego:.2f}cm2_por_pliego"

    if tipo_unidad == "Líquido (ml)":
        c1, c2 = st.columns(2)
        ml_envase = c1.number_input("ml por envase", min_value=1.0, value=100.0, key="inv_ml_envase")
        envases = c2.number_input("Cantidad de envases", min_value=0.001, value=1.0, key="inv_ml_envases")
        return float(ml_envase * envases), "ml", ""

    if tipo_unidad == "Peso (gr)":
        c1, c2 = st.columns(2)
        gr_envase = c1.number_input("gr por envase", min_value=1.0, value=100.0, key="inv_gr_envase")
        envases = c2.number_input("Cantidad de envases", min_value=0.001, value=1.0, key="inv_gr_envases")
        return float(gr_envase * envases), "gr", ""

    qty = st.number_input("Cantidad comprada", min_value=0.001, value=1.0, key="inv_qty_unidad")
    return




