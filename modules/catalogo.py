from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, money, require_text


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
        )
        view = view[mask]

    if categoria != "Todas":
        view = view[view["categoria"] == categoria]
    if estado != "Todos":
        view = view[view["estado"] == estado]
    if canal != "Todos":
        view = view[view["canal"] == canal]

    return view


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

        total = conn.execute("SELECT COUNT(*) AS c FROM catalogo_items WHERE COALESCE(activo,1)=1").fetchone()
        if int(total["c"] or 0) == 0:
            for item in DEFAULT_ITEMS:
                conn.execute(
                    """
                    INSERT INTO catalogo_items(
                        usuario, sku, nombre, categoria, subcategoria, tipo, descripcion,
                        unidad, precio, costo, tiempo_entrega_dias, canal, estado,
                        proveedor_sugerido, tags, destacado, activo
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
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
                destacado
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
                proveedor_sugerido, tags, destacado, activo
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
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
                destacado=?
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
        st.caption(f"Gestión de catálogo para {usuario} · versión SQLite")

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
        _render_copy_catalogo(filtrado)
