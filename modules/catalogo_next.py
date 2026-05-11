from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, money, require_text
from security.permissions import has_permission

# ============================================================
# INTEGRACIÓN ENTRE MÓDULOS
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
        if session_key:
            st.session_state[session_key] = payload.get("payload_data", {})
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


ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOG_IMAGES_DIR = ROOT_DIR / "data" / "catalogo_fotos"

CATALOGO_PERMISSIONS = (
    ("catalogo.view", "Consultar catálogo comercial."),
    ("catalogo.create", "Crear productos y servicios en catálogo."),
    ("catalogo.edit", "Editar productos y servicios del catálogo."),
    ("catalogo.delete", "Desactivar productos y servicios del catálogo."),
    ("catalogo.export", "Exportar catálogo comercial."),
)

DEFAULT_CATEGORIES = [
    "Impresión",
    "Sublimación",
    "Paquetes",
    "Servicios",
    "Accesorios",
    "Corporativo",
    "Temporada",
]

DEFAULT_CHANNELS = ["WhatsApp", "Instagram", "Web", "Tienda", "Mayorista", "Aliados"]
DEFAULT_TYPES = ["Producto", "Servicio", "Paquete", "Combo", "Personalizado"]
DEFAULT_STATUS = ["Activo", "Borrador", "Pausado", "Agotado", "Archivado"]
DEFAULT_UNITS = ["unidad", "kit", "servicio", "m2", "docena", "paquete"]


DEFAULT_ITEMS: list[dict[str, Any]] = [
    {
        "sku": "CAT-001",
        "nombre": "Tarjeta PVC Premium",
        "categoria": "Impresión",
        "subcategoria": "Tarjetas",
        "tipo": "Producto",
        "descripcion": "Tarjeta PVC de alta duración con acabado premium.",
        "unidad": "unidad",
        "precio": 22.0,
        "costo": 11.5,
        "tiempo_entrega_dias": 2,
        "canal": "WhatsApp",
        "estado": "Activo",
        "proveedor_sugerido": "Proveedor PVC Norte",
        "tags": "pvc, tarjeta, premium",
        "destacado": 1,
        "usa_cmyk": 1,
        "requiere_corte": 1,
        "requiere_sublimacion": 0,
        "requiere_produccion_manual": 0,
        "requiere_otros_procesos": 0,
        "activo_cotizaciones": 1,
        "activo_ventas": 1,
        "activo_produccion": 1,
        "costo_base_referencial": 11.5,
        "merma_pct_estimada": 3.0,
        "ruta_base": "CMYK > Corte > Calidad",
        "notas_tecnicas": "Impresión y corte de precisión.",
        "precio_mayorista": 18.0,
        "precio_minimo": 16.0,
        "stock_objetivo": 20,
        "orden_minima": 1,
        "lead_time_comercial_dias": 2,
        "visible_catalogo_publico": 1,
        "prioridad_comercial": 80,
        "temporada": "Todo el año",
        "coleccion": "Base",
        "imagen_url": "",
        "imagen_path": "",
        "imagen_nombre": "",
    },
    {
        "sku": "CAT-002",
        "nombre": "Sticker troquelado",
        "categoria": "Sublimación",
        "subcategoria": "Stickers",
        "tipo": "Producto",
        "descripcion": "Sticker personalizado con corte troquelado.",
        "unidad": "unidad",
        "precio": 18.0,
        "costo": 8.7,
        "tiempo_entrega_dias": 1,
        "canal": "Instagram",
        "estado": "Activo",
        "proveedor_sugerido": "Sticker Labs",
        "tags": "sticker, troquelado, personalizado",
        "destacado": 0,
        "usa_cmyk": 1,
        "requiere_corte": 1,
        "requiere_sublimacion": 0,
        "requiere_produccion_manual": 0,
        "requiere_otros_procesos": 0,
        "activo_cotizaciones": 1,
        "activo_ventas": 1,
        "activo_produccion": 1,
        "costo_base_referencial": 8.7,
        "merma_pct_estimada": 4.0,
        "ruta_base": "CMYK > Corte",
        "notas_tecnicas": "Adhesivo, troquelado fino.",
        "precio_mayorista": 14.0,
        "precio_minimo": 12.5,
        "stock_objetivo": 50,
        "orden_minima": 6,
        "lead_time_comercial_dias": 1,
        "visible_catalogo_publico": 1,
        "prioridad_comercial": 70,
        "temporada": "Todo el año",
        "coleccion": "Base",
        "imagen_url": "",
        "imagen_path": "",
        "imagen_nombre": "",
    },
    {
        "sku": "CAT-003",
        "nombre": "Kit Branding Express",
        "categoria": "Paquetes",
        "subcategoria": "Branding",
        "tipo": "Paquete",
        "descripcion": "Paquete express para branding inicial de marca.",
        "unidad": "kit",
        "precio": 125.0,
        "costo": 61.0,
        "tiempo_entrega_dias": 4,
        "canal": "Web",
        "estado": "Activo",
        "proveedor_sugerido": "Varios",
        "tags": "branding, kit, emprendedores",
        "destacado": 1,
        "usa_cmyk": 1,
        "requiere_corte": 1,
        "requiere_sublimacion": 0,
        "requiere_produccion_manual": 1,
        "requiere_otros_procesos": 0,
        "activo_cotizaciones": 1,
        "activo_ventas": 1,
        "activo_produccion": 1,
        "costo_base_referencial": 61.0,
        "merma_pct_estimada": 5.0,
        "ruta_base": "CMYK > Corte > Manual > Calidad",
        "notas_tecnicas": "Requiere ensamblado y revisión final.",
        "precio_mayorista": 105.0,
        "precio_minimo": 95.0,
        "stock_objetivo": 10,
        "orden_minima": 1,
        "lead_time_comercial_dias": 4,
        "visible_catalogo_publico": 1,
        "prioridad_comercial": 95,
        "temporada": "Lanzamientos",
        "coleccion": "Kits",
        "imagen_url": "",
        "imagen_path": "",
        "imagen_nombre": "",
    },
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _safe_text(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return value.strip("-")[:60] or "producto"


def _save_uploaded_image(uploaded_file: Any, sku: str) -> tuple[str | None, str | None]:
    if uploaded_file is None:
        return None, None

    CATALOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("La imagen debe ser PNG, JPG, JPEG o WEBP.")

    safe_name = f"{_slug(sku)}-{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    path = CATALOG_IMAGES_DIR / safe_name
    path.write_bytes(uploaded_file.getbuffer())

    return str(path), uploaded_file.name


def _render_product_image(row: pd.Series | dict[str, Any], *, height: int = 190) -> None:
    image_path = _safe_text(row.get("imagen_path"))
    image_url = _safe_text(row.get("imagen_url"))

    if image_path and Path(image_path).exists():
        st.image(image_path, use_container_width=True)
    elif image_url:
        st.image(image_url, use_container_width=True)
    else:
        st.markdown(
            f"""
            <div style="height:{height}px;border-radius:18px;border:1px dashed rgba(255,255,255,.25);
                        display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,255,255,.02));">
                <div style="text-align:center;opacity:.75;font-size:1.05rem;">📷<br>Sin foto</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _margin_pct(precio: float, costo: float) -> float:
    precio = _safe_float(precio)
    costo = _safe_float(costo)
    if precio <= 0:
        return 0.0
    return ((precio - costo) / precio) * 100


def _profit_usd(precio: float, costo: float) -> float:
    return round(_safe_float(precio) - _safe_float(costo), 2)


def _commercial_score(row: pd.Series | dict[str, Any]) -> int:
    precio = _safe_float(row.get("precio", 0))
    costo = _safe_float(row.get("costo", 0))
    margen = _margin_pct(precio, costo)
    prioridad = max(0, min(100, _safe_int(row.get("prioridad_comercial", 50), 50)))
    destacado = 12 if _safe_int(row.get("destacado", 0)) else 0
    visible = 8 if _safe_int(row.get("visible_catalogo_publico", 1)) else -10
    canales = 8 if _safe_text(row.get("canal")) else 0
    estado = _safe_text(row.get("estado", "Activo"))
    estado_score = 10 if estado == "Activo" else -15 if estado in {"Pausado", "Agotado", "Archivado"} else 0
    margen_score = max(0, min(35, int(margen * 0.7)))
    score = int((prioridad * 0.35) + margen_score + destacado + visible + canales + estado_score)
    return max(0, min(100, score))


def _can_create() -> bool:
    return has_permission("catalogo.create") or has_permission("inventario.create")


def _can_edit() -> bool:
    return has_permission("catalogo.edit") or has_permission("inventario.edit")


def _can_delete() -> bool:
    return has_permission("catalogo.delete") or has_permission("inventario.edit")


def _can_export() -> bool:
    return has_permission("catalogo.export") or has_permission("inventario.view")


def _can_view() -> bool:
    return has_permission("catalogo.view") or has_permission("inventario.view") or has_permission("dashboard.view")


def _seed_catalog_permissions() -> None:
    with db_transaction() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "permisos" in tables:
            conn.executemany(
                "INSERT OR IGNORE INTO permisos (codigo, descripcion) VALUES (?, ?)",
                CATALOGO_PERMISSIONS,
            )
        if "roles_permisos" in tables:
            admin_codes = [code for code, _ in CATALOGO_PERMISSIONS]
            conn.executemany(
                "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Administration', ?)",
                [(code,) for code in admin_codes],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Operator', ?)",
                [("catalogo.view",), ("catalogo.export",)],
            )


def _ensure_catalogo_schema() -> None:
    _seed_catalog_permissions()
    CATALOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

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
            "precio_mayorista": "REAL NOT NULL DEFAULT 0",
            "precio_minimo": "REAL NOT NULL DEFAULT 0",
            "stock_objetivo": "INTEGER NOT NULL DEFAULT 0",
            "orden_minima": "INTEGER NOT NULL DEFAULT 1",
            "lead_time_comercial_dias": "INTEGER NOT NULL DEFAULT 0",
            "visible_catalogo_publico": "INTEGER NOT NULL DEFAULT 1",
            "prioridad_comercial": "INTEGER NOT NULL DEFAULT 50",
            "temporada": "TEXT",
            "coleccion": "TEXT",
            "imagen_url": "TEXT",
            "imagen_path": "TEXT",
            "imagen_nombre": "TEXT",
            "ultima_revision_precio": "TEXT",
        }
        for col, col_def in missing_columns.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE catalogo_items ADD COLUMN {col} {col_def}")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_sku ON catalogo_items(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_nombre ON catalogo_items(nombre)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_categoria ON catalogo_items(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_estado ON catalogo_items(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_canal ON catalogo_items(canal)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_tipo ON catalogo_items(tipo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_activo ON catalogo_items(activo)")

        total = conn.execute("SELECT COUNT(*) AS c FROM catalogo_items WHERE COALESCE(activo,1)=1").fetchone()
        if int(total["c"] or 0) == 0:
            for item in DEFAULT_ITEMS:
                _insert_catalog_item(conn, "system", item)


def _catalog_tuple(usuario: str, data: dict[str, Any]) -> tuple[Any, ...]:
    sku = require_text(data.get("sku"), "SKU").upper()
    nombre = require_text(data.get("nombre"), "Nombre")
    categoria = require_text(data.get("categoria"), "Categoría")
    tipo = require_text(data.get("tipo") or "Producto", "Tipo")
    unidad = require_text(data.get("unidad") or "unidad", "Unidad")
    costo = money(_safe_float(data.get("costo")))
    costo_base = money(_safe_float(data.get("costo_base_referencial"), costo))
    precio = money(_safe_float(data.get("precio")))
    precio_minimo = money(_safe_float(data.get("precio_minimo")))
    precio_mayorista = money(_safe_float(data.get("precio_mayorista")))

    if precio_minimo <= 0 and costo > 0:
        precio_minimo = money(costo * 1.15)
    if precio_mayorista <= 0 and precio > 0:
        precio_mayorista = money(precio * 0.85)

    return (
        usuario,
        sku,
        clean_text(nombre),
        clean_text(categoria),
        clean_text(data.get("subcategoria")),
        clean_text(tipo),
        clean_text(data.get("descripcion")),
        clean_text(unidad),
        precio,
        costo,
        _safe_int(data.get("tiempo_entrega_dias")),
        clean_text(data.get("canal") or "WhatsApp"),
        clean_text(data.get("estado") or "Activo"),
        clean_text(data.get("proveedor_sugerido")),
        clean_text(data.get("tags")),
        1 if data.get("destacado") else 0,
        _safe_int(data.get("inventario_id")) or None,
        1 if data.get("usa_cmyk") else 0,
        1 if data.get("requiere_corte") else 0,
        1 if data.get("requiere_sublimacion") else 0,
        1 if data.get("requiere_produccion_manual") else 0,
        1 if data.get("requiere_otros_procesos") else 0,
        1 if data.get("activo_cotizaciones", True) else 0,
        1 if data.get("activo_ventas", True) else 0,
        1 if data.get("activo_produccion", True) else 0,
        costo_base,
        _safe_float(data.get("merma_pct_estimada")),
        clean_text(data.get("ruta_base")),
        clean_text(data.get("notas_tecnicas")),
        precio_mayorista,
        precio_minimo,
        _safe_int(data.get("stock_objetivo")),
        max(1, _safe_int(data.get("orden_minima"), 1)),
        _safe_int(data.get("lead_time_comercial_dias"), _safe_int(data.get("tiempo_entrega_dias"))),
        1 if data.get("visible_catalogo_publico", True) else 0,
        max(0, min(100, _safe_int(data.get("prioridad_comercial"), 50))),
        clean_text(data.get("temporada")),
        clean_text(data.get("coleccion")),
        clean_text(data.get("imagen_url")),
        clean_text(data.get("imagen_path")),
        clean_text(data.get("imagen_nombre")),
        clean_text(data.get("ultima_revision_precio") or datetime.now().date().isoformat()),
    )


def _insert_catalog_item(conn: Any, usuario: str, data: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO catalogo_items(
            usuario, sku, nombre, categoria, subcategoria, tipo, descripcion,
            unidad, precio, costo, tiempo_entrega_dias, canal, estado,
            proveedor_sugerido, tags, destacado, inventario_id, usa_cmyk,
            requiere_corte, requiere_sublimacion, requiere_produccion_manual,
            requiere_otros_procesos, activo_cotizaciones, activo_ventas,
            activo_produccion, costo_base_referencial, merma_pct_estimada,
            ruta_base, notas_tecnicas, precio_mayorista, precio_minimo,
            stock_objetivo, orden_minima, lead_time_comercial_dias,
            visible_catalogo_publico, prioridad_comercial, temporada, coleccion,
            imagen_url, imagen_path, imagen_nombre, ultima_revision_precio, activo
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        """,
        _catalog_tuple(usuario, data),
    )
    return int(cur.lastrowid)


def _load_catalogo_df() -> pd.DataFrame:
    _ensure_catalogo_schema()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id, fecha_creacion, fecha_actualizacion, usuario, sku, nombre,
                categoria, subcategoria, tipo, descripcion, unidad, precio, costo,
                tiempo_entrega_dias, canal, estado, proveedor_sugerido, tags,
                destacado, inventario_id, usa_cmyk, requiere_corte,
                requiere_sublimacion, requiere_produccion_manual,
                requiere_otros_procesos, activo_cotizaciones, activo_ventas,
                activo_produccion, costo_base_referencial, merma_pct_estimada,
                ruta_base, notas_tecnicas, precio_mayorista, precio_minimo,
                stock_objetivo, orden_minima, lead_time_comercial_dias,
                visible_catalogo_publico, prioridad_comercial, temporada, coleccion,
                imagen_url, imagen_path, imagen_nombre, ultima_revision_precio
            FROM catalogo_items
            WHERE COALESCE(activo,1)=1
            ORDER BY destacado DESC, prioridad_comercial DESC, nombre ASC
            """,
            conn,
        )

    if not df.empty:
        df["margen_pct"] = df.apply(lambda r: _margin_pct(r["precio"], r["costo"]), axis=1)
        df["utilidad_usd"] = df.apply(lambda r: _profit_usd(r["precio"], r["costo"]), axis=1)
        df["score_comercial"] = df.apply(_commercial_score, axis=1)
    return df


def _load_inventory_links_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()]
        if not cols:
            return pd.DataFrame(columns=["id", "label", "stock_actual"])

        nombre_col = "nombre" if "nombre" in cols else "item" if "item" in cols else None
        sku_col = "sku" if "sku" in cols else None
        stock_col = "stock_actual" if "stock_actual" in cols else None
        estado_col = "estado" if "estado" in cols else None

        if not nombre_col:
            return pd.DataFrame(columns=["id", "label", "stock_actual"])

        sql = f"SELECT id, {nombre_col} AS nombre"
        sql += f", COALESCE({sku_col}, '') AS sku" if sku_col else ", '' AS sku"
        sql += f", COALESCE({stock_col}, 0) AS stock_actual" if stock_col else ", 0 AS stock_actual"
        sql += " FROM inventario"
        if estado_col:
            sql += " WHERE COALESCE(estado,'activo')='activo'"
        sql += " ORDER BY nombre ASC"

        df = pd.read_sql_query(sql, conn)

    if df.empty:
        return pd.DataFrame(columns=["id", "label", "stock_actual"])

    df["label"] = df.apply(
        lambda r: f"{r['nombre']} ({r['sku']})" if str(r["sku"]).strip() else str(r["nombre"]),
        axis=1,
    )
    return df[["id", "label", "stock_actual"]]


def _filter_catalog(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    query = c1.text_input("Buscar", placeholder="SKU, nombre, categoría, tags, ruta...", key="cat_next_query")
    categoria = c2.selectbox("Categoría", ["Todas"] + sorted(df["categoria"].dropna().unique().tolist()), key="cat_next_categoria")
    estado = c3.selectbox("Estado", ["Todos"] + sorted(df["estado"].dropna().unique().tolist()), key="cat_next_estado")
    canal = c4.selectbox("Canal", ["Todos"] + sorted(df["canal"].dropna().unique().tolist()), key="cat_next_canal")
    tipo = c5.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].dropna().unique().tolist()), key="cat_next_tipo")

    view = df.copy()
    txt = clean_text(query)

    if txt:
        fields = [
            "sku",
            "nombre",
            "categoria",
            "subcategoria",
            "tipo",
            "descripcion",
            "tags",
            "proveedor_sugerido",
            "ruta_base",
            "notas_tecnicas",
            "coleccion",
            "temporada",
        ]
        mask = False
        for field in fields:
            mask = mask | view[field].astype(str).str.contains(txt, case=False, na=False)
        view = view[mask]

    if categoria != "Todas":
        view = view[view["categoria"] == categoria]
    if estado != "Todos":
        view = view[view["estado"] == estado]
    if canal != "Todos":
        view = view[view["canal"] == canal]
    if tipo != "Todos":
        view = view[view["tipo"] == tipo]

    return view.sort_values(["destacado", "score_comercial", "nombre"], ascending=[False, False, True])


def _render_metrics(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay productos en el catálogo.")
        return

    activos = df[df["estado"].astype(str) == "Activo"]
    con_foto = df.apply(
        lambda r: bool(_safe_text(r.get("imagen_path")) or _safe_text(r.get("imagen_url"))),
        axis=1,
    ).sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Items", len(df))
    c2.metric("Con foto", int(con_foto))
    c3.metric("Activos", len(activos))
    c4.metric("Ticket promedio", f"$ {float(activos['precio'].mean() if not activos.empty else 0):,.2f}")
    c5.metric("Margen prom.", f"{float(activos['margen_pct'].mean() if not activos.empty else 0):.1f}%")
    c6.metric("Score prom.", f"{float(df['score_comercial'].mean()):.0f}/100")


def _render_cards(view: pd.DataFrame) -> None:
    if view.empty:
        st.warning("No hay resultados con esos filtros.")
        return

    for _, row in view.head(24).iterrows():
        with st.container(border=True):
            img_col, info_col = st.columns([1, 2])

            with img_col:
                _render_product_image(row, height=220)

            with info_col:
                top1, top2, top3 = st.columns([2.6, 1.2, 1.2])
                badge = "⭐ " if _safe_int(row["destacado"]) else ""
                top1.markdown(f"### {badge}{row['nombre']}")
                top1.caption(f"{row['sku']} · {row['categoria']} / {row['subcategoria']} · {row['tipo']}")
                top2.metric("Precio", f"$ {_safe_float(row['precio']):,.2f}")
                top3.metric("Score", f"{_safe_int(row['score_comercial'])}/100")

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Costo", f"$ {_safe_float(row['costo']):,.2f}")
                m2.metric("Utilidad", f"$ {_safe_float(row['utilidad_usd']):,.2f}")
                m3.metric("Margen", f"{_safe_float(row['margen_pct']):.1f}%")
                m4.metric("Entrega", f"{_safe_int(row['lead_time_comercial_dias'])} días")
                m5.metric("Mínimo", f"{_safe_int(row['orden_minima'])} {row['unidad']}")

                st.write(row["descripcion"] or "Sin descripción.")
                st.caption(
                    f"Canal: {row['canal']} · Estado: {row['estado']} · Colección: {row.get('coleccion') or '-'} · Tags: {row.get('tags') or '-'}"
                )

                if row.get("ruta_base"):
                    st.code(str(row["ruta_base"]), language="text")


def _collect_form_values(prefix: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
    base = base or {}

    c1, c2, c3 = st.columns([1, 2, 1])
    sku = c1.text_input("SKU", value=_safe_text(base.get("sku")), key=f"{prefix}_sku")
    nombre = c2.text_input("Nombre comercial", value=_safe_text(base.get("nombre")), key=f"{prefix}_nombre")
    estado = c3.selectbox(
        "Estado",
        DEFAULT_STATUS,
        index=DEFAULT_STATUS.index(base.get("estado")) if base.get("estado") in DEFAULT_STATUS else 0,
        key=f"{prefix}_estado",
    )

    c4, c5, c6, c7 = st.columns(4)
    categoria = c4.selectbox(
        "Categoría",
        DEFAULT_CATEGORIES,
        index=DEFAULT_CATEGORIES.index(base.get("categoria")) if base.get("categoria") in DEFAULT_CATEGORIES else 0,
        key=f"{prefix}_categoria",
    )
    subcategoria = c5.text_input("Subcategoría", value=_safe_text(base.get("subcategoria")), key=f"{prefix}_subcategoria")
    tipo = c6.selectbox(
        "Tipo",
        DEFAULT_TYPES,
        index=DEFAULT_TYPES.index(base.get("tipo")) if base.get("tipo") in DEFAULT_TYPES else 0,
        key=f"{prefix}_tipo",
    )
    unidad = c7.selectbox(
        "Unidad",
        DEFAULT_UNITS,
        index=DEFAULT_UNITS.index(base.get("unidad")) if base.get("unidad") in DEFAULT_UNITS else 0,
        key=f"{prefix}_unidad",
    )

    descripcion = st.text_area("Descripción vendedora", value=_safe_text(base.get("descripcion")), height=90, key=f"{prefix}_descripcion")

    p1, p2, p3, p4 = st.columns(4)
    precio = p1.number_input("Precio público USD", min_value=0.0, value=_safe_float(base.get("precio")), step=1.0, key=f"{prefix}_precio")
    costo = p2.number_input("Costo USD", min_value=0.0, value=_safe_float(base.get("costo")), step=1.0, key=f"{prefix}_costo")
    precio_mayorista = p3.number_input(
        "Precio mayorista",
        min_value=0.0,
        value=_safe_float(base.get("precio_mayorista")),
        step=1.0,
        key=f"{prefix}_precio_mayorista",
    )
    precio_minimo = p4.number_input(
        "Precio mínimo",
        min_value=0.0,
        value=_safe_float(base.get("precio_minimo")),
        step=1.0,
        key=f"{prefix}_precio_minimo",
    )

    c8, c9, c10, c11 = st.columns(4)
    canal = c8.selectbox(
        "Canal principal",
        DEFAULT_CHANNELS,
        index=DEFAULT_CHANNELS.index(base.get("canal")) if base.get("canal") in DEFAULT_CHANNELS else 0,
        key=f"{prefix}_canal",
    )
    tiempo_entrega = c9.number_input(
        "Entrega producción días",
        min_value=0,
        value=_safe_int(base.get("tiempo_entrega_dias")),
        step=1,
        key=f"{prefix}_tiempo",
    )
    lead_time = c10.number_input(
        "Promesa comercial días",
        min_value=0,
        value=_safe_int(base.get("lead_time_comercial_dias"), _safe_int(base.get("tiempo_entrega_dias"))),
        step=1,
        key=f"{prefix}_lead",
    )
    prioridad = c11.slider(
        "Prioridad comercial",
        min_value=0,
        max_value=100,
        value=_safe_int(base.get("prioridad_comercial"), 50),
        key=f"{prefix}_prioridad",
    )

    c12, c13, c14, c15 = st.columns(4)
    stock_objetivo = c12.number_input("Stock objetivo", min_value=0, value=_safe_int(base.get("stock_objetivo")), step=1, key=f"{prefix}_stock")
    orden_minima = c13.number_input(
        "Orden mínima",
        min_value=1,
        value=max(1, _safe_int(base.get("orden_minima"), 1)),
        step=1,
        key=f"{prefix}_orden_minima",
    )
    merma = c14.number_input("Merma estimada %", min_value=0.0, value=_safe_float(base.get("merma_pct_estimada")), step=0.5, key=f"{prefix}_merma")
    costo_base = c15.number_input(
        "Costo base ref.",
        min_value=0.0,
        value=_safe_float(base.get("costo_base_referencial"), _safe_float(base.get("costo"))),
        step=1.0,
        key=f"{prefix}_costo_base",
    )

    proveedor = st.text_input("Proveedor sugerido", value=_safe_text(base.get("proveedor_sugerido")), key=f"{prefix}_proveedor")
    tags = st.text_input("Tags", value=_safe_text(base.get("tags")), key=f"{prefix}_tags")
    ruta_base = st.text_input("Ruta base de producción", value=_safe_text(base.get("ruta_base")), key=f"{prefix}_ruta")
    notas = st.text_area("Notas técnicas", value=_safe_text(base.get("notas_tecnicas")), height=80, key=f"{prefix}_notas")

    b1, b2, b3, b4, b5 = st.columns(5)
    destacado = b1.checkbox("Destacado", value=bool(_safe_int(base.get("destacado"))), key=f"{prefix}_destacado")
    visible = b2.checkbox("Visible público", value=bool(_safe_int(base.get("visible_catalogo_publico"), 1)), key=f"{prefix}_visible")
    activo_cot = b3.checkbox("Cotizaciones", value=bool(_safe_int(base.get("activo_cotizaciones"), 1)), key=f"{prefix}_cot")
    activo_ventas = b4.checkbox("Ventas", value=bool(_safe_int(base.get("activo_ventas"), 1)), key=f"{prefix}_ventas")
    activo_prod = b5.checkbox("Producción", value=bool(_safe_int(base.get("activo_produccion"), 1)), key=f"{prefix}_prod")

    r1, r2, r3, r4, r5 = st.columns(5)
    usa_cmyk = r1.checkbox("CMYK", value=bool(_safe_int(base.get("usa_cmyk"))), key=f"{prefix}_cmyk")
    req_corte = r2.checkbox("Corte", value=bool(_safe_int(base.get("requiere_corte"))), key=f"{prefix}_corte")
    req_sub = r3.checkbox("Sublimación", value=bool(_safe_int(base.get("requiere_sublimacion"))), key=f"{prefix}_sub")
    req_manual = r4.checkbox("Manual", value=bool(_safe_int(base.get("requiere_produccion_manual"))), key=f"{prefix}_manual")
    req_otros = r5.checkbox("Otros proc.", value=bool(_safe_int(base.get("requiere_otros_procesos"))), key=f"{prefix}_otros")

    st.markdown("#### 📸 Foto del producto")
    img_col1, img_col2 = st.columns([1, 2])

    with img_col1:
        _render_product_image(base, height=220)

    with img_col2:
        uploaded_image = st.file_uploader(
            "Subir foto del producto",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{prefix}_uploaded_image",
        )

        if uploaded_image is not None:
            st.image(uploaded_image, caption="Vista previa", width=260)

        imagen_url = st.text_input(
            "O pega URL de imagen",
            value=_safe_text(base.get("imagen_url")),
            key=f"{prefix}_imagen",
        )

    temporada = st.text_input("Temporada", value=_safe_text(base.get("temporada")), key=f"{prefix}_temporada")
    coleccion = st.text_input("Colección", value=_safe_text(base.get("coleccion")), key=f"{prefix}_coleccion")

    return {
        "sku": sku,
        "nombre": nombre,
        "categoria": categoria,
        "subcategoria": subcategoria,
        "tipo": tipo,
        "descripcion": descripcion,
        "unidad": unidad,
        "precio": precio,
        "costo": costo,
        "tiempo_entrega_dias": tiempo_entrega,
        "canal": canal,
        "estado": estado,
        "proveedor_sugerido": proveedor,
        "tags": tags,
        "destacado": destacado,
        "usa_cmyk": usa_cmyk,
        "requiere_corte": req_corte,
        "requiere_sublimacion": req_sub,
        "requiere_produccion_manual": req_manual,
        "requiere_otros_procesos": req_otros,
        "activo_cotizaciones": activo_cot,
        "activo_ventas": activo_ventas,
        "activo_produccion": activo_prod,
        "costo_base_referencial": costo_base,
        "merma_pct_estimada": merma,
        "ruta_base": ruta_base,
        "notas_tecnicas": notas,
        "precio_mayorista": precio_mayorista,
        "precio_minimo": precio_minimo,
        "stock_objetivo": stock_objetivo,
        "orden_minima": orden_minima,
        "lead_time_comercial_dias": lead_time,
        "visible_catalogo_publico": visible,
        "prioridad_comercial": prioridad,
        "temporada": temporada,
        "coleccion": coleccion,
        "imagen_url": imagen_url,
        "uploaded_image": uploaded_image,
        "imagen_path": base.get("imagen_path"),
        "imagen_nombre": base.get("imagen_nombre"),
        "ultima_revision_precio": datetime.now().date().isoformat(),
    }


def _create_item(usuario: str, data: dict[str, Any]) -> int:
    _ensure_catalogo_schema()

    uploaded = data.pop("uploaded_image", None)
    image_path, image_name = _save_uploaded_image(uploaded, _safe_text(data.get("sku")))

    if image_path:
        data["imagen_path"] = image_path
        data["imagen_nombre"] = image_name

    with db_transaction() as conn:
        sku = require_text(data.get("sku"), "SKU").upper()
        exists = conn.execute(
            "SELECT id FROM catalogo_items WHERE upper(sku)=? AND COALESCE(activo,1)=1",
            (sku,),
        ).fetchone()

        if exists:
            raise ValueError("Ya existe un item activo con ese SKU.")

        return _insert_catalog_item(conn, usuario, data)


def _update_item(item_id: int, usuario: str, data: dict[str, Any]) -> None:
    _ensure_catalogo_schema()

    uploaded = data.pop("uploaded_image", None)
    image_path, image_name = _save_uploaded_image(uploaded, _safe_text(data.get("sku")))

    if image_path:
        data["imagen_path"] = image_path
        data["imagen_nombre"] = image_name

    with db_transaction() as conn:
        sku = require_text(data.get("sku"), "SKU").upper()
        exists = conn.execute(
            "SELECT id FROM catalogo_items WHERE upper(sku)=? AND id != ? AND COALESCE(activo,1)=1",
            (sku, int(item_id)),
        ).fetchone()

        if exists:
            raise ValueError("Ya existe otro item activo con ese SKU.")

        conn.execute(
            """
            UPDATE catalogo_items
            SET fecha_actualizacion=CURRENT_TIMESTAMP,
                usuario=?, sku=?, nombre=?, categoria=?, subcategoria=?, tipo=?, descripcion=?,
                unidad=?, precio=?, costo=?, tiempo_entrega_dias=?, canal=?, estado=?,
                proveedor_sugerido=?, tags=?, destacado=?, inventario_id=?, usa_cmyk=?,
                requiere_corte=?, requiere_sublimacion=?, requiere_produccion_manual=?,
                requiere_otros_procesos=?, activo_cotizaciones=?, activo_ventas=?,
                activo_produccion=?, costo_base_referencial=?, merma_pct_estimada=?,
                ruta_base=?, notas_tecnicas=?, precio_mayorista=?, precio_minimo=?,
                stock_objetivo=?, orden_minima=?, lead_time_comercial_dias=?,
                visible_catalogo_publico=?, prioridad_comercial=?, temporada=?, coleccion=?,
                imagen_url=?, imagen_path=?, imagen_nombre=?, ultima_revision_precio=?
            WHERE id=?
            """,
            _catalog_tuple(usuario, data) + (int(item_id),),
        )


def _archive_item(item_id: int) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE catalogo_items SET activo=0, estado='Archivado', fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
            (int(item_id),),
        )


def _render_studio(df: pd.DataFrame, usuario: str) -> None:
    st.subheader("Product Studio")
    tab_new, tab_edit = st.tabs(["Crear producto", "Editar producto"])

    with tab_new:
        if not _can_create():
            st.info("Modo solo lectura: necesitas catalogo.create o inventario.create para crear productos.")

        data = _collect_form_values("cat_new")
        st.caption(
            f"Margen estimado: {_margin_pct(data['precio'], data['costo']):.1f}% · "
            f"Score estimado: {_commercial_score(data)}/100"
        )

        if st.button("✨ Crear en catálogo", disabled=not _can_create(), use_container_width=True, key="cat_new_submit"):
            try:
                new_id = _create_item(usuario, data)
                st.success(f"Producto #{new_id} creado correctamente.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_edit:
        if df.empty:
            st.info("No hay productos para editar.")
            return

        item_id = st.selectbox(
            "Producto",
            df["id"].tolist(),
            format_func=lambda x: f"{df[df['id'] == x]['sku'].iloc[0]} · {df[df['id'] == x]['nombre'].iloc[0]}",
            key="cat_edit_item",
        )

        row = df[df["id"] == item_id].iloc[0].to_dict()
        data = _collect_form_values("cat_edit", row)

        st.caption(
            f"Margen estimado: {_margin_pct(data['precio'], data['costo']):.1f}% · "
            f"Score estimado: {_commercial_score(data)}/100"
        )

        c1, c2 = st.columns(2)

        if c1.button("💾 Guardar cambios", disabled=not _can_edit(), use_container_width=True, key="cat_edit_submit"):
            try:
                _update_item(int(item_id), usuario, data)
                st.success("Producto actualizado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo actualizar: {exc}")

        if c2.button("🗃️ Archivar producto", disabled=not _can_delete(), use_container_width=True, key="cat_archive_submit"):
            try:
                _archive_item(int(item_id))
                st.success("Producto archivado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo archivar: {exc}")


def _render_export_import(df: pd.DataFrame, usuario: str) -> None:
    st.subheader("Importar / Exportar")

    if _can_export() and not df.empty:
        export_cols = [
            "sku",
            "nombre",
            "categoria",
            "subcategoria",
            "tipo",
            "descripcion",
            "unidad",
            "precio",
            "costo",
            "precio_mayorista",
            "precio_minimo",
            "margen_pct",
            "tiempo_entrega_dias",
            "lead_time_comercial_dias",
            "canal",
            "estado",
            "proveedor_sugerido",
            "tags",
            "destacado",
            "visible_catalogo_publico",
            "prioridad_comercial",
            "score_comercial",
            "temporada",
            "coleccion",
            "imagen_url",
            "imagen_path",
            "imagen_nombre",
            "ruta_base",
            "notas_tecnicas",
        ]
        csv = df[export_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Exportar catálogo CSV",
            data=csv,
            file_name="catalogo_imperio_atomico.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("Necesitas catalogo.export o inventario.view para exportar.")

    st.divider()
    st.markdown("#### Importación rápida CSV")
    st.caption("Columnas mínimas: sku, nombre, categoria, precio, costo. Las demás son opcionales.")
    uploaded = st.file_uploader("Subir CSV", type=["csv"], key="cat_import_csv")

    if uploaded is not None:
        try:
            import_df = pd.read_csv(uploaded)
            st.dataframe(import_df.head(20), use_container_width=True, hide_index=True)

            if st.button("Importar filas nuevas", disabled=not _can_create(), use_container_width=True):
                created = 0
                errors: list[str] = []

                with db_transaction() as conn:
                    for idx, raw in import_df.iterrows():
                        data = raw.to_dict()
                        sku = _safe_text(data.get("sku")).upper()

                        if not sku:
                            errors.append(f"Fila {idx + 1}: SKU vacío")
                            continue

                        exists = conn.execute(
                            "SELECT id FROM catalogo_items WHERE upper(sku)=? AND COALESCE(activo,1)=1",
                            (sku,),
                        ).fetchone()

                        if exists:
                            errors.append(f"Fila {idx + 1}: SKU duplicado {sku}")
                            continue

                        try:
                            _insert_catalog_item(conn, usuario, data)
                            created += 1
                        except Exception as exc:
                            errors.append(f"Fila {idx + 1}: {exc}")

                st.success(f"Importación completada. Creados: {created}")

                if errors:
                    st.warning("Algunas filas no se importaron.")
                    st.write(errors[:20])

                st.rerun()
        except Exception as exc:
            st.error(f"No se pudo leer el CSV: {exc}")


def _render_insights(df: pd.DataFrame) -> None:
    st.subheader("Insights comerciales")

    if df.empty:
        st.info("No hay datos suficientes.")
        return

    c1, c2 = st.columns(2)

    with c1:
        por_categoria = df.groupby("categoria", as_index=False).agg(
            items=("id", "count"),
            ticket=("precio", "mean"),
            margen=("margen_pct", "mean"),
        )
        st.caption("Categorías por cantidad")
        st.bar_chart(por_categoria.set_index("categoria")["items"])
        st.dataframe(por_categoria.round(2), use_container_width=True, hide_index=True)

    with c2:
        top_score = df.sort_values("score_comercial", ascending=False).head(10)[
            ["sku", "nombre", "score_comercial", "margen_pct", "precio"]
        ]
        st.caption("Top productos por score comercial")
        st.dataframe(top_score, use_container_width=True, hide_index=True)

    alertas = df[
        (df["margen_pct"] < 25)
        | (df["precio"] <= df["costo"])
        | (df["visible_catalogo_publico"] == 0)
    ].copy()

    if not alertas.empty:
        st.warning("Productos que requieren revisión de precio, margen o visibilidad.")
        st.dataframe(
            alertas[
                [
                    "sku",
                    "nombre",
                    "precio",
                    "costo",
                    "margen_pct",
                    "visible_catalogo_publico",
                    "estado",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_catalogo_hub(usuario: str) -> None:
    _ensure_catalogo_schema()

    if not _can_view():
        st.error("🚫 No tienes acceso al Catálogo.")
        return

    st.caption("Catálogo comercial avanzado: productos, servicios, precios, rutas, fotos, canales y readiness para ventas.")

    if not (_can_create() or _can_edit()):
        st.info("Modo solo lectura: puedes consultar y exportar, pero no crear ni editar productos.")

    df = _load_catalogo_df()
    _render_metrics(df)

    tab_catalog, tab_studio, tab_integraciones, tab_insights, tab_data = st.tabs(
    [
        "🛍️ Catálogo Pro",
        "✨ Product Studio",
        "🔗 Integraciones",
        "📊 Insights",
        "⬇️ Datos",
    ]
)

    with tab_catalog:
        view = _filter_catalog(df)
        view_mode = st.radio("Vista", ["Tarjetas", "Tabla ejecutiva"], horizontal=True, key="cat_next_view_mode")

        if view_mode == "Tarjetas":
            _render_cards(view)
        else:
            cols = [
                "sku",
                "nombre",
                "categoria",
                "tipo",
                "estado",
                "canal",
                "precio",
                "costo",
                "utilidad_usd",
                "margen_pct",
                "score_comercial",
                "prioridad_comercial",
                "visible_catalogo_publico",
                "imagen_url",
                "imagen_path",
                "ruta_base",
            ]
            st.dataframe(view[cols], use_container_width=True, hide_index=True)

    with tab_studio:
        _render_studio(df, usuario)

    with tab_integraciones:
    _render_module_dispatcher(df, usuario)

    with tab_insights:
        _render_insights(df)

    with tab_data:
        _render_export_import(df, usuario)

        with st.expander("Permisos del módulo"):
            st.write(
                {
                    "catalogo.view": _can_view(),
                    "catalogo.create": _can_create(),
                    "catalogo.edit": _can_edit(),
                    "catalogo.delete": _can_delete(),
                    "catalogo.export": _can_export(),
                }
            )
