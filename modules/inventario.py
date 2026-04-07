from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from pathlib import Path
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
# INTEGRACION ENTRE MODULOS (FALLBACK SEGURO)
# ============================================================


try:
    from modules.integration_hub import dispatch_to_module, render_send_buttons
except Exception:
    def dispatch_to_module(
        source_module: str,
        target_module: str,
        payload: dict[str, Any],
        success_message: str | None = None,
        session_key: str | None = None,
    ) -> None:
        if "module_inbox" not in st.session_state:
            st.session_state["module_inbox"] = {}
        st.session_state["module_inbox"][target_module] = payload
        if success_message:
            st.success(success_message)

    def render_send_buttons(
        source_module: str,
        payload_builders: dict[str, Any],
        layout: str = "horizontal",
    ) -> None:
        if not payload_builders:
            return

        items = list(payload_builders.items())
        cols = st.columns(len(items)) if layout == "horizontal" else [st] * len(items)

        for idx, (label, builder) in enumerate(items):
            btn_label = f"Enviar a {label}"
            container = cols[idx] if layout == "horizontal" else st
            if container.button(btn_label, key=f"{source_module}_send_{idx}"):
                try:
                    target_module, payload_data = builder()
                    payload = {
                        "source_module": source_module,
                        "source_action": f"send_to_{str(target_module).replace(' ', '_')}",
                        "record_id": None,
                        "referencia": "",
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "usuario": st.session_state.get("usuario", "Sistema"),
                        "payload_data": payload_data,
                    }
                    dispatch_to_module(
                        source_module=source_module,
                        target_module=target_module,
                        payload=payload,
                        success_message=f"Datos enviados a {label}.",
                    )
                except Exception as exc:
                    st.error(f"No se pudo enviar a {label}: {exc}")


# ============================================================
# CONFIG EXTRA
# ============================================================

UPLOAD_DIR = Path("uploads/proveedores")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


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


def _today_iso() -> str:
    return date.today().isoformat()


def _next_code(prefix: str, table: str, field: str) -> str:
    with db_transaction() as conn:
        row = conn.execute(
            f"SELECT {field} FROM {table} WHERE {field} LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}-%",),
        ).fetchone()
    if not row or not row[field]:
        return f"{prefix}-0001"
    last = str(row[field]).split("-")[-1]
    n = _safe_int(last, 0) + 1
    return f"{prefix}-{n:04d}"


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


def _calc_purchase_totals(costo_base_usd: float, impuestos_pct: float, delivery_usd: float) -> tuple[float, float, float]:
    base = float(costo_base_usd or 0.0)
    impuesto = base * (float(impuestos_pct or 0.0) / 100.0)
    delivery = float(delivery_usd or 0.0)
    total = base + impuesto + delivery
    return float(base), float(impuesto), float(total)


def _save_uploaded_support_file(file_obj, provider_id: int | None, reference_type: str, reference_id: int | None) -> str | None:
    if file_obj is None:
        return None

    original_name = Path(file_obj.name).name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{stamp}_{clean_text(original_name).replace(' ', '_')}"
    target = UPLOAD_DIR / safe_name

    with open(target, "wb") as f:
        f.write(file_obj.getbuffer())

    return str(target)


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

        prov_cols = {r[1] for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()}
        if "especialidades" not in prov_cols:
            conn.execute("ALTER TABLE proveedores ADD COLUMN especialidades TEXT")

        extra_provider_columns = {
            "email": "TEXT",
            "direccion": "TEXT",
            "ciudad": "TEXT",
            "pais": "TEXT",
            "condicion_pago_default": "TEXT DEFAULT 'contado'",
            "dias_credito_default": "INTEGER DEFAULT 0",
            "moneda_default": "TEXT DEFAULT 'USD'",
            "metodo_pago_default": "TEXT DEFAULT 'transferencia'",
            "banco": "TEXT",
            "datos_bancarios": "TEXT",
            "tipo_proveedor": "TEXT DEFAULT 'general'",
            "estatus_comercial": "TEXT DEFAULT 'aprobado'",
            "lead_time_dias": "INTEGER DEFAULT 0",
            "pedido_minimo_usd": "REAL DEFAULT 0",
            "ultima_compra": "TEXT",
        }
        for name, ddl in extra_provider_columns.items():
            if name not in prov_cols:
                conn.execute(f"ALTER TABLE proveedores ADD COLUMN {name} {ddl}")

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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedor_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                sku_proveedor TEXT,
                nombre_proveedor_item TEXT,
                unidad_compra TEXT,
                equivalencia_unidad REAL DEFAULT 1,
                precio_referencia_usd REAL DEFAULT 0,
                moneda_referencia TEXT DEFAULT 'USD',
                pedido_minimo REAL DEFAULT 0,
                lead_time_dias INTEGER DEFAULT 0,
                proveedor_principal INTEGER DEFAULT 0,
                activo INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(proveedor_id, inventario_id),
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_compra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                proveedor_id INTEGER NOT NULL,
                estado TEXT NOT NULL DEFAULT 'borrador',
                moneda TEXT NOT NULL DEFAULT 'USD',
                tasa_cambio REAL NOT NULL DEFAULT 1,
                subtotal_usd REAL NOT NULL DEFAULT 0,
                impuesto_usd REAL NOT NULL DEFAULT 0,
                delivery_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                condicion_pago TEXT NOT NULL DEFAULT 'contado',
                fecha_entrega_estimada TEXT,
                fecha_cierre TEXT,
                observaciones TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_compra_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_compra_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                descripcion TEXT,
                cantidad REAL NOT NULL,
                cantidad_recibida REAL NOT NULL DEFAULT 0,
                unidad TEXT,
                costo_unit_usd REAL NOT NULL DEFAULT 0,
                impuesto_pct REAL NOT NULL DEFAULT 0,
                subtotal_usd REAL NOT NULL DEFAULT 0,
                impuesto_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                estado_linea TEXT NOT NULL DEFAULT 'pendiente',
                FOREIGN KEY (orden_compra_id) REFERENCES ordenes_compra(id),
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recepciones_orden_compra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_compra_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'recibida',
                observaciones TEXT,
                FOREIGN KEY (orden_compra_id) REFERENCES ordenes_compra(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recepciones_orden_compra_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recepcion_id INTEGER NOT NULL,
                orden_detalle_id INTEGER NOT NULL,
                inventario_id INTEGER NOT NULL,
                cantidad_recibida REAL NOT NULL,
                costo_unit_usd REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (recepcion_id) REFERENCES recepciones_orden_compra(id),
                FOREIGN KEY (orden_detalle_id) REFERENCES ordenes_compra_detalle(id),
                FOREIGN KEY (inventario_id) REFERENCES inventario(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluaciones_proveedor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                proveedor_id INTEGER NOT NULL,
                usuario TEXT NOT NULL,
                calidad INTEGER NOT NULL DEFAULT 0,
                entrega INTEGER NOT NULL DEFAULT 0,
                precio INTEGER NOT NULL DEFAULT 0,
                soporte INTEGER NOT NULL DEFAULT 0,
                incidencia TEXT,
                comentario TEXT,
                calificacion_general REAL NOT NULL DEFAULT 0,
                decision TEXT NOT NULL DEFAULT 'aprobado',
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedor_documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor_id INTEGER,
                tipo_referencia TEXT NOT NULL DEFAULT 'general',
                referencia_id INTEGER,
                titulo TEXT,
                tipo_documento TEXT,
                nombre_archivo TEXT,
                ruta_archivo TEXT,
                url_externa TEXT,
                fecha_documento TEXT,
                fecha_vencimiento TEXT,
                observaciones TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_compra ON cuotas_compra_proveedor(compra_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_fecha ON cuotas_compra_proveedor(fecha_vencimiento)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_compra_proveedor_estado ON cuotas_compra_proveedor(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proveedor_items_proveedor ON proveedor_items(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proveedor_items_inventario ON proveedor_items(inventario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_proveedor ON ordenes_compra(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_estado ON ordenes_compra(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_proveedor ON evaluaciones_proveedor(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_proveedor ON proveedor_documentos(proveedor_id)")


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
    costo_base_usd: float | None = None,
    proveedor_id: int | None = None,
    proveedor_nombre: str = "",
    impuestos_pct: float = 0.0,
    delivery_usd: float = 0.0,
    tasa_usada: float = 1.0,
    moneda_pago: str = "USD",
    metodo_pago: str = "transferencia",
    referencia_extra: str = "",
    financial_input: CompraFinancialInput | None = None,
    costo_total_usd: float | None = None,
) -> int:
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_compra_ref = costo_base_usd if costo_base_usd is not None else costo_total_usd
    costo_base_usd = as_positive(costo_compra_ref, "Costo base", allow_zero=False)
    impuestos_pct = max(0.0, float(impuestos_pct or 0.0))
    delivery_usd = max(0.0, float(delivery_usd or 0.0))

    base_usd, impuesto_usd, total_compra_usd = _calc_purchase_totals(
        costo_base_usd=float(costo_base_usd),
        impuestos_pct=float(impuestos_pct),
        delivery_usd=float(delivery_usd),
    )
    costo_unit = total_compra_usd / cantidad
    financial_input = financial_input or CompraFinancialInput()

    monto_pagado_inicial_usd, saldo_pendiente_usd = validar_condicion_compra(
        total_compra_usd=float(total_compra_usd),
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

        ref = (
            f"Compra proveedor: {proveedor_nombre or 'N/A'} | "
            f"Base: ${base_usd:,.2f} | IVA: ${impuesto_usd:,.2f} | Delivery: ${delivery_usd:,.2f}"
        )
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
                money(total_compra_usd),
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
                round(float(impuesto_usd), 4),
                1,
                clean_text(metodo_pago).lower() or "efectivo",
            ),
        )
        compra_id = int(cur_hist.lastrowid)

        if proveedor_id is not None:
            conn.execute(
                "UPDATE proveedores SET ultima_compra=? WHERE id=?",
                (_today_iso(), int(proveedor_id)),
            )

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
                    else total_compra_usd
                    * (monto_pagado_inicial_usd / max(float(total_compra_usd), 0.0001))
                    * float(tasa_usada)
                ),
                tasa_cambio=float(tasa_usada or 1.0),
                metodo_pago=clean_text(metodo_pago).lower() or str(moneda_pago).lower(),
                usuario=usuario,
                metadata={
                    "modulo": "inventario",
                    "tipo_pago_compra": clean_text(financial_input.tipo_pago).lower(),
                    "proveedor_id": int(proveedor_id) if proveedor_id is not None else None,
                    "costo_base_usd": float(base_usd),
                    "impuesto_usd": float(impuesto_usd),
                    "delivery_usd": float(delivery_usd),
                    "total_compra_usd": float(total_compra_usd),
                },
            )

        crear_cuenta_por_pagar_desde_compra(
            conn,
            usuario=usuario,
            compra_id=compra_id,
            proveedor_id=proveedor_id,
            total_compra_usd=float(total_compra_usd),
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
# SERVICIOS NUEVOS COMPRAS / PROVEEDORES
# ============================================================

def save_proveedor_full(data: dict[str, Any]) -> int:
    nombre = require_text(data.get("nombre"), "Nombre")

    with db_transaction() as conn:
        existing = None
        proveedor_id = data.get("id")
        if proveedor_id:
            existing = conn.execute("SELECT id FROM proveedores WHERE id=?", (int(proveedor_id),)).fetchone()
        if not existing:
            existing = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (nombre,)).fetchone()

        payload = (
            nombre,
            clean_text(data.get("telefono")),
            clean_text(data.get("rif")),
            clean_text(data.get("contacto")),
            clean_text(data.get("observaciones")),
            clean_text(data.get("especialidades")),
            clean_text(data.get("email")),
            clean_text(data.get("direccion")),
            clean_text(data.get("ciudad")),
            clean_text(data.get("pais")),
            clean_text(data.get("condicion_pago_default") or "contado").lower(),
            _safe_int(data.get("dias_credito_default"), 0),
            clean_text(data.get("moneda_default") or "USD"),
            clean_text(data.get("metodo_pago_default") or "transferencia").lower(),
            clean_text(data.get("banco")),
            clean_text(data.get("datos_bancarios")),
            clean_text(data.get("tipo_proveedor") or "general").lower(),
            clean_text(data.get("estatus_comercial") or "aprobado").lower(),
            _safe_int(data.get("lead_time_dias"), 0),
            _safe_float(data.get("pedido_minimo_usd"), 0.0),
            data.get("ultima_compra"),
        )

        if existing:
            conn.execute(
                """
                UPDATE proveedores
                SET nombre=?, telefono=?, rif=?, contacto=?, observaciones=?, especialidades=?,
                    email=?, direccion=?, ciudad=?, pais=?, condicion_pago_default=?, dias_credito_default=?,
                    moneda_default=?, metodo_pago_default=?, banco=?, datos_bancarios=?, tipo_proveedor=?,
                    estatus_comercial=?, lead_time_dias=?, pedido_minimo_usd=?, ultima_compra=?, activo=1
                WHERE id=?
                """,
                payload + (int(existing["id"]),),
            )
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO proveedores(
                nombre, telefono, rif, contacto, observaciones, especialidades,
                email, direccion, ciudad, pais, condicion_pago_default, dias_credito_default,
                moneda_default, metodo_pago_default, banco, datos_bancarios, tipo_proveedor,
                estatus_comercial, lead_time_dias, pedido_minimo_usd, ultima_compra, activo
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            payload,
        )
        return int(cur.lastrowid)


def save_proveedor_item(data: dict[str, Any]) -> int:
    proveedor_id = _safe_int(data.get("proveedor_id"))
    inventario_id = _safe_int(data.get("inventario_id"))
    if not proveedor_id or not inventario_id:
        raise ValueError("Proveedor y producto son obligatorios.")

    with db_transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM proveedor_items WHERE proveedor_id=? AND inventario_id=?",
            (proveedor_id, inventario_id),
        ).fetchone()

        payload = (
            clean_text(data.get("sku_proveedor")),
            clean_text(data.get("nombre_proveedor_item")),
            clean_text(data.get("unidad_compra") or "unidad"),
            _safe_float(data.get("equivalencia_unidad"), 1.0),
            _safe_float(data.get("precio_referencia_usd"), 0.0),
            clean_text(data.get("moneda_referencia") or "USD"),
            _safe_float(data.get("pedido_minimo"), 0.0),
            _safe_int(data.get("lead_time_dias"), 0),
            1 if data.get("proveedor_principal") else 0,
        )

        if data.get("proveedor_principal"):
            conn.execute(
                "UPDATE proveedor_items SET proveedor_principal=0 WHERE inventario_id=?",
                (inventario_id,),
            )

        if existing:
            conn.execute(
                """
                UPDATE proveedor_items
                SET sku_proveedor=?, nombre_proveedor_item=?, unidad_compra=?, equivalencia_unidad=?,
                    precio_referencia_usd=?, moneda_referencia=?, pedido_minimo=?, lead_time_dias=?,
                    proveedor_principal=?, activo=1, fecha_actualizacion=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                payload + (int(existing["id"]),),
            )
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO proveedor_items(
                proveedor_id, inventario_id, sku_proveedor, nombre_proveedor_item, unidad_compra,
                equivalencia_unidad, precio_referencia_usd, moneda_referencia, pedido_minimo,
                lead_time_dias, proveedor_principal, activo
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (proveedor_id, inventario_id) + payload,
        )
        return int(cur.lastrowid)


def create_orden_compra(usuario: str, proveedor_id: int, header: dict[str, Any], items: list[dict[str, Any]]) -> int:
    if not items:
        raise ValueError("Debes agregar al menos un ítem a la orden de compra.")

    subtotal = 0.0
    impuesto = 0.0
    total = 0.0
    normalized: list[dict[str, Any]] = []

    for item in items:
        cantidad = _safe_float(item.get("cantidad"), 0.0)
        costo = _safe_float(item.get("costo_unit_usd"), 0.0)
        impuesto_pct = _safe_float(item.get("impuesto_pct"), 0.0)
        inventario_id = _safe_int(item.get("inventario_id"))

        if inventario_id <= 0:
            raise ValueError("Cada línea debe tener un producto válido.")
        if cantidad <= 0 or costo < 0:
            raise ValueError("Cada línea debe tener cantidad > 0 y costo válido.")

        line_sub = cantidad * costo
        line_tax = line_sub * (impuesto_pct / 100.0)
        line_total = line_sub + line_tax
        subtotal += line_sub
        impuesto += line_tax
        total += line_total

        normalized.append(
            {
                "inventario_id": inventario_id,
                "descripcion": clean_text(item.get("descripcion")),
                "cantidad": cantidad,
                "unidad": clean_text(item.get("unidad") or "unidad"),
                "costo_unit_usd": costo,
                "impuesto_pct": impuesto_pct,
                "subtotal_usd": line_sub,
                "impuesto_usd": line_tax,
                "total_usd": line_total,
            }
        )

    delivery = _safe_float(header.get("delivery_usd"), 0.0)
    total_oc = total + delivery
    code = header.get("codigo") or _next_code("OC", "ordenes_compra", "codigo")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ordenes_compra(
                codigo, fecha, usuario, proveedor_id, estado, moneda, tasa_cambio,
                subtotal_usd, impuesto_usd, delivery_usd, total_usd, condicion_pago,
                fecha_entrega_estimada, observaciones
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                code,
                _today_iso(),
                usuario,
                int(proveedor_id),
                clean_text(header.get("estado") or "emitida").lower(),
                clean_text(header.get("moneda") or "USD"),
                _safe_float(header.get("tasa_cambio"), 1.0),
                money(subtotal),
                money(impuesto),
                money(delivery),
                money(total_oc),
                clean_text(header.get("condicion_pago") or "contado").lower(),
                header.get("fecha_entrega_estimada"),
                clean_text(header.get("observaciones")),
            ),
        )
        oc_id = int(cur.lastrowid)

        for item in normalized:
            conn.execute(
                """
                INSERT INTO ordenes_compra_detalle(
                    orden_compra_id, inventario_id, descripcion, cantidad, cantidad_recibida,
                    unidad, costo_unit_usd, impuesto_pct, subtotal_usd, impuesto_usd, total_usd, estado_linea
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    oc_id,
                    int(item["inventario_id"]),
                    item["descripcion"],
                    float(item["cantidad"]),
                    0,
                    item["unidad"],
                    money(item["costo_unit_usd"]),
                    float(item["impuesto_pct"]),
                    money(item["subtotal_usd"]),
                    money(item["impuesto_usd"]),
                    money(item["total_usd"]),
                    "pendiente",
                ),
            )

    return oc_id


def receive_orden_compra(usuario: str, orden_compra_id: int, quantities: dict[int, float], referencia: str = "") -> int:
    with db_transaction() as conn:
        oc = conn.execute(
            "SELECT id, estado FROM ordenes_compra WHERE id=?",
            (int(orden_compra_id),),
        ).fetchone()
        if not oc:
            raise ValueError("La orden de compra no existe.")
        if str(oc["estado"]).lower() in {"cancelada", "cerrada"}:
            raise ValueError("La orden no admite recepción por su estado actual.")

        details = conn.execute(
            """
            SELECT id, inventario_id, cantidad, cantidad_recibida, costo_unit_usd
            FROM ordenes_compra_detalle
            WHERE orden_compra_id=?
            ORDER BY id ASC
            """,
            (int(orden_compra_id),),
        ).fetchall()
        if not details:
            raise ValueError("La orden no tiene líneas.")

        cur = conn.execute(
            """
            INSERT INTO recepciones_orden_compra(orden_compra_id, fecha, usuario, estado, observaciones)
            VALUES(?,?,?,?,?)
            """,
            (int(orden_compra_id), _today_iso(), usuario, "recibida", clean_text(referencia)),
        )
        recepcion_id = int(cur.lastrowid)

        any_received = False
        for row in details:
            det_id = int(row["id"])
            qty_to_receive = _safe_float(quantities.get(det_id), 0.0)
            if qty_to_receive <= 0:
                continue

            ordered = _safe_float(row["cantidad"])
            already = _safe_float(row["cantidad_recibida"])
            available = max(ordered - already, 0.0)
            if qty_to_receive > available + 1e-9:
                raise ValueError(f"La línea {det_id} supera lo pendiente por recibir.")

            any_received = True
            new_received = already + qty_to_receive
            estado_linea = "recibida" if new_received >= ordered - 1e-9 else "parcial"

            conn.execute(
                """
                INSERT INTO recepciones_orden_compra_detalle(
                    recepcion_id, orden_detalle_id, inventario_id, cantidad_recibida, costo_unit_usd
                ) VALUES(?,?,?,?,?)
                """,
                (
                    recepcion_id,
                    det_id,
                    int(row["inventario_id"]),
                    float(qty_to_receive),
                    money(_safe_float(row["costo_unit_usd"])),
                ),
            )

            conn.execute(
                """
                UPDATE ordenes_compra_detalle
                SET cantidad_recibida=?, estado_linea=?
                WHERE id=?
                """,
                (float(new_received), estado_linea, det_id),
            )

            conn.execute(
                """
                INSERT INTO movimientos_inventario(
                    usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    usuario,
                    int(row["inventario_id"]),
                    "entrada",
                    float(qty_to_receive),
                    money(_safe_float(row["costo_unit_usd"])),
                    f"Recepción OC #{orden_compra_id} | {referencia}".strip(" |"),
                ),
            )

            conn.execute(
                "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
                (float(qty_to_receive), int(row["inventario_id"])),
            )

        if not any_received:
            raise ValueError("Debes indicar al menos una cantidad recibida.")

        pending = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM ordenes_compra_detalle
            WHERE orden_compra_id=? AND COALESCE(estado_linea,'pendiente') != 'recibida'
            """,
            (int(orden_compra_id),),
        ).fetchone()

        if int(pending["c"] or 0) == 0:
            conn.execute(
                "UPDATE ordenes_compra SET estado='cerrada', fecha_cierre=? WHERE id=?",
                (_today_iso(), int(orden_compra_id)),
            )
        else:
            conn.execute(
                "UPDATE ordenes_compra SET estado='parcial' WHERE id=?",
                (int(orden_compra_id),),
            )

    return int(recepcion_id)


def save_evaluacion(usuario: str, proveedor_id: int, payload: dict[str, Any]) -> int:
    calidad = max(0, min(5, _safe_int(payload.get("calidad"), 0)))
    entrega = max(0, min(5, _safe_int(payload.get("entrega"), 0)))
    precio = max(0, min(5, _safe_int(payload.get("precio"), 0)))
    soporte = max(0, min(5, _safe_int(payload.get("soporte"), 0)))
    promedio = round((calidad + entrega + precio + soporte) / 4.0, 2)

    decision = clean_text(payload.get("decision") or "aprobado").lower()
    if not decision:
        if promedio >= 4.0:
            decision = "aprobado"
        elif promedio >= 3.0:
            decision = "condicionado"
        else:
            decision = "bloqueado"

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO evaluaciones_proveedor(
                fecha, proveedor_id, usuario, calidad, entrega, precio, soporte,
                incidencia, comentario, calificacion_general, decision
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _today_iso(),
                int(proveedor_id),
                usuario,
                calidad,
                entrega,
                precio,
                soporte,
                clean_text(payload.get("incidencia")),
                clean_text(payload.get("comentario")),
                promedio,
                decision,
            ),
        )
        conn.execute(
            "UPDATE proveedores SET estatus_comercial=? WHERE id=?",
            (decision, int(proveedor_id)),
        )
        return int(cur.lastrowid)

def registrar_pago_proveedor_ui(
    usuario: str,
    cuenta_por_pagar_id: int,
    monto_usd: float,
    moneda_pago: str,
    monto_moneda_pago: float,
    tasa_cambio: float,
    metodo_pago: str,
    referencia: str = "",
    observaciones: str = "",
) -> int:
    monto_usd = _safe_float(monto_usd, 0.0)
    if monto_usd <= 0:
        raise ValueError("El monto debe ser mayor a cero.")

    with db_transaction() as conn:
        cxp = conn.execute(
            """
            SELECT id, proveedor_id, compra_id, monto_original_usd, monto_pagado_usd, saldo_usd, estado
            FROM cuentas_por_pagar_proveedores
            WHERE id=?
            """,
            (int(cuenta_por_pagar_id),),
        ).fetchone()
        if not cxp:
            raise ValueError("La cuenta por pagar no existe.")

        saldo_actual = _safe_float(cxp["saldo_usd"], 0.0)
        if monto_usd > saldo_actual + 1e-9:
            raise ValueError("El pago excede el saldo pendiente.")

        cur = conn.execute(
            """
            INSERT INTO pagos_proveedores(
                fecha, usuario, cuenta_por_pagar_id, proveedor_id, monto_usd,
                moneda_pago, monto_moneda_pago, tasa_cambio, referencia, observaciones
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _today_iso(),
                usuario,
                int(cuenta_por_pagar_id),
                int(cxp["proveedor_id"]) if cxp["proveedor_id"] is not None else None,
                money(monto_usd),
                clean_text(moneda_pago) or "USD",
                money(monto_moneda_pago),
                max(_safe_float(tasa_cambio, 1.0), 0.0001),
                clean_text(referencia),
                clean_text(observaciones),
            ),
        )
        pago_id = int(cur.lastrowid)

        nuevo_pagado = _safe_float(cxp["monto_pagado_usd"], 0.0) + monto_usd
        nuevo_saldo = max(_safe_float(cxp["monto_original_usd"], 0.0) - nuevo_pagado, 0.0)
        nuevo_estado = "pagada" if nuevo_saldo <= 1e-9 else "pendiente"

        conn.execute(
            """
            UPDATE cuentas_por_pagar_proveedores
            SET monto_pagado_usd=?, saldo_usd=?, estado=?
            WHERE id=?
            """,
            (money(nuevo_pagado), money(nuevo_saldo), nuevo_estado, int(cuenta_por_pagar_id)),
        )

        conn.execute(
            """
            UPDATE historial_compras
            SET saldo_pendiente_usd=?, tipo_pago=CASE WHEN ? <= 0 THEN 'contado' ELSE tipo_pago END
            WHERE id=?
            """,
            (money(nuevo_saldo), money(nuevo_saldo), int(cxp["compra_id"])),
        )

        registrar_egreso(
            conn,
            origen="pago_proveedor",
            referencia_id=pago_id,
            descripcion=f"Pago proveedor CxP #{cuenta_por_pagar_id}",
            monto_usd=float(monto_usd),
            moneda=str(moneda_pago),
            monto_moneda=float(monto_moneda_pago),
            tasa_cambio=float(tasa_cambio or 1.0),
            metodo_pago=clean_text(metodo_pago).lower() or clean_text(moneda_pago).lower(),
            usuario=usuario,
            metadata={
                "modulo": "inventario",
                "submodulo": "pagos_proveedores",
                "cuenta_por_pagar_id": int(cuenta_por_pagar_id),
                "proveedor_id": int(cxp["proveedor_id"]) if cxp["proveedor_id"] is not None else None,
                "compra_id": int(cxp["compra_id"]),
            },
        )

    return pago_id


# ============================================================
# DATA LOADERS
# ============================================================

# ============================================================

def _load_inventory_df(include_inactive: bool = False) -> pd.DataFrame:
    cols = [
        "id",
        "fecha",
        "sku",
        "nombre",
        "categoria",
        "unidad",
        "stock_actual",
        "stock_minimo",
        "estado",
        "costo_unitario_usd",
        "precio_venta_usd",
        "valor_stock",
    ]
    where_estado = ""
    if not include_inactive:
        where_estado = "WHERE COALESCE(estado,'activo')='activo'"
    with db_transaction() as conn:
        rows = conn.execute(
            f"""
            SELECT id, fecha, sku, nombre, categoria, unidad, stock_actual, stock_minimo,
                   COALESCE(estado,'activo') AS estado,
                   costo_unitario_usd, precio_venta_usd,
                   (stock_actual * costo_unitario_usd) AS valor_stock
            FROM inventario
            {where_estado}
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


def _load_proveedores_full_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                nombre,
                telefono,
                email,
                rif,
                contacto,
                direccion,
                ciudad,
                pais,
                observaciones,
                especialidades,
                condicion_pago_default,
                dias_credito_default,
                moneda_default,
                metodo_pago_default,
                banco,
                datos_bancarios,
                tipo_proveedor,
                estatus_comercial,
                lead_time_dias,
                pedido_minimo_usd,
                ultima_compra,
                fecha_creacion
            FROM proveedores
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre ASC
            """
        ).fetchall()

    cols = [
        "id",
        "nombre",
        "telefono",
        "email",
        "rif",
        "contacto",
        "direccion",
        "ciudad",
        "pais",
        "observaciones",
        "especialidades",
        "condicion_pago_default",
        "dias_credito_default",
        "moneda_default",
        "metodo_pago_default",
        "banco",
        "datos_bancarios",
        "tipo_proveedor",
        "estatus_comercial",
        "lead_time_dias",
        "pedido_minimo_usd",
        "ultima_compra",
        "fecha_creacion",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_proveedor_items_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                pi.id,
                pi.proveedor_id,
                p.nombre AS proveedor,
                pi.inventario_id,
                i.sku,
                i.nombre AS producto,
                pi.sku_proveedor,
                pi.nombre_proveedor_item,
                pi.unidad_compra,
                pi.equivalencia_unidad,
                pi.precio_referencia_usd,
                pi.moneda_referencia,
                pi.pedido_minimo,
                pi.lead_time_dias,
                pi.proveedor_principal,
                pi.activo
            FROM proveedor_items pi
            JOIN proveedores p ON p.id = pi.proveedor_id
            JOIN inventario i ON i.id = pi.inventario_id
            WHERE COALESCE(pi.activo,1)=1
            ORDER BY p.nombre ASC, i.nombre ASC
            """
        ).fetchall()

    cols = [
        "id",
        "proveedor_id",
        "proveedor",
        "inventario_id",
        "sku",
        "producto",
        "sku_proveedor",
        "nombre_proveedor_item",
        "unidad_compra",
        "equivalencia_unidad",
        "precio_referencia_usd",
        "moneda_referencia",
        "pedido_minimo",
        "lead_time_dias",
        "proveedor_principal",
        "activo",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_ordenes_compra_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                oc.id,
                oc.codigo,
                oc.fecha,
                oc.usuario,
                p.nombre AS proveedor,
                oc.estado,
                oc.moneda,
                oc.tasa_cambio,
                oc.subtotal_usd,
                oc.impuesto_usd,
                oc.delivery_usd,
                oc.total_usd,
                oc.condicion_pago,
                oc.fecha_entrega_estimada,
                oc.fecha_cierre,
                oc.observaciones
            FROM ordenes_compra oc
            JOIN proveedores p ON p.id = oc.proveedor_id
            ORDER BY oc.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "codigo",
        "fecha",
        "usuario",
        "proveedor",
        "estado",
        "moneda",
        "tasa_cambio",
        "subtotal_usd",
        "impuesto_usd",
        "delivery_usd",
        "total_usd",
        "condicion_pago",
        "fecha_entrega_estimada",
        "fecha_cierre",
        "observaciones",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_orden_detalle_df(orden_compra_id: int | None = None) -> pd.DataFrame:
    params: tuple[Any, ...] = ()
    sql = """
        SELECT
            d.id,
            d.orden_compra_id,
            i.sku,
            i.nombre AS producto,
            d.descripcion,
            d.cantidad,
            d.cantidad_recibida,
            d.unidad,
            d.costo_unit_usd,
            d.impuesto_pct,
            d.subtotal_usd,
            d.impuesto_usd,
            d.total_usd,
            d.estado_linea
        FROM ordenes_compra_detalle d
        JOIN inventario i ON i.id = d.inventario_id
    """
    if orden_compra_id is not None:
        sql += " WHERE d.orden_compra_id=?"
        params = (int(orden_compra_id),)
    sql += " ORDER BY d.id ASC"

    with db_transaction() as conn:
        rows = conn.execute(sql, params).fetchall()

    cols = [
        "id",
        "orden_compra_id",
        "sku",
        "producto",
        "descripcion",
        "cantidad",
        "cantidad_recibida",
        "unidad",
        "costo_unit_usd",
        "impuesto_pct",
        "subtotal_usd",
        "impuesto_usd",
        "total_usd",
        "estado_linea",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_evaluaciones_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                e.id,
                e.fecha,
                p.nombre AS proveedor,
                e.usuario,
                e.calidad,
                e.entrega,
                e.precio,
                e.soporte,
                e.calificacion_general,
                e.decision,
                e.incidencia,
                e.comentario
            FROM evaluaciones_proveedor e
            JOIN proveedores p ON p.id = e.proveedor_id
            ORDER BY e.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "fecha",
        "proveedor",
        "usuario",
        "calidad",
        "entrega",
        "precio",
        "soporte",
        "calificacion_general",
        "decision",
        "incidencia",
        "comentario",
    ]
    return pd.DataFrame(rows, columns=cols)


def _load_documentos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                d.id,
                COALESCE(p.nombre, 'SIN PROVEEDOR') AS proveedor,
                d.tipo_referencia,
                d.referencia_id,
                d.titulo,
                d.tipo_documento,
                d.nombre_archivo,
                d.ruta_archivo,
                d.url_externa,
                d.fecha_documento,
                d.fecha_vencimiento,
                d.observaciones,
                d.created_at
            FROM proveedor_documentos d
            LEFT JOIN proveedores p ON p.id = d.proveedor_id
            ORDER BY d.id DESC
            """
        ).fetchall()

    cols = [
        "id",
        "proveedor",
        "tipo_referencia",
        "referencia_id",
        "titulo",
        "tipo_documento",
        "nombre_archivo",
        "ruta_archivo",
        "url_externa",
        "fecha_documento",
        "fecha_vencimiento",
        "observaciones",
        "created_at",
    ]
    return pd.DataFrame(rows, columns=cols)


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
    _ensure_inventory_support_tables()
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
# UI SECCIONES BASE
# ============================================================

def _render_inventario_dashboard(df: pd.DataFrame) -> None:
    st.subheader("📊 Panel de control de inventario")

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
            help="Solo para dejar una referencia inicial si estás creando el producto ahora.",
        )
        precio_base = st.number_input(
            "Precio inicial USD",
            min_value=0.0,
            value=0.0,
            format="%.4f",
            key="inv_compra_new_precio",
            help="Déjalo en 0 si ese producto no se vende.",
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

    costo_base_compra = d2.number_input(
        "Costo base USD (sin IVA ni delivery)",
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

    base_usd, impuesto_usd, total_compra_usd = _calc_purchase_totals(
        costo_base_usd=float(costo_base_compra),
        impuestos_pct=float(impuesto_pct),
        delivery_usd=float(delivery_usd),
    )
    costo_unit_estimado = total_compra_usd / max(float(cantidad), 0.0001)

    st.markdown("### 🧮 Resumen del costo real")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Base", f"${base_usd:,.2f}")
    r2.metric("IVA / impuesto", f"${impuesto_usd:,.2f}")
    r3.metric("Delivery", f"${delivery_usd:,.2f}")
    r4.metric("Total final", f"${total_compra_usd:,.2f}")
    st.caption(f"Costo unitario real estimado: ${costo_unit_estimado:,.4f} por {unidad_resuelta}")

    st.markdown("### 🔗 Enviar referencia a otros módulos")

    def _build_to_costeo():
        nombre_item = nuevo_nombre if modo_item == "Crear y comprar" else (
            str(items_map[inv_id]["nombre"]) if inv_id in items_map else ""
        )
        sku_item = nuevo_sku if modo_item == "Crear y comprar" else (
            str(items_map[inv_id]["sku"]) if inv_id in items_map else ""
        )
        return (
            "costeo",
            {
                "item": nombre_item,
                "sku": sku_item,
                "costo_unitario": round(float(costo_unit_estimado), 4),
                "unidad": unidad_resuelta,
                "stock": float(cantidad),
                "referencia": f"COMPRA-{sku_item or 'N/A'}",
            },
        )

    def _build_to_cxp():
        return (
            "cuentas por pagar",
            {
                "compra_id": None,
                "proveedor": clean_text(proveedor_nombre),
                "monto": round(float(total_compra_usd), 2),
                "saldo": round(max(float(total_compra_usd) - 0.0, 0.0), 2),
                "vencimiento": "",
                "referencia": f"PROV-{clean_text(proveedor_nombre) or 'N/A'}",
            },
        )

    render_send_buttons(
        source_module="inventario",
        payload_builders={"Costeo": _build_to_costeo, "Cuentas por pagar": _build_to_cxp},
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
        monto_pagado = float(total_compra_usd)
        st.success("Compra de contado: se toma el total final como pago completo.")
        st.metric("Monto pagado", f"${monto_pagado:,.2f}")
    else:
        c1, c2, c3 = st.columns(3)
        monto_pagado = c1.number_input(
            "Inicial USD",
            min_value=0.0,
            max_value=float(total_compra_usd),
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

        saldo_financiar = max(float(total_compra_usd) - float(monto_pagado), 0.0)
        if saldo_financiar <= 0:
            st.warning("No hay saldo para financiar. Revisa el monto inicial.")
        else:
            inicio = st.date_input("Fecha primera cuota", value=date.today(), key="inv_compra_primera_cuota")
            cuota_base = round(saldo_financiar / max(cantidad_cuotas, 1), 2)

            st.caption(f"Saldo a financiar: ${saldo_financiar:,.2f}")
            st.caption(f"Cuota base sugerida: ${cuota_base:,.2f}")

            delta_dias = 30 if frecuencia == "mensual" else 15 if frecuencia == "quincenal" else 7

            for i in range(cantidad_cuotas):
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
                    value=inicio + timedelta(days=(delta_dias * i)),
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

                impuesto_usd_cuota = round(float(monto_cuota) * float(impuesto_cuota) / 100.0, 2)
                total_cuota = round(float(monto_cuota) + impuesto_usd_cuota, 2)

                cuotas_generadas.append(
                    {
                        "numero_cuota": i + 1,
                        "fecha_vencimiento": fecha_cuota.isoformat(),
                        "monto_base_usd": float(monto_cuota),
                        "impuesto_pct": float(impuesto_cuota),
                        "impuesto_usd": float(impuesto_usd_cuota),
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
                costo_base_usd=float(costo_base_compra),
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

            st.success(
                f"Compra registrada en {money(cantidad)} {unidad_resuelta}. "
                f"Total real: ${total_compra_usd:,.2f}. ID compra #{compra_id}"
            )

            dispatch_to_module(
                source_module="inventario",
                target_module="cuentas por pagar",
                payload={
                    "source_module": "inventario",
                    "source_action": "compra_registrada",
                    "record_id": compra_id,
                    "referencia": clean_text(proveedor_nombre),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "usuario": usuario,
                    "payload_data": {
                        "compra_id": compra_id,
                        "proveedor": clean_text(proveedor_nombre),
                        "monto": round(float(total_compra_usd), 2),
                        "saldo": round(max(float(total_compra_usd) - float(monto_pagado), 0.0), 2),
                        "vencimiento": fecha_venc.isoformat() if fecha_venc else "",
                    },
                },
            )
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
            "costo_total_usd": st.column_config.NumberColumn("Total final USD", format="%.2f"),
            "costo_unit_usd": st.column_config.NumberColumn("Costo unitario real", format="%.4f"),
            "impuestos": st.column_config.NumberColumn("Impuesto %", format="%.2f"),
            "delivery": st.column_config.NumberColumn("Delivery USD", format="%.4f"),
            "monto_pagado_inicial_usd": st.column_config.NumberColumn("Pagado inicial", format="%.2f"),
            "saldo_pendiente_usd": st.column_config.NumberColumn("Saldo", format="%.2f"),
        },
    )


def _render_proveedores() -> None:
    st.subheader("👤 Directorio de proveedores")
    df_prov = _load_proveedores_full_df()

    if df_prov.empty:
        st.info("No hay proveedores registrados todavía.")
    else:
        cfp1, cfp2 = st.columns([2, 1])
        filtro = cfp1.text_input("🔍 Buscar proveedor")
        selected_tags = cfp2.multiselect("Filtrar por especialidad", _extract_supplier_tags(df_prov))

        df_view = df_prov.copy()
        if filtro:
            searchable_cols = [
                "nombre",
                "telefono",
                "email",
                "rif",
                "contacto",
                "direccion",
                "ciudad",
                "pais",
                "observaciones",
                "especialidades",
                "tipo_proveedor",
                "estatus_comercial",
            ]
            df_view = _filter_df_by_query(df_view, filtro, searchable_cols)

        if selected_tags:
            df_view = df_view[
                df_view["especialidades"].fillna("").astype(str).apply(
                    lambda txt: all(tag.lower() in txt.lower() for tag in selected_tags)
                )
            ]

        st.dataframe(
            df_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "dias_credito_default": st.column_config.NumberColumn("Días crédito", format="%d"),
                "lead_time_dias": st.column_config.NumberColumn("Lead time", format="%d"),
                "pedido_minimo_usd": st.column_config.NumberColumn("Pedido mínimo USD", format="%.2f"),
            },
        )

    st.divider()
    st.subheader("➕ Registrar / Editar proveedor")

    proveedor_existente = None
    if not df_prov.empty:
        pid_sel = st.selectbox(
            "Editar proveedor existente (opcional)",
            options=[None] + df_prov["id"].tolist(),
            format_func=lambda x: "Nuevo proveedor" if x is None else str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
            key="inv_prov_edit_sel",
        )
        if pid_sel is not None:
            proveedor_existente = df_prov[df_prov["id"] == pid_sel].iloc[0]

    with st.form("form_proveedor"):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Nombre", value="" if proveedor_existente is None else str(proveedor_existente["nombre"]))
        telefono = c2.text_input("Teléfono", value="" if proveedor_existente is None else str(proveedor_existente["telefono"]))
        email = c3.text_input("Email", value="" if proveedor_existente is None else str(proveedor_existente["email"]))

        c4, c5, c6 = st.columns(3)
        rif = c4.text_input("RIF", value="" if proveedor_existente is None else str(proveedor_existente["rif"]))
        contacto = c5.text_input("Contacto", value="" if proveedor_existente is None else str(proveedor_existente["contacto"]))
        tipo_proveedor = c6.selectbox(
            "Tipo proveedor",
            ["general", "materia_prima", "servicios", "logistica", "consumibles"],
            index=["general", "materia_prima", "servicios", "logistica", "consumibles"].index(
                str(proveedor_existente["tipo_proveedor"])
                if proveedor_existente is not None and str(proveedor_existente["tipo_proveedor"]) in ["general", "materia_prima", "servicios", "logistica", "consumibles"]
                else "general"
            ),
        )

        c7, c8, c9 = st.columns(3)
        ciudad = c7.text_input("Ciudad", value="" if proveedor_existente is None else str(proveedor_existente["ciudad"]))
        pais = c8.text_input("País", value="" if proveedor_existente is None else str(proveedor_existente["pais"]))
        direccion = c9.text_input("Dirección", value="" if proveedor_existente is None else str(proveedor_existente["direccion"]))

        c10, c11, c12, c13 = st.columns(4)
        condicion_pago_default = c10.selectbox(
            "Condición default",
            ["contado", "credito"],
            index=["contado", "credito"].index(
                str(proveedor_existente["condicion_pago_default"])
                if proveedor_existente is not None and str(proveedor_existente["condicion_pago_default"]) in ["contado", "credito"]
                else "contado"
            ),
        )
        dias_credito_default = c11.number_input(
            "Días crédito default",
            min_value=0,
            value=0 if proveedor_existente is None else _safe_int(proveedor_existente["dias_credito_default"], 0),
        )
        moneda_default = c12.selectbox(
            "Moneda default",
            ["USD", "VES (BCV)", "VES (Binance)"],
            index=["USD", "VES (BCV)", "VES (Binance)"].index(
                str(proveedor_existente["moneda_default"])
                if proveedor_existente is not None and str(proveedor_existente["moneda_default"]) in ["USD", "VES (BCV)", "VES (Binance)"]
                else "USD"
            ),
        )
        metodo_pago_default = c13.selectbox(
            "Método pago default",
            ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"],
            index=["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"].index(
                str(proveedor_existente["metodo_pago_default"])
                if proveedor_existente is not None and str(proveedor_existente["metodo_pago_default"]) in ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"]
                else "transferencia"
            ),
        )

        c14, c15, c16, c17 = st.columns(4)
        banco = c14.text_input("Banco", value="" if proveedor_existente is None else str(proveedor_existente["banco"]))
        datos_bancarios = c15.text_input(
            "Datos bancarios",
            value="" if proveedor_existente is None else str(proveedor_existente["datos_bancarios"]),
        )
        lead_time_dias = c16.number_input(
            "Lead time (días)",
            min_value=0,
            value=0 if proveedor_existente is None else _safe_int(proveedor_existente["lead_time_dias"], 0),
        )
        pedido_minimo_usd = c17.number_input(
            "Pedido mínimo USD",
            min_value=0.0,
            value=0.0 if proveedor_existente is None else _safe_float(proveedor_existente["pedido_minimo_usd"], 0.0),
            format="%.2f",
        )

        estatus_comercial = st.selectbox(
            "Estatus comercial",
            ["aprobado", "condicionado", "bloqueado"],
            index=["aprobado", "condicionado", "bloqueado"].index(
                str(proveedor_existente["estatus_comercial"])
                if proveedor_existente is not None and str(proveedor_existente["estatus_comercial"]) in ["aprobado", "condicionado", "bloqueado"]
                else "aprobado"
            ),
        )

        observaciones = st.text_area(
            "Observaciones",
            value="" if proveedor_existente is None else str(proveedor_existente["observaciones"]),
        )
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
            try:
                provider_id = save_proveedor_full(
                    {
                        "id": None if proveedor_existente is None else int(proveedor_existente["id"]),
                        "nombre": nombre,
                        "telefono": telefono,
                        "email": email,
                        "rif": rif,
                        "contacto": contacto,
                        "direccion": direccion,
                        "ciudad": ciudad,
                        "pais": pais,
                        "observaciones": observaciones,
                        "especialidades": especialidades_norm,
                        "condicion_pago_default": condicion_pago_default,
                        "dias_credito_default": dias_credito_default,
                        "moneda_default": moneda_default,
                        "metodo_pago_default": metodo_pago_default,
                        "banco": banco,
                        "datos_bancarios": datos_bancarios,
                        "tipo_proveedor": tipo_proveedor,
                        "estatus_comercial": estatus_comercial,
                        "lead_time_dias": lead_time_dias,
                        "pedido_minimo_usd": pedido_minimo_usd,
                        "ultima_compra": None if proveedor_existente is None else proveedor_existente["ultima_compra"],
                    }
                )
                st.success(f"Proveedor guardado. ID #{provider_id}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar el proveedor: {exc}")

    if not df_prov.empty:
        sel = st.selectbox(
            "Proveedor a eliminar",
            df_prov["id"].tolist(),
            format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]),
            key="inv_prov_delete_sel",
        )
        if st.button("🗑 Eliminar proveedor", key="inv_delete_provider_btn"):
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


def _inventario_has_column(col_name: str) -> bool:
    with db_transaction() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}
    return col_name in cols


def _render_variantes() -> None:
    st.subheader("🎨 Variantes por color")

    df_items = _load_inventory_df(include_inactive=False)
    tab_alta, tab_listado = st.tabs(["➕ Registrar variante", "📋 Listado"])

    with tab_alta:
        if df_items.empty:
            st.info("Primero registra productos en inventario para poder crear variantes.")
        else:
            with st.form("form_inv_variante"):
                inventario_id = _select_inventory_item(df_items, "Producto base", "inv_var_producto")
                c1, c2 = st.columns(2)
                color = c1.text_input("Color", placeholder="Ej: Negro")
                sku_variante = c2.text_input("SKU variante (opcional)")
                c3, c4 = st.columns(2)
                stock_actual = c3.number_input("Stock inicial", min_value=0.0, value=0.0, format="%.3f")
                stock_minimo = c4.number_input("Stock mínimo", min_value=0.0, value=0.0, format="%.3f")
                guardar = st.form_submit_button("💾 Guardar variante", use_container_width=True)

            if guardar:
                try:
                    var_id = _create_variant(
                        inventario_id=int(inventario_id),
                        color=color,
                        sku_variante=sku_variante,
                        stock_actual=float(stock_actual),
                        stock_minimo=float(stock_minimo),
                    )
                    st.success(f"Variante registrada. ID #{var_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar la variante: {exc}")

    with tab_listado:
        df_var = _load_variantes_df()
        if df_var.empty:
            st.info("No hay variantes registradas.")
            return
        q = st.text_input("🔎 Buscar variante", key="inv_var_q")
        view = _filter_df_by_query(df_var.copy(), q, ["producto", "color", "sku_variante", "sku_base"])
        st.dataframe(view, use_container_width=True, hide_index=True)


def _render_resumen_abastecimiento() -> None:
    st.subheader("📊 Resumen de abastecimiento")
    df_oc = _load_ordenes_compra_df()
    df_eval = _load_evaluaciones_df()
    df_cxp = _load_cuentas_por_pagar_df()
    c1, c2, c3 = st.columns(3)
    c1.metric("OC abiertas", 0 if df_oc.empty else int(df_oc["estado"].astype(str).str.lower().isin(["emitida", "parcial", "borrador"]).sum()))
    c2.metric("Saldo CxP", f"${0.0 if df_cxp.empty else float(df_cxp['saldo_usd'].fillna(0).sum()):,.2f}")
    c3.metric("Evaluación promedio", f"{0.0 if df_eval.empty else float(df_eval['calificacion_general'].fillna(0).mean()):.2f}/5")


def _render_catalogo_proveedor_producto() -> None:
    st.subheader("🔗 Catálogo proveedor-producto")
    df_rel = _load_proveedor_items_df()
    if df_rel.empty:
        st.info("No hay relaciones proveedor-producto registradas.")
        return
    q = st.text_input("🔎 Buscar relación", key="inv_rel_q")
    view = _filter_df_by_query(df_rel.copy(), q, ["proveedor", "producto", "sku", "sku_proveedor", "nombre_proveedor_item"])
    st.dataframe(view, use_container_width=True, hide_index=True)


def _render_ordenes_compra(usuario: str) -> None:
    st.subheader("🧾 Órdenes de compra")
    tab_crear, tab_listar, tab_recibir = st.tabs(["➕ Crear OC", "📋 Órdenes", "📥 Recepción"])

    with tab_crear:
        df_prov = _load_proveedores_full_df()
        df_items = _load_inventory_df(include_inactive=False)
        if df_prov.empty:
            st.info("Debes registrar al menos un proveedor para crear órdenes.")
        elif df_items.empty:
            st.info("Debes registrar productos en inventario para crear órdenes.")
        else:
            proveedor_id = int(
                st.selectbox(
                    "Proveedor",
                    df_prov["id"].tolist(),
                    format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]),
                    key="inv_oc_prov",
                )
            )
            c1, c2, c3 = st.columns(3)
            moneda = c1.selectbox("Moneda", ["USD", "VES (BCV)", "VES (Binance)"], key="inv_oc_moneda")
            tasa_cambio = c2.number_input("Tasa cambio", min_value=0.0001, value=1.0, format="%.4f", key="inv_oc_tasa")
            condicion_pago = c3.selectbox("Condición pago", ["contado", "credito"], key="inv_oc_cond")
            c4, c5 = st.columns(2)
            delivery_usd = c4.number_input("Delivery USD", min_value=0.0, value=0.0, format="%.2f", key="inv_oc_delivery")
            fecha_entrega = c5.date_input("Fecha entrega estimada", value=date.today(), key="inv_oc_fecha")
            observaciones = st.text_area("Observaciones", key="inv_oc_obs")

            lineas: list[dict[str, Any]] = []
            st.markdown("##### Ítems")
            n_lineas = st.number_input("Cantidad de líneas", min_value=1, max_value=20, value=1, step=1, key="inv_oc_nlineas")
            for idx in range(int(n_lineas)):
                l1, l2, l3, l4 = st.columns([3, 1, 1, 1])
                inv_id = int(
                    l1.selectbox(
                        f"Producto línea {idx + 1}",
                        df_items["id"].tolist(),
                        format_func=lambda i: f"{df_items[df_items['id']==i]['nombre'].iloc[0]} ({df_items[df_items['id']==i]['sku'].iloc[0]})",
                        key=f"inv_oc_item_{idx}",
                    )
                )
                qty = float(l2.number_input("Cantidad", min_value=0.0, value=0.0, format="%.3f", key=f"inv_oc_qty_{idx}"))
                cost = float(l3.number_input("Costo USD", min_value=0.0, value=0.0, format="%.4f", key=f"inv_oc_cost_{idx}"))
                imp = float(l4.number_input("Imp %", min_value=0.0, value=0.0, format="%.2f", key=f"inv_oc_imp_{idx}"))
                if qty > 0:
                    unidad = str(df_items[df_items["id"] == inv_id]["unidad"].iloc[0])
                    lineas.append({"inventario_id": inv_id, "cantidad": qty, "costo_unit_usd": cost, "impuesto_pct": imp, "unidad": unidad})

            if st.button("💾 Crear orden de compra", use_container_width=True, key="inv_oc_save"):
                try:
                    oc_id = create_orden_compra(
                        usuario=usuario,
                        proveedor_id=proveedor_id,
                        header={
                            "moneda": moneda,
                            "tasa_cambio": float(tasa_cambio),
                            "delivery_usd": float(delivery_usd),
                            "condicion_pago": condicion_pago,
                            "fecha_entrega_estimada": fecha_entrega.isoformat() if fecha_entrega else None,
                            "observaciones": observaciones,
                            "estado": "emitida",
                        },
                        items=lineas,
                    )
                    st.success(f"Orden de compra creada. ID #{oc_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo crear la orden: {exc}")

    with tab_listar:
        df_oc = _load_ordenes_compra_df()
        if df_oc.empty:
            st.info("No hay órdenes de compra registradas.")
        else:
            q = st.text_input("🔎 Buscar OC", key="inv_oc_q")
            view = _filter_df_by_query(df_oc.copy(), q, ["codigo", "proveedor", "estado", "usuario"])
            st.dataframe(view, use_container_width=True, hide_index=True)
            sel_oc = int(st.selectbox("Ver detalle de OC", df_oc["id"].tolist(), key="inv_oc_det_sel"))
            st.dataframe(_load_orden_detalle_df(sel_oc), use_container_width=True, hide_index=True)

    with tab_recibir:
        df_oc = _load_ordenes_compra_df()
        abiertas = df_oc[df_oc["estado"].astype(str).str.lower().isin(["emitida", "parcial", "borrador"])].copy() if not df_oc.empty else pd.DataFrame()
        if abiertas.empty:
            st.info("No hay órdenes abiertas para recepción.")
        else:
            oc_id = int(
                st.selectbox(
                    "Orden a recibir",
                    abiertas["id"].tolist(),
                    format_func=lambda i: f"{abiertas[abiertas['id']==i]['codigo'].iloc[0]} - {abiertas[abiertas['id']==i]['proveedor'].iloc[0]}",
                    key="inv_oc_recv_sel",
                )
            )
            detalle = _load_orden_detalle_df(oc_id)
            qty_map: dict[int, float] = {}
            for _, row in detalle.iterrows():
                pendiente = max(_safe_float(row.get("cantidad")) - _safe_float(row.get("cantidad_recibida")), 0.0)
                if pendiente <= 0:
                    continue
                qty_map[int(row["id"])] = st.number_input(
                    f"{row['producto']} | Pendiente {pendiente:,.3f}",
                    min_value=0.0,
                    max_value=float(pendiente),
                    value=0.0,
                    format="%.3f",
                    key=f"inv_recv_qty_{int(row['id'])}",
                )
            referencia = st.text_input("Referencia recepción", key="inv_recv_ref")
            if st.button("📥 Registrar recepción", use_container_width=True, key="inv_recv_save"):
                try:
                    rec_id = receive_orden_compra(usuario=usuario, orden_compra_id=oc_id, quantities=qty_map, referencia=referencia)
                    st.success(f"Recepción registrada. ID #{rec_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar la recepción: {exc}")


def _render_evaluacion_proveedores(usuario: str) -> None:
    st.subheader("⭐ Evaluación de proveedores")
    df_prov = _load_proveedores_full_df()
    if df_prov.empty:
        st.info("Debes registrar proveedores antes de evaluar.")
        return

    with st.form("form_eval_proveedor"):
        proveedor_id = int(
            st.selectbox(
                "Proveedor",
                df_prov["id"].tolist(),
                format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]),
                key="inv_eval_prov",
            )
        )
        c1, c2, c3, c4 = st.columns(4)
        calidad = c1.slider("Calidad", 0, 5, 4)
        entrega = c2.slider("Entrega", 0, 5, 4)
        precio = c3.slider("Precio", 0, 5, 4)
        soporte = c4.slider("Soporte", 0, 5, 4)
        incidencia = st.text_input("Incidencia")
        comentario = st.text_area("Comentario")
        decision = st.selectbox("Decisión", ["aprobado", "condicionado", "bloqueado"])
        guardar = st.form_submit_button("💾 Guardar evaluación", use_container_width=True)

    if guardar:
        try:
            eval_id = save_evaluacion(
                usuario=usuario,
                proveedor_id=proveedor_id,
                payload={
                    "calidad": calidad,
                    "entrega": entrega,
                    "precio": precio,
                    "soporte": soporte,
                    "incidencia": incidencia,
                    "comentario": comentario,
                    "decision": decision,
                },
            )
            st.success(f"Evaluación registrada. ID #{eval_id}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar la evaluación: {exc}")

    df_eval = _load_evaluaciones_df()
    if df_eval.empty:
        st.info("No hay evaluaciones registradas.")
    else:
        st.dataframe(df_eval, use_container_width=True, hide_index=True)


def _render_documentos_proveedor() -> None:
    st.subheader("📎 Documentos y soportes")
    df_prov = _load_proveedores_full_df()

    with st.form("form_doc_proveedor"):
        proveedor_opts = [None] + (df_prov["id"].tolist() if not df_prov.empty else [])
        proveedor_id = st.selectbox(
            "Proveedor (opcional)",
            proveedor_opts,
            format_func=lambda i: "Sin proveedor" if i is None else str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]),
            key="inv_doc_prov",
        )
        c1, c2 = st.columns(2)
        tipo_referencia = c1.selectbox("Tipo referencia", ["general", "compra", "orden_compra", "cuenta_por_pagar", "pago"])
        referencia_id_txt = c2.text_input("ID referencia")
        c3, c4 = st.columns(2)
        titulo = c3.text_input("Título")
        tipo_documento = c4.text_input("Tipo documento", placeholder="factura, contrato, soporte...")
        url_externa = st.text_input("URL externa (opcional)")
        c5, c6 = st.columns(2)
        fecha_documento = c5.date_input("Fecha documento", value=date.today())
        fecha_vencimiento = c6.date_input("Fecha vencimiento", value=date.today() + timedelta(days=30))
        observaciones = st.text_area("Observaciones")
        archivo = st.file_uploader("Archivo", type=["pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "txt"])
        guardar = st.form_submit_button("💾 Guardar documento", use_container_width=True)

    if guardar:
        try:
            ref_id = _safe_int(referencia_id_txt, 0) or None
            ruta = _save_uploaded_support_file(archivo, int(proveedor_id) if proveedor_id is not None else None, tipo_referencia, ref_id)
            nombre_archivo = Path(archivo.name).name if archivo is not None else ""
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO proveedor_documentos(
                        proveedor_id, tipo_referencia, referencia_id, titulo, tipo_documento,
                        nombre_archivo, ruta_archivo, url_externa, fecha_documento, fecha_vencimiento, observaciones
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(proveedor_id) if proveedor_id is not None else None,
                        clean_text(tipo_referencia) or "general",
                        ref_id,
                        clean_text(titulo),
                        clean_text(tipo_documento),
                        clean_text(nombre_archivo),
                        clean_text(ruta),
                        clean_text(url_externa),
                        fecha_documento.isoformat() if fecha_documento else None,
                        fecha_vencimiento.isoformat() if fecha_vencimiento else None,
                        clean_text(observaciones),
                    ),
                )
            st.success("Documento guardado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar el documento: {exc}")

    df_doc = _load_documentos_df()
    if df_doc.empty:
        st.info("No hay documentos registrados.")
    else:
        st.dataframe(df_doc, use_container_width=True, hide_index=True)


def _render_cuentas_por_pagar() -> None:
    st.subheader("💳 Cuentas por pagar a proveedores")
    df_cxp = _load_cuentas_por_pagar_df()
    if df_cxp.empty:
        st.info("No hay cuentas por pagar registradas.")
        return
    st.dataframe(df_cxp, use_container_width=True, hide_index=True)
    st.markdown("### 📅 Calendario de cuotas")
    _render_calendario_cuotas(_load_cuotas_compra_df())


def _render_pagos_proveedores(usuario: str) -> None:
    st.subheader("💸 Pagos a proveedores")
    df_cxp = _load_cuentas_por_pagar_df()
    if df_cxp.empty:
        st.info("No hay cuentas por pagar registradas.")
        return

    abiertas = df_cxp[df_cxp["saldo_usd"].fillna(0).astype(float) > 0].copy()
    if abiertas.empty:
        st.success("No hay saldos pendientes por pagar.")
        return

    cuenta_id = int(
        st.selectbox(
            "Cuenta por pagar",
            abiertas["id"].tolist(),
            format_func=lambda i: f"CxP #{i} | {abiertas[abiertas['id']==i]['proveedor'].iloc[0]} | Saldo ${float(abiertas[abiertas['id']==i]['saldo_usd'].iloc[0]):,.2f}",
            key="inv_pago_cxp",
        )
    )
    fila = abiertas[abiertas["id"] == cuenta_id].iloc[0]
    saldo = float(fila["saldo_usd"] or 0.0)
    st.caption(f"Saldo pendiente: ${saldo:,.2f}")

    c1, c2, c3 = st.columns(3)
    monto_usd = c1.number_input("Monto USD", min_value=0.0, max_value=max(saldo, 0.0), value=min(saldo, saldo), format="%.2f")
    moneda_pago = c2.selectbox("Moneda pago", ["USD", "VES (BCV)", "VES (Binance)"])
    tasa = c3.number_input("Tasa cambio", min_value=0.0001, value=1.0, format="%.4f")
    c4, c5 = st.columns(2)
    metodo = c4.selectbox("Método pago", ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"])
    referencia = c5.text_input("Referencia")
    observaciones = st.text_area("Observaciones")
    monto_moneda = monto_usd if "USD" in moneda_pago else (monto_usd * tasa)
    st.caption(f"Monto en moneda de pago: {monto_moneda:,.2f} {moneda_pago}")

    if st.button("💾 Registrar pago", use_container_width=True, key="inv_pago_save"):
        try:
            pago_id = registrar_pago_proveedor_ui(
                usuario=usuario,
                cuenta_por_pagar_id=cuenta_id,
                monto_usd=float(monto_usd),
                moneda_pago=moneda_pago,
                monto_moneda_pago=float(monto_moneda),
                tasa_cambio=float(tasa),
                metodo_pago=metodo,
                referencia=referencia,
                observaciones=observaciones,
            )
            st.success(f"Pago registrado. ID #{pago_id}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar el pago: {exc}")

    st.markdown("#### Historial de pagos de la cuenta")
    df_pagos = _load_pagos_proveedores_df(cuenta_id)
    if df_pagos.empty:
        st.info("Aún no hay pagos para esta cuenta.")
    else:
        st.dataframe(df_pagos, use_container_width=True, hide_index=True)


def _render_movimientos() -> None:
    st.subheader("🔄 Movimientos de inventario")
    df = _load_movements_df(limit=2000)
    if df.empty:
        st.info("No hay movimientos registrados.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_reposicion(df: pd.DataFrame) -> None:
    st.subheader("📦 Reposición")
    plan = _build_restock_recommendations(df)
    if plan.empty:
        st.success("No hay productos críticos para reponer.")
    else:
        st.dataframe(plan, use_container_width=True, hide_index=True)


def _render_ajustes(usuario: str) -> None:
    st.subheader("🔧 Ajustes de inventario")
    df_items = _load_inventory_df(include_inactive=False)
    tab_stock, tab_reval, tab_config = st.tabs(["📦 Ajuste de stock", "💲 Revalorización", "⚙️ Configuración"])

    with tab_stock:
        if df_items.empty:
            st.info("No hay productos activos para ajustar.")
        else:
            item_id = _select_inventory_item(df_items, "Producto", "inv_adj_item")
            tipo = st.selectbox("Tipo", ["entrada", "salida", "ajuste"], key="inv_adj_tipo")
            cantidad = st.number_input("Cantidad", min_value=0.0, value=0.0, format="%.3f", key="inv_adj_qty")
            costo = st.number_input(
                "Costo unitario USD",
                min_value=0.0,
                value=float(df_items[df_items["id"] == item_id]["costo_unitario_usd"].iloc[0]),
                format="%.4f",
                key="inv_adj_cost",
            )
            motivo = st.text_input("Motivo / referencia", key="inv_adj_ref")
            if st.button("💾 Registrar ajuste", use_container_width=True, key="inv_adj_save"):
                try:
                    mov_id = add_inventory_movement(
                        usuario=usuario,
                        inventario_id=item_id,
                        tipo=tipo,
                        cantidad=float(cantidad),
                        costo_unitario_usd=float(costo),
                        referencia=motivo,
                    )
                    st.success(f"Movimiento registrado. ID #{mov_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar el ajuste: {exc}")

    with tab_reval:
        if df_items.empty:
            st.info("No hay productos activos para revalorizar.")
        else:
            item_id = _select_inventory_item(df_items, "Producto a revalorizar", "inv_reval_item")
            fila = df_items[df_items["id"] == item_id].iloc[0]
            c1, c2 = st.columns(2)
            costo_nuevo = c1.number_input("Nuevo costo unitario USD", min_value=0.0, value=float(fila["costo_unitario_usd"] or 0.0), format="%.4f")
            precio_nuevo = c2.number_input("Nuevo precio venta USD", min_value=0.0, value=float(fila["precio_venta_usd"] or 0.0), format="%.4f")
            if st.button("💾 Guardar revalorización", use_container_width=True, key="inv_reval_save"):
                try:
                    with db_transaction() as conn:
                        conn.execute(
                            "UPDATE inventario SET costo_unitario_usd=?, precio_venta_usd=? WHERE id=?",
                            (money(costo_nuevo), money(precio_nuevo), int(item_id)),
                        )
                    st.success("Revalorización aplicada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo actualizar el producto: {exc}")

    with tab_config:
        c1, c2, c3 = st.columns(3)
        alerta = c1.number_input("Días de alerta", min_value=1, value=_safe_int(st.session_state.get("inv_alerta_dias", 14), 14))
        imp = c2.number_input("Impuesto default %", min_value=0.0, value=_safe_float(st.session_state.get("inv_impuesto_default", 16.0), 16.0), format="%.2f")
        delivery = c3.number_input("Delivery default USD", min_value=0.0, value=_safe_float(st.session_state.get("inv_delivery_default", 0.0), 0.0), format="%.2f")
        if st.button("💾 Guardar configuración", use_container_width=True, key="inv_cfg_save"):
            with db_transaction() as conn:
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_alerta_dias'", (str(int(alerta)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_impuesto_default'", (str(float(imp)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_delivery_default'", (str(float(delivery)),))
            st.session_state["inv_alerta_dias"] = int(alerta)
            st.session_state["inv_impuesto_default"] = float(imp)
            st.session_state["inv_delivery_default"] = float(delivery)
            st.success("Configuración guardada.")


def _render_reportes(df: pd.DataFrame) -> None:
    st.subheader("📈 Reportes")
    if df.empty:
        st.info("No hay inventario activo para reportar.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Total productos", len(df))
    c2.metric("Valor inventario", f"${float(df['valor_stock'].sum()):,.2f}")
    c3.metric("Productos críticos", int((df["stock_actual"] <= df["stock_minimo"]).sum()))

    st.markdown("#### 🏆 Top productos por valor")
    top = df.copy().sort_values("valor_stock", ascending=False).head(10)
    st.dataframe(
        top[["sku", "nombre", "categoria", "stock_actual", "costo_unitario_usd", "valor_stock"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### ⬇️ Exportaciones CSV")
    st.download_button(
        "Exportar inventario CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"inventario_{date.today().isoformat()}.csv",
        mime="text/csv",
        key="inv_export_stock",
    )
    df_mov = _load_movements_df(limit=50000)
    if not df_mov.empty:
        st.download_button(
            "Exportar movimientos CSV",
            data=df_mov.to_csv(index=False).encode("utf-8"),
            file_name=f"movimientos_inventario_{date.today().isoformat()}.csv",
            mime="text/csv",
            key="inv_export_mov",
        )
    df_var = _load_variantes_df()
    if not df_var.empty:
        st.download_button(
            "Exportar variantes CSV",
            data=df_var.to_csv(index=False).encode("utf-8"),
            file_name=f"variantes_inventario_{date.today().isoformat()}.csv",
            mime="text/csv",
            key="inv_export_var",
        )


def _render_productos(usuario: str) -> None:
    st.subheader("📦 Productos")

    df = _load_inventory_df(include_inactive=True)

    if df.empty:
        st.info("No hay productos registrados todavía.")
    else:
        b1, b2 = st.columns([2, 1])
        buscar = b1.text_input("🔎 Buscar producto", key="inv_productos_buscar")
        estado = b2.selectbox("Estado", ["Todos", "activo", "inactivo"], key="inv_productos_estado")

        view = df.copy()
        if buscar:
            view = _filter_df_by_query(view, buscar, ["sku", "nombre", "categoria", "unidad"])

        if estado != "Todos":
            view = view[view["estado"].astype(str).str.lower() == estado]

        st.dataframe(
            view,
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

    st.divider()
    st.subheader("➕ Registrar / Editar producto")

    producto_existente = None
    if not df.empty:
        pid_sel = st.selectbox(
            "Editar producto existente (opcional)",
            options=[None] + df["id"].tolist(),
            format_func=lambda x: "Nuevo producto" if x is None else str(df[df["id"] == x]["nombre"].iloc[0]),
            key="inv_producto_edit_sel",
        )
        if pid_sel is not None:
            producto_existente = df[df["id"] == pid_sel].iloc[0]

    with st.form("form_producto"):
        c1, c2, c3, c4 = st.columns(4)
        sku = c1.text_input("SKU", value="" if producto_existente is None else str(producto_existente["sku"]))
        nombre = c2.text_input("Nombre", value="" if producto_existente is None else str(producto_existente["nombre"]))
        categoria = c3.text_input(
            "Categoría",
            value="General" if producto_existente is None else str(producto_existente["categoria"]),
        )
        unidad = c4.text_input(
            "Unidad",
            value="unidad" if producto_existente is None else str(producto_existente["unidad"]),
        )

        c5, c6, c7, c8 = st.columns(4)
        stock_actual = c5.number_input(
            "Stock actual",
            min_value=0.0,
            value=0.0 if producto_existente is None else _safe_float(producto_existente["stock_actual"], 0.0),
            format="%.3f",
        )
        stock_minimo = c6.number_input(
            "Stock mínimo",
            min_value=0.0,
            value=0.0 if producto_existente is None else _safe_float(producto_existente["stock_minimo"], 0.0),
            format="%.3f",
        )
        costo_unitario_usd = c7.number_input(
            "Costo unitario USD",
            min_value=0.0,
            value=0.0 if producto_existente is None else _safe_float(producto_existente["costo_unitario_usd"], 0.0),
            format="%.4f",
        )
        precio_venta_usd = c8.number_input(
            "Precio venta USD",
            min_value=0.0,
            value=0.0 if producto_existente is None else _safe_float(producto_existente["precio_venta_usd"], 0.0),
            format="%.4f",
        )

        estado_producto = st.selectbox(
            "Estado",
            ["activo", "inactivo"],
            index=["activo", "inactivo"].index(
                str(producto_existente["estado"]).lower()
                if producto_existente is not None and str(producto_existente["estado"]).lower() in ["activo", "inactivo"]
                else "activo"
            ),
        )

        guardar_producto = st.form_submit_button("💾 Guardar producto", use_container_width=True)

    if guardar_producto:
        try:
            if not clean_text(sku):
                raise ValueError("El SKU es obligatorio.")
            if not clean_text(nombre):
                raise ValueError("El nombre es obligatorio.")

            with db_transaction() as conn:
                if producto_existente is None:
                    if _inventario_has_column("creado_por") and _inventario_has_column("creado_en"):
                        conn.execute(
                            """
                            INSERT INTO inventario (
                                usuario, sku, nombre, categoria, unidad,
                                stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd,
                                estado, creado_por, creado_en
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                usuario,
                                clean_text(sku),
                                clean_text(nombre),
                                clean_text(categoria),
                                clean_text(unidad),
                                float(stock_actual),
                                float(stock_minimo),
                                float(costo_unitario_usd),
                                float(precio_venta_usd),
                                clean_text(estado_producto).lower(),
                                usuario,
                                datetime.now().isoformat(timespec="seconds"),
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO inventario (
                                usuario, sku, nombre, categoria, unidad,
                                stock_actual, stock_minimo,
                                costo_unitario_usd, precio_venta_usd, estado
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                usuario,
                                clean_text(sku),
                                clean_text(nombre),
                                clean_text(categoria),
                                clean_text(unidad),
                                float(stock_actual),
                                float(stock_minimo),
                                float(costo_unitario_usd),
                                float(precio_venta_usd),
                                clean_text(estado_producto).lower(),
                            ),
                        )
                else:
                    if _inventario_has_column("actualizado_en") and _inventario_has_column("actualizado_por"):
                        conn.execute(
                            """
                            UPDATE inventario
                            SET sku=?,
                                nombre=?,
                                categoria=?,
                                unidad=?,
                                stock_actual=?,
                                stock_minimo=?,
                                costo_unitario_usd=?,
                                precio_venta_usd=?,
                                estado=?,
                                actualizado_en=?,
                                actualizado_por=?
                            WHERE id=?
                            """,
                            (
                                clean_text(sku),
                                clean_text(nombre),
                                clean_text(categoria),
                                clean_text(unidad),
                                float(stock_actual),
                                float(stock_minimo),
                                float(costo_unitario_usd),
                                float(precio_venta_usd),
                                clean_text(estado_producto).lower(),
                                datetime.now().isoformat(timespec="seconds"),
                                usuario,
                                int(producto_existente["id"]),
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE inventario
                            SET sku=?, nombre=?, categoria=?, unidad=?,
                                stock_actual=?, stock_minimo=?,
                                costo_unitario_usd=?, precio_venta_usd=?, estado=?
                            WHERE id=?
                            """,
                            (
                                clean_text(sku),
                                clean_text(nombre),
                                clean_text(categoria),
                                clean_text(unidad),
                                float(stock_actual),
                                float(stock_minimo),
                                float(costo_unitario_usd),
                                float(precio_venta_usd),
                                clean_text(estado_producto).lower(),
                                int(producto_existente["id"]),
                            ),
                        )

            st.success("Producto guardado correctamente.")
            st.rerun()

        except Exception as exc:
            st.error(f"No se pudo guardar el producto: {exc}")

    if not df.empty:
        st.divider()
        st.subheader("🗑 Desactivar producto")

        activos = df[df["estado"].astype(str).str.lower() == "activo"].copy()
        if activos.empty:
            st.caption("No hay productos activos para desactivar.")
        else:
            prod_del = st.selectbox(
                "Producto a desactivar",
                activos["id"].tolist(),
                format_func=lambda i: f"{activos[activos['id'] == i]['nombre'].iloc[0]} ({activos[activos['id'] == i]['sku'].iloc[0]})",
                key="inv_producto_delete_sel",
            )

            if st.button("🗑 Desactivar producto", key="inv_delete_producto_btn"):
                try:
                    with db_transaction() as conn:
                        if _inventario_has_column("actualizado_en") and _inventario_has_column("actualizado_por"):
                            conn.execute(
                                """
                                UPDATE inventario
                                SET estado='inactivo',
                                    actualizado_en=?,
                                    actualizado_por=?
                                WHERE id=?
                                """,
                                (
                                    datetime.now().isoformat(timespec="seconds"),
                                    usuario,
                                    int(prod_del),
                                ),
                            )
                        else:
                            conn.execute("UPDATE inventario SET estado='inactivo' WHERE id=?", (int(prod_del),))
                    st.success("Producto desactivado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo desactivar el producto: {exc}")


def _render_resumen_financiero() -> None:
    st.subheader("💵 Resumen financiero de compras")

    df_hist = _load_historial_compras_df(limit=5000)
    if df_hist.empty:
        st.info("No hay información financiera de compras todavía.")
        return

    df = df_hist.copy()

    total_comprado = _safe_float(df["costo_total_usd"].sum(), 0.0)
    total_pagado = _safe_float(df["monto_pagado_inicial_usd"].sum(), 0.0)
    total_saldo = _safe_float(df["saldo_pendiente_usd"].sum(), 0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total comprado", f"${total_comprado:,.2f}")
    c2.metric("Pagado inicial", f"${total_pagado:,.2f}")
    c3.metric("Saldo pendiente", f"${total_saldo:,.2f}")

    df_group = (
        df.groupby("proveedor", dropna=False)
        .agg(compras=("id", "count"), total_usd=("costo_total_usd", "sum"), saldo_usd=("saldo_pendiente_usd", "sum"))
        .reset_index()
        .sort_values("total_usd", ascending=False)
    )
    df_group["proveedor"] = df_group["proveedor"].fillna("Sin proveedor")
    st.markdown("#### 🏷️ Top proveedores por monto comprado")
    st.dataframe(df_group.head(20), use_container_width=True, hide_index=True)


def _render_integridad_e_integraciones() -> None:
    st.subheader("🧪 Integridad e integraciones")
    st.caption("Verifica la disponibilidad de tablas de módulos relacionados y su volumen de registros.")

    integraciones: list[tuple[str, str]] = [
        ("📥 Compras", "historial_compras"),
        ("🧾 Órdenes de compra", "ordenes_compra"),
        ("👤 Proveedores", "proveedores"),
        ("💸 Cuentas por pagar", "cuentas_por_pagar_proveedores"),
        ("🧮 Costeo", "costeo_detalle"),
        ("📚 Contabilidad", "libro_diario"),
    ]

    rows: list[dict[str, Any]] = []
    with db_transaction() as conn:
        for modulo, tabla in integraciones:
            existe = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone())
            total = 0
            if existe:
                total = _safe_int(conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0], 0)
            rows.append(
                {
                    "modulo": modulo,
                    "tabla_referencia": tabla,
                    "estado": "✅ Conectado" if existe else "⚠️ Sin tabla",
                    "registros": int(total),
                }
            )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_inventario_module(usuario: str, tasa_bcv: float, tasa_binance: float) -> None:
    st.title("📦 Centro de Control de Inventario")
    df = _load_inventory_df()

    sections = [
        "📊 Panel de control",
        "📋 Existencias",
        "📦 Productos",
        "📥 Compras",
        "🧾 Órdenes de compra",
        "🎨 Variantes",
        "👤 Proveedores",
        "🔗 Proveedor-Producto",
        "⭐ Evaluación",
        "📎 Documentos",
        "💳 CxP",
        "💸 Pagos proveedores",
        "🔄 Movimientos",
        "📦 Reposición",
        "🔧 Ajustes",
        "📈 Reportes",
        "🧪 Integración",
    ]
    selected_section = st.selectbox("Navegación del módulo de inventario", sections, index=0)

    if selected_section == "📊 Panel de control":
        _render_inventario_dashboard(df)
    elif selected_section == "📋 Existencias":
        _render_existencias(df)
    elif selected_section == "📦 Productos":
        _render_productos(usuario)
    elif selected_section == "📥 Compras":
        compras_tabs = st.tabs(["Registrar compra", "Historial compras", "Resumen abastecimiento"])
        with compras_tabs[0]:
            _render_compras(usuario, tasa_bcv, tasa_binance)
        with compras_tabs[1]:
            _render_historial_compras()
        with compras_tabs[2]:
            _render_resumen_abastecimiento()
    elif selected_section == "🧾 Órdenes de compra":
        _render_ordenes_compra(usuario)
    elif selected_section == "🎨 Variantes":
        _render_variantes()
    elif selected_section == "👤 Proveedores":
        _render_proveedores()
    elif selected_section == "🔗 Proveedor-Producto":
        _render_catalogo_proveedor_producto()
    elif selected_section == "⭐ Evaluación":
        _render_evaluacion_proveedores(usuario)
    elif selected_section == "📎 Documentos":
        _render_documentos_proveedor()
    elif selected_section == "💳 CxP":
        _render_cuentas_por_pagar()
    elif selected_section == "💸 Pagos proveedores":
        _render_pagos_proveedores(usuario)
    elif selected_section == "🔄 Movimientos":
        _render_movimientos()
    elif selected_section == "📦 Reposición":
        _render_reposicion(df)
    elif selected_section == "🔧 Ajustes":
        _render_ajustes(usuario)
    elif selected_section == "📈 Reportes":
        _render_reportes(df)
    elif selected_section == "🧪 Integración":
        _render_integridad_e_integraciones()


def render_inventario(usuario: str) -> None:
    _ensure_inventory_support_tables()
    _ensure_config_defaults()

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)
    tasa_binance = float(st.session_state.get("tasa_binance", 38.0) or 38.0)

    render_inventario_module(
        usuario=usuario,
        tasa_bcv=tasa_bcv,
        tasa_binance=tasa_binance,
    )



