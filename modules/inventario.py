from __future__ import annotations

import re
from datetime import date

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


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)

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
        conn.execute(
            """
            UPDATE historial_compras
            SET tipo_pago = COALESCE(NULLIF(tipo_pago, ''), 'contado'),
                monto_pagado_inicial_usd = CASE
                    WHEN COALESCE(tipo_pago, 'contado') = 'contado' AND COALESCE(monto_pagado_inicial_usd, 0) = 0
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
                    WHEN COALESCE(fiscal_credito_iva_deducible, 1) = 1 THEN ROUND(COALESCE(costo_total_usd, 0) * (COALESCE(impuestos, 0) / 100.0), 4)
                    ELSE 0
                END,
                fiscal_credito_iva_deducible = CASE
                    WHEN COALESCE(fiscal_credito_iva_deducible, 1) IN (0,1) THEN COALESCE(fiscal_credito_iva_deducible, 1)
                    ELSE 1
                END
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id)")


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
    return float(qty), "unidad", ""


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


def _get_or_create_provider(conn, proveedor_nombre: str) -> int | None:
    name = clean_text(proveedor_nombre)
    if not name:
        return None
    row = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    conn.execute("INSERT INTO proveedores(nombre, activo) VALUES(?,1)", (name,))
    new_row = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (name,)).fetchone()
    return int(new_row["id"]) if new_row else None


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
            (usuario, sku, nombre, categoria, unidad, stock_inicial, stock_minimo, money(costo), money(precio)),
        )
        return int(cur.lastrowid)


def add_inventory_movement(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
    conn=None,
) -> None:
    if tipo not in {"entrada", "salida", "ajuste"}:
        raise ValueError("Tipo de movimiento inválido")

    costo_unitario_usd = as_positive(costo_unitario_usd, "Costo unitario")
    referencia = clean_text(referencia)

    if tipo == "ajuste":
        delta = float(cantidad)
        if delta == 0:
            raise ValueError("En ajuste la cantidad no puede ser 0")
    else:
        qty = as_positive(cantidad, "Cantidad", allow_zero=False)
        delta = qty if tipo == "entrada" else -qty

    def _exec(connection):
        row = connection.execute(
            "SELECT stock_actual FROM inventario WHERE id=? AND estado='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Producto no existe o está inactivo")

        stock_actual = float(row["stock_actual"] or 0.0)
        nuevo = stock_actual + float(delta)
        if nuevo < 0:
            raise ValueError("Stock insuficiente para registrar salida/ajuste")

        connection.execute(
            """
            INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (usuario, int(inventario_id), tipo, float(delta), money(costo_unitario_usd), referencia),
        )
        connection.execute(
            "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
            (float(delta), int(inventario_id)),
        )

    if conn is not None:
        _exec(conn)
    else:
        with db_transaction() as tx:
            _exec(tx)


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
    referencia_extra: str = "",
    financial_input: CompraFinancialInput | None = None,
) -> None:
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
            "SELECT nombre, unidad, stock_actual, costo_unitario_usd FROM inventario WHERE id=? AND estado='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Producto no encontrado")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nueva_cantidad = stock_actual + cantidad
        costo_promedio = (((stock_actual * costo_actual) + (cantidad * costo_unit)) / nueva_cantidad) if nueva_cantidad > 0 else costo_unit

        conn.execute(
            "UPDATE inventario SET costo_unitario_usd=? WHERE id=?",
            (money(costo_promedio), int(inventario_id)),
        )

        ref = f"Compra proveedor: {proveedor_nombre or 'N/A'}"
        if referencia_extra:
            ref = f"{ref} | {referencia_extra}"

        add_inventory_movement(
            usuario=usuario,
            inventario_id=int(inventario_id),
            tipo="entrada",
            cantidad=float(cantidad),
            costo_unitario_usd=float(costo_unit),
            referencia=ref,
            conn=conn,
        )

        cur_hist = conn.execute(
            """
            INSERT INTO historial_compras
            (usuario, inventario_id, proveedor_id, item, cantidad, unidad, costo_total_usd, costo_unit_usd,
             impuestos, delivery, tasa_usada, moneda_pago, tipo_pago, monto_pagado_inicial_usd,
             saldo_pendiente_usd, fecha_vencimiento, fiscal_tipo, fiscal_tasa_iva, fiscal_iva_credito_usd, fiscal_credito_iva_deducible, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
                monto_moneda=float(monto_pagado_inicial_usd if str(moneda_pago).upper() == "USD" else costo_total_usd * (monto_pagado_inicial_usd / max(float(costo_total_usd), 0.0001)) * float(tasa_usada)),
                tasa_cambio=float(tasa_usada or 1.0),
                metodo_pago=str(moneda_pago).lower(),
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
            "SELECT id FROM inventario WHERE nombre=? AND estado='activo'",
            (clean_text(nombre),),
        ).fetchone()
        if row:
            return int(row["id"])

        desired_sku = sku_base if clean_text(sku_base) else nombre
        sku = _build_unique_sku(conn, desired_sku)
        cur = conn.execute(
            """
            INSERT INTO inventario(usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd)            
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
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
            WHERE estado='activo'
            ORDER BY nombre ASC
            """
        ).fetchall()
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
            WHERE m.estado='activo'
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
            WHERE m.estado='activo'
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
            SELECT id, nombre, telefono, rif, contacto, observaciones, COALESCE(especialidades,'') AS especialidades, fecha_creacion
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

    # Algunas instalaciones antiguas/devuelven filas sin etiquetas (RangeIndex).
    # Normalizamos siempre la estructura para evitar KeyError al acceder por nombre.
    if list(df.columns) != cols:
        if df.shape[1] == len(cols):
            df.columns = cols
        else:
            df = df.reindex(columns=cols)

    return df


def _load_cuentas_por_pagar_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT cxp.id,
                   cxp.fecha,
                   cxp.compra_id,
                   COALESCE(p.nombre, 'SIN PROVEEDOR') AS proveedor,
                   hc.item,
                   hc.tipo_pago,
                   cxp.monto_original_usd,
                   cxp.monto_pagado_usd,
                   cxp.saldo_usd,
                   CASE
                       WHEN cxp.saldo_usd <= 0 THEN 'pagada'
                       WHEN cxp.fecha_vencimiento IS NOT NULL AND DATE(cxp.fecha_vencimiento) < DATE('now') THEN 'vencida'
                       ELSE cxp.estado
                   END AS estado,
                   cxp.fecha_vencimiento,
                   cxp.notas
            FROM cuentas_por_pagar_proveedores cxp
            LEFT JOIN proveedores p ON p.id = cxp.proveedor_id
            LEFT JOIN historial_compras hc ON hc.id = cxp.compra_id
            ORDER BY
                CASE
                    WHEN cxp.saldo_usd > 0 AND cxp.fecha_vencimiento IS NOT NULL THEN 0
                    ELSE 1
                END,
                cxp.fecha_vencimiento ASC,
                cxp.fecha DESC
            """
        ).fetchall()
    cols = [
        "id",
        "fecha",
        "compra_id",
        "proveedor",
        "item",
        "tipo_pago",
        "monto_original_usd",
        "monto_pagado_usd",
        "saldo_usd",
        "estado",
        "fecha_vencimiento",
        "notas",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_pagos_proveedores_df(cuenta_por_pagar_id: int | None = None) -> pd.DataFrame:
    params: tuple = ()
    sql = """
        SELECT pp.id,
               pp.fecha,
               pp.cuenta_por_pagar_id,
               COALESCE(p.nombre, 'SIN PROVEEDOR') AS proveedor,
               pp.monto_usd,
               pp.moneda_pago,
               pp.monto_moneda_pago,
               pp.tasa_cambio,
               pp.referencia,
               pp.observaciones
        FROM pagos_proveedores pp
        LEFT JOIN proveedores p ON p.id = pp.proveedor_id
    """
    if cuenta_por_pagar_id is not None:
        sql += " WHERE pp.cuenta_por_pagar_id=?"
        params = (int(cuenta_por_pagar_id),)
    sql += " ORDER BY pp.fecha DESC, pp.id DESC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    cols = [
        "id",
        "fecha",
        "cuenta_por_pagar_id",
        "proveedor",
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
        "monto_pagado_inicial_usd",
        "saldo_pendiente_usd",
        "fecha_vencimiento",
    ]
    return pd.DataFrame(rows, columns=cols)


# ============================================================
# UI
# ============================================================

def render_inventario(usuario: str) -> None:
    _ensure_inventory_support_tables()
    _ensure_config_defaults()

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)
    tasa_binance = float(st.session_state.get("tasa_binance", 38.0) or 38.0)

    st.subheader("📦 Centro de Control de Suministros")
    df = _load_inventory_df()

    c1, c2, c3, c4 = st.columns(4)
    total_items = int(len(df))
    capital_total = float(df["valor_stock"].sum()) if not df.empty else 0.0
    criticos = int((df["stock_actual"] <= df["stock_minimo"]).sum()) if not df.empty else 0
    salud = ((total_items - criticos) / total_items * 100) if total_items else 0.0
    c1.metric("💰 Capital en Inventario", f"${capital_total:,.2f}")
    c2.metric("📦 Total Ítems", total_items)
    c3.metric("🚨 Stock Bajo", criticos, delta="Revisar" if criticos else "OK", delta_color="inverse")
    c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")
    st.progress(min(max(salud / 100.0, 0.0), 1.0))
  
    with st.expander("📨 Solicitudes recibidas desde Diagnóstico IA", expanded=False):
        df_diag_mov = _load_diagnostico_movimientos(limit=25)
        if df_diag_mov.empty:
            st.caption("No hay consumos enviados desde Diagnóstico IA todavía.")
        else:
            st.dataframe(df_diag_mov, use_container_width=True, hide_index=True)

    tabs = st.tabs(["📋 Existencias", "📥 Registrar Compra", "📊 Historial Compras", "👤 Proveedores", "🔧 Ajustes"])

    with tabs[0]:
        st.subheader("📋 Existencias actuales")
        if df.empty:
            st.info("No hay productos activos.")
        else:
            buscar_inv = st.text_input("🔎 Buscar producto", key="inv_existencias_buscar")
            view_inv = df.copy()
            if buscar_inv:
                view_inv = view_inv[
                    view_inv["sku"].astype(str).str.contains(buscar_inv, case=False, na=False)
                    | view_inv["nombre"].astype(str).str.contains(buscar_inv, case=False, na=False)
                    | view_inv["categoria"].astype(str).str.contains(buscar_inv, case=False, na=False)
                ]
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

    with tabs[1]:
        st.subheader("📥 Registrar Compra")

        with db_transaction() as conn:
            items_rows = conn.execute(
                "SELECT id, sku, nombre, categoria, unidad, costo_unitario_usd, precio_venta_usd FROM inventario WHERE estado='activo' ORDER BY nombre"
            ).fetchall()
        items_map = {int(r["id"]): r for r in items_rows}

        modo_item = st.radio("Ítem", ["Usar existente", "Crear y comprar"], horizontal=True, key="inv_compra_modo_item")
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
            tipo_unidad = cnew4.selectbox("Tipo unidad", ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"], key="inv_compra_new_tipo_unidad")
            cantidad, unidad_resuelta, _ = _calc_stock_by_unit_type(tipo_unidad)
            nuevo_min = st.number_input("Stock mínimo", min_value=0.0, value=0.0, key="inv_compra_new_min")
            costo_base = st.number_input("Costo inicial unitario USD", min_value=0.0, value=0.0, format="%.4f", key="inv_compra_new_costo")
            precio_base = st.number_input("Precio inicial USD", min_value=0.0, value=0.0, format="%.4f", key="inv_compra_new_precio")
        else:
            cantidad = st.number_input("Cantidad comprada", min_value=0.001, value=1.0, key="inv_compra_qty_existente")
            unidad_resuelta = str(items_map[inv_id]["unidad"]) if inv_id in items_map else "unidad"

        d1, d2, d3 = st.columns(3)
        proveedor_nombre = d1.text_input("Proveedor", key="inv_compra_proveedor")
        costo_total = d2.number_input("Costo total USD", min_value=0.0001, value=1.0, format="%.4f", key="inv_compra_total")
        impuesto_pct = d3.number_input("Impuesto (%)", min_value=0.0, max_value=100.0, value=float(st.session_state.get("inv_impuesto_default", 16.0)), format="%.2f", key="inv_compra_impuesto")

        d4, d5, d6 = st.columns(3)
        delivery_monto = d4.number_input("Delivery", min_value=0.0, value=float(st.session_state.get("inv_delivery_default", 0.0)), format="%.4f", key="inv_compra_delivery")
        delivery_moneda = d5.selectbox("Moneda delivery", ["USD", "VES (BCV)", "VES (Binance)"], key="inv_compra_delivery_moneda")
        delivery_manual = d6.checkbox("Tasa manual delivery", key="inv_compra_delivery_manual")
        delivery_usd, tasa_delivery = _resolve_delivery_usd(delivery_monto, delivery_moneda, tasa_bcv, tasa_binance, delivery_manual)

        p1, p2, p3, p4 = st.columns(4)
        tipo_pago = p1.selectbox("Tipo de pago", ["contado", "credito"], key="inv_compra_tipo_pago")
        monto_pagado = p2.number_input("Pago inicial USD", min_value=0.0, value=float(costo_total if tipo_pago == "contado" else 0.0), format="%.4f", key="inv_compra_pagado")
        fecha_venc = p3.date_input("Vence", value=None, key="inv_compra_vence")
        moneda_pago = p4.selectbox("Moneda pago", ["USD", "VES (BCV)", "VES (Binance)"], key="inv_compra_moneda")
        tasa_pago = _rate_from_label(moneda_pago, tasa_bcv, tasa_binance)
        if p4.checkbox("Tasa manual pago", key="inv_compra_tasa_manual"):
            tasa_pago = st.number_input("Tasa usada en pago", min_value=0.0001, value=float(tasa_pago), format="%.4f", key="inv_compra_tasa_pago")

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

                with db_transaction() as conn:
                    proveedor_id = _get_or_create_provider(conn, proveedor_nombre)
                fin_input = CompraFinancialInput(
                    tipo_pago=clean_text(tipo_pago).lower(),
                    monto_pagado_inicial_usd=float(monto_pagado),
                    fecha_vencimiento=fecha_venc.isoformat() if fecha_venc else None,
                )
                registrar_compra(
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
                    financial_input=fin_input,
                )
                st.success(f"Compra registrada en {money(cantidad)} {unidad_resuelta}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo registrar la compra: {exc}")

    with tabs[2]:
        st.subheader("📊 Historial de Compras")
        df_hist = _load_historial_compras_df(limit=2000)
        if df_hist.empty:
            st.info("No hay compras registradas.")
        else:
            h1, h2 = st.columns([2, 1])
            buscar_hist = h1.text_input("🔎 Buscar compra", key="inv_hist_buscar")
            tipo_hist = h2.selectbox("Condición", ["Todos", "contado", "credito"], key="inv_hist_tipo")
            view_hist = df_hist.copy()
            if buscar_hist:
                view_hist = view_hist[
                    view_hist["item"].astype(str).str.contains(buscar_hist, case=False, na=False)
                    | view_hist["proveedor"].astype(str).str.contains(buscar_hist, case=False, na=False)
                    | view_hist["sku"].astype(str).str.contains(buscar_hist, case=False, na=False)
                ]
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

    with tabs[3]:
        st.subheader("👤 Directorio de Proveedores")
        df_prov = _load_proveedores_df()

        if df_prov.empty:
            st.info("No hay proveedores registrados todavía.")
        else:
            cfp1, cfp2 = st.columns([2, 1])
            filtro = cfp1.text_input("🔍 Buscar proveedor")


            # especialidades disponibles para filtro
            tags = set()
            for txt in df_prov["especialidades"].fillna("").astype(str):
                for t in [clean_text(x) for x in txt.split(",") if clean_text(x)]:
                    tags.add(t)
            selected_tags = cfp2.multiselect("Filtrar por especialidad", sorted(tags))

            df_view = df_prov.copy()
            if filtro:
                df_view = df_view[df_view.astype(str).apply(lambda x: x.str.contains(filtro, case=False, na=False)).any(axis=1)]
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
                            "UPDATE proveedores SET telefono=?, rif=?, contacto=?, observaciones=?, especialidades=?, activo=1 WHERE id=?",
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
                            "INSERT INTO proveedores(nombre, telefono, rif, contacto, observaciones, especialidades, activo) VALUES(?,?,?,?,?,?,1)",
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
            sel = st.selectbox("Proveedor a eliminar", df_prov["id"].tolist(), format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]))
            if st.button("🗑 Eliminar proveedor"):
                with db_transaction() as conn:
                    compras = conn.execute("SELECT COUNT(*) AS c FROM historial_compras WHERE proveedor_id=? AND COALESCE(activo,1)=1", (int(sel),)).fetchone()
                    if int(compras["c"] or 0) > 0:
                        st.error("Tiene compras asociadas")
                    else:
                        conn.execute("UPDATE proveedores SET activo=0 WHERE id=?", (int(sel),))
                        st.success("Proveedor eliminado")
                        st.rerun()

    with tabs[4]:
        st.subheader("🔧 Ajustes de Inventario 360°")

        df_adj = _load_inventory_df()
        if df_adj.empty:
            st.info("No hay productos activos para ajustar.")
        else:
            t1, t2, t3, t4 = st.tabs([
                "🧮 Stock",
                "💲 Costos y Precios",
                "📦 Políticas",
                "🧹 Mantenimiento",
            ])

            with t1:
                st.caption("Ajustes de stock por reconteo individual y por lote.")
                a1, a2 = st.tabs(["Individual", "Masivo por CSV"])

                with a1:
                    aid = st.selectbox(
                        "Producto",
                        df_adj["id"].tolist(),
                        format_func=lambda i: f"{df_adj.loc[df_adj['id']==i,'nombre'].iloc[0]} ({df_adj.loc[df_adj['id']==i,'sku'].iloc[0]})",
                        key="inv_adj_stock_item",
                    )
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
                                preview = recon.copy()
                                st.dataframe(preview.head(20), use_container_width=True)
                                if st.button("⚙️ Aplicar ajustes masivos desde CSV"):
                                    with db_transaction() as conn:
                                        updated = 0
                                        for r in recon.itertuples(index=False):
                                            sku = clean_text(getattr(r, "sku", ""))
                                            stock_f = _safe_float(getattr(r, "stock_fisico", 0.0), 0.0)
                                            row = conn.execute("SELECT id, stock_actual, costo_unitario_usd FROM inventario WHERE sku=? AND estado='activo'", (sku,)).fetchone()
                                            if not row:
                                                continue
                                            delta = float(stock_f) - float(row["stock_actual"] or 0.0)
                                            if abs(delta) < 1e-9:
                                                continue
                                            add_inventory_movement(
                                                usuario=usuario,
                                                inventario_id=int(row["id"]),
                                                tipo="ajuste",
                                                cantidad=float(delta),
                                                costo_unitario_usd=float(row["costo_unitario_usd"] or 0.0),
                                                referencia="Ajuste masivo por CSV",
                                                conn=conn,
                                            )
                                            updated += 1
                                    st.success(f"Ajustes aplicados en {updated} productos")
                                    st.rerun()
                        except Exception as exc:
                            st.error(f"Error procesando CSV: {exc}")

            with t2:
                rid = st.selectbox(
                    "Producto a revalorizar",
                    df_adj["id"].tolist(),
                    format_func=lambda i: f"{df_adj.loc[df_adj['id']==i,'nombre'].iloc[0]} ({df_adj.loc[df_adj['id']==i,'sku'].iloc[0]})",
                    key="inv_adj_reval_item",
                )
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
                        rows = conn.execute("SELECT id, stock_actual, stock_minimo FROM inventario WHERE estado='activo'").fetchall()
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
                mid = st.selectbox(
                    "Producto",
                    df_adj["id"].tolist(),
                    format_func=lambda i: f"{df_adj.loc[df_adj['id']==i,'nombre'].iloc[0]} ({df_adj.loc[df_adj['id']==i,'sku'].iloc[0]})",
                    key="inv_maint_item",
                )
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
            impuesto = st.number_input("Impuesto default compras (%)", min_value=0.0, max_value=100.0, value=float(cfg_map.get("inv_impuesto_default", 16.0)), format="%.2f")
            delivery = st.number_input("Delivery default ($)", min_value=0.0, value=float(cfg_map.get("inv_delivery_default", 0.0)), format="%.2f")
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
    if buscar:
        view = view[
            view["referencia"].astype(str).str.contains(buscar, case=False, na=False)
            | view["nombre"].astype(str).str.contains(buscar, case=False, na=False)
            | view["sku"].astype(str).str.contains(buscar, case=False, na=False)
            | view["usuario"].astype(str).str.contains(buscar, case=False, na=False)
        ]
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







