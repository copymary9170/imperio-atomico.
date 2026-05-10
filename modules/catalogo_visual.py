from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, money, require_text
from security.permissions import has_permission


ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOG_IMAGES_DIR = ROOT_DIR / "data" / "catalogo_fotos"

CATALOGO_PERMISSIONS = (
    ("catalogo.view", "Consultar catálogo comercial."),
    ("catalogo.create", "Crear productos y servicios en catálogo."),
    ("catalogo.edit", "Editar productos y servicios del catálogo."),
    ("catalogo.delete", "Desactivar productos y servicios del catálogo."),
    ("catalogo.export", "Exportar catálogo comercial."),
)

DEFAULT_CATEGORIES = ["Impresión", "Sublimación", "Paquetes", "Servicios", "Accesorios", "Corporativo", "Temporada"]
DEFAULT_CHANNELS = ["WhatsApp", "Instagram", "Web", "Tienda", "Mayorista", "Aliados"]
DEFAULT_TYPES = ["Producto", "Servicio", "Paquete", "Combo", "Personalizado"]
DEFAULT_STATUS = ["Activo", "Borrador", "Pausado", "Agotado", "Archivado"]
DEFAULT_UNITS = ["unidad", "kit", "servicio", "m2", "docena", "paquete"]


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


def _margin_pct(precio: float, costo: float) -> float:
    precio = _safe_float(precio)
    costo = _safe_float(costo)
    if precio <= 0:
        return 0.0
    return ((precio - costo) / precio) * 100


def _commercial_score(row: pd.Series | dict[str, Any]) -> int:
    precio = _safe_float(row.get("precio", 0))
    costo = _safe_float(row.get("costo", 0))
    margen = _margin_pct(precio, costo)
    prioridad = max(0, min(100, _safe_int(row.get("prioridad_comercial", 50), 50)))
    destacado = 12 if _safe_int(row.get("destacado", 0)) else 0
    visible = 8 if _safe_int(row.get("visible_catalogo_publico", 1)) else -10
    estado = _safe_text(row.get("estado", "Activo"))
    estado_score = 10 if estado == "Activo" else -15 if estado in {"Pausado", "Agotado", "Archivado"} else 0
    margen_score = max(0, min(35, int(margen * 0.7)))
    return max(0, min(100, int((prioridad * 0.35) + margen_score + destacado + visible + estado_score)))


def _can_view() -> bool:
    return has_permission("catalogo.view") or has_permission("inventario.view") or has_permission("dashboard.view")


def _can_create() -> bool:
    return has_permission("catalogo.create") or has_permission("inventario.create")


def _can_edit() -> bool:
    return has_permission("catalogo.edit") or has_permission("inventario.edit")


def _can_delete() -> bool:
    return has_permission("catalogo.delete") or has_permission("inventario.edit")


def _can_export() -> bool:
    return has_permission("catalogo.export") or has_permission("inventario.view")


def _seed_catalog_permissions() -> None:
    with db_transaction() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "permisos" in tables:
            conn.executemany(
                "INSERT OR IGNORE INTO permisos (codigo, descripcion) VALUES (?, ?)",
                CATALOGO_PERMISSIONS,
            )
        if "roles_permisos" in tables:
            all_codes = [code for code, _ in CATALOGO_PERMISSIONS]
            conn.executemany(
                "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Admin', ?)",
                [(code,) for code in all_codes],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Administration', ?)",
                [(code,) for code in all_codes],
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
        missing = {
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
            "ruta_base": "TEXT",
            "notas_tecnicas": "TEXT",
            "activo_cotizaciones": "INTEGER NOT NULL DEFAULT 1",
            "activo_ventas": "INTEGER NOT NULL DEFAULT 1",
            "activo_produccion": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, definition in missing.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE catalogo_items ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_sku ON catalogo_items(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_categoria ON catalogo_items(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalogo_estado ON catalogo_items(estado)")

        total = conn.execute("SELECT COUNT(*) AS c FROM catalogo_items WHERE COALESCE(activo,1)=1").fetchone()
        if int(total["c"] or 0) == 0:
            _insert_item(
                conn,
                "system",
                {
                    "sku": "CAT-001",
                    "nombre": "Tarjeta PVC Premium",
                    "categoria": "Impresión",
                    "subcategoria": "Tarjetas",
                    "tipo": "Producto",
                    "descripcion": "Tarjeta PVC de alta duración con acabado premium.",
                    "unidad": "unidad",
                    "precio": 22,
                    "costo": 11.5,
                    "tiempo_entrega_dias": 2,
                    "canal": "WhatsApp",
                    "estado": "Activo",
                    "tags": "pvc, tarjeta, premium",
                    "destacado": 1,
                    "visible_catalogo_publico": 1,
                    "prioridad_comercial": 85,
                    "ruta_base": "CMYK > Corte > Calidad",
                },
            )


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return value.strip("-")[:60] or "producto"


def _save_uploaded_image(uploaded_file: Any, sku: str) -> tuple[str, str] | tuple[None, None]:
    if uploaded_file is None:
        return None, None
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


def _load_df() -> pd.DataFrame:
    _ensure_catalogo_schema()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM catalogo_items
            WHERE COALESCE(activo,1)=1
            ORDER BY destacado DESC, prioridad_comercial DESC, nombre ASC
            """,
            conn,
        )
    if not df.empty:
        df["margen_pct"] = df.apply(lambda r: _margin_pct(r.get("precio"), r.get("costo")), axis=1)
        df["utilidad_usd"] = df.apply(lambda r: _safe_float(r.get("precio")) - _safe_float(r.get("costo")), axis=1)
        df["score_comercial"] = df.apply(_commercial_score, axis=1)
    return df


def _item_values(usuario: str, data: dict[str, Any]) -> dict[str, Any]:
    sku = require_text(data.get("sku"), "SKU").upper()
    nombre = require_text(data.get("nombre"), "Nombre")
    categoria = require_text(data.get("categoria"), "Categoría")
    precio = money(_safe_float(data.get("precio")))
    costo = money(_safe_float(data.get("costo")))
    precio_mayorista = money(_safe_float(data.get("precio_mayorista"), precio * 0.85 if precio else 0))
    precio_minimo = money(_safe_float(data.get("precio_minimo"), costo * 1.15 if costo else 0))
    return {
        "usuario": usuario,
        "sku": sku,
        "nombre": clean_text(nombre),
        "categoria": clean_text(categoria),
        "subcategoria": clean_text(data.get("subcategoria")),
        "tipo": clean_text(data.get("tipo") or "Producto"),
        "descripcion": clean_text(data.get("descripcion")),
        "unidad": clean_text(data.get("unidad") or "unidad"),
        "precio": precio,
        "costo": costo,
        "tiempo_entrega_dias": _safe_int(data.get("tiempo_entrega_dias")),
        "canal": clean_text(data.get("canal") or "WhatsApp"),
        "estado": clean_text(data.get("estado") or "Activo"),
        "proveedor_sugerido": clean_text(data.get("proveedor_sugerido")),
        "tags": clean_text(data.get("tags")),
        "destacado": 1 if data.get("destacado") else 0,
        "precio_mayorista": precio_mayorista,
        "precio_minimo": precio_minimo,
        "stock_objetivo": _safe_int(data.get("stock_objetivo")),
        "orden_minima": max(1, _safe_int(data.get("orden_minima"), 1)),
        "lead_time_comercial_dias": _safe_int(data.get("lead_time_comercial_dias"), _safe_int(data.get("tiempo_entrega_dias"))),
        "visible_catalogo_publico": 1 if data.get("visible_catalogo_publico", True) else 0,
        "prioridad_comercial": max(0, min(100, _safe_int(data.get("prioridad_comercial"), 50))),
        "temporada": clean_text(data.get("temporada")),
        "coleccion": clean_text(data.get("coleccion")),
        "imagen_url": clean_text(data.get("imagen_url")),
        "imagen_path": clean_text(data.get("imagen_path")),
        "imagen_nombre": clean_text(data.get("imagen_nombre")),
        "ruta_base": clean_text(data.get("ruta_base")),
        "notas_tecnicas": clean_text(data.get("notas_tecnicas")),
        "activo_cotizaciones": 1 if data.get("activo_cotizaciones", True) else 0,
        "activo_ventas": 1 if data.get("activo_ventas", True) else 0,
        "activo_produccion": 1 if data.get("activo_produccion", True) else 0,
        "ultima_revision_precio": datetime.now().date().isoformat(),
    }


def _insert_item(conn: Any, usuario: str, data: dict[str, Any]) -> int:
    vals = _item_values(usuario, data)
    columns = ", ".join(vals.keys())
    placeholders = ", ".join(["?"] * len(vals))
    cur = conn.execute(
        f"INSERT INTO catalogo_items({columns}, activo) VALUES({placeholders}, 1)",
        tuple(vals.values()),
    )
    return int(cur.lastrowid)


def _create_item(usuario: str, data: dict[str, Any]) -> int:
    _ensure_catalogo_schema()
    uploaded = data.pop("uploaded_image", None)
    image_path, image_name = _save_uploaded_image(uploaded, _safe_text(data.get("sku")))
    if image_path:
        data["imagen_path"] = image_path
        data["imagen_nombre"] = image_name
    with db_transaction() as conn:
        sku = require_text(data.get("sku"), "SKU").upper()
        exists = conn.execute("SELECT id FROM catalogo_items WHERE upper(sku)=? AND COALESCE(activo,1)=1", (sku,)).fetchone()
        if exists:
            raise ValueError("Ya existe un producto activo con ese SKU.")
        return _insert_item(conn, usuario, data)


def _update_item(item_id: int, usuario: str, data: dict[str, Any], current: dict[str, Any]) -> None:
    _ensure_catalogo_schema()
    uploaded = data.pop("uploaded_image", None)
    image_path, image_name = _save_uploaded_image(uploaded, _safe_text(data.get("sku")))
    if image_path:
        data["imagen_path"] = image_path
        data["imagen_nombre"] = image_name
    else:
        data["imagen_path"] = current.get("imagen_path")
        data["imagen_nombre"] = current.get("imagen_nombre")
    vals = _item_values(usuario, data)
    assignments = ", ".join([f"{col}=?" for col in vals.keys()])
    with db_transaction() as conn:
        sku = vals["sku"]
        exists = conn.execute(
            "SELECT id FROM catalogo_items WHERE upper(sku)=? AND id != ? AND COALESCE(activo,1)=1",
            (sku, int(item_id)),
        ).fetchone()
        if exists:
            raise ValueError("Ya existe otro producto activo con ese SKU.")
        conn.execute(
            f"UPDATE catalogo_items SET fecha_actualizacion=CURRENT_TIMESTAMP, {assignments} WHERE id=?",
            tuple(vals.values()) + (int(item_id),),
        )


def _archive_item(item_id: int) -> None:
    with db_transaction() as conn:
        conn.execute("UPDATE catalogo_items SET activo=0, estado='Archivado', fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?", (int(item_id),))


def _form(prefix: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
    base = base or {}
    c_img, c_main = st.columns([1, 2])
    with c_img:
        st.markdown("#### Foto del producto")
        _render_product_image(base, height=240)
        uploaded_image = st.file_uploader(
            "Subir foto",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{prefix}_uploaded_image",
        )
        if uploaded_image is not None:
            st.image(uploaded_image, caption="Vista previa", use_container_width=True)
        imagen_url = st.text_input("O pega URL de imagen", value=_safe_text(base.get("imagen_url")), key=f"{prefix}_imagen_url")

    with c_main:
        c1, c2, c3 = st.columns([1, 2, 1])
        sku = c1.text_input("SKU", value=_safe_text(base.get("sku")), key=f"{prefix}_sku")
        nombre = c2.text_input("Nombre comercial", value=_safe_text(base.get("nombre")), key=f"{prefix}_nombre")
        estado = c3.selectbox("Estado", DEFAULT_STATUS, index=DEFAULT_STATUS.index(base.get("estado")) if base.get("estado") in DEFAULT_STATUS else 0, key=f"{prefix}_estado")
        categoria = st.selectbox("Categoría", DEFAULT_CATEGORIES, index=DEFAULT_CATEGORIES.index(base.get("categoria")) if base.get("categoria") in DEFAULT_CATEGORIES else 0, key=f"{prefix}_categoria")
        descripcion = st.text_area("Descripción", value=_safe_text(base.get("descripcion")), height=95, key=f"{prefix}_descripcion")

    c4, c5, c6, c7 = st.columns(4)
    subcategoria = c4.text_input("Subcategoría", value=_safe_text(base.get("subcategoria")), key=f"{prefix}_subcategoria")
    tipo = c5.selectbox("Tipo", DEFAULT_TYPES, index=DEFAULT_TYPES.index(base.get("tipo")) if base.get("tipo") in DEFAULT_TYPES else 0, key=f"{prefix}_tipo")
    unidad = c6.selectbox("Unidad", DEFAULT_UNITS, index=DEFAULT_UNITS.index(base.get("unidad")) if base.get("unidad") in DEFAULT_UNITS else 0, key=f"{prefix}_unidad")
    canal = c7.selectbox("Canal", DEFAULT_CHANNELS, index=DEFAULT_CHANNELS.index(base.get("canal")) if base.get("canal") in DEFAULT_CHANNELS else 0, key=f"{prefix}_canal")

    p1, p2, p3, p4 = st.columns(4)
    precio = p1.number_input("Precio público", min_value=0.0, value=_safe_float(base.get("precio")), step=1.0, key=f"{prefix}_precio")
    costo = p2.number_input("Costo", min_value=0.0, value=_safe_float(base.get("costo")), step=1.0, key=f"{prefix}_costo")
    precio_mayorista = p3.number_input("Precio mayorista", min_value=0.0, value=_safe_float(base.get("precio_mayorista")), step=1.0, key=f"{prefix}_precio_mayorista")
    precio_minimo = p4.number_input("Precio mínimo", min_value=0.0, value=_safe_float(base.get("precio_minimo")), step=1.0, key=f"{prefix}_precio_minimo")

    o1, o2, o3, o4 = st.columns(4)
    tiempo = o1.number_input("Entrega días", min_value=0, value=_safe_int(base.get("tiempo_entrega_dias")), step=1, key=f"{prefix}_tiempo")
    lead = o2.number_input("Promesa días", min_value=0, value=_safe_int(base.get("lead_time_comercial_dias"), _safe_int(base.get("tiempo_entrega_dias"))), step=1, key=f"{prefix}_lead")
    stock = o3.number_input("Stock objetivo", min_value=0, value=_safe_int(base.get("stock_objetivo")), step=1, key=f"{prefix}_stock")
    orden = o4.number_input("Orden mínima", min_value=1, value=max(1, _safe_int(base.get("orden_minima"), 1)), step=1, key=f"{prefix}_orden")

    proveedor = st.text_input("Proveedor sugerido", value=_safe_text(base.get("proveedor_sugerido")), key=f"{prefix}_proveedor")
    tags = st.text_input("Tags", value=_safe_text(base.get("tags")), key=f"{prefix}_tags")
    ruta = st.text_input("Ruta productiva", value=_safe_text(base.get("ruta_base")), key=f"{prefix}_ruta")
    notas = st.text_area("Notas técnicas", value=_safe_text(base.get("notas_tecnicas")), height=70, key=f"{prefix}_notas")

    b1, b2, b3, b4, b5 = st.columns(5)
    destacado = b1.checkbox("Destacado", value=bool(_safe_int(base.get("destacado"))), key=f"{prefix}_destacado")
    visible = b2.checkbox("Visible público", value=bool(_safe_int(base.get("visible_catalogo_publico"), 1)), key=f"{prefix}_visible")
    cot = b3.checkbox("Cotizaciones", value=bool(_safe_int(base.get("activo_cotizaciones"), 1)), key=f"{prefix}_cot")
    ventas = b4.checkbox("Ventas", value=bool(_safe_int(base.get("activo_ventas"), 1)), key=f"{prefix}_ventas")
    prod = b5.checkbox("Producción", value=bool(_safe_int(base.get("activo_produccion"), 1)), key=f"{prefix}_prod")

    temporada = st.text_input("Temporada", value=_safe_text(base.get("temporada")), key=f"{prefix}_temporada")
    coleccion = st.text_input("Colección", value=_safe_text(base.get("coleccion")), key=f"{prefix}_coleccion")
    prioridad = st.slider("Prioridad comercial", 0, 100, _safe_int(base.get("prioridad_comercial"), 50), key=f"{prefix}_prioridad")

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
        "precio_mayorista": precio_mayorista,
        "precio_minimo": precio_minimo,
        "tiempo_entrega_dias": tiempo,
        "lead_time_comercial_dias": lead,
        "canal": canal,
        "estado": estado,
        "proveedor_sugerido": proveedor,
        "tags": tags,
        "destacado": destacado,
        "stock_objetivo": stock,
        "orden_minima": orden,
        "visible_catalogo_publico": visible,
        "prioridad_comercial": prioridad,
        "temporada": temporada,
        "coleccion": coleccion,
        "imagen_url": imagen_url,
        "uploaded_image": uploaded_image,
        "ruta_base": ruta,
        "notas_tecnicas": notas,
        "activo_cotizaciones": cot,
        "activo_ventas": ventas,
        "activo_produccion": prod,
    }


def _render_metrics(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay productos en catálogo.")
        return
    activos = df[df["estado"].astype(str) == "Activo"]
    con_foto = df.apply(lambda r: bool(_safe_text(r.get("imagen_path")) or _safe_text(r.get("imagen_url"))), axis=1).sum()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Items", len(df))
    c2.metric("Con foto", int(con_foto))
    c3.metric("Activos", len(activos))
    c4.metric("Ticket prom.", f"$ {float(activos['precio'].mean() if not activos.empty else 0):,.2f}")
    c5.metric("Margen prom.", f"{float(activos['margen_pct'].mean() if not activos.empty else 0):.1f}%")
    c6.metric("Score prom.", f"{float(df['score_comercial'].mean()):.0f}/100")


def _filter_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    query = c1.text_input("Buscar", placeholder="SKU, nombre, tags, colección...", key="cat_visual_query")
    categoria = c2.selectbox("Categoría", ["Todas"] + sorted(df["categoria"].dropna().unique().tolist()), key="cat_visual_categoria")
    estado = c3.selectbox("Estado", ["Todos"] + sorted(df["estado"].dropna().unique().tolist()), key="cat_visual_estado")
    solo_fotos = c4.checkbox("Solo con foto", key="cat_visual_solo_fotos")
    view = df.copy()
    txt = clean_text(query)
    if txt:
        mask = False
        for field in ["sku", "nombre", "categoria", "subcategoria", "descripcion", "tags", "coleccion", "temporada"]:
            mask = mask | view[field].astype(str).str.contains(txt, case=False, na=False)
        view = view[mask]
    if categoria != "Todas":
        view = view[view["categoria"] == categoria]
    if estado != "Todos":
        view = view[view["estado"] == estado]
    if solo_fotos:
        view = view[view.apply(lambda r: bool(_safe_text(r.get("imagen_path")) or _safe_text(r.get("imagen_url"))), axis=1)]
    return view.sort_values(["destacado", "score_comercial", "nombre"], ascending=[False, False, True])


def _render_showroom(view: pd.DataFrame) -> None:
    if view.empty:
        st.warning("No hay productos con esos filtros.")
        return
    rows = list(view.head(36).iterrows())
    for i in range(0, len(rows), 3):
        cols = st.columns(3)
        for col, (_, row) in zip(cols, rows[i:i + 3]):
            with col:
                with st.container(border=True):
                    _render_product_image(row, height=210)
                    badge = "⭐ " if _safe_int(row.get("destacado")) else ""
                    st.markdown(f"#### {badge}{row['nombre']}")
                    st.caption(f"{row['sku']} · {row['categoria']} · {row['estado']}")
                    m1, m2 = st.columns(2)
                    m1.metric("Precio", f"$ {_safe_float(row['precio']):,.2f}")
                    m2.metric("Margen", f"{_safe_float(row['margen_pct']):.1f}%")
                    st.write(_safe_text(row.get("descripcion"), "Sin descripción."))
                    st.caption(f"Score {int(row['score_comercial'])}/100 · {row.get('canal') or '-'} · {row.get('coleccion') or '-'}")


def _render_studio(df: pd.DataFrame, usuario: str) -> None:
    tab_new, tab_edit = st.tabs(["➕ Crear producto con foto", "✏️ Editar foto / producto"])
    with tab_new:
        data = _form("cat_photo_new")
        st.caption(f"Margen estimado: {_margin_pct(data['precio'], data['costo']):.1f}% · Score estimado: {_commercial_score(data)}/100")
        if st.button("✨ Crear producto", disabled=not _can_create(), use_container_width=True):
            try:
                new_id = _create_item(usuario, data)
                st.success(f"Producto #{new_id} creado con foto correctamente.")
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
            key="cat_photo_edit_id",
        )
        current = df[df["id"] == item_id].iloc[0].to_dict()
        data = _form("cat_photo_edit", current)
        c1, c2 = st.columns(2)
        if c1.button("💾 Guardar cambios", disabled=not _can_edit(), use_container_width=True):
            try:
                _update_item(int(item_id), usuario, data, current)
                st.success("Producto actualizado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo actualizar: {exc}")
        if c2.button("🗃️ Archivar", disabled=not _can_delete(), use_container_width=True):
            try:
                _archive_item(int(item_id))
                st.success("Producto archivado.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo archivar: {exc}")


def _render_data(df: pd.DataFrame) -> None:
    if df.empty:
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    if _can_export():
        export = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Exportar catálogo con fotos", export, "catalogo_con_fotos.csv", "text/csv", use_container_width=True)


def _render_visual_header() -> None:
    st.markdown(
        """
        <div style="padding:1.2rem 1.4rem;border-radius:24px;background:linear-gradient(135deg,#ff4d00,#ff006e,#6d28d9);color:white;margin-bottom:1rem;box-shadow:0 24px 60px rgba(0,0,0,.28);">
            <div style="font-size:.78rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;opacity:.88;">📸 Catálogo visual activo</div>
            <div style="font-size:2.15rem;font-weight:900;line-height:1.1;margin-top:.2rem;">Fotos reales para identificar cada producto</div>
            <div style="margin-top:.55rem;opacity:.9;max-width:850px;">Sube imágenes PNG, JPG o WEBP, guarda cada foto en el producto y visualízala en tarjetas tipo showroom.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_catalogo_hub(usuario: str) -> None:
    _ensure_catalogo_schema()
    if not _can_view():
        st.error("🚫 No tienes acceso al Catálogo.")
        return
    _render_visual_header()
    if not (_can_create() or _can_edit()):
        st.info("Modo solo lectura: puedes ver fotos y productos, pero no crear ni editar.")
    df = _load_df()
    _render_metrics(df)
    tab_showroom, tab_studio, tab_table = st.tabs(["🖼️ Showroom", "📸 Fotos y edición", "📋 Datos"])
    with tab_showroom:
        view = _filter_df(df)
        _render_showroom(view)
    with tab_studio:
        _render_studio(df, usuario)
    with tab_table:
        _render_data(df)
        with st.expander("Permisos"):
            st.write(
                {
                    "catalogo.view": _can_view(),
                    "catalogo.create": _can_create(),
                    "catalogo.edit": _can_edit(),
                    "catalogo.delete": _can_delete(),
                    "catalogo.export": _can_export(),
                }
            )
