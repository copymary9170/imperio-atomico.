rom __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, money, require_text

# ============================================================
# INTEGRACIÓN ENTRE MÓDULOS (fallback seguro)
# ============================================================

try:
    from modules.integration_hub import (
        build_standard_payload,
        dispatch_to_module,
        render_module_inbox,
    )
except Exception:
    def build_standard_payload(
        source_module: str,
        source_action: str,
        record_id: int | None = None,
        referencia: str | None = None,
        usuario: str | None = None,
        payload_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "source_module": source_module,
            "source_action": source_action,
            "record_id": record_id,
            "referencia": referencia,
            "timestamp": "",
            "usuario": usuario,
            "payload_data": payload_data or {},
        }

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

    def render_module_inbox(
        module_name: str,
        title: str = "Datos recibidos",
        use_button_label: str = "Usar datos",
        clear_button_label: str = "Limpiar",
        session_prefill_key: str | None = None,
    ) -> dict[str, Any] | None:
        inbox = st.session_state.get("module_inbox", {})
        payload = inbox.get(module_name)
        if not payload:
            return None

        with st.container(border=True):
            st.info(title)
            st.json(payload.get("payload_data", {}))

            c1, c2 = st.columns(2)
            if c1.button(use_button_label, key=f"{module_name}_use_inbox"):
                if session_prefill_key:
                    st.session_state[session_prefill_key] = payload.get("payload_data", {})
                st.success("Datos cargados en sesión.")
                return payload.get("payload_data", {})

            if c2.button(clear_button_label, key=f"{module_name}_clear_inbox"):
                st.session_state["module_inbox"].pop(module_name, None)
                st.success("Datos limpiados.")
                st.rerun()

        return payload.get("payload_data", {})


# ============================================================
# MODELO
# ============================================================

@dataclass(frozen=True)
class CatalogItem:
    sku: str
    nombre: str
    categoria: str
    subcategoria: str
    tipo: str
    descripcion: str
    unidad: str
    precio: float
    costo: float
    tiempo_entrega_dias: int
    canal: str
    estado: str
    proveedor_sugerido: str
    tags: str
    destacado: int = 0

    inventario_id: int | None = None
    usa_cmyk: int = 0
    requiere_corte: int = 0
    requiere_sublimacion: int = 0
    requiere_produccion_manual: int = 0
    requiere_otros_procesos: int = 0

    activo_cotizaciones: int = 1
    activo_ventas: int = 1
    activo_produccion: int = 1

    costo_base_referencial: float = 0.0
    merma_pct_estimada: float = 0.0
    ruta_base: str = ""
    notas_tecnicas: str = ""

    @property
    def margen_pct(self) -> float:
        if self.precio <= 0:
            return 0.0
        return ((self.precio - self.costo) / self.precio) * 100


DEFAULT_ITEMS: tuple[CatalogItem, ...] = (
    CatalogItem(
        sku="CAT-001",
        nombre="Tarjeta PVC Premium",
        categoria="Impresión",
        subcategoria="Tarjetas",
        tipo="Producto",
        descripcion="Tarjeta PVC de alta duración con acabado premium.",
        unidad="unidad",
        precio=22.0,
        costo=11.5,
        tiempo_entrega_dias=2,
        canal="WhatsApp",
        estado="Activo",
        proveedor_sugerido="Proveedor PVC Norte",
        tags="pvc,tarjeta,premium",
        destacado=1,
        usa_cmyk=1,
        requiere_corte=1,
        costo_base_referencial=11.5,
        ruta_base="CMYK > Corte > Calidad",
        notas_tecnicas="Impresión y corte de precisión.",
    ),
    CatalogItem(
        sku="CAT-002",
        nombre="Sticker troquelado",
        categoria="Sublimación",
        subcategoria="Stickers",
        tipo="Producto",
        descripcion="Sticker personalizado con corte troquelado.",
        unidad="unidad",
        precio=18.0,
        costo=8.7,
        tiempo_entrega_dias=1,
        canal="Instagram",
        estado="Activo",
        proveedor_sugerido="Sticker Labs",
        tags="sticker,troquelado,personalizado",
        destacado=0,
        usa_cmyk=1,
        requiere_corte=1,
        costo_base_referencial=8.7,
        ruta_base="CMYK > Corte",
        notas_tecnicas="Adhesivo, troquelado fino.",
    ),
    CatalogItem(
        sku="CAT-003",
        nombre="Kit Branding Express",
        categoria="Paquetes",
        subcategoria="Branding",
        tipo="Paquete",
        descripcion="Paquete express para branding inicial de marca.",
        unidad="kit",
        precio=125.0,
        costo=61.0,
        tiempo_entrega_dias=4,
        canal="Web",
        estado="Activo",
        proveedor_sugerido="Varios",
        tags="branding,kit,emprendedores",
        destacado=1,
        usa_cmyk=1,
        requiere_corte=1,
        requiere_produccion_manual=1,
        costo_base_referencial=61.0,
        ruta_base="CMYK > Corte > Manual > Calidad",
        notas_tecnicas="Requiere ensamblado y revisión final.",
    ),
    CatalogItem(
        sku="CAT-004",
        nombre="Diseño para gran formato",
        categoria="Servicios",
        subcategoria="Diseño",
        tipo="Servicio",
        descripcion="Diseño gráfico listo para impresión en gran formato.",
        unidad="servicio",
        precio=60.0,
        costo=22.0,
        tiempo_entrega_dias=2,
        canal="WhatsApp",
        estado="Borrador",
        proveedor_sugerido="Interno",
        tags="diseño,gran formato",
        destacado=0,
        costo_base_referencial=22.0,
        ruta_base="Diseño",
        notas_tecnicas="No consume inventario directo.",
    ),
)


# ============================================================
# AUXILIARES
# ============================================================

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


def _margin_pct(precio: float, costo: float) -> float:
    precio = float(precio or 0.0)
    costo = float(costo or 0.0)
    if precio <= 0:
        return 0.0
    return ((precio - costo) / precio) * 100


def _catalog_filter(df: pd.DataFrame, query: str, categoria: str, estado: str, canal: str) -> pd.DataFrame:
    view = df.copy()

    txt = clean_text(query)
    if txt:
        mask = (
            view["sku"].astype(str).str.contains(txt, case=False, na=False)
            | view["nombre"].astype(str).str.contains(txt, case=False, na=False)
            | view["categoria"].astype(str).str.contains(txt, case=False, na=False)
            | view["subcategoria"].astype(str).str.contains(txt, case=False, na=False)
            | view["descripcion"].astype(str).str.contains(txt, case=False, na=False)
            | view["tags"].astype(str).str.contains(txt, case=False, na=False)
            | view["proveedor_sugerido"].astype(str).str.contains(txt, case=False, na=False)
            | view["ruta_base"].astype(str).str.contains(txt, case=False, na=False)
            | view["notas_tecnicas"].astype(str).str.contains(txt, case=False, na=False)
        )
        view = view[mask]

    if categoria != "Todas":
        view = view[view["categoria"] == categoria]
    if estado != "Todos":
        view = view[view["estado"] == estado]
    if canal != "Todos":
        view = view[view["canal"] == canal]

    return view


def _load_inventory_links_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()]
        if not cols:
            return pd.DataFrame(columns=["id", "label"])

        nombre_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
        sku_col = "sku" if "sku" in cols else None
        estado_col = "estado" if "estado" in cols else None
        activo_col = "activo" if "activo" in cols else None

        if not nombre_col:
            return pd.DataFrame(columns=["id", "label"])

        sql = f"SELECT id, {nombre_col} AS nombre"
        if sku_col:
            sql += f", COALESCE({sku_col}, '') AS sku"
        else:
            sql += ", '' AS sku"
        sql += " FROM inventario"

        conditions = []
        if estado_col:
            conditions.append("COALESCE(estado,'activo')='activo'")
        elif activo_col:
            conditions.append("COALESCE(activo,1)=1")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY nombre ASC"

        rows = conn.execute(sql).fetchall()

    df = pd.DataFrame(rows, columns=["id", "nombre", "sku"])
    if df.empty:
        return pd.DataFrame(columns=["id", "label"])

    df["label"] = df.apply(
        lambda r: f"{r['nombre']} ({r['sku']})" if str(r["sku"]).strip() else str(r["nombre"]),
        axis=1,
    )
    return df[["id", "label"]]


def _build_catalog_payload(row: pd.Series) -> dict[str, Any]:
    return {
        "catalogo_id": int(row["id"]),
        "sku": str(row["sku"]),
        "nombre": str(row["nombre"]),
        "categoria": str(row["categoria"]),
        "subcategoria": str(row["subcategoria"]),
        "tipo": str(row["tipo"]),
        "descripcion": str(row["descripcion"]),
        "unidad": str(row["unidad"]),
        "precio": float(row["precio"] or 0.0),
        "costo": float(row["costo"] or 0.0),
        "tiempo_entrega_dias": int(row["tiempo_entrega_dias"] or 0),
        "proveedor_sugerido": str(row["proveedor_sugerido"] or ""),
        "tags": str(row["tags"] or ""),
        "inventario_id": int(row["inventario_id"]) if row.get("inventario_id") not in (None, "", 0) else None,
        "usa_cmyk": bool(int(row.get("usa_cmyk", 0) or 0)),
        "requiere_corte": bool(int(row.get("requiere_corte", 0) or 0)),
        "requiere_sublimacion": bool(int(row.get("requiere_sublimacion", 0) or 0)),
        "requiere_produccion_manual": bool(int(row.get("requiere_produccion_manual", 0) or 0)),
        "requiere_otros_procesos": bool(int(row.get("requiere_otros_procesos", 0) or 0)),
        "activo_cotizaciones": bool(int(row.get("activo_cotizaciones", 1) or 0)),
        "activo_ventas": bool(int(row.get("activo_ventas", 1) or 0)),
        "activo_produccion": bool(int(row.get("activo_produccion", 1) or 0)),
        "costo_base_referencial": float(row.get("costo_base_referencial", row["costo"]) or 0.0),
        "merma_pct_estimada": float(row.get("merma_pct_estimada", 0.0) or 0.0),
        "ruta_base": str(row.get("ruta_base", "") or ""),
        "notas_tecnicas": str(row.get("notas_tecnicas", "") or ""),
    }


# ============================================================
# SCHEMA
# ============================================================

def _ensure_catalogo_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalogo_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                sku TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                subcategoria TEXT,
                tipo TEXT NOT NULL DEFAULT 'Producto',
                descripcion TEXT,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                precio REAL NOT NULL DEFAULT 0,
                costo REAL NOT NULL DEFAULT 0,
                tiempo_entrega_dias INTEGER NOT NULL DEFAULT 0,
                canal TEXT NOT NULL DEFAULT 'WhatsApp',
                estado TEXT NOT NULL DEFAULT 'Activo',
                proveedor_sugerido TEXT,
                tags TEXT,
                destacado INTEGER NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_sku ON catalogo_items(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_nombre ON catalogo_items(nombre)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_categoria ON catalogo_items(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_estado ON catalogo_items(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_activo ON catalogo_items(activo)")

        cols = {r[1] for r in conn.execute("PRAGMA table_info(catalogo_items)").fetchall()}
        missing_columns = {
            "inventario_id": "INTEGER",
            "usa_cmyk": "INTEGER NOT NULL DEFAULT 0",
            "requiere_corte": "INTEGER NOT NULL DEFAULT 0",
            "requiere_sublimacion": "INTEGER NOT NULL DEFAULT 0",
            "requiere_produccion_manual": "INTEGER NOT NULL DEFAULT 0",
            "requiere_otros_procesos": "INTEGER NOT NULL DEFAULT 0",
            "activo_cotizaciones": "INTEGER NOT NULL DEFAULT 1",
            "activo_ventas": "INTEGER NOT NULL DEFAULT 1",
            "activo_produccion": "INTEGER NOT NULL DEFAULT 1",
            "costo_base_referencial": "REAL NOT NULL DEFAULT 0",
            "merma_pct_estimada": "REAL NOT NULL DEFAULT 0",
            "ruta_base": "TEXT",
            "notas_tecnicas": "TEXT",
        }
        for col_name, col_def in missing_columns.items():
            if col_name not in cols:
                conn.execute(f"ALTER TABLE catalogo_items ADD COLUMN {col_name} {col_def}")

        total = conn.execute("SELECT COUNT(*) AS c FROM catalogo_items WHERE COALESCE(activo,1)=1").fetchone()
        if int(total["c"] or 0) == 0:
            for item in DEFAULT_ITEMS:
                conn.execute(
                    """
                    INSERT INTO catalogo_items(
                        usuario, sku, nombre, categoria, subcategoria, tipo, descripcion,
                        unidad, precio, costo, tiempo_entrega_dias, canal, estado,
                        proveedor_sugerido, tags, destacado, inventario_id, usa_cmyk,
                        requiere_corte, requiere_sublimacion, requiere_produccion_manual,
                        requiere_otros_procesos, activo_cotizaciones, activo_ventas,
                        activo_produccion, costo_base_referencial, merma_pct_estimada,
                        ruta_base, notas_tecnicas, activo
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "system",
                        item.sku,
                        item.nombre,
                        item.categoria,
                        item.subcategoria,
                        item.tipo,
                        item.descripcion,
                        item.unidad,
                        money(item.precio),
                        money(item.costo),
                        int(item.tiempo_entrega_dias),
                        item.canal,
                        item.estado,
                        item.proveedor_sugerido,
                        item.tags,
                        int(item.destacado),
                        int(item.inventario_id) if item.inventario_id else None,
                        int(item.usa_cmyk),
                        int(item.requiere_corte),
                        int(item.requiere_sublimacion),
                        int(item.requiere_produccion_manual),
                        int(item.requiere_otros_procesos),
                        int(item.activo_cotizaciones),
                        int(item.activo_ventas),
                        int(item.activo_produccion),
                        money(item.costo_base_referencial),
                        float(item.merma_pct_estimada),
                        item.ruta_base,
                        item.notas_tecnicas,
                        1,
                    ),
                )


# ============================================================
# LOADERS
# ============================================================

def _load_catalogo_df() -> pd.DataFrame:
    _ensure_catalogo_tables()
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                fecha_creacion,
                fecha_actualizacion,
                usuario,
                sku,
                nombre,
                categoria,
                subcategoria,
                tipo,
                descripcion,
                unidad,
                precio,
                costo,
                tiempo_entrega_dias,
                canal,
                estado,
                proveedor_sugerido,
                tags,
                destacado,
                inventario_id,
                usa_cmyk,
                requiere_corte,
                requiere_sublimacion,
                requiere_produccion_manual,
                requiere_otros_procesos,
                activo_cotizaciones,
                activo_ventas,
                activo_produccion,
                costo_base_referencial,
                merma_pct_estimada,
                ruta_base,
                notas_tecnicas
            FROM catalogo_items
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre ASC, id ASC
            """
        ).fetchall()

    cols = [
        "id",
        "fecha_creacion",
        "fecha_actualizacion",
        "usuario",
        "sku",
        "nombre",
        "categoria",
        "subcategoria",
        "tipo",
        "descripcion",
        "unidad",
        "precio",
        "costo",
        "tiempo_entrega_dias",
        "canal",
        "estado",
        "proveedor_sugerido",
        "tags",
        "destacado",
        "inventario_id",
        "usa_cmyk",
        "requiere_corte",
        "requiere_sublimacion",
        "requiere_produccion_manual",
        "requiere_otros_procesos",
        "activo_cotizaciones",
        "activo_ventas",
        "activo_produccion",
        "costo_base_referencial",
        "merma_pct_estimada",
        "ruta_base",
        "notas_tecnicas",
    ]
    return pd.DataFrame(rows, columns=cols)


# ============================================================
# SERVICIOS
# ============================================================

def crear_item_catalogo(
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    subcategoria: str,
    tipo: str,
    descripcion: str,
    unidad: str,
    precio: float,
    costo: float,
    tiempo_entrega_dias: int,
    canal: str,
    estado: str,
    proveedor_sugerido: str,
    tags: str,
    destacado: bool,
    inventario_id: int | None,
    usa_cmyk: bool,
    requiere_corte: bool,
    requiere_sublimacion: bool,
    requiere_produccion_manual: bool,
    requiere_otros_procesos: bool,
    activo_cotizaciones: bool,
    activo_ventas: bool,
    activo_produccion: bool,
    costo_base_referencial: float,
    merma_pct_estimada: float,
    ruta_base: str,
    notas_tecnicas: str,
) -> int:
    sku = require_text(sku, "SKU").upper()
    nombre = require_text(nombre, "Nombre")
    categoria = require_text(categoria, "Categoría")
    tipo = require_text(tipo, "Tipo")
    unidad = require_text(unidad, "Unidad")

    with db_transaction() as conn:
        exists = conn.execute(
            "SELECT id FROM catalogo_items WHERE upper(sku)=? AND COALESCE(activo,1)=1",
            (sku,),
        ).fetchone()
        if exists:
            raise ValueError("Ya existe un item con ese SKU.")

        cur = conn.execute(
            """
            INSERT INTO catalogo_items(
                usuario, sku, nombre, categoria, subcategoria, tipo, descripcion,
                unidad, precio, costo, tiempo_entrega_dias, canal, estado,
                proveedor_sugerido, tags, destacado, inventario_id, usa_cmyk,
                requiere_corte, requiere_sublimacion, requiere_produccion_manual,
                requiere_otros_procesos, activo_cotizaciones, activo_ventas,
                activo_produccion, costo_base_referencial, merma_pct_estimada,
                ruta_base, notas_tecnicas, activo
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (
                usuario,
                sku,
                clean_text(nombre),
                clean_text(categoria),
                clean_text(subcategoria),
                clean_text(tipo),
                clean_text(descripcion),
                clean_text(unidad),
                money(precio),
                money(costo),
                int(tiempo_entrega_dias),
                clean_text(canal),
                clean_text(estado),
                clean_text(proveedor_sugerido),
                clean_text(tags),
                1 if destacado else 0,
                int(inventario_id) if inventario_id else None,
                1 if usa_cmyk else 0,
                1 if requiere_corte else 0,
                1 if requiere_sublimacion else 0,
                1 if requiere_produccion_manual else 0,
                1 if requiere_otros_procesos else 0,
                1 if activo_cotizaciones else 0,
                1 if activo_ventas else 0,
                1 if activo_produccion else 0,
                money(costo_base_referencial),
                float(merma_pct_estimada),
                clean_text(ruta_base),
                clean_text(notas_tecnicas),
            ),
        )
        return int(cur.lastrowid)


def actualizar_item_catalogo(
    item_id: int,
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    subcategoria: str,
    tipo: str,
    descripcion: str,
    unidad: str,
    precio: float,
    costo: float,
    tiempo_entrega_dias: int,
    canal: str,
    estado: str,
    proveedor_sugerido: str,
    tags: str,
    destacado: bool,
    inventario_id: int | None,
    usa_cmyk: bool,
    requiere_corte: bool,
    requiere_sublimacion: bool,
    requiere_produccion_manual: bool,
    requiere_otros_procesos: bool,
    activo_cotizaciones: bool,
    activo_ventas: bool,
    activo_produccion: bool,
    costo_base_referencial: float,
    merma_pct_estimada: float,
    ruta_base: str,
    notas_tecnicas: str,
) -> None:
    sku = require_text(sku, "SKU").upper()
    nombre = require_text(nombre, "Nombre")
    categoria = require_text(categoria, "Categoría")
    tipo = require_text(tipo, "Tipo")
    unidad = require_text(unidad, "Unidad")

    with db_transaction() as conn:
        exists = conn.execute(
            """
            SELECT id
            FROM catalogo_items
            WHERE upper(sku)=?
              AND id != ?
              AND COALESCE(activo,1)=1
            """,
            (sku, int(item_id)),
        ).fetchone()
        if exists:
            raise ValueError("Ya existe otro item con ese SKU.")

        conn.execute(
            """
            UPDATE catalogo_items
            SET fecha_actualizacion=CURRENT_TIMESTAMP,
                usuario=?,
                sku=?,
                nombre=?,
                categoria=?,
                subcategoria=?,
                tipo=?,
                descripcion=?,
                unidad=?,
                precio=?,
                costo=?,
                tiempo_entrega_dias=?,
                canal=?,
                estado=?,
                proveedor_sugerido=?,
                tags=?,
                destacado=?,
                inventario_id=?,
                usa_cmyk=?,
                requiere_corte=?,
                requiere_sublimacion=?,
                requiere_produccion_manual=?,
                requiere_otros_procesos=?,
                activo_cotizaciones=?,
                activo_ventas=?,
                activo_produccion=?,
                costo_base_referencial=?,
                merma_pct_estimada=?,
                ruta_base=?,
                notas_tecnicas=?
            WHERE id=?
            """,
            (
                usuario,
                sku,
                clean_text(nombre),
                clean_text(categoria),
                clean_text(subcategoria),
                clean_text(tipo),
                clean_text(descripcion),
                clean_text(unidad),
                money(precio),
                money(costo),
                int(tiempo_entrega_dias),
                clean_text(canal),
                clean_text(estado),
                clean_text(proveedor_sugerido),
                clean_text(tags),
                1 if destacado else 0,
                int(inventario_id) if inventario_id else None,
                1 if usa_cmyk else 0,
                1 if requiere_corte else 0,
                1 if requiere_sublimacion else 0,
                1 if requiere_produccion_manual else 0,
                1 if requiere_otros_procesos else 0,
                1 if activo_cotizaciones else 0,
                1 if activo_ventas else 0,
                1 if activo_produccion else 0,
                money(costo_base_referencial),
                float(merma_pct_estimada),
                clean_text(ruta_base),
                clean_text(notas_tecnicas),
                int(item_id),
            ),
        )


def eliminar_item_catalogo(item_id: int) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE catalogo_items SET activo=0, fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
            (int(item_id),),
        )


# ============================================================
# UI HELPERS
# ============================================================

def _render_metrics_catalogo(df: pd.DataFrame) -> None:
    activos = df[df["estado"].astype(str) == "Activo"].copy()

    items_publicados = int(len(activos))
    margen_promedio = 0.0 if activos.empty else float(
        activos.apply(lambda r: _margin_pct(r["precio"], r["costo"]), axis=1).mean()
    )
    ticket_promedio = 0.0 if activos.empty else float(activos["precio"].mean())
    canales_activos = 0 if activos.empty else int(activos["canal"].nunique())
    destacados = 0 if activos.empty else int(activos["destacado"].fillna(0).astype(int).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Items publicados", items_publicados)
    c2.metric("Margen promedio", f"{margen_promedio:.1f}%")
    c3.metric("Ticket promedio", f"${ticket_promedio:.2f}")
    c4.metric("Canales activos", canales_activos)
    c5.metric("Destacados", destacados)


def _render_send_buttons_catalogo(view: pd.DataFrame) -> None:
    if view.empty:
        return

    st.markdown("### Enviar item a otros módulos")

    item_id = st.selectbox(
        "Selecciona un item",
        options=view["id"].tolist(),
        format_func=lambda x: f"{view[view['id'] == x]['sku'].iloc[0]} · {view[view['id'] == x]['nombre'].iloc[0]}",
        key="catalogo_send_item_id",
    )
    row = view[view["id"] == item_id].iloc[0]
    payload_data = _build_catalog_payload(row)
    usuario = st.session_state.get("usuario", "Sistema")

    c1, c2, c3 = st.columns(3)

    if c1.button("📤 Enviar a Cotizaciones", use_container_width=True, key="cat_send_cot"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="cotizaciones",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_quote",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a Cotizaciones.",
        )

    if c2.button("📤 Enviar a Ventas", use_container_width=True, key="cat_send_ventas"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="ventas",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_sales",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a Ventas.",
        )

    if c3.button("📤 Enviar a Costeo", use_container_width=True, key="cat_send_costeo"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="costeo",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_costing",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a Costeo.",
        )

    c4, c5, c6 = st.columns(3)

    if c4.button("📤 Enviar a CMYK", use_container_width=True, key="cat_send_cmyk"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="cmyk",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_cmyk",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a CMYK.",
        )

    if c5.button("📤 Enviar a Inventario", use_container_width=True, key="cat_send_inv"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="inventario",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_inventory",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a Inventario.",
        )

    if c6.button("📤 Enviar a Rutas", use_container_width=True, key="cat_send_rutas"):
        dispatch_to_module(
            source_module="catalogo",
            target_module="rutas_produccion",
            payload=build_standard_payload(
                source_module="catalogo",
                source_action="send_item_to_routes",
                record_id=int(row["id"]),
                referencia=str(row["sku"]),
                usuario=usuario,
                payload_data=payload_data,
            ),
            success_message="Ítem enviado a Rutas de producción.",
        )


def _render_portafolio_catalogo(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay items con los filtros actuales.")
        return

    view = df.copy()
    view["margen_pct"] = view.apply(lambda r: round(_margin_pct(r["precio"], r["costo"]), 1), axis=1)

    st.dataframe(
        view[
            [
                "sku",
                "nombre",
                "categoria",
                "subcategoria",
                "tipo",
                "unidad",
                "precio",
                "costo",
                "margen_pct",
                "tiempo_entrega_dias",
                "canal",
                "estado",
                "proveedor_sugerido",
                "destacado",
                "usa_cmyk",
                "requiere_corte",
                "requiere_sublimacion",
                "requiere_produccion_manual",
                "activo_cotizaciones",
                "activo_ventas",
                "activo_produccion",
                "ruta_base",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "precio": st.column_config.NumberColumn("Precio", format="$ %.2f"),
            "costo": st.column_config.NumberColumn("Costo", format="$ %.2f"),
            "margen_pct": st.column_config.NumberColumn("Margen %", format="%.1f"),
            "tiempo_entrega_dias": st.column_config.NumberColumn("Entrega (días)", format="%d"),
        },
    )

    _render_send_buttons_catalogo(view)

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    st.download_button(
        "⬇️ Exportar catálogo filtrado",
        data=csv_buffer.getvalue(),
        file_name="catalogo_filtrado.csv",
        mime="text/csv",
    )


def _render_editor_catalogo(df: pd.DataFrame, usuario: str | None) -> None:
    usuario_final = usuario or "system"
    inventory_links = _load_inventory_links_df()
    inventory_options = [0] + inventory_links["id"].tolist() if not inventory_links.empty else [0]
    inventory_map = {0: "Sin vincular"}
    if not inventory_links.empty:
        inventory_map.update({int(r["id"]): str(r["label"]) for _, r in inventory_links.iterrows()})

    subtabs = st.tabs(["Nuevo item", "Editar item", "Eliminar item"])

    with subtabs[0]:
        with st.form("catalogo_nuevo_item", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            sku = c1.text_input("SKU")
            nombre = c2.text_input("Nombre")
            categoria = c3.text_input("Categoría")
            subcategoria = c4.text_input("Subcategoría")

            c5, c6, c7 = st.columns(3)
            tipo = c5.selectbox("Tipo", ["Producto", "Servicio", "Paquete"])
            unidad = c6.text_input("Unidad", value="unidad")
            proveedor_sugerido = c7.text_input("Proveedor sugerido")

            descripcion = st.text_area("Descripción")

            c8, c9, c10, c11 = st.columns(4)
            precio = c8.number_input("Precio", min_value=0.0, step=1.0)
            costo = c9.number_input("Costo", min_value=0.0, step=1.0)
            entrega = c10.number_input("Entrega (días)", min_value=0, step=1)
            canal = c11.selectbox("Canal", ["WhatsApp", "Instagram", "Web", "Sucursal"])

            c12, c13 = st.columns(2)
            estado = c12.selectbox("Estado", ["Activo", "Borrador", "Pausado", "Descontinuado"])
            destacado = c13.checkbox("Destacado")

            tags = st.text_input("Tags", placeholder="premium, rapido, pvc")

            st.markdown("### Integración operativa")
            op1, op2, op3 = st.columns(3)
            inventario_id = op1.selectbox(
                "Vincular a inventario",
                options=inventory_options,
                format_func=lambda x: inventory_map.get(int(x), "Sin vincular"),
                index=0,
                key="catalogo_new_inventario_id",
            )
            costo_base_referencial = op2.number_input(
                "Costo base referencial",
                min_value=0.0,
                step=1.0,
                value=float(costo),
                key="catalogo_new_costo_base_ref",
            )
            merma_pct_estimada = op3.number_input(
                "Merma estimada %",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                value=0.0,
                key="catalogo_new_merma_pct",
            )

            op4, op5, op6 = st.columns(3)
            usa_cmyk = op4.checkbox("Usa CMYK", key="catalogo_new_usa_cmyk")
            requiere_corte = op5.checkbox("Requiere corte", key="catalogo_new_req_corte")
            requiere_sublimacion = op6.checkbox("Requiere sublimación", key="catalogo_new_req_subli")

            op7, op8, op9 = st.columns(3)
            requiere_produccion_manual = op7.checkbox("Requiere producción manual", key="catalogo_new_req_manual")
            requiere_otros_procesos = op8.checkbox("Requiere otros procesos", key="catalogo_new_req_otros")
            activo_produccion = op9.checkbox("Disponible para producción", value=True, key="catalogo_new_activo_prod")

            op10, op11 = st.columns(2)
            activo_cotizaciones = op10.checkbox("Disponible en cotizaciones", value=True, key="catalogo_new_activo_cot")
            activo_ventas = op11.checkbox("Disponible en ventas", value=True, key="catalogo_new_activo_ventas")

            ruta_base = st.text_input("Ruta base", placeholder="CMYK > Corte > Calidad")
            notas_tecnicas = st.text_area(
                "Notas técnicas",
                placeholder="Instrucciones de producción, acabados, restricciones...",
            )

            submitted = st.form_submit_button("Guardar item", use_container_width=True)
            if submitted:
                try:
                    item_id = crear_item_catalogo(
                        usuario=usuario_final,
                        sku=sku,
                        nombre=nombre,
                        categoria=categoria,
                        subcategoria=subcategoria,
                        tipo=tipo,
                        descripcion=descripcion,
                        unidad=unidad,
                        precio=float(precio),
                        costo=float(costo),
                        tiempo_entrega_dias=int(entrega),
                        canal=canal,
                        estado=estado,
                        proveedor_sugerido=proveedor_sugerido,
                        tags=tags,
                        destacado=bool(destacado),
                        inventario_id=int(inventario_id) if int(inventario_id) > 0 else None,
                        usa_cmyk=bool(usa_cmyk),
                        requiere_corte=bool(requiere_corte),
                        requiere_sublimacion=bool(requiere_sublimacion),
                        requiere_produccion_manual=bool(requiere_produccion_manual),
                        requiere_otros_procesos=bool(requiere_otros_procesos),
                        activo_cotizaciones=bool(activo_cotizaciones),
                        activo_ventas=bool(activo_ventas),
                        activo_produccion=bool(activo_produccion),
                        costo_base_referencial=float(costo_base_referencial),
                        merma_pct_estimada=float(merma_pct_estimada),
                        ruta_base=ruta_base,
                        notas_tecnicas=notas_tecnicas,
                    )
                    st.success(f"Ítem agregado al catálogo. ID #{item_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar el item: {exc}")

    with subtabs[1]:
        if df.empty:
            st.info("No hay items para editar.")
        else:
            item_id = st.selectbox(
                "Selecciona un item",
                options=df["id"].tolist(),
                format_func=lambda x: f"{df[df['id'] == x]['sku'].iloc[0]} · {df[df['id'] == x]['nombre'].iloc[0]}",
                key="catalogo_edit_id",
            )
            row = df[df["id"] == item_id].iloc[0]

            inventario_id_actual = _safe_int(row.get("inventario_id"), 0)
            inventory_index = inventory_options.index(inventario_id_actual) if inventario_id_actual in inventory_options else 0

            with st.form("catalogo_editar_item"):
                c1, c2, c3, c4 = st.columns(4)
                sku_new = c1.text_input("SKU", value=str(row["sku"]))
                nombre_new = c2.text_input("Nombre", value=str(row["nombre"]))
                categoria_new = c3.text_input("Categoría", value=str(row["categoria"]))
                subcategoria_new = c4.text_input("Subcategoría", value=str(row["subcategoria"]))

                c5, c6, c7 = st.columns(3)
                tipo_options = ["Producto", "Servicio", "Paquete"]
                tipo_value = str(row["tipo"]) if str(row["tipo"]) in tipo_options else "Producto"
                tipo_new = c5.selectbox("Tipo", tipo_options, index=tipo_options.index(tipo_value))
                unidad_new = c6.text_input("Unidad", value=str(row["unidad"]))
                proveedor_new = c7.text_input("Proveedor sugerido", value=str(row["proveedor_sugerido"]))

                descripcion_new = st.text_area("Descripción", value=str(row["descripcion"]))

                c8, c9, c10, c11 = st.columns(4)
                precio_new = c8.number_input("Precio", min_value=0.0, value=float(row["precio"]), step=1.0)
                costo_new = c9.number_input("Costo", min_value=0.0, value=float(row["costo"]), step=1.0)
                entrega_new = c10.number_input("Entrega (días)", min_value=0, value=int(row["tiempo_entrega_dias"]), step=1)
                canal_options = ["WhatsApp", "Instagram", "Web", "Sucursal"]
                canal_value = str(row["canal"]) if str(row["canal"]) in canal_options else "WhatsApp"
                canal_new = c11.selectbox("Canal", canal_options, index=canal_options.index(canal_value))

                c12, c13 = st.columns(2)
                estado_options = ["Activo", "Borrador", "Pausado", "Descontinuado"]
                estado_value = str(row["estado"]) if str(row["estado"]) in estado_options else "Activo"
                estado_new = c12.selectbox("Estado", estado_options, index=estado_options.index(estado_value))
                destacado_new = c13.checkbox("Destacado", value=bool(int(row["destacado"] or 0)))

                tags_new = st.text_input("Tags", value=str(row["tags"]))

                st.markdown("### Integración operativa")
                op1, op2, op3 = st.columns(3)
                inventario_id_new = op1.selectbox(
                    "Vincular a inventario",
                    options=inventory_options,
                    format_func=lambda x: inventory_map.get(int(x), "Sin vincular"),
                    index=inventory_index,
                    key="catalogo_edit_inventario_id",
                )
                costo_base_referencial_new = op2.number_input(
                    "Costo base referencial",
                    min_value=0.0,
                    value=float(row.get("costo_base_referencial", row["costo"]) or 0.0),
                    step=1.0,
                    key="catalogo_edit_costo_base_ref",
                )
                merma_pct_estimada_new = op3.number_input(
                    "Merma estimada %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(row.get("merma_pct_estimada", 0.0) or 0.0),
                    step=0.5,
                    key="catalogo_edit_merma_pct",
                )

                op4, op5, op6 = st.columns(3)
                usa_cmyk_new = op4.checkbox("Usa CMYK", value=bool(int(row.get("usa_cmyk", 0) or 0)), key="catalogo_edit_usa_cmyk")
                requiere_corte_new = op5.checkbox("Requiere corte", value=bool(int(row.get("requiere_corte", 0) or 0)), key="catalogo_edit_req_corte")
                requiere_sublimacion_new = op6.checkbox(
                    "Requiere sublimación",
                    value=bool(int(row.get("requiere_sublimacion", 0) or 0)),
                    key="catalogo_edit_req_subli",
                )

                op7, op8, op9 = st.columns(3)
                requiere_produccion_manual_new = op7.checkbox(
                    "Requiere producción manual",
                    value=bool(int(row.get("requiere_produccion_manual", 0) or 0)),
                    key="catalogo_edit_req_manual",
                )
                requiere_otros_procesos_new = op8.checkbox(
                    "Requiere otros procesos",
                    value=bool(int(row.get("requiere_otros_procesos", 0) or 0)),
                    key="catalogo_edit_req_otros",
                )
                activo_produccion_new = op9.checkbox(
                    "Disponible para producción",
                    value=bool(int(row.get("activo_produccion", 1) or 0)),
                    key="catalogo_edit_activo_prod",
                )

                op10, op11 = st.columns(2)
                activo_cotizaciones_new = op10.checkbox(
                    "Disponible en cotizaciones",
                    value=bool(int(row.get("activo_cotizaciones", 1) or 0)),
                    key="catalogo_edit_activo_cot",
                )
                activo_ventas_new = op11.checkbox(
                    "Disponible en ventas",
                    value=bool(int(row.get("activo_ventas", 1) or 0)),
                    key="catalogo_edit_activo_ventas",
                )

                ruta_base_new = st.text_input("Ruta base", value=str(row.get("ruta_base", "") or ""))
                notas_tecnicas_new = st.text_area("Notas técnicas", value=str(row.get("notas_tecnicas", "") or ""))

                submitted = st.form_submit_button("Actualizar item", use_container_width=True)
                if submitted:
                    try:
                        actualizar_item_catalogo(
                            item_id=int(item_id),
                            usuario=usuario_final,
                            sku=sku_new,
                            nombre=nombre_new,
                            categoria=categoria_new,
                            subcategoria=subcategoria_new,
                            tipo=tipo_new,
                            descripcion=descripcion_new,
                            unidad=unidad_new,
                            precio=float(precio_new),
                            costo=float(costo_new),
                            tiempo_entrega_dias=int(entrega_new),
                            canal=canal_new,
                            estado=estado_new,
                            proveedor_sugerido=proveedor_new,
                            tags=tags_new,
                            destacado=bool(destacado_new),
                            inventario_id=int(inventario_id_new) if int(inventario_id_new) > 0 else None,
                            usa_cmyk=bool(usa_cmyk_new),
                            requiere_corte=bool(requiere_corte_new),
                            requiere_sublimacion=bool(requiere_sublimacion_new),
                            requiere_produccion_manual=bool(requiere_produccion_manual_new),
                            requiere_otros_procesos=bool(requiere_otros_procesos_new),
                            activo_cotizaciones=bool(activo_cotizaciones_new),
                            activo_ventas=bool(activo_ventas_new),
                            activo_produccion=bool(activo_produccion_new),
                            costo_base_referencial=float(costo_base_referencial_new),
                            merma_pct_estimada=float(merma_pct_estimada_new),
                            ruta_base=ruta_base_new,
                            notas_tecnicas=notas_tecnicas_new,
                        )
                        st.success("Ítem actualizado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"No se pudo actualizar el item: {exc}")

    with subtabs[2]:
        if df.empty:
            st.info("No hay items para eliminar.")
        else:
            item_id_delete = st.selectbox(
                "Selecciona item a eliminar",
                options=df["id"].tolist(),
                format_func=lambda x: f"{df[df['id'] == x]['sku'].iloc[0]} · {df[df['id'] == x]['nombre'].iloc[0]}",
                key="catalogo_delete_id",
            )

            if st.button("🗑 Eliminar item", use_container_width=True):
                try:
                    eliminar_item_catalogo(int(item_id_delete))
                    st.success("Ítem eliminado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo eliminar el item: {exc}")


def _render_copy_catalogo(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay registros con ese filtro.")
        return

    item_id = st.selectbox(
        "Selecciona item para generar copy",
        options=df["id"].tolist(),
        format_func=lambda x: f"{df[df['id'] == x]['sku'].iloc[0]} · {df[df['id'] == x]['nombre'].iloc[0]}",
        key="catalogo_copy_id",
    )
    item = df[df["id"] == item_id].iloc[0]

    tags = str(item["tags"]).strip()
    tags_txt = f"\nEtiquetas: {tags}" if tags else ""

    copy = (
        f"🔥 {item['nombre']} ({item['sku']})\n"
        f"Categoría: {item['categoria']} · {item['subcategoria']} · Tipo: {item['tipo']}\n"
        f"Precio desde: ${float(item['precio']):.2f}\n"
        f"Entrega estimada: {int(item['tiempo_entrega_dias'])} día(s)\n"
        f"{item['descripcion']}{tags_txt}\n"
        "¿Te cotizo ahora mismo?"
    )

    st.text_area("Mensaje listo para WhatsApp/Instagram", value=copy, height=180)
    st.code(copy)


# ============================================================
# UI
# ============================================================

def render_catalogo_hub(usuario: str | None = None) -> None:
    _ensure_catalogo_tables()

    st.markdown("## 🛍️ Catálogo comercial 360")
    if usuario:
        st.caption(f"Gestión de catálogo para {usuario} · versión maestra conectada")

    # bandeja opcional por si luego decides enviarle datos a catálogo
    render_module_inbox(
        module_name="catalogo",
        title="Datos recibidos en Catálogo",
        use_button_label="Usar datos",
        clear_button_label="Limpiar datos recibidos",
        session_prefill_key="catalogo_prefill",
    )

    df = _load_catalogo_df()

    _render_metrics_catalogo(df)

    st.markdown("### 🎯 Filtros inteligentes")
    f0, f1, f2, f3 = st.columns(4)

    query = f0.text_input("Buscar", placeholder="SKU, nombre, tags, proveedor...")
    categorias = ["Todas"] + sorted(df["categoria"].dropna().astype(str).unique().tolist()) if not df.empty else ["Todas"]
    estados = ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist()) if not df.empty else ["Todos"]
    canales = ["Todos"] + sorted(df["canal"].dropna().astype(str).unique().tolist()) if not df.empty else ["Todos"]

    categoria = f1.selectbox("Categoría", categorias)
    estado = f2.selectbox("Estado", estados)
    canal = f3.selectbox("Canal", canales)

    filtrado = _catalog_filter(df, query, categoria, estado, canal)

    tab_portafolio, tab_editor, tab_copy = st.tabs(
        ["🧾 Portafolio", "🛠️ Editor", "📲 Copy comercial"]
    )

    with tab_portafolio:
        _render_portafolio_catalogo(filtrado)

    with tab_editor:
        _render_editor_catalogo(df, usuario)

    with tab_copy:
        _render_copy_catalogo(filado if False else filtrado)





