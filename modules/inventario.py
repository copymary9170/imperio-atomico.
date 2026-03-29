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


def _resolve_delivery_usd(
    delivery_monto: float,
    delivery_moneda: str,
    tasa_bcv: float,
    tasa_binance: float,
    manual: bool,
) -> tuple[float, float]:
    auto = _rate_from_label(delivery_moneda, tasa_bcv, tasa_binance)
    tasa = auto
    if manual:
        tasa = st.number_input(
            "Tasa usada en delivery",
            min_value=0.0001,
            value=float(auto),
            format="%.4f",
            key="inv_tasa_delivery_manual",
        )
    delivery_usd = float(delivery_monto) / max(float(tasa), 0.0001)
    return float(delivery_usd), float(tasa)


def _build_unique_sku(conn, desired: str) -> str:
    base = _slug(desired)
    sku = base
    i = 1
    while conn.execute("SELECT 1 FROM inventario WHERE sku=?", (sku,)).fetchone():
        i += 1
        sku = f"{base}-{i}"
    return sku


def _build_unique_variant_sku(conn, inventario_id: int, color: str, sku_base: str | None = None) -> str:
    color_slug = _slug(color)
    if sku_base:
        base = f"{_slug(sku_base)}-{color_slug}"
    else:
        row = conn.execute("SELECT sku FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
        parent_sku = str(row["sku"]) if row and row["sku"] else f"prod-{inventario_id}"
        base = f"{_slug(parent_sku)}-{color_slug}"

    sku_var = base
    i = 1
    while conn.execute("SELECT 1 FROM inventario_variantes WHERE sku_variante=?", (sku_var,)).fetchone():
        i += 1
        sku_var = f"{base}-{i}"
    return sku_var


def _get_or_create_provider(conn, proveedor_nombre: str) -> int | None:
    name = clean_text(proveedor_nombre)
    if not name:
        return None
    row = conn.execute(
        "SELECT id FROM proveedores WHERE nombre=? AND COALESCE(activo,1)=1",
        (name,),
    ).fetchone()
    if row:
        return int(row["id"])
    conn.execute("INSERT INTO proveedores(nombre, activo) VALUES(?,1)", (name,))
    new_row = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (name,)).fetchone()
    return int(new_row["id"]) if new_row else None


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

        cols_var = {r[1] for r in conn.execute("PRAGMA table_info(inventario_variantes)").fetchall()}
        if "sku_variante" not in cols_var:
            conn.execute("ALTER TABLE inventario_variantes ADD COLUMN sku_variante TEXT")

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
# PRODUCTOS Y MOVIMIENTOS
# ============================================================

def create_producto(
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    unidad: str,
    costo: float,
    precio: float,
    stock_inicial: float = 0.0,
    stock_minimo: float = 0.0,
) -> int:
    sku = require_text(sku, "SKU")
    nombre = require_text(nombre, "Producto")
    categoria = require_text(categoria, "Categoría")
    unidad = require_text(unidad, "Unidad")

    costo = as_positive(costo, "Costo")
    precio = as_positive(precio, "Precio")
    stock_inicial = as_positive(stock_inicial, "Stock inicial")
    stock_minimo = as_positive(stock_minimo, "Stock mínimo")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO inventario (
                usuario, sku, nombre, categoria, unidad,
                stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                stock_inicial,
                stock_minimo,
                money(costo),
                money(precio),
            ),
        )
        return int(cur.lastrowid)


def add_inventory_movement(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float = 0.0,
    referencia: str = "",
) -> int:
    tipo_normalizado = clean_text(tipo).lower() or "ajuste"
    if tipo_normalizado not in {"entrada", "salida", "ajuste"}:
        raise ValueError("Tipo de movimiento inválido. Usa: entrada, salida o ajuste.")

    qty = float(cantidad or 0.0)
    if tipo_normalizado == "entrada":
        qty = abs(qty)
    elif tipo_normalizado == "salida":
        qty = -abs(qty)

    if qty == 0:
        raise ValueError("La cantidad del movimiento debe ser distinta de cero.")

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT stock_actual, costo_unitario_usd FROM inventario WHERE id=?",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("El ítem de inventario no existe.")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nuevo_stock = stock_actual + qty
        if nuevo_stock < 0:
            raise ValueError("El ajuste deja el inventario en negativo.")

        costo_mov = float(costo_unitario_usd if costo_unitario_usd is not None else costo_actual)

        conn.execute(
            """
            INSERT INTO movimientos_inventario(
                usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                require_text(usuario, "Usuario"),
                int(inventario_id),
                tipo_normalizado,
                float(qty),
                max(0.0, float(costo_mov or 0.0)),
                str(referencia or "").strip(),
            ),
        )

        conn.execute(
            "UPDATE inventario SET stock_actual=? WHERE id=?",
            (
                float(nuevo_stock),
                int(inventario_id),
            ),
        )

        mov_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return int(mov_id)


def registrar_compra(
    usuario: str,
    inventario_id: int,
    cantidad: float,
    costo_total_usd: float,
    proveedor_id: int | None,
    proveedor_nombre: str,
    impuestos_pct: float,
    delivery_usd: float,
    tasa_usada: float,
    moneda_pago: str,
    metodo_pago: str,
    referencia_extra: str = "",
    financial_input: CompraFinancialInput | None = None,
) -> int:
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_total_usd = as_positive(costo_total_usd, "Costo total", allow_zero=False)
    costo_unit = costo_total_usd / cantidad
    financial_input = financial_input or CompraFinancialInput()

    monto_pagado_inicial_usd, saldo_pendiente_usd = validar_condicion_compra(
        total_compra_usd=float(costo_total_usd),
        tipo_pago=financial_input.tipo_pago,
        monto_pagado_inicial_usd=financial_input.monto_pagado_inicial_usd,
        fecha_vencimiento=financial_input.fecha_vencimiento,
    )

    with db_transaction() as conn:
        if periodo_esta_cerrado(conn, fecha_movimiento=date.today().isoformat(), tipo_cierre="mensual"):
            raise ValueError("Periodo mensual cerrado: no se permiten nuevas compras en esta fecha.")

        row = conn.execute(
            "SELECT nombre, unidad, stock_actual, costo_unitario_usd FROM inventario WHERE id=? AND COALESCE(estado,'activo')='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Producto no encontrado")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nueva_cantidad = stock_actual + cantidad
        costo_promedio = (
            ((stock_actual * costo_actual) + (cantidad * costo_unit)) / nueva_cantidad
            if nueva_cantidad > 0
            else costo_unit
        )

        conn.execute(
            "UPDATE inventario SET costo_unitario_usd=? WHERE id=?",
            (money(costo_promedio), int(inventario_id)),
        )

        ref = f"Compra proveedor: {proveedor_nombre or 'N/A'}"
        if referencia_extra:
            ref = f"{ref} | {referencia_extra}"

        conn.execute(
            """
            INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                int(inventario_id),
                "entrada",
                float(cantidad),
                money(costo_unit),
                ref,
            ),
        )
        conn.execute(
            "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
            (float(cantidad), int(inventario_id)),
        )

        cur_hist = conn.execute(
            """
            INSERT INTO historial_compras
            (
                usuario, inventario_id, proveedor_id, item, cantidad, unidad, costo_total_usd, costo_unit_usd,
                impuestos, delivery, tasa_usada, moneda_pago, tipo_pago, monto_pagado_inicial_usd,
                saldo_pendiente_usd, fecha_vencimiento, fiscal_tipo, fiscal_tasa_iva, fiscal_iva_credito_usd,
                fiscal_credito_iva_deducible, metodo_pago, activo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                usuario,
                int(inventario_id),
                int(proveedor_id) if proveedor_id is not None else None,
                str(row["nombre"]),
                float(cantidad),
                str(row["unidad"]),
                money(costo_total_usd),
                money(costo_unit),
                float(impuestos_pct),
                money(delivery_usd),
                float(tasa_usada),
                str(moneda_pago),
                clean_text(financial_input.tipo_pago).lower(),
                money(monto_pagado_inicial_usd),
                money(saldo_pendiente_usd),
                financial_input.fecha_vencimiento,
                "gravada" if float(impuestos_pct or 0) > 0 else "exenta",
                0.16,
                round(float(costo_total_usd) * (float(impuestos_pct or 0) / 100.0), 4),
                1,
                clean_text(metodo_pago).lower() or "efectivo",
            ),
        )
        compra_id = int(cur_hist.lastrowid)

        if monto_pagado_inicial_usd > 0:
            registrar_egreso(
                conn,
                origen="compra_pago_inicial",
                referencia_id=compra_id,
                descripcion=f"Pago inicial compra #{compra_id} · {row['nombre']}",
                monto_usd=float(monto_pagado_inicial_usd),
                moneda=str(moneda_pago),
                monto_moneda=float(
                    monto_pagado_inicial_usd
                    if str(moneda_pago).upper() == "USD"
                    else costo_total_usd
                    * (monto_pagado_inicial_usd / max(float(costo_total_usd), 0.0001))
                    * float(tasa_usada)
                ),
                tasa_cambio=float(tasa_usada or 1.0),
                metodo_pago=clean_text(metodo_pago).lower() or str(moneda_pago).lower(),
                usuario=usuario,
                metadata={
                    "modulo": "inventario",
                    "tipo_pago_compra": clean_text(financial_input.tipo_pago).lower(),
                    "proveedor_id": int(proveedor_id) if proveedor_id is not None else None,
                },
            )

        crear_cuenta_por_pagar_desde_compra(
            conn,
            usuario=usuario,
            compra_id=compra_id,
            proveedor_id=proveedor_id,
            total_compra_usd=float(costo_total_usd),
            financial_input=financial_input,
        )
        contabilizar_compra(conn, compra_id=compra_id, usuario=usuario)
        return compra_id


def _save_installments(
    compra_id: int,
    proveedor_id: int | None,
    cuotas: list[dict[str, Any]],
) -> None:
    if not cuotas:
        return

    with db_transaction() as conn:
        for cuota in cuotas:
            conn.execute(
                """
                INSERT INTO cuotas_compra_proveedor (
                    compra_id, proveedor_id, numero_cuota, fecha_vencimiento,
                    monto_base_usd, impuesto_pct, impuesto_usd, monto_total_usd,
                    metodo_pago, moneda_pago, tasa_cambio, estado
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente')
                """,
                (
                    int(compra_id),
                    int(proveedor_id) if proveedor_id is not None else None,
                    int(cuota["numero_cuota"]),
                    str(cuota["fecha_vencimiento"]),
                    float(cuota["monto_base_usd"]),
                    float(cuota["impuesto_pct"]),
                    float(cuota["impuesto_usd"]),
                    float(cuota["monto_total_usd"]),
                    str(cuota["metodo_pago"]),
                    str(cuota["moneda_pago"]),
                    float(cuota["tasa_cambio"]),
                ),
            )


def _create_inventory_item_for_purchase(
    usuario: str,
    sku_base: str,
    nombre: str,
    categoria: str,
    unidad: str,
    minimo: float,
    costo_inicial: float,
    precio_inicial: float,
) -> int:
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id FROM inventario WHERE nombre=? AND COALESCE(estado,'activo')='activo'",
            (clean_text(nombre),),
        ).fetchone()
        if row:
            return int(row["id"])

        desired_sku = sku_base if clean_text(sku_base) else nombre
        sku = _build_unique_sku(conn, desired_sku)
        cur = conn.execute(
            """
            INSERT INTO inventario(
                usuario, sku, nombre, categoria, unidad,
                stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd, estado
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'activo')
            """,
            (
                usuario,
                sku,
                clean_text(nombre),
                clean_text(categoria) or "General",
                clean_text(unidad) or "unidad",
                float(minimo or 0.0),
                money(costo_inicial),
                money(precio_inicial),
            ),
        )
        return int(cur.lastrowid)


def _create_variant(
    inventario_id: int,
    color: str,
    sku_variante: str = "",
    stock_actual: float = 0.0,
    stock_minimo: float = 0.0,
) -> int:
    color_norm = require_text(color, "Color")
    with db_transaction() as conn:
        exists = conn.execute(
            """
            SELECT id
            FROM inventario_variantes
            WHERE inventario_id=? AND lower(color)=lower(?) AND COALESCE(activo,1)=1
            """,
            (int(inventario_id), color_norm),
        ).fetchone()
        if exists:
            raise ValueError("Ya existe una variante con ese color para este producto.")

        sku_final = clean_text(sku_variante)
        if not sku_final:
            sku_final = _build_unique_variant_sku(conn, int(inventario_id), color_norm)

        cur = conn.execute(
            """
            INSERT INTO inventario_variantes(
                inventario_id, color, sku_variante, stock_actual, stock_minimo, activo
            )
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                int(inventario_id),
                color_norm,
                sku_final,
                float(stock_actual or 0.0),
                float(stock_minimo or 0.0),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# DATA LOADERS
# ============================================================

def _load_inventory_df() -> pd.DataFrame:
    cols = [
        "id",
        "fecha",
        "sku",
        "nombre",
        "categoria",
        "unidad",
        "stock_actual",
        "stock_minimo",
        "costo_unitario_usd",
        "precio_venta_usd",
        "valor_stock",
    ]
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, fecha, sku, nombre, categoria, unidad, stock_actual, stock_minimo,
                   costo_unitario_usd, precio_venta_usd,
                   (stock_actual * costo_unitario_usd) AS valor_stock
            FROM inventario
            WHERE COALESCE(estado,'activo')='activo'
            ORDER BY nombre ASC
            """
        ).fetchall()
    return pd.DataFrame(rows, columns=cols)


def _load_variantes_df(inventario_id: int | None = None) -> pd.DataFrame:
    params: tuple[Any, ...] = ()
    sql = """
        SELECT
            v.id,
            v.inventario_id,
            i.sku AS sku_base,
            i.nombre AS producto,
            v.color,
            COALESCE(v.sku_variante, '') AS sku_variante,
            COALESCE(v.stock_actual, 0) AS stock_actual,
            COALESCE(v.stock_minimo, 0) AS stock_minimo,
            COALESCE(i.unidad, 'unidad') AS unidad,
            COALESCE(i.costo_unitario_usd, 0) AS costo_unitario_usd,
            COALESCE(i.precio_venta_usd, 0) AS precio_venta_usd
        FROM inventario_variantes v
        JOIN inventario i ON i.id = v.inventario_id
        WHERE COALESCE(v.activo,1)=1
          AND COALESCE(i.estado,'activo')='activo'
    """
    if inventario_id is not None:
        sql += " AND v.inventario_id=?"
        params = (int(inventario_id),)
    sql += " ORDER BY i.nombre ASC, v.color ASC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    cols = [
        "id",
        "inventario_id",
        "sku_base",
        "producto",
        "color",
        "sku_variante",
        "stock_actual",
        "stock_minimo",
        "unidad",
        "costo_unitario_usd",
        "precio_venta_usd",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_movements_df(limit: int = 1000) -> pd.DataFrame:
    cols = [
        "id",
        "fecha",
        "usuario",
        "sku",
        "nombre",
        "tipo",
        "cantidad",
        "costo_unitario_usd",
        "costo_total_usd",
        "referencia",
    ]
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.fecha, m.usuario, i.sku, i.nombre, m.tipo, m.cantidad,
                   m.costo_unitario_usd, (ABS(m.cantidad) * m.costo_unitario_usd) AS costo_total_usd,
                   m.referencia
            FROM movimientos_inventario m
            JOIN inventario i ON i.id = m.inventario_id
            WHERE COALESCE(m.estado,'activo')='activo'
            ORDER BY m.fecha DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return pd.DataFrame(rows, columns=cols)


def _load_diagnostico_movimientos(limit: int = 20) -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT m.fecha, i.nombre AS insumo, m.cantidad, i.unidad, m.referencia
            FROM movimientos_inventario m
            JOIN inventario i ON i.id = m.inventario_id
            WHERE COALESCE(m.estado,'activo')='activo'
              AND lower(COALESCE(m.referencia, '')) LIKE '%diagnóstico ia%'
            ORDER BY m.fecha DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return pd.DataFrame(rows, columns=["fecha", "insumo", "cantidad", "unidad", "referencia"])


def _load_proveedores_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, nombre, telefono, rif, contacto, observaciones,
                   COALESCE(especialidades,'') AS especialidades, fecha_creacion
            FROM proveedores
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre ASC
            """
        ).fetchall()

    cols = [
        "id",
        "nombre",
        "telefono",
        "rif",
        "contacto",
        "observaciones",
        "especialidades",
        "fecha_creacion",
    ]
    df = pd.DataFrame(rows, columns=cols)

    if list(df.columns) != cols:
        if df.shape[1] == len(cols):
            df.columns = cols
        else:
            df = df.reindex(columns=cols)

    return df


def _load_cuentas_por_pagar_df() -> pd.DataFrame:
    _ensure_inventory_support_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                cxp.id,
                cxp.compra_id,
                COALESCE(p.nombre, 'Proveedor sin nombre') AS proveedor,
                COALESCE(hc.item, '') AS item,
                CASE
                    WHEN COALESCE(cxp.saldo_usd,0) <= 0 THEN 'pagada'
                    WHEN cxp.fecha_vencimiento IS NOT NULL AND DATE(cxp.fecha_vencimiento) < DATE('now') THEN 'vencida'
                    ELSE COALESCE(cxp.estado,'pendiente')
                END AS estado,
                cxp.fecha_vencimiento,
                cxp.monto_original_usd,
                cxp.monto_pagado_usd,
                cxp.saldo_usd,
                cxp.notas
            FROM cuentas_por_pagar_proveedores cxp
            LEFT JOIN proveedores p ON p.id = cxp.proveedor_id
            LEFT JOIN historial_compras hc ON hc.id = cxp.compra_id
            ORDER BY
                CASE
                    WHEN COALESCE(cxp.saldo_usd,0) > 0 AND cxp.fecha_vencimiento IS NOT NULL THEN 0
                    ELSE 1
                END,
                cxp.fecha_vencimiento ASC,
                cxp.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "compra_id",
        "proveedor",
        "item",
        "estado",
        "fecha_vencimiento",
        "monto_original_usd",
        "monto_pagado_usd",
        "saldo_usd",
        "notas",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_pagos_proveedores_df(cuenta_por_pagar_id: int) -> pd.DataFrame:
    _ensure_inventory_support_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                pp.id,
                pp.fecha,
                pp.usuario,
                pp.monto_usd,
                pp.moneda_pago,
                pp.monto_moneda_pago,
                pp.tasa_cambio,
                pp.referencia,
                pp.observaciones
            FROM pagos_proveedores pp
            WHERE pp.cuenta_por_pagar_id = ?
            ORDER BY pp.fecha DESC, pp.id DESC
            """,
            (int(cuenta_por_pagar_id),),
        ).fetchall()

    cols = [
        "id",
        "fecha",
        "usuario",
        "monto_usd",
        "moneda_pago",
        "monto_moneda_pago",
        "tasa_cambio",
        "referencia",
        "observaciones",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_historial_compras_df(limit: int = 1000) -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT hc.id,
                   hc.fecha,
                   hc.usuario,
                   i.sku,
                   hc.item,
                   COALESCE(p.nombre, 'SIN PROVEEDOR') AS proveedor,
                   hc.cantidad,
                   hc.unidad,
                   hc.costo_total_usd,
                   hc.costo_unit_usd,
                   hc.impuestos,
                   hc.delivery,
                   hc.moneda_pago,
                   COALESCE(hc.tipo_pago, 'contado') AS tipo_pago,
                   COALESCE(hc.metodo_pago, 'efectivo') AS metodo_pago,
                   COALESCE(hc.monto_pagado_inicial_usd, 0) AS monto_pagado_inicial_usd,
                   COALESCE(hc.saldo_pendiente_usd, 0) AS saldo_pendiente_usd,
                   hc.fecha_vencimiento
            FROM historial_compras hc
            LEFT JOIN inventario i ON i.id = hc.inventario_id
            LEFT JOIN proveedores p ON p.id = hc.proveedor_id
            WHERE COALESCE(hc.activo, 1)=1
            ORDER BY hc.fecha DESC, hc.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    cols = [
        "id",
        "fecha",
        "usuario",
        "sku",
        "item",
        "proveedor",
        "cantidad",
        "unidad",
        "costo_total_usd",
        "costo_unit_usd",
        "impuestos",
        "delivery",
        "moneda_pago",
        "tipo_pago",
        "metodo_pago",
        "monto_pagado_inicial_usd",
        "saldo_pendiente_usd",
        "fecha_vencimiento",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_cuotas_compra_df(compra_id: int | None = None) -> pd.DataFrame:
    params: tuple[Any, ...] = ()
    sql = """
        SELECT c.id,
               c.compra_id,
               COALESCE(p.nombre, 'SIN PROVEEDOR') AS proveedor,
               c.numero_cuota,
               c.fecha_vencimiento,
               c.monto_base_usd,
               c.impuesto_pct,
               c.impuesto_usd,
               c.monto_total_usd,
               c.metodo_pago,
               c.moneda_pago,
               c.tasa_cambio,
               c.estado,
               c.fecha_pago
        FROM cuotas_compra_proveedor c
        LEFT JOIN proveedores p ON p.id = c.proveedor_id
    """
    if compra_id is not None:
        sql += " WHERE c.compra_id=?"
        params = (int(compra_id),)
    sql += " ORDER BY c.fecha_vencimiento ASC, c.numero_cuota ASC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    cols = [
        "id",
        "compra_id",
        "proveedor",
        "numero_cuota",
        "fecha_vencimiento",
        "monto_base_usd",
        "impuesto_pct",
        "impuesto_usd",
        "monto_total_usd",
        "metodo_pago",
        "moneda_pago",
        "tasa_cambio",
        "estado",
        "fecha_pago",
    ]
    return pd.DataFrame(rows, columns=cols)


# ============================================================
# REPORTES / CÁLCULOS
# ============================================================

def _build_restock_recommendations(df_inv: pd.DataFrame) -> pd.DataFrame:
    if df_inv is None or df_inv.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "sku",
                "nombre",
                "categoria",
                "unidad",
                "stock_actual",
                "stock_minimo",
                "faltante",
                "sugerido_compra",
                "costo_estimado_usd",
                "prioridad",
            ]
        )

    df = df_inv.copy()
    df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce").fillna(0.0)
    df["stock_minimo"] = pd.to_numeric(df["stock_minimo"], errors="coerce").fillna(0.0)
    df["costo_unitario_usd"] = pd.to_numeric(df["costo_unitario_usd"], errors="coerce").fillna(0.0)

    criticos = df[df["stock_actual"] <= df["stock_minimo"]].copy()
    if criticos.empty:
        return pd.DataFrame(
            columns=[
                "id",
                "sku",
                "nombre",
                "categoria",
                "unidad",
                "stock_actual",
                "stock_minimo",
                "faltante",
                "sugerido_compra",
                "costo_estimado_usd",
                "prioridad",
            ]
        )

    criticos["faltante"] = (criticos["stock_minimo"] - criticos["stock_actual"]).clip(lower=0.0)
    criticos["sugerido_compra"] = (
        criticos["faltante"] + (criticos["stock_minimo"] * 0.2)
    ).clip(lower=0.001).round(3)
    criticos["costo_estimado_usd"] = (criticos["sugerido_compra"] * criticos["costo_unitario_usd"]).round(2)
    criticos["prioridad"] = criticos["faltante"].apply(lambda v: "Alta" if float(v) > 0 else "Media")

    return criticos[
        [
            "id",
            "sku",
            "nombre",
            "categoria",
            "unidad",
            "stock_actual",
            "stock_minimo",
            "faltante",
            "sugerido_compra",
            "costo_estimado_usd",
            "prioridad",
        ]
    ].sort_values(by=["prioridad", "faltante", "costo_estimado_usd"], ascending=[True, False, False])


# ============================================================
# UI HELPERS
# ============================================================

def _render_calendario_cuotas(df_cuotas: pd.DataFrame) -> None:
    st.subheader("📅 Calendario de cuotas")

    if df_cuotas.empty:
        st.info("No hay cuotas registradas.")
        return

    df = df_cuotas.copy()
    df["fecha_vencimiento_date"] = df["fecha_vencimiento"].apply(_safe_date)
    df = df.dropna(subset=["fecha_vencimiento_date"])

    if df.empty:
        st.info("No hay cuotas con fecha válida.")
        return

    hoy = date.today()
    anios_disponibles = sorted(df["fecha_vencimiento_date"].apply(lambda x: x.year).unique().tolist())
    anio_default = hoy.year if hoy.year in anios_disponibles else anios_disponibles[0]

    c1, c2 = st.columns(2)
    anio = c1.selectbox("Año", anios_disponibles, index=anios_disponibles.index(anio_default), key="inv_cal_anio")
    mes = c2.selectbox(
        "Mes",
        options=list(range(1, 13)),
        index=hoy.month - 1,
        format_func=lambda m: calendar.month_name[m],
        key="inv_cal_mes",
    )

    df_mes = df[
        (df["fecha_vencimiento_date"].apply(lambda x: x.year) == anio)
        & (df["fecha_vencimiento_date"].apply(lambda x: x.month) == mes)
    ].copy()

    cal = calendar.monthcalendar(anio, mes)
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    hdr = st.columns(7)
    for i, d in enumerate(dias_semana):
        hdr[i].markdown(f"**{d}**")

    eventos_por_dia: dict[int, list[dict[str, Any]]] = {}
    for _, row in df_mes.iterrows():
        fecha = row["fecha_vencimiento_date"]
        eventos_por_dia.setdefault(fecha.day, []).append(dict(row))

    for semana in cal:
        cols = st.columns(7)
        for idx, dia in enumerate(semana):
            with cols[idx]:
                if dia == 0:
                    st.markdown(" ")
                    continue

                eventos = eventos_por_dia.get(dia, [])
                fecha_actual = date(anio, mes, dia)

                if fecha_actual < hoy:
                    color = "#fde2e2"
                elif fecha_actual == hoy:
                    color = "#fff3cd"
                else:
                    color = "#e8f5e9"

                html = f"""
                <div style="
                    border:1px solid #ddd;
                    border-radius:10px;
                    padding:8px;
                    min-height:120px;
                    background:{color};
                    margin-bottom:8px;
                ">
                    <div style="font-weight:700; margin-bottom:6px;">{dia}</div>
                """

                if not eventos:
                    html += '<div style="font-size:12px; color:#777;">Sin cuotas</div>'
                else:
                    for ev in eventos[:3]:
                        estado = str(ev.get("estado", "pendiente")).lower()
                        proveedor = str(ev.get("proveedor", "Proveedor"))
                        total = _safe_float(ev.get("monto_total_usd"))
                        badge = "🟢" if estado == "pagada" else "🔴"
                        html += f"""
                        <div style="font-size:12px; margin-bottom:6px; padding:4px; border-radius:6px; background:white;">
                            {badge} <b>{proveedor}</b><br>
                            Cuota #{int(_safe_float(ev.get("numero_cuota"), 0))}<br>
                            Total: ${total:,.2f}
                        </div>
                        """

                    if len(eventos) > 3:
                        html += f'<div style="font-size:11px; color:#555;">+{len(eventos)-3} más</div>'

                html += "</div>"
                st.markdown(html, unsafe_allow_html=True)

    st.markdown("### 🗓️ Próximas cuotas")
    proximas = df[
        (df["estado"].astype(str).str.lower() != "pagada")
        & (df["fecha_vencimiento_date"] >= hoy)
    ].sort_values("fecha_vencimiento_date")

    if proximas.empty:
        st.success("No hay cuotas pendientes próximas.")
    else:
        st.dataframe(
            proximas[
                [
                    "proveedor",
                    "compra_id",
                    "numero_cuota",
                    "fecha_vencimiento",
                    "monto_base_usd",
                    "impuesto_pct",
                    "impuesto_usd",
                    "monto_total_usd",
                    "metodo_pago",
                    "estado",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "monto_base_usd": st.column_config.NumberColumn("Base USD", format="%.2f"),
                "impuesto_pct": st.column_config.NumberColumn("Impuesto %", format="%.2f"),
                "impuesto_usd": st.column_config.NumberColumn("Impuesto USD", format="%.2f"),
                "monto_total_usd": st.column_config.NumberColumn("Total USD", format="%.2f"),
            },
        )


# ============================================================
# UI SECCIONES
# ============================================================

def _render_inventario_dashboard(df: pd.DataFrame) -> None:
    st.subheader("📊 Dashboard de Inventario")

    total_items = int(len(df))
    capital_total = float(df["valor_stock"].sum()) if not df.empty else 0.0
    criticos = int((df["stock_actual"] <= df["stock_minimo"]).sum()) if not df.empty else 0
    agotados = int((df["stock_actual"] <= 0).sum()) if not df.empty else 0
    salud = ((total_items - criticos) / total_items * 100) if total_items else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💰 Capital inventario", f"${capital_total:,.2f}")
    c2.metric("📦 Ítems activos", total_items)
    c3.metric("🚨 Stock bajo", criticos)
    c4.metric("🟥 Agotados", agotados)
    c5.metric("🧠 Salud almacén", f"{salud:.0f}%")

    st.progress(min(max(salud / 100.0, 0.0), 1.0))

    if df.empty:
        st.info("No hay productos activos.")
        return

    col1, col2 = st.columns(2)

    with col1:
        top_valor = df.sort_values("valor_stock", ascending=False).head(10).copy()
        if not top_valor.empty:
            st.markdown("#### Top productos por valor")
            st.dataframe(
                top_valor[["sku", "nombre", "categoria", "stock_actual", "valor_stock"]],
                use_container_width=True,
                hide_index=True,
            )

    with col2:
        riesgo = df.copy()
        riesgo["estado_stock"] = riesgo.apply(
            lambda r: "Crítico" if float(r["stock_actual"] or 0) <= float(r["stock_minimo"] or 0) else "Operativo",
            axis=1,
        )
        chart = riesgo.groupby("estado_stock", as_index=False)["id"].count().rename(columns={"id": "cantidad"})
        if not chart.empty:
            st.markdown("#### Estado del stock")
            st.bar_chart(chart.set_index("estado_stock")[["cantidad"]])

    df_var = _load_variantes_df()
    if not df_var.empty:
        st.markdown("#### Variantes por color")
        resumen_var = df_var.groupby("producto", as_index=False)["id"].count().rename(columns={"id": "variantes"})
        st.dataframe(resumen_var, use_container_width=True, hide_index=True)


def _render_existencias(df: pd.DataFrame) -> None:
    st.subheader("📋 Existencias actuales")
    if df.empty:
        st.info("No hay productos activos.")
        return

    plan_reposicion = _build_restock_recommendations(df)
    if plan_reposicion.empty:
        st.success("✅ Sin alertas de reposición. Todos los productos están por encima del mínimo.")
    else:
        presupuesto = float(plan_reposicion["costo_estimado_usd"].sum())
        st.warning(
            f"⚠️ Reposición sugerida para {len(plan_reposicion)} ítems críticos. "
            f"Presupuesto estimado: ${presupuesto:,.2f}."
        )
        with st.expander("🧾 Ver plan sugerido de reposición", expanded=False):
            st.dataframe(
                plan_reposicion,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
                    "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
                    "faltante": st.column_config.NumberColumn("Faltante", format="%.3f"),
                    "sugerido_compra": st.column_config.NumberColumn("Compra sugerida", format="%.3f"),
                    "costo_estimado_usd": st.column_config.NumberColumn("Costo estimado USD", format="%.2f"),
                },
            )

    buscar_inv = st.text_input("🔎 Buscar producto", key="inv_existencias_buscar")
    view_inv = _filter_df_by_query(df.copy(), buscar_inv, ["sku", "nombre", "categoria", "unidad"])

    st.dataframe(
        view_inv,
        use_container_width=True,
        hide_index=True,
        column_config={
            "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
            "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo USD", format="%.4f"),
            "precio_venta_usd": st.column_config.NumberColumn("Precio USD", format="%.4f"),
            "valor_stock": st.column_config.NumberColumn("Valor stock", format="%.2f"),
        },
    )

    st.markdown("### 🎨 Variantes")
    df_var = _load_variantes_df()
    if df_var.empty:
        st.caption("No hay variantes registradas todavía.")
    else:
        buscar_var = st.text_input("🔎 Buscar variante", key="inv_existencias_buscar_var")
        view_var = _filter_df_by_query(df_var.copy(), buscar_var, ["producto", "color", "sku_variante", "sku_base"])
        st.dataframe(
            view_var,
            use_container_width=True,
            hide_index=True,
            column_config={
                "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
                "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
                "costo_unitario_usd": st.column_config.NumberColumn("Costo USD", format="%.4f"),
                "precio_venta_usd": st.column_config.NumberColumn("Precio USD", format="%.4f"),
            },
        )


def _render_compras(usuario: str, tasa_bcv: float, tasa_binance: float) -> None:
    st.subheader("📥 Registrar compra")

    with db_transaction() as conn:
        items_rows = conn.execute(
            """
            SELECT id, sku, nombre, categoria, unidad, costo_unitario_usd, precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado,'activo')='activo'
            ORDER BY nombre
            """
        ).fetchall()

    items_map = {int(r["id"]): r for r in items_rows}

    modo_item = st.radio(
        "Ítem",
        ["Usar existente", "Crear y comprar"],
        horizontal=True,
        key="inv_compra_modo_item",
    )
    inv_id = None

    if modo_item == "Usar existente" and items_map:
        inv_id = st.selectbox(
            "Producto",
            list(items_map.keys()),
            format_func=lambda i: f"{items_map[i]['nombre']} ({items_map[i]['sku']})",
            key="inv_compra_item_id",
        )
    elif modo_item == "Usar existente":
        st.warning("No hay productos creados. Usa 'Crear y comprar'.")

    if modo_item == "Crear y comprar":
        cnew1, cnew2, cnew3, cnew4 = st.columns(4)
        nuevo_nombre = cnew1.text_input("Nombre", key="inv_compra_new_nombre")
        nuevo_sku = cnew2.text_input("SKU base", key="inv_compra_new_sku")
        nueva_categoria = cnew3.text_input("Categoría", value="General", key="inv_compra_new_cat")
        tipo_unidad = cnew4.selectbox(
            "Tipo unidad",
            ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"],
            key="inv_compra_new_tipo_unidad",
        )
        cantidad, unidad_resuelta, _ = _calc_stock_by_unit_type(tipo_unidad)
        nuevo_min = st.number_input("Stock mínimo", min_value=0.0, value=0.0, key="inv_compra_new_min")
        costo_base = st.number_input(
            "Costo inicial unitario USD",
            min_value=0.0,
            value=0.0,
            format="%.4f",
            key="inv_compra_new_costo",
        )
        precio_base = st.number_input(
            "Precio inicial USD",
            min_value=0.0,
            value=0.0,
            format="%.4f",
            key="inv_compra_new_precio",
        )
    else:
        cantidad = st.number_input(
            "Cantidad comprada",
            min_value=0.001,
            value=1.0,
            key="inv_compra_qty_existente",
        )
        unidad_resuelta = str(items_map[inv_id]["unidad"]) if inv_id in items_map else "unidad"
        nuevo_nombre = ""
        nuevo_sku = ""
        nueva_categoria = ""
        nuevo_min = 0.0
        costo_base = 0.0
        precio_base = 0.0

    df_prov = _load_proveedores_df()

    d1, d2, d3 = st.columns(3)
    if not df_prov.empty:
        opciones_prov = ["-- Seleccionar proveedor --"] + df_prov["nombre"].astype(str).tolist() + ["Otro / escribir manual"]
        proveedor_sel = d1.selectbox("Proveedor", opciones_prov, key="inv_compra_proveedor_sel")

        if proveedor_sel == "Otro / escribir manual":
            proveedor_nombre = d1.text_input("Nombre proveedor", key="inv_compra_proveedor_manual")
        elif proveedor_sel == "-- Seleccionar proveedor --":
            proveedor_nombre = ""
        else:
            proveedor_nombre = proveedor_sel
    else:
        proveedor_nombre = d1.text_input("Proveedor", key="inv_compra_proveedor")

    costo_total = d2.number_input(
        "Costo total USD",
        min_value=0.0001,
        value=1.0,
        format="%.4f",
        key="inv_compra_total",
    )
    impuesto_pct = d3.number_input(
        "Impuesto general compra (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(st.session_state.get("inv_impuesto_default", 16.0)),
        format="%.2f",
        key="inv_compra_impuesto",
    )

    d4, d5, d6 = st.columns(3)
    delivery_monto = d4.number_input(
        "Delivery",
        min_value=0.0,
        value=float(st.session_state.get("inv_delivery_default", 0.0)),
        format="%.4f",
        key="inv_compra_delivery",
    )
    delivery_moneda = d5.selectbox(
        "Moneda delivery",
        ["USD", "VES (BCV)", "VES (Binance)"],
        key="inv_compra_delivery_moneda",
    )
    delivery_manual = d6.checkbox("Tasa manual delivery", key="inv_compra_delivery_manual")
    delivery_usd, tasa_delivery = _resolve_delivery_usd(
        delivery_monto,
        delivery_moneda,
        tasa_bcv,
        tasa_binance,
        delivery_manual,
    )

    st.divider()
    st.markdown("### 💳 Condición de pago")

    p1, p2, p3, p4 = st.columns(4)
    tipo_pago = p1.selectbox("Tipo de pago", ["contado", "credito"], key="inv_compra_tipo_pago")
    moneda_pago = p2.selectbox(
        "Moneda pago",
        ["USD", "VES (BCV)", "VES (Binance)"],
        key="inv_compra_moneda",
    )
    metodo_pago_general = p3.selectbox(
        "Método de pago",
        ["efectivo", "pago_movil", "transferencia", "zelle", "binance", "tarjeta", "otro"],
        key="inv_compra_metodo_pago",
    )
    tasa_pago = _rate_from_label(moneda_pago, tasa_bcv, tasa_binance)
    if p4.checkbox("Tasa manual pago", key="inv_compra_tasa_manual"):
        tasa_pago = st.number_input(
            "Tasa usada en pago",
            min_value=0.0001,
            value=float(tasa_pago),
            format="%.4f",
            key="inv_compra_tasa_pago",
        )

    monto_pagado = 0.0
    fecha_venc: date | None = None
    cuotas_generadas: list[dict[str, Any]] = []

    if tipo_pago == "contado":
        monto_pagado = float(costo_total)
        st.success("Compra de contado: se toma el costo total como pago completo.")
        st.metric("Monto pagado", f"${monto_pagado:,.2f}")
    else:
        c1, c2, c3 = st.columns(3)
        monto_pagado = c1.number_input(
            "Inicial USD",
            min_value=0.0,
            max_value=float(costo_total),
            value=0.0,
            format="%.4f",
            key="inv_compra_pagado",
        )
        cantidad_cuotas = int(
            c2.number_input(
                "Número de cuotas",
                min_value=1,
                max_value=36,
                value=1,
                step=1,
                key="inv_compra_num_cuotas",
            )
        )
        frecuencia = c3.selectbox(
            "Frecuencia cuotas",
            ["mensual", "quincenal", "semanal"],
            key="inv_compra_freq_cuotas",
        )

        saldo_financiar = max(float(costo_total) - float(monto_pagado), 0.0)
        if saldo_financiar <= 0:
            st.warning("No hay saldo para financiar. Revisa el monto inicial.")
        else:
            inicio = st.date_input("Fecha primera cuota", value=date.today(), key="inv_compra_primera_cuota")
            cuota_base = round(saldo_financiar / max(cantidad_cuotas, 1), 2)

            st.caption(f"Saldo a financiar: ${saldo_financiar:,.2f}")
            st.caption(f"Cuota base sugerida: ${cuota_base:,.2f}")

            delta_dias = 30 if frecuencia == "mensual" else 15 if frecuencia == "quincenal" else 7

            for i in range(cantidad_cuotas):
                fecha_default = inicio + timedelta(days=(delta_dias * i))
                st.markdown(f"#### Cuota {i + 1}")
                q1, q2, q3, q4 = st.columns(4)
                monto_cuota = q1.number_input(
                    f"Monto cuota {i + 1}",
                    min_value=0.0,
                    value=float(cuota_base),
                    format="%.4f",
                    key=f"inv_compra_cuota_monto_{i}",
                )
                fecha_cuota = q2.date_input(
                    f"Fecha cuota {i + 1}",
                    value=fecha_default,
                    key=f"inv_compra_cuota_fecha_{i}",
                )
                impuesto_cuota = q3.number_input(
                    f"Impuesto cuota {i + 1} (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    format="%.2f",
                    key=f"inv_compra_cuota_impuesto_{i}",
                )
                metodo_cuota = q4.selectbox(
                    f"Método cuota {i + 1}",
                    ["efectivo", "pago_movil", "transferencia", "zelle", "binance", "tarjeta", "otro"],
                    key=f"inv_compra_cuota_metodo_{i}",
                )

                impuesto_usd = round(float(monto_cuota) * float(impuesto_cuota) / 100.0, 2)
                total_cuota = round(float(monto_cuota) + impuesto_usd, 2)

                cuotas_generadas.append(
                    {
                        "numero_cuota": i + 1,
                        "fecha_vencimiento": fecha_cuota.isoformat(),
                        "monto_base_usd": float(monto_cuota),
                        "impuesto_pct": float(impuesto_cuota),
                        "impuesto_usd": float(impuesto_usd),
                        "monto_total_usd": float(total_cuota),
                        "metodo_pago": metodo_cuota,
                        "moneda_pago": str(moneda_pago),
                        "tasa_cambio": float(tasa_pago or 1.0),
                    }
                )

            if cuotas_generadas:
                fecha_venc = pd.to_datetime([x["fecha_vencimiento"] for x in cuotas_generadas]).max().date()
                cronograma_df = pd.DataFrame(cuotas_generadas)
                st.markdown("### 📅 Cronograma de cuotas")
                st.dataframe(cronograma_df, use_container_width=True, hide_index=True)

                total_cuotas = float(cronograma_df["monto_total_usd"].sum())
                csum1, csum2 = st.columns(2)
                csum1.metric("Total cuotas", f"${total_cuotas:,.2f}")
                csum2.metric("Último vencimiento", str(fecha_venc))

    if st.button("✅ Guardar compra", use_container_width=True):
        try:
            target_id = inv_id

            if modo_item == "Crear y comprar":
                target_id = _create_inventory_item_for_purchase(
                    usuario=usuario,
                    sku_base=nuevo_sku,
                    nombre=nuevo_nombre,
                    categoria=nueva_categoria,
                    unidad=unidad_resuelta,
                    minimo=float(nuevo_min),
                    costo_inicial=float(costo_base),
                    precio_inicial=float(precio_base),
                )

            if target_id is None:
                raise ValueError("Debes seleccionar o crear un producto para registrar la compra.")

            if not clean_text(proveedor_nombre):
                raise ValueError("Debes seleccionar o escribir un proveedor.")

            with db_transaction() as conn:
                proveedor_id = _get_or_create_provider(conn, proveedor_nombre)

            fin_input = CompraFinancialInput(
                tipo_pago=clean_text(tipo_pago).lower(),
                monto_pagado_inicial_usd=float(monto_pagado),
                fecha_vencimiento=fecha_venc.isoformat() if fecha_venc else None,
            )

            compra_id = registrar_compra(
                usuario=usuario,
                inventario_id=int(target_id),
                cantidad=float(cantidad),
                costo_total_usd=float(costo_total),
                proveedor_id=proveedor_id,
                proveedor_nombre=proveedor_nombre,
                impuestos_pct=float(impuesto_pct),
                delivery_usd=float(delivery_usd),
                tasa_usada=float(tasa_pago if tasa_pago else tasa_delivery),
                moneda_pago=str(moneda_pago),
                metodo_pago=str(metodo_pago_general),
                financial_input=fin_input,
            )

            if tipo_pago == "credito" and cuotas_generadas:
                _save_installments(compra_id=compra_id, proveedor_id=proveedor_id, cuotas=cuotas_generadas)

            st.success(f"Compra registrada en {money(cantidad)} {unidad_resuelta}. ID compra #{compra_id}")
            st.rerun()

        except Exception as exc:
            st.error(f"No se pudo registrar la compra: {exc}")


def _render_historial_compras() -> None:
    st.subheader("📊 Historial de compras")
    df_hist = _load_historial_compras_df(limit=2000)
    if df_hist.empty:
        st.info("No hay compras registradas.")
        return

    h1, h2 = st.columns([2, 1])
    buscar_hist = h1.text_input("🔎 Buscar compra", key="inv_hist_buscar")
    tipo_hist = h2.selectbox("Condición", ["Todos", "contado", "credito"], key="inv_hist_tipo")
    view_hist = _filter_df_by_query(df_hist.copy(), buscar_hist, ["item", "proveedor", "sku"])
    if tipo_hist != "Todos":
        view_hist = view_hist[view_hist["tipo_pago"].astype(str).str.lower() == tipo_hist]

    st.dataframe(
        view_hist,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_total_usd": st.column_config.NumberColumn("Total USD", format="%.2f"),
            "costo_unit_usd": st.column_config.NumberColumn("Costo unitario", format="%.4f"),
            "impuestos": st.column_config.NumberColumn("Impuesto %", format="%.2f"),
            "delivery": st.column_config.NumberColumn("Delivery USD", format="%.4f"),
            "monto_pagado_inicial_usd": st.column_config.NumberColumn("Pagado inicial", format="%.2f"),
            "saldo_pendiente_usd": st.column_config.NumberColumn("Saldo", format="%.2f"),
        },
    )


def _render_proveedores() -> None:
    st.subheader("👤 Directorio de proveedores")
    df_prov = _load_proveedores_df()

    if df_prov.empty:
        st.info("No hay proveedores registrados todavía.")
    else:
        cfp1, cfp2 = st.columns([2, 1])
        filtro = cfp1.text_input("🔍 Buscar proveedor")
        selected_tags = cfp2.multiselect("Filtrar por especialidad", _extract_supplier_tags(df_prov))

        df_view = df_prov.copy()
        if filtro:
            searchable_cols = ["nombre", "telefono", "rif", "contacto", "observaciones", "especialidades"]
            df_view = _filter_df_by_query(df_view, filtro, searchable_cols)
        if selected_tags:
            df_view = df_view[
                df_view["especialidades"].fillna("").astype(str).apply(
                    lambda txt: all(tag.lower() in txt.lower() for tag in selected_tags)
                )
            ]
        st.dataframe(df_view, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("➕ Registrar / Editar proveedor")

    proveedor_existente = None
    if not df_prov.empty:
        pid_sel = st.selectbox(
            "Editar proveedor existente (opcional)",
            options=[None] + df_prov["id"].tolist(),
            format_func=lambda x: "Nuevo proveedor" if x is None else str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
        )
        if pid_sel is not None:
            proveedor_existente = df_prov[df_prov["id"] == pid_sel].iloc[0]

    with st.form("form_proveedor"):
        nombre = st.text_input("Nombre", value="" if proveedor_existente is None else str(proveedor_existente["nombre"]))
        telefono = st.text_input("Teléfono", value="" if proveedor_existente is None else str(proveedor_existente["telefono"]))
        rif = st.text_input("RIF", value="" if proveedor_existente is None else str(proveedor_existente["rif"]))
        contacto = st.text_input("Contacto", value="" if proveedor_existente is None else str(proveedor_existente["contacto"]))
        observaciones = st.text_area("Observaciones", value="" if proveedor_existente is None else str(proveedor_existente["observaciones"]))
        especialidades_txt = st.text_input(
            "Especialidades / ítems (separados por coma)",
            placeholder="Impresoras, Tintas, Vinil, Sublimación",
            value="" if proveedor_existente is None else str(proveedor_existente["especialidades"]),
        )
        guardar = st.form_submit_button("💾 Guardar", use_container_width=True)

    if guardar:
        if not clean_text(nombre):
            st.error("Nombre obligatorio")
        else:
            especialidades_norm = ", ".join([clean_text(x) for x in especialidades_txt.split(",") if clean_text(x)])
            with db_transaction() as conn:
                exists = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (clean_text(nombre),)).fetchone()
                if exists:
                    conn.execute(
                        """
                        UPDATE proveedores
                        SET telefono=?, rif=?, contacto=?, observaciones=?, especialidades=?, activo=1
                        WHERE id=?
                        """,
                        (
                            clean_text(telefono),
                            clean_text(rif),
                            clean_text(contacto),
                            clean_text(observaciones),
                            especialidades_norm,
                            int(exists["id"]),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO proveedores(nombre, telefono, rif, contacto, observaciones, especialidades, activo)
                        VALUES(?,?,?,?,?,?,1)
                        """,
                        (
                            clean_text(nombre),
                            clean_text(telefono),
                            clean_text(rif),
                            clean_text(contacto),
                            clean_text(observaciones),
                            especialidades_norm,
                        ),
                    )
            st.success("Proveedor guardado")
            st.rerun()

    if not df_prov.empty:
        sel = st.selectbox(
            "Proveedor a eliminar",
            df_prov["id"].tolist(),
            format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]),
        )
        if st.button("🗑 Eliminar proveedor"):
            with db_transaction() as conn:
                compras = conn.execute(
                    "SELECT COUNT(*) AS c FROM historial_compras WHERE proveedor_id=? AND COALESCE(activo,1)=1",
                    (int(sel),),
                ).fetchone()
                if int(compras["c"] or 0) > 0:
                    st.error("Tiene compras asociadas")
                else:
                    conn.execute("UPDATE proveedores SET activo=0 WHERE id=?", (int(sel),))
                    st.success("Proveedor eliminado")
                    st.rerun()


def _render_variantes() -> None:
    st.subheader("🎨 Variantes por color")

    df_inv = _load_inventory_df()
    if df_inv.empty:
        st.info("Primero debes tener productos creados.")
        return

    tab1, tab2 = st.tabs(["Registrar variante", "Listado de variantes"])

    with tab1:
        producto_id = _select_inventory_item(df_inv, "Producto base", "inv_var_item")
        prow = df_inv[df_inv["id"] == producto_id].iloc[0]

        st.caption(
            f"Base: {prow['nombre']} | SKU: {prow['sku']} | "
            f"Precio heredado: ${float(prow['precio_venta_usd'] or 0):,.4f} | "
            f"Unidad: {prow['unidad']}"
        )

        c1, c2, c3, c4 = st.columns(4)
        color = c1.text_input("Color", key="inv_var_color")
        sku_variante = c2.text_input("SKU variante (opcional)", key="inv_var_sku")
        stock_actual = c3.number_input("Stock inicial", min_value=0.0, value=0.0, format="%.3f", key="inv_var_stock")
        stock_minimo = c4.number_input("Stock mínimo", min_value=0.0, value=0.0, format="%.3f", key="inv_var_min")

        if st.button("✅ Guardar variante", use_container_width=True):
            try:
                var_id = _create_variant(
                    inventario_id=int(producto_id),
                    color=color,
                    sku_variante=sku_variante,
                    stock_actual=float(stock_actual),
                    stock_minimo=float(stock_minimo),
                )
                st.success(f"Variante creada correctamente. ID #{var_id}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear la variante: {exc}")

    with tab2:
        df_var = _load_variantes_df()
        if df_var.empty:
            st.caption("No hay variantes registradas.")
        else:
            buscar = st.text_input("🔎 Buscar variante", key="inv_var_buscar")
            view = _filter_df_by_query(df_var.copy(), buscar, ["producto", "color", "sku_variante", "sku_base"])
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
                    "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
                    "costo_unitario_usd": st.column_config.NumberColumn("Costo USD", format="%.4f"),
                    "precio_venta_usd": st.column_config.NumberColumn("Precio USD", format="%.4f"),
                },
            )


def _render_cuentas_por_pagar() -> None:
    st.subheader("💳 Cuentas por pagar a proveedores")
    subtabs = st.tabs(["Resumen CxP", "Calendario de cuotas"])

    with subtabs[0]:
        df_cxp = _load_cuentas_por_pagar_df()
        if df_cxp.empty:
            st.info("No hay cuentas por pagar registradas.")
        else:
            f1, f2 = st.columns([2, 1])
            buscar = f1.text_input("🔎 Buscar cuenta por pagar", key="inv_cxp_buscar")
            estado = f2.selectbox("Estado", ["Todos", "pendiente", "vencida", "pagada"], key="inv_cxp_estado")

            view = _filter_df_by_query(df_cxp.copy(), buscar, ["proveedor", "item", "estado", "notas"])
            if estado != "Todos":
                view = view[view["estado"].astype(str).str.lower() == estado.lower()]

            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "monto_original_usd": st.column_config.NumberColumn("Monto original", format="%.2f"),
                    "monto_pagado_usd": st.column_config.NumberColumn("Pagado", format="%.2f"),
                    "saldo_usd": st.column_config.NumberColumn("Saldo", format="%.2f"),
                },
            )

            total_saldo = float(view["saldo_usd"].sum()) if not view.empty else 0.0
            st.metric("Saldo total visible", f"${total_saldo:,.2f}")

    with subtabs[1]:
        df_cuotas = _load_cuotas_compra_df()
        if df_cuotas.empty:
            st.info("No hay cuotas registradas.")
        else:
            h1, h2 = st.columns([2, 1])
            buscar_cuota = h1.text_input("🔎 Buscar cuota", key="inv_cuota_buscar")
            estado_cuota = h2.selectbox("Estado cuota", ["Todos", "pendiente", "pagada"], key="inv_cuota_estado")

            view_cuotas = _filter_df_by_query(df_cuotas.copy(), buscar_cuota, ["proveedor", "metodo_pago"])
            if estado_cuota != "Todos":
                view_cuotas = view_cuotas[view_cuotas["estado"].astype(str).str.lower() == estado_cuota]

            st.dataframe(
                view_cuotas,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "monto_base_usd": st.column_config.NumberColumn("Base", format="%.2f"),
                    "impuesto_pct": st.column_config.NumberColumn("Impuesto %", format="%.2f"),
                    "impuesto_usd": st.column_config.NumberColumn("Impuesto USD", format="%.2f"),
                    "monto_total_usd": st.column_config.NumberColumn("Total cuota", format="%.2f"),
                },
            )

            _render_calendario_cuotas(view_cuotas)


def _render_movimientos() -> None:
    st.subheader("🔄 Movimientos de inventario")
    df = _load_movements_df(limit=2000)

    if df.empty:
        st.info("No hay movimientos registrados.")
        return

    f1, f2 = st.columns([2, 1])
    buscar = f1.text_input("🔎 Buscar movimiento", placeholder="referencia, producto, usuario...", key="inv_mov_buscar")
    tipo = f2.selectbox("Tipo", ["Todos", "entrada", "salida", "ajuste"], key="inv_mov_tipo")

    view = df.copy()
    view = _filter_df_by_query(view, buscar, ["referencia", "nombre", "sku", "usuario"])
    if tipo != "Todos":
        view = view[view["tipo"] == tipo]

    st.metric("💵 Valor movimientos visibles", f"$ {float(view['costo_total_usd'].sum() if not view.empty else 0):,.2f}")

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo unitario", format="%.2f"),
            "costo_total_usd": st.column_config.NumberColumn("Costo total", format="%.2f"),
        },
    )


def _render_kardex_tab(usuario: str) -> None:
    st.subheader("🧾 Kardex")
    render_kardex(usuario)


def _render_reposicion(df: pd.DataFrame) -> None:
    st.subheader("📦 Reposición")
    plan = _build_restock_recommendations(df)
    if plan.empty:
        st.success("No hay productos críticos para reponer.")
        return

    presupuesto = float(plan["costo_estimado_usd"].sum())
    c1, c2 = st.columns(2)
    c1.metric("Ítems a reponer", len(plan))
    c2.metric("Presupuesto estimado", f"${presupuesto:,.2f}")

    st.dataframe(
        plan,
        use_container_width=True,
        hide_index=True,
        column_config={
            "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
            "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
            "faltante": st.column_config.NumberColumn("Faltante", format="%.3f"),
            "sugerido_compra": st.column_config.NumberColumn("Compra sugerida", format="%.3f"),
            "costo_estimado_usd": st.column_config.NumberColumn("Costo estimado USD", format="%.2f"),
        },
    )


def _render_ajustes(usuario: str) -> None:
    st.subheader("🔧 Ajustes de inventario")
    df_adj = _load_inventory_df()

    if df_adj.empty:
        st.info("No hay productos activos para ajustar.")
        return

    t1, t2, t3, t4 = st.tabs(["🧮 Stock", "💲 Costos y Precios", "📦 Políticas", "🧹 Mantenimiento"])

    with t1:
        st.caption("Ajustes de stock por reconteo individual y por lote.")
        a1, a2 = st.tabs(["Individual", "Masivo por CSV"])

        with a1:
            aid = _select_inventory_item(df_adj, "Producto", "inv_adj_stock_item")
            arow = df_adj[df_adj["id"] == aid].iloc[0]
            stock_sistema = float(arow["stock_actual"] or 0.0)
            stock_fisico = st.number_input("Stock físico contado", min_value=0.0, value=stock_sistema, key="inv_adj_stock_fisico")
            delta = float(stock_fisico) - stock_sistema
            m1, m2 = st.columns(2)
            m1.metric("Sistema", f"{stock_sistema:,.3f}")
            m2.metric("Delta", f"{delta:,.3f}")
            motivo = st.text_input("Motivo", value="Ajuste por reconteo físico", key="inv_adj_stock_motivo")
            if st.button("✅ Aplicar ajuste individual"):
                if abs(delta) < 1e-9:
                    st.warning("No hay diferencia")
                else:
                    add_inventory_movement(
                        usuario=usuario,
                        inventario_id=int(aid),
                        tipo="ajuste",
                        cantidad=float(delta),
                        costo_unitario_usd=float(arow["costo_unitario_usd"] or 0.0),
                        referencia=motivo,
                    )
                    st.success("Ajuste aplicado")
                    st.rerun()

        with a2:
            st.caption("Carga CSV con columnas: sku, stock_fisico")
            template = pd.DataFrame({"sku": ["sku-ejemplo"], "stock_fisico": [10.0]})
            st.download_button(
                "⬇️ Descargar plantilla CSV",
                data=template.to_csv(index=False).encode("utf-8"),
                file_name="plantilla_reconteo.csv",
                mime="text/csv",
            )
            file = st.file_uploader("Subir reconteo CSV", type=["csv"], key="inv_adj_csv")
            if file is not None:
                try:
                    recon = pd.read_csv(file)
                    required = {"sku", "stock_fisico"}
                    if not required.issubset(set(recon.columns)):
                        st.error("CSV inválido. Debe tener columnas sku y stock_fisico")
                    else:
                        st.dataframe(recon.head(20), use_container_width=True)
                        if st.button("⚙️ Aplicar ajustes masivos desde CSV"):
                            with db_transaction() as conn:
                                updated = 0
                                for r in recon.itertuples(index=False):
                                    sku = clean_text(getattr(r, "sku", ""))
                                    stock_f = _safe_float(getattr(r, "stock_fisico", 0.0), 0.0)
                                    row = conn.execute(
                                        "SELECT id, stock_actual, costo_unitario_usd FROM inventario WHERE sku=? AND COALESCE(estado,'activo')='activo'",
                                        (sku,),
                                    ).fetchone()
                                    if not row:
                                        continue
                                    delta = float(stock_f) - float(row["stock_actual"] or 0.0)
                                    if abs(delta) < 1e-9:
                                        continue

                                    conn.execute(
                                        """
                                        INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
                                        VALUES (?, ?, 'ajuste', ?, ?, ?)
                                        """,
                                        (
                                            usuario,
                                            int(row["id"]),
                                            float(delta),
                                            float(row["costo_unitario_usd"] or 0.0),
                                            "Ajuste masivo por CSV",
                                        ),
                                    )
                                    conn.execute(
                                        "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
                                        (float(delta), int(row["id"])),
                                    )
                                    updated += 1
                            st.success(f"Ajustes aplicados en {updated} productos")
                            st.rerun()
                except Exception as exc:
                    st.error(f"Error procesando CSV: {exc}")

    with t2:
        rid = _select_inventory_item(df_adj, "Producto a revalorizar", "inv_adj_reval_item")
        rrow = df_adj[df_adj["id"] == rid].iloc[0]
        costo_actual = float(rrow["costo_unitario_usd"] or 0.0)
        precio_actual = float(rrow["precio_venta_usd"] or 0.0)
        nuevo_costo = st.number_input("Nuevo costo USD", min_value=0.0, value=costo_actual, format="%.4f")
        modo_precio = st.radio("Modo precio", ["Manual", "Por margen"], horizontal=True)
        if modo_precio == "Por margen":
            margen = st.number_input("Margen (%)", min_value=0.0, value=30.0)
            nuevo_precio = float(nuevo_costo) * (1 + float(margen) / 100.0)
        else:
            nuevo_precio = st.number_input("Nuevo precio venta USD", min_value=0.0, value=precio_actual, format="%.4f")

        p1, p2 = st.columns(2)
        p1.metric("Costo actual", f"${costo_actual:,.4f}")
        p2.metric("Precio nuevo", f"${nuevo_precio:,.4f}")

        if st.button("💾 Aplicar revalorización"):
            with db_transaction() as conn:
                conn.execute(
                    "UPDATE inventario SET costo_unitario_usd=?, precio_venta_usd=? WHERE id=?",
                    (money(nuevo_costo), money(nuevo_precio), int(rid)),
                )
            st.success("Revalorización aplicada")
            st.rerun()

    with t3:
        st.markdown("#### Ajuste masivo de mínimos")
        metodo = st.radio("Método", ["Incremento porcentual", "Asignar valor fijo"], horizontal=True, key="inv_pol_metodo")
        if metodo == "Incremento porcentual":
            pct = st.number_input("% a incrementar/reducir mínimos", value=10.0, format="%.2f", key="inv_pol_pct")
            fijo = None
        else:
            fijo = st.number_input("Nuevo mínimo fijo", min_value=0.0, value=1.0, key="inv_pol_fijo")
            pct = None

        aplicar_solo_criticos = st.checkbox("Aplicar solo a productos críticos", key="inv_pol_crit")
        if st.button("⚙️ Ejecutar ajuste masivo de mínimos"):
            with db_transaction() as conn:
                rows = conn.execute("SELECT id, stock_actual, stock_minimo FROM inventario WHERE COALESCE(estado,'activo')='activo'").fetchall()
                updated = 0
                for r in rows:
                    sid = int(r["id"])
                    stock = float(r["stock_actual"] or 0.0)
                    minimo = float(r["stock_minimo"] or 0.0)
                    if aplicar_solo_criticos and stock > minimo:
                        continue
                    if metodo == "Incremento porcentual":
                        nuevo_minimo = max(0.0, minimo * (1 + float(pct) / 100.0))
                    else:
                        nuevo_minimo = float(fijo)
                    conn.execute("UPDATE inventario SET stock_minimo=? WHERE id=?", (nuevo_minimo, sid))
                    updated += 1
            st.success(f"Mínimos actualizados en {updated} productos")
            st.rerun()

    with t4:
        st.markdown("#### Mantenimiento de estructura")
        mid = _select_inventory_item(df_adj, "Producto", "inv_maint_item")
        mrow = df_adj[df_adj["id"] == mid].iloc[0]
        nuevo_nombre = st.text_input("Nuevo nombre", value=str(mrow["nombre"]), key="inv_maint_nombre")
        nueva_categoria = st.text_input("Nueva categoría", value=str(mrow["categoria"]), key="inv_maint_cat")
        nueva_unidad = st.text_input("Nueva unidad", value=str(mrow["unidad"]), key="inv_maint_unidad")
        activar = st.checkbox("Mantener activo", value=True, key="inv_maint_activo")

        if st.button("💾 Guardar cambios estructurales"):
            with db_transaction() as conn:
                conn.execute(
                    "UPDATE inventario SET nombre=?, categoria=?, unidad=?, estado=? WHERE id=?",
                    (
                        clean_text(nuevo_nombre),
                        clean_text(nueva_categoria),
                        clean_text(nueva_unidad),
                        "activo" if activar else "inactivo",
                        int(mid),
                    ),
                )
            st.success("Cambios estructurales guardados")
            st.rerun()

    st.divider()
    st.markdown("### Configuración estratégica")
    with db_transaction() as conn:
        cfg = pd.read_sql("SELECT parametro, valor FROM configuracion", conn)

    cfg_map = {str(r.parametro): _safe_float(r.valor, 0.0) for r in cfg.itertuples() if str(r.valor).strip() != ""}

    c1, c2, c3 = st.columns(3)
    c1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
    c2.metric("🛡️ Impuesto sugerido", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
    c3.metric("🚚 Delivery sugerido", f"${cfg_map.get('inv_delivery_default', 0.0):.2f}")

    with st.form("form_config_inventario"):
        alerta = st.number_input("Días alerta reposición", min_value=1, max_value=365, value=int(cfg_map.get("inv_alerta_dias", 14)))
        impuesto = st.number_input(
            "Impuesto default compras (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(cfg_map.get("inv_impuesto_default", 16.0)),
            format="%.2f",
        )
        delivery = st.number_input(
            "Delivery default ($)",
            min_value=0.0,
            value=float(cfg_map.get("inv_delivery_default", 0.0)),
            format="%.2f",
        )
        guardar = st.form_submit_button("💾 Guardar Configuración", use_container_width=True)

    if guardar:
        with db_transaction() as conn:
            conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_alerta_dias'", (str(int(alerta)),))
            conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_impuesto_default'", (str(float(impuesto)),))
            conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_delivery_default'", (str(float(delivery)),))
        st.session_state.inv_alerta_dias = int(alerta)
        st.session_state.inv_impuesto_default = float(impuesto)
        st.session_state.inv_delivery_default = float(delivery)
        st.success("✅ Configuración actualizada correctamente")
        st.rerun()


def _render_reportes(df: pd.DataFrame) -> None:
    st.subheader("📈 Reportes")

    if df.empty:
        st.info("No hay inventario activo para reportar.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total productos", len(df))
    c2.metric("Valor inventario", f"${float(df['valor_stock'].sum()):,.2f}")
    c3.metric("Productos críticos", int((df["stock_actual"] <= df["stock_minimo"]).sum()))

    top_valor = df.sort_values("valor_stock", ascending=False).head(10)
    st.markdown("#### Top por valor")
    st.dataframe(
        top_valor[["sku", "nombre", "categoria", "stock_actual", "valor_stock"]],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Exportar existencias CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"inventario_existencias_{date.today().isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    df_var = _load_variantes_df()
    if not df_var.empty:
        st.download_button(
            "⬇️ Exportar variantes CSV",
            data=df_var.to_csv(index=False).encode("utf-8"),
            file_name=f"inventario_variantes_{date.today().isoformat()}.csv",
            mime="text/csv",
            use_container_width=True,
            key="inv_export_variantes",
        )

    df_mov = _load_movements_df(limit=5000)
    if not df_mov.empty:
        st.markdown("#### Exportes operativos")
        st.download_button(
            "⬇️ Exportar movimientos CSV",
            data=df_mov.to_csv(index=False).encode("utf-8"),
            file_name=f"inventario_movimientos_{date.today().isoformat()}.csv",
            mime="text/csv",
            use_container_width=True,
            key="inv_export_movs",
        )


# ============================================================
# UI
# ============================================================

def render_inventario(usuario: str) -> None:
    _ensure_inventory_support_tables()
    _ensure_config_defaults()

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)
    tasa_binance = float(st.session_state.get("tasa_binance", 38.0) or 38.0)

    st.subheader("📦 Centro de Control de Inventario")
    st.caption(
        "Catálogo, compras, variantes por color, proveedores, cuentas por pagar, "
        "movimientos, kardex, reposición, ajustes y reportes."
    )

    df = _load_inventory_df()

    with st.expander("📨 Solicitudes recibidas desde Diagnóstico IA", expanded=False):
        df_diag_mov = _load_diagnostico_movimientos(limit=25)
        if df_diag_mov.empty:
            st.caption("No hay consumos enviados desde Diagnóstico IA todavía.")
        else:
            st.dataframe(df_diag_mov, use_container_width=True, hide_index=True)

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "📋 Existencias",
            "📥 Compras",
            "🎨 Variantes",
            "👤 Proveedores",
            "💳 CxP",
            "🔄 Movimientos",
            "🧾 Kardex",
            "📦 Reposición",
            "🔧 Ajustes",
            "📈 Reportes",
        ]
    )

    with tabs[0]:
        _render_inventario_dashboard(df)

    with tabs[1]:
        _render_existencias(df)

    with tabs[2]:
        compras_tabs = st.tabs(["Registrar compra", "Historial compras"])
        with compras_tabs[0]:
            _render_compras(usuario, tasa_bcv, tasa_binance)
        with compras_tabs[1]:
            _render_historial_compras()

    with tabs[3]:
        _render_variantes()

    with tabs[4]:
        _render_proveedores()

    with tabs[5]:
        _render_cuentas_por_pagar()

    with tabs[6]:
        _render_movimientos()

    with tabs[7]:
        _render_kardex_tab(usuario)

    with tabs[8]:
        _render_reposicion(df)

    with tabs[9]:
        _render_ajustes(usuario)

    with tabs[10]:
        _render_reportes(df)


# ============================================================
# KARDEX INVENTARIO
# ============================================================

def render_kardex(usuario: str) -> None:
    _ = usuario
    df = _load_movements_df(limit=1000)

    if df.empty:
        st.info("No hay movimientos registrados.")
        return

    f1, f2 = st.columns([2, 1])
    buscar = f1.text_input("🔎 Buscar movimiento", placeholder="referencia, producto, usuario...")
    tipo = f2.selectbox("Tipo", ["Todos", "entrada", "salida", "ajuste"])

    view = df.copy()
    view = _filter_df_by_query(view, buscar, ["referencia", "nombre", "sku", "usuario"])
    if tipo != "Todos":
        view = view[view["tipo"] == tipo]

    st.metric("💵 Valor movimientos visibles", f"$ {float(view['costo_total_usd'].sum() if not view.empty else 0):,.2f}")

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": "ID",
            "fecha": "Fecha",
            "usuario": "Usuario",
            "sku": "SKU",
            "nombre": "Producto",
            "tipo": "Tipo",
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo unitario", format="%.2f"),
            "costo_total_usd": st.column_config.NumberColumn("Costo total", format="%.2f"),
            "referencia": "Referencia",
        },
    )



