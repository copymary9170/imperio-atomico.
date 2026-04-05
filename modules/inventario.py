from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, money, require_text
from modules.inventario import (
    _filter_df_by_query,
    _get_or_create_provider,
    _load_cuentas_por_pagar_df,
    _load_inventory_df,
    _load_pagos_proveedores_df,
    _load_proveedores_df,
)
from services.tesoreria_service import registrar_egreso


# ============================================================
# UPGRADE COMPRAS / PROVEEDORES
# ============================================================
# Este archivo agrega lo que hoy le falta al módulo base:
# - ficha ampliada del proveedor
# - relación proveedor-producto
# - órdenes de compra
# - recepción parcial de OC
# - evaluación de proveedores
# - documentos / referencias de soporte
# - registro UI de pagos a proveedores
#
# Uso recomendado:
# 1) importa este archivo desde tu app principal.
# 2) llama ensure_procurement_upgrade_schema() al iniciar.
# 3) agrega render_compras_proveedores_upgrade(usuario) como una nueva pestaña,
#    o integra cada sección dentro de tu módulo inventario.
# ============================================================


UPLOAD_DIR = Path("uploads/proveedores")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# AUXILIARES
# ============================================================


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)



def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
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



def _save_uploaded_support_file(file_obj, provider_id: int | None, reference_type: str, reference_id: int | None) -> str | None:
    if file_obj is None:
        return None

    original_name = Path(file_obj.name).name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{stamp}_{clean_text(original_name).replace(' ', '_')}"
    target = UPLOAD_DIR / safe_name
    with open(target, "wb") as f:
        f.write(file_obj.getbuffer())

    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO proveedor_documentos(
                proveedor_id, tipo_referencia, referencia_id, nombre_archivo, ruta_archivo, titulo, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(provider_id) if provider_id is not None else None,
                clean_text(reference_type) or "general",
                int(reference_id) if reference_id is not None else None,
                original_name,
                str(target),
                original_name,
                "",
            ),
        )
    return str(target)


# ============================================================
# SCHEMA
# ============================================================


def ensure_procurement_upgrade_schema() -> None:
    with db_transaction() as conn:
        # -------------------------
        # proveedores: columnas nuevas
        # -------------------------
        cols = {r[1] for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()}
        provider_columns = {
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
        for name, ddl in provider_columns.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE proveedores ADD COLUMN {name} {ddl}")

        # -------------------------
        # proveedor-producto
        # -------------------------
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

        # -------------------------
        # órdenes de compra
        # -------------------------
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

        # -------------------------
        # recepciones de orden
        # -------------------------
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

        # -------------------------
        # evaluación proveedores
        # -------------------------
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

        # -------------------------
        # documentos proveedor / compra / OC
        # -------------------------
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

        conn.execute("CREATE INDEX IF NOT EXISTS idx_proveedor_items_proveedor ON proveedor_items(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proveedor_items_inventario ON proveedor_items(inventario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_proveedor ON ordenes_compra(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_estado ON ordenes_compra(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_proveedor ON evaluaciones_proveedor(proveedor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_proveedor ON proveedor_documentos(proveedor_id)")


# ============================================================
# LOADERS
# ============================================================


def _load_proveedores_full_df() -> pd.DataFrame:
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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


# ============================================================
# SERVICIOS
# ============================================================


def save_proveedor_full(data: dict[str, Any]) -> int:
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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
    ensure_procurement_upgrade_schema()
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
                "inventario_id": _safe_int(item.get("inventario_id")),
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
    ensure_procurement_upgrade_schema()
    with db_transaction() as conn:
        oc = conn.execute("SELECT id, estado FROM ordenes_compra WHERE id=?", (int(orden_compra_id),)).fetchone()
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
            "INSERT INTO recepciones_orden_compra(orden_compra_id, fecha, usuario, estado, observaciones) VALUES(?,?,?,?,?)",
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
            "SELECT COUNT(*) AS c FROM ordenes_compra_detalle WHERE orden_compra_id=? AND COALESCE(estado_linea,'pendiente') != 'recibida'",
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

    return recepcion_id



def save_evaluacion(usuario: str, proveedor_id: int, payload: dict[str, Any]) -> int:
    ensure_procurement_upgrade_schema()
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



def registrar_pago_proveedor_ui(usuario: str, cuenta_por_pagar_id: int, monto_usd: float, moneda_pago: str, monto_moneda_pago: float, tasa_cambio: float, metodo_pago: str, referencia: str = "", observaciones: str = "") -> int:
    ensure_procurement_upgrade_schema()
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
                "modulo": "compras_proveedores_upgrade",
                "cuenta_por_pagar_id": int(cuenta_por_pagar_id),
                "proveedor_id": int(cxp["proveedor_id"]) if cxp["proveedor_id"] is not None else None,
                "compra_id": int(cxp["compra_id"]),
            },
        )

    return pago_id


# ============================================================
# UI
# ============================================================


def _render_proveedores_ficha() -> None:
    st.subheader("🏢 Ficha ampliada de proveedores")
    df = _load_proveedores_full_df()

    if not df.empty:
        q = st.text_input("🔎 Buscar proveedor ampliado", key="upg_prov_q")
        view = _filter_df_by_query(df.copy(), q, [
            "nombre", "telefono", "email", "rif", "contacto", "direccion", "ciudad",
            "pais", "especialidades", "tipo_proveedor", "estatus_comercial"
        ])
        st.dataframe(view, use_container_width=True, hide_index=True)
    else:
        st.info("No hay proveedores aún.")

    st.divider()
    st.markdown("### ➕ Crear / editar ficha")

    selected = None
    if not df.empty:
        selected_id = st.selectbox(
            "Proveedor existente",
            options=[None] + df["id"].tolist(),
            format_func=lambda x: "Nuevo proveedor" if x is None else str(df[df["id"] == x]["nombre"].iloc[0]),
            key="upg_prov_sel",
        )
        if selected_id is not None:
            selected = df[df["id"] == selected_id].iloc[0]

    with st.form("upg_proveedor_form"):
        c1, c2, c3 = st.columns(3)
        nombre = c1.text_input("Nombre", value="" if selected is None else str(selected["nombre"]))
        contacto = c2.text_input("Contacto", value="" if selected is None else str(selected["contacto"]))
        telefono = c3.text_input("Teléfono", value="" if selected is None else str(selected["telefono"]))

        c4, c5, c6 = st.columns(3)
        email = c4.text_input("Email", value="" if selected is None else str(selected["email"]))
        rif = c5.text_input("RIF", value="" if selected is None else str(selected["rif"]))
        tipo_proveedor = c6.selectbox(
            "Tipo proveedor",
            ["general", "materia_prima", "servicios", "logistica", "consumibles"],
            index=["general", "materia_prima", "servicios", "logistica", "consumibles"].index(
                str(selected["tipo_proveedor"]) if selected is not None and str(selected["tipo_proveedor"]) in ["general", "materia_prima", "servicios", "logistica", "consumibles"] else "general"
            ),
        )

        c7, c8, c9 = st.columns(3)
        ciudad = c7.text_input("Ciudad", value="" if selected is None else str(selected["ciudad"]))
        pais = c8.text_input("País", value="" if selected is None else str(selected["pais"]))
        estatus = c9.selectbox(
            "Estatus comercial",
            ["aprobado", "condicionado", "bloqueado"],
            index=["aprobado", "condicionado", "bloqueado"].index(
                str(selected["estatus_comercial"]) if selected is not None and str(selected["estatus_comercial"]) in ["aprobado", "condicionado", "bloqueado"] else "aprobado"
            ),
        )

        direccion = st.text_area("Dirección", value="" if selected is None else str(selected["direccion"]))
        observaciones = st.text_area("Observaciones", value="" if selected is None else str(selected["observaciones"]))
        especialidades = st.text_input("Especialidades", value="" if selected is None else str(selected["especialidades"]))

        p1, p2, p3, p4 = st.columns(4)
        condicion_pago_default = p1.selectbox(
            "Condición pago default",
            ["contado", "credito"],
            index=["contado", "credito"].index(
                str(selected["condicion_pago_default"]) if selected is not None and str(selected["condicion_pago_default"]) in ["contado", "credito"] else "contado"
            ),
        )
        dias_credito_default = p2.number_input(
            "Días crédito",
            min_value=0,
            value=0 if selected is None else _safe_int(selected["dias_credito_default"], 0),
        )
        moneda_default = p3.selectbox(
            "Moneda default",
            ["USD", "VES (BCV)", "VES (Binance)"],
            index=["USD", "VES (BCV)", "VES (Binance)"].index(
                str(selected["moneda_default"]) if selected is not None and str(selected["moneda_default"]) in ["USD", "VES (BCV)", "VES (Binance)"] else "USD"
            ),
        )
        metodo_pago_default = p4.selectbox(
            "Método pago default",
            ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"],
            index=["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"].index(
                str(selected["metodo_pago_default"]) if selected is not None and str(selected["metodo_pago_default"]) in ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"] else "transferencia"
            ),
        )

        b1, b2, b3 = st.columns(3)
        banco = b1.text_input("Banco", value="" if selected is None else str(selected["banco"]))
        datos_bancarios = b2.text_input("Datos bancarios", value="" if selected is None else str(selected["datos_bancarios"]))
        lead_time = b3.number_input("Lead time (días)", min_value=0, value=0 if selected is None else _safe_int(selected["lead_time_dias"], 0))
        pedido_minimo = st.number_input(
            "Pedido mínimo USD",
            min_value=0.0,
            value=0.0 if selected is None else _safe_float(selected["pedido_minimo_usd"], 0.0),
            format="%.2f",
        )

        ok = st.form_submit_button("💾 Guardar ficha", use_container_width=True)

    if ok:
        try:
            provider_id = save_proveedor_full(
                {
                    "id": None if selected is None else int(selected["id"]),
                    "nombre": nombre,
                    "contacto": contacto,
                    "telefono": telefono,
                    "email": email,
                    "rif": rif,
                    "tipo_proveedor": tipo_proveedor,
                    "ciudad": ciudad,
                    "pais": pais,
                    "estatus_comercial": estatus,
                    "direccion": direccion,
                    "observaciones": observaciones,
                    "especialidades": especialidades,
                    "condicion_pago_default": condicion_pago_default,
                    "dias_credito_default": dias_credito_default,
                    "moneda_default": moneda_default,
                    "metodo_pago_default": metodo_pago_default,
                    "banco": banco,
                    "datos_bancarios": datos_bancarios,
                    "lead_time_dias": lead_time,
                    "pedido_minimo_usd": pedido_minimo,
                }
            )
            st.success(f"Proveedor guardado correctamente. ID #{provider_id}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar la ficha: {exc}")


def _render_catalogo_proveedor_producto() -> None:
    st.subheader("🔗 Catálogo proveedor-producto")
    df_rel = _load_proveedor_items_df()

    if not df_rel.empty:
        q = st.text_input("🔎 Buscar relación", key="upg_rel_q")
        view = _filter_df_by_query(
            df_rel.copy(),
            q,
            ["proveedor", "producto", "sku", "sku_proveedor", "nombre_proveedor_item", "unidad_compra"],
        )
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "equivalencia_unidad": st.column_config.NumberColumn("Equivalencia", format="%.3f"),
                "precio_referencia_usd": st.column_config.NumberColumn("Precio ref. USD", format="%.4f"),
                "pedido_minimo": st.column_config.NumberColumn("Pedido mínimo", format="%.3f"),
                "lead_time_dias": st.column_config.NumberColumn("Lead time", format="%d"),
            },
        )
    else:
        st.info("No hay relaciones proveedor-producto registradas.")

    df_prov = _load_proveedores_full_df()
    df_inv = _load_inventory_df()

    st.divider()
    st.markdown("### ➕ Asignar producto a proveedor")

    if df_prov.empty or df_inv.empty:
        st.warning("Necesitas al menos un proveedor y un producto activo.")
        return

    c1, c2 = st.columns(2)
    proveedor_id = c1.selectbox(
        "Proveedor",
        options=df_prov["id"].tolist(),
        format_func=lambda x: str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
        key="upg_rel_proveedor",
    )
    inventario_id = c2.selectbox(
        "Producto",
        options=df_inv["id"].tolist(),
        format_func=lambda x: f"{df_inv[df_inv['id'] == x]['nombre'].iloc[0]} ({df_inv[df_inv['id'] == x]['sku'].iloc[0]})",
        key="upg_rel_producto",
    )

    r1, r2, r3 = st.columns(3)
    sku_proveedor = r1.text_input("SKU proveedor", key="upg_rel_sku_prov")
    nombre_proveedor_item = r2.text_input("Nombre proveedor item", key="upg_rel_nombre_item")
    unidad_compra = r3.text_input("Unidad compra", value="unidad", key="upg_rel_unidad")

    r4, r5, r6, r7 = st.columns(4)
    equivalencia_unidad = r4.number_input("Equivalencia", min_value=0.0001, value=1.0, format="%.4f", key="upg_rel_eq")
    precio_referencia_usd = r5.number_input("Precio referencia USD", min_value=0.0, value=0.0, format="%.4f", key="upg_rel_precio")
    pedido_minimo = r6.number_input("Pedido mínimo", min_value=0.0, value=0.0, format="%.3f", key="upg_rel_min")
    lead_time_dias = r7.number_input("Lead time días", min_value=0, value=0, key="upg_rel_lt")

    c3, c4 = st.columns(2)
    moneda_referencia = c3.selectbox("Moneda referencia", ["USD", "VES (BCV)", "VES (Binance)"], key="upg_rel_moneda")
    proveedor_principal = c4.checkbox("Proveedor principal para este producto", key="upg_rel_principal")

    if st.button("💾 Guardar relación proveedor-producto", use_container_width=True):
        try:
            rel_id = save_proveedor_item(
                {
                    "proveedor_id": proveedor_id,
                    "inventario_id": inventario_id,
                    "sku_proveedor": sku_proveedor,
                    "nombre_proveedor_item": nombre_proveedor_item,
                    "unidad_compra": unidad_compra,
                    "equivalencia_unidad": equivalencia_unidad,
                    "precio_referencia_usd": precio_referencia_usd,
                    "moneda_referencia": moneda_referencia,
                    "pedido_minimo": pedido_minimo,
                    "lead_time_dias": lead_time_dias,
                    "proveedor_principal": proveedor_principal,
                }
            )
            st.success(f"Relación guardada. ID #{rel_id}")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar la relación: {exc}")


def _render_ordenes_compra(usuario: str) -> None:
    st.subheader("🧾 Órdenes de compra")

    subtabs = st.tabs(["Crear OC", "Listado OC", "Recepción parcial"])

    with subtabs[0]:
        df_prov = _load_proveedores_full_df()
        df_inv = _load_inventory_df()

        if df_prov.empty or df_inv.empty:
            st.warning("Necesitas proveedores y productos activos para crear órdenes de compra.")
        else:
            oc_codigo_default = _next_code("OC", "ordenes_compra", "codigo")

            h1, h2, h3, h4 = st.columns(4)
            proveedor_id = h1.selectbox(
                "Proveedor",
                options=df_prov["id"].tolist(),
                format_func=lambda x: str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
                key="upg_oc_proveedor",
            )
            codigo = h2.text_input("Código", value=oc_codigo_default, key="upg_oc_codigo")
            moneda = h3.selectbox("Moneda", ["USD", "VES (BCV)", "VES (Binance)"], key="upg_oc_moneda")
            condicion_pago = h4.selectbox("Condición pago", ["contado", "credito"], key="upg_oc_condicion")

            h5, h6, h7 = st.columns(3)
            tasa_cambio = h5.number_input("Tasa cambio", min_value=0.0001, value=1.0, format="%.4f", key="upg_oc_tasa")
            delivery_usd = h6.number_input("Delivery USD", min_value=0.0, value=0.0, format="%.4f", key="upg_oc_delivery")
            fecha_entrega_estimada = h7.date_input("Entrega estimada", value=date.today(), key="upg_oc_entrega")

            observaciones = st.text_area("Observaciones OC", key="upg_oc_obs")

            st.markdown("### Detalle")
            num_lineas = int(
                st.number_input("Número de líneas", min_value=1, max_value=20, value=1, step=1, key="upg_oc_num_lineas")
            )

            items: list[dict[str, Any]] = []
            total_preview = 0.0
            impuesto_preview = 0.0
            subtotal_preview = 0.0

            for i in range(num_lineas):
                st.markdown(f"#### Línea {i + 1}")
                d1, d2, d3, d4, d5 = st.columns(5)
                inventario_id = d1.selectbox(
                    f"Producto {i + 1}",
                    options=df_inv["id"].tolist(),
                    format_func=lambda x: f"{df_inv[df_inv['id'] == x]['nombre'].iloc[0]} ({df_inv[df_inv['id'] == x]['sku'].iloc[0]})",
                    key=f"upg_oc_item_{i}",
                )
                descripcion = d2.text_input(f"Descripción {i + 1}", key=f"upg_oc_desc_{i}")
                cantidad = d3.number_input(f"Cantidad {i + 1}", min_value=0.001, value=1.0, format="%.3f", key=f"upg_oc_qty_{i}")
                costo_unit_usd = d4.number_input(f"Costo unit. USD {i + 1}", min_value=0.0, value=0.0, format="%.4f", key=f"upg_oc_cost_{i}")
                impuesto_pct = d5.number_input(f"Impuesto % {i + 1}", min_value=0.0, max_value=100.0, value=0.0, format="%.2f", key=f"upg_oc_tax_{i}")

                unidad = str(df_inv[df_inv["id"] == inventario_id]["unidad"].iloc[0])
                line_sub = float(cantidad) * float(costo_unit_usd)
                line_tax = line_sub * (float(impuesto_pct) / 100.0)
                line_total = line_sub + line_tax

                subtotal_preview += line_sub
                impuesto_preview += line_tax
                total_preview += line_total

                items.append(
                    {
                        "inventario_id": int(inventario_id),
                        "descripcion": descripcion,
                        "cantidad": float(cantidad),
                        "unidad": unidad,
                        "costo_unit_usd": float(costo_unit_usd),
                        "impuesto_pct": float(impuesto_pct),
                    }
                )

            st.markdown("### Resumen OC")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Subtotal", f"${subtotal_preview:,.2f}")
            s2.metric("Impuesto", f"${impuesto_preview:,.2f}")
            s3.metric("Delivery", f"${float(delivery_usd):,.2f}")
            s4.metric("Total", f"${subtotal_preview + impuesto_preview + float(delivery_usd):,.2f}")

            if st.button("✅ Crear orden de compra", use_container_width=True):
                try:
                    oc_id = create_orden_compra(
                        usuario=usuario,
                        proveedor_id=int(proveedor_id),
                        header={
                            "codigo": codigo,
                            "estado": "emitida",
                            "moneda": moneda,
                            "tasa_cambio": tasa_cambio,
                            "delivery_usd": delivery_usd,
                            "condicion_pago": condicion_pago,
                            "fecha_entrega_estimada": fecha_entrega_estimada.isoformat(),
                            "observaciones": observaciones,
                        },
                        items=items,
                    )
                    st.success(f"Orden de compra creada correctamente. ID #{oc_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo crear la OC: {exc}")

    with subtabs[1]:
        df_oc = _load_ordenes_compra_df()
        if df_oc.empty:
            st.info("No hay órdenes de compra registradas.")
        else:
            q = st.text_input("🔎 Buscar OC", key="upg_oc_q")
            estado = st.selectbox("Estado OC", ["Todos", "borrador", "emitida", "parcial", "cerrada", "cancelada"], key="upg_oc_estado")
            view = _filter_df_by_query(df_oc.copy(), q, ["codigo", "proveedor", "usuario", "estado", "observaciones"])
            if estado != "Todos":
                view = view[view["estado"].astype(str).str.lower() == estado]

            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "subtotal_usd": st.column_config.NumberColumn("Subtotal", format="%.2f"),
                    "impuesto_usd": st.column_config.NumberColumn("Impuesto", format="%.2f"),
                    "delivery_usd": st.column_config.NumberColumn("Delivery", format="%.2f"),
                    "total_usd": st.column_config.NumberColumn("Total", format="%.2f"),
                },
            )

            selected_oc = st.selectbox(
                "Ver detalle de OC",
                options=df_oc["id"].tolist(),
                format_func=lambda x: f"{df_oc[df_oc['id'] == x]['codigo'].iloc[0]} · {df_oc[df_oc['id'] == x]['proveedor'].iloc[0]}",
                key="upg_oc_detalle_sel",
            )
            df_det = _load_orden_detalle_df(selected_oc)
            if not df_det.empty:
                st.markdown("### Detalle de la orden")
                st.dataframe(
                    df_det,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
                        "cantidad_recibida": st.column_config.NumberColumn("Recibida", format="%.3f"),
                        "costo_unit_usd": st.column_config.NumberColumn("Costo unit.", format="%.4f"),
                        "subtotal_usd": st.column_config.NumberColumn("Subtotal", format="%.2f"),
                        "impuesto_usd": st.column_config.NumberColumn("Impuesto", format="%.2f"),
                        "total_usd": st.column_config.NumberColumn("Total", format="%.2f"),
                    },
                )

    with subtabs[2]:
        df_oc = _load_ordenes_compra_df()
        if df_oc.empty:
            st.info("No hay OC para recibir.")
        else:
            abiertas = df_oc[df_oc["estado"].astype(str).str.lower().isin(["emitida", "parcial", "borrador"])]
            if abiertas.empty:
                st.success("No hay órdenes pendientes de recepción.")
            else:
                oc_id = st.selectbox(
                    "Orden a recibir",
                    options=abiertas["id"].tolist(),
                    format_func=lambda x: f"{abiertas[abiertas['id'] == x]['codigo'].iloc[0]} · {abiertas[abiertas['id'] == x]['proveedor'].iloc[0]}",
                    key="upg_recv_oc_id",
                )
                df_det = _load_orden_detalle_df(oc_id)
                if df_det.empty:
                    st.warning("La orden no tiene detalle.")
                else:
                    cantidades: dict[int, float] = {}
                    st.markdown("### Cantidades recibidas")
                    for row in df_det.itertuples(index=False):
                        pendiente = max(float(row.cantidad) - float(row.cantidad_recibida), 0.0)
                        c1, c2, c3, c4 = st.columns(4)
                        c1.write(f"**{row.producto}**")
                        c2.write(f"Ordenado: {float(row.cantidad):,.3f}")
                        c3.write(f"Pendiente: {pendiente:,.3f}")
                        cantidades[int(row.id)] = c4.number_input(
                            f"Recibir línea {int(row.id)}",
                            min_value=0.0,
                            max_value=float(pendiente),
                            value=0.0,
                            format="%.3f",
                            key=f"upg_recv_qty_{int(row.id)}",
                        )

                    referencia = st.text_input("Referencia recepción", value="Recepción parcial OC", key="upg_recv_ref")
                    if st.button("📦 Registrar recepción", use_container_width=True):
                        try:
                            recepcion_id = receive_orden_compra(usuario, int(oc_id), cantidades, referencia=referencia)
                            st.success(f"Recepción registrada correctamente. ID #{recepcion_id}")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"No se pudo registrar la recepción: {exc}")


def _render_evaluacion_proveedores(usuario: str) -> None:
    st.subheader("⭐ Evaluación de proveedores")
    subtabs = st.tabs(["Registrar evaluación", "Historial"])

    with subtabs[0]:
        df_prov = _load_proveedores_full_df()
        if df_prov.empty:
            st.info("No hay proveedores para evaluar.")
        else:
            proveedor_id = st.selectbox(
                "Proveedor",
                options=df_prov["id"].tolist(),
                format_func=lambda x: str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
                key="upg_eval_prov_id",
            )

            c1, c2, c3, c4 = st.columns(4)
            calidad = c1.slider("Calidad", min_value=1, max_value=5, value=4, key="upg_eval_calidad")
            entrega = c2.slider("Entrega", min_value=1, max_value=5, value=4, key="upg_eval_entrega")
            precio = c3.slider("Precio", min_value=1, max_value=5, value=4, key="upg_eval_precio")
            soporte = c4.slider("Soporte", min_value=1, max_value=5, value=4, key="upg_eval_soporte")

            promedio = round((calidad + entrega + precio + soporte) / 4.0, 2)
            st.metric("Calificación general", f"{promedio:.2f}/5")

            incidencia = st.text_input("Incidencia", key="upg_eval_incidencia")
            comentario = st.text_area("Comentario", key="upg_eval_comentario")
            decision = st.selectbox("Decisión", ["aprobado", "condicionado", "bloqueado"], key="upg_eval_decision")

            if st.button("💾 Guardar evaluación", use_container_width=True):
                try:
                    eval_id = save_evaluacion(
                        usuario,
                        int(proveedor_id),
                        {
                            "calidad": calidad,
                            "entrega": entrega,
                            "precio": precio,
                            "soporte": soporte,
                            "incidencia": incidencia,
                            "comentario": comentario,
                            "decision": decision,
                        },
                    )
                    st.success(f"Evaluación guardada. ID #{eval_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la evaluación: {exc}")

    with subtabs[1]:
        df_eval = _load_evaluaciones_df()
        if df_eval.empty:
            st.info("No hay evaluaciones registradas.")
        else:
            q = st.text_input("🔎 Buscar evaluación", key="upg_eval_q")
            view = _filter_df_by_query(df_eval.copy(), q, ["proveedor", "usuario", "decision", "incidencia", "comentario"])
            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "calidad": st.column_config.NumberColumn("Calidad", format="%d"),
                    "entrega": st.column_config.NumberColumn("Entrega", format="%d"),
                    "precio": st.column_config.NumberColumn("Precio", format="%d"),
                    "soporte": st.column_config.NumberColumn("Soporte", format="%d"),
                    "calificacion_general": st.column_config.NumberColumn("General", format="%.2f"),
                },
            )


def _render_documentos_proveedor() -> None:
    st.subheader("📎 Documentos y soportes")
    subtabs = st.tabs(["Adjuntar documento", "Listado"])

    with subtabs[0]:
        df_prov = _load_proveedores_full_df()

        c1, c2, c3 = st.columns(3)
        proveedor_id = None
        if not df_prov.empty:
            proveedor_id = c1.selectbox(
                "Proveedor",
                options=[None] + df_prov["id"].tolist(),
                format_func=lambda x: "Sin proveedor" if x is None else str(df_prov[df_prov["id"] == x]["nombre"].iloc[0]),
                key="upg_doc_prov_id",
            )
        else:
            c1.caption("No hay proveedores cargados.")

        tipo_referencia = c2.selectbox("Tipo referencia", ["general", "proveedor", "compra", "orden_compra"], key="upg_doc_tipo_ref")
        referencia_id = c3.number_input("ID referencia", min_value=0, value=0, step=1, key="upg_doc_ref_id")

        d1, d2, d3 = st.columns(3)
        titulo = d1.text_input("Título", key="upg_doc_titulo")
        tipo_documento = d2.text_input("Tipo documento", placeholder="factura, contrato, cotización...", key="upg_doc_tipo")
        url_externa = d3.text_input("URL externa (opcional)", key="upg_doc_url")

        d4, d5 = st.columns(2)
        fecha_documento = d4.date_input("Fecha documento", value=date.today(), key="upg_doc_fecha")
        fecha_vencimiento = d5.date_input("Fecha vencimiento", value=date.today(), key="upg_doc_venc")

        observaciones = st.text_area("Observaciones", key="upg_doc_obs")
        file_obj = st.file_uploader("Archivo soporte", key="upg_doc_file")

        if st.button("💾 Guardar documento", use_container_width=True):
            try:
                ruta = None
                if file_obj is not None:
                    ruta = _save_uploaded_support_file(
                        file_obj=file_obj,
                        provider_id=proveedor_id,
                        reference_type=tipo_referencia,
                        reference_id=int(referencia_id) if int(referencia_id) > 0 else None,
                    )

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
                            clean_text(tipo_referencia),
                            int(referencia_id) if int(referencia_id) > 0 else None,
                            clean_text(titulo),
                            clean_text(tipo_documento),
                            Path(file_obj.name).name if file_obj is not None else "",
                            ruta or "",
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

    with subtabs[1]:
        df_doc = _load_documentos_df()
        if df_doc.empty:
            st.info("No hay documentos registrados.")
        else:
            q = st.text_input("🔎 Buscar documento", key="upg_doc_q")
            view = _filter_df_by_query(
                df_doc.copy(),
                q,
                ["proveedor", "tipo_referencia", "titulo", "tipo_documento", "nombre_archivo", "observaciones"],
            )
            st.dataframe(view, use_container_width=True, hide_index=True)


def _render_pagos_proveedores(usuario: str) -> None:
    st.subheader("💸 Pagos a proveedores")

    subtabs = st.tabs(["Registrar pago", "Historial pagos"])

    with subtabs[0]:
        df_cxp = _load_cuentas_por_pagar_df()
        if df_cxp.empty:
            st.info("No hay cuentas por pagar disponibles.")
        else:
            pendientes = df_cxp[df_cxp["saldo_usd"].fillna(0).astype(float) > 0].copy()
            if pendientes.empty:
                st.success("No hay saldos pendientes.")
            else:
                cuenta_id = st.selectbox(
                    "Cuenta por pagar",
                    options=pendientes["id"].tolist(),
                    format_func=lambda x: (
                        f"CxP #{x} · "
                        f"{pendientes[pendientes['id'] == x]['proveedor'].iloc[0]} · "
                        f"Saldo ${float(pendientes[pendientes['id'] == x]['saldo_usd'].iloc[0]):,.2f}"
                    ),
                    key="upg_pago_cxp_id",
                )

                row = pendientes[pendientes["id"] == cuenta_id].iloc[0]
                saldo = float(row["saldo_usd"] or 0.0)
                st.metric("Saldo pendiente", f"${saldo:,.2f}")

                p1, p2, p3, p4 = st.columns(4)
                monto_usd = p1.number_input("Monto USD", min_value=0.0001, max_value=float(saldo), value=min(float(saldo), 1.0), format="%.4f", key="upg_pago_monto_usd")
                moneda_pago = p2.selectbox("Moneda pago", ["USD", "VES (BCV)", "VES (Binance)"], key="upg_pago_moneda")
                tasa_cambio = p3.number_input("Tasa cambio", min_value=0.0001, value=1.0, format="%.4f", key="upg_pago_tasa")
                metodo_pago = p4.selectbox(
                    "Método pago",
                    ["transferencia", "efectivo", "pago_movil", "zelle", "binance", "tarjeta", "otro"],
                    key="upg_pago_metodo",
                )

                monto_moneda_pago = st.number_input(
                    "Monto en moneda de pago",
                    min_value=0.0,
                    value=float(monto_usd if moneda_pago == "USD" else monto_usd * tasa_cambio),
                    format="%.4f",
                    key="upg_pago_monto_moneda",
                )
                referencia = st.text_input("Referencia", key="upg_pago_ref")
                observaciones = st.text_area("Observaciones", key="upg_pago_obs")

                if st.button("✅ Registrar pago proveedor", use_container_width=True):
                    try:
                        pago_id = registrar_pago_proveedor_ui(
                            usuario=usuario,
                            cuenta_por_pagar_id=int(cuenta_id),
                            monto_usd=float(monto_usd),
                            moneda_pago=str(moneda_pago),
                            monto_moneda_pago=float(monto_moneda_pago),
                            tasa_cambio=float(tasa_cambio),
                            metodo_pago=str(metodo_pago),
                            referencia=referencia,
                            observaciones=observaciones,
                        )
                        st.success(f"Pago registrado correctamente. ID #{pago_id}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo registrar el pago: {exc}")

    with subtabs[1]:
        df_cxp = _load_cuentas_por_pagar_df()
        if df_cxp.empty:
            st.info("No hay cuentas por pagar registradas.")
        else:
            cuenta_id = st.selectbox(
                "Ver pagos de cuenta",
                options=df_cxp["id"].tolist(),
                format_func=lambda x: f"CxP #{x} · {df_cxp[df_cxp['id'] == x]['proveedor'].iloc[0]}",
                key="upg_hist_pago_cxp",
            )
            df_pagos = _load_pagos_proveedores_df(int(cuenta_id))
            if df_pagos.empty:
                st.info("No hay pagos para esta cuenta.")
            else:
                st.dataframe(
                    df_pagos,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "monto_usd": st.column_config.NumberColumn("Monto USD", format="%.2f"),
                        "monto_moneda_pago": st.column_config.NumberColumn("Monto moneda pago", format="%.2f"),
                        "tasa_cambio": st.column_config.NumberColumn("Tasa", format="%.4f"),
                    },
                )


def _render_resumen_abastecimiento() -> None:
    st.subheader("📊 Resumen de abastecimiento")

    df_prov = _load_proveedores_full_df()
    df_rel = _load_proveedor_items_df()
    df_oc = _load_ordenes_compra_df()
    df_eval = _load_evaluaciones_df()
    df_cxp = _load_cuentas_por_pagar_df()

    total_proveedores = len(df_prov)
    total_relaciones = len(df_rel)
    oc_abiertas = 0 if df_oc.empty else int(df_oc["estado"].astype(str).str.lower().isin(["emitida", "parcial", "borrador"]).sum())
    saldo_cxp = 0.0 if df_cxp.empty else float(df_cxp["saldo_usd"].fillna(0).sum())
    eval_prom = 0.0 if df_eval.empty else float(df_eval["calificacion_general"].fillna(0).mean())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Proveedores", total_proveedores)
    c2.metric("Relaciones proveedor-producto", total_relaciones)
    c3.metric("OC abiertas", oc_abiertas)
    c4.metric("Saldo CxP", f"${saldo_cxp:,.2f}")
    c5.metric("Evaluación promedio", f"{eval_prom:.2f}/5")

    if not df_oc.empty:
        st.markdown("### Últimas órdenes de compra")
        st.dataframe(
            df_oc.head(10),
            use_container_width=True,
            hide_index=True,
            column_config={
                "subtotal_usd": st.column_config.NumberColumn("Subtotal", format="%.2f"),
                "impuesto_usd": st.column_config.NumberColumn("Impuesto", format="%.2f"),
                "delivery_usd": st.column_config.NumberColumn("Delivery", format="%.2f"),
                "total_usd": st.column_config.NumberColumn("Total", format="%.2f"),
            },
        )

    if not df_eval.empty:
        st.markdown("### Últimas evaluaciones")
        st.dataframe(
            df_eval.head(10),
            use_container_width=True,
            hide_index=True,
            column_config={
                "calificacion_general": st.column_config.NumberColumn("General", format="%.2f"),
            },
        )


def render_compras_proveedores_upgrade(usuario: str) -> None:
    ensure_procurement_upgrade_schema()

    st.subheader("🚚 Compras / Proveedores · Upgrade")
    st.caption(
        "Ficha ampliada, catálogo proveedor-producto, órdenes de compra, recepción parcial, "
        "evaluación, documentos y pagos a proveedores."
    )

    tabs = st.tabs(
        [
            "📊 Resumen",
            "🏢 Proveedores",
            "🔗 Proveedor-Producto",
            "🧾 Órdenes de Compra",
            "⭐ Evaluación",
            "📎 Documentos",
            "💸 Pagos",
        ]
    )

    with tabs[0]:
        _render_resumen_abastecimiento()

    with tabs[1]:
        _render_proveedores_ficha()

    with tabs[2]:
        _render_catalogo_proveedor_producto()

    with tabs[3]:
        _render_ordenes_compra(usuario)

    with tabs[4]:
        _render_evaluacion_proveedores(usuario)

    with tabs[5]:
        _render_documentos_proveedor()

    with tabs[6]:
        _render_pagos_proveedores(usuario)

