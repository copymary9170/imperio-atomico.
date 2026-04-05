from __future__ import annotations

import io
from dataclasses import dataclass, asdict

import pandas as pd
import streamlit as st


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
    destacado: bool

    @property
    def margen_pct(self) -> float:
        if self.precio <= 0:
            return 0.0
        return ((self.precio - self.costo) / self.precio) * 100


DEFAULT_ITEMS: tuple[CatalogItem, ...] = (
    CatalogItem(
        "CAT-001",
        "Tarjeta PVC Premium",
        "Impresión",
        "Tarjetas",
        "Producto",
        "Tarjeta PVC de alta duración con acabado premium.",
        "unidad",
        22.0,
        11.5,
        2,
        "WhatsApp",
        "Activo",
        "Proveedor PVC Norte",
        "pvc,tarjeta,premium",
        True,
    ),
    CatalogItem(
        "CAT-002",
        "Sticker troquelado",
        "Sublimación",
        "Stickers",
        "Producto",
        "Sticker personalizado con corte troquelado.",
        "unidad",
        18.0,
        8.7,
        1,
        "Instagram",
        "Activo",
        "Sticker Labs",
        "sticker,troquelado,personalizado",
        False,
    ),
    CatalogItem(
        "CAT-003",
        "Kit Branding Express",
        "Paquetes",
        "Branding",
        "Paquete",
        "Paquete express para branding inicial de marca.",
        "kit",
        125.0,
        61.0,
        4,
        "Web",
        "Activo",
        "Varios",
        "branding,kit,emprendedores",
        True,
    ),
    CatalogItem(
        "CAT-004",
        "Diseño para gran formato",
        "Servicios",
        "Diseño",
        "Servicio",
        "Diseño gráfico listo para impresión en gran formato.",
        "servicio",
        60.0,
        22.0,
        2,
        "WhatsApp",
        "Borrador",
        "Interno",
        "diseño,gran formato",
        False,
    ),
)


# ============================================================
# DATOS
# ============================================================

def _catalog_columns() -> list[str]:
    return [
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


def _get_catalog_df() -> pd.DataFrame:
    if "catalogo_items" not in st.session_state:
        st.session_state["catalogo_items"] = [asdict(item) for item in DEFAULT_ITEMS]

    df = pd.DataFrame(st.session_state["catalogo_items"])
    if df.empty:
        df = pd.DataFrame(columns=_catalog_columns())

    for col in _catalog_columns():
        if col not in df.columns:
            if col == "destacado":
                df[col] = False
            elif col in {"precio", "costo", "tiempo_entrega_dias"}:
                df[col] = 0
            else:
                df[col] = ""

    return df[_catalog_columns()].copy()


def _save_catalog_df(df: pd.DataFrame) -> None:
    df = df.copy()
    st.session_state["catalogo_items"] = df.to_dict(orient="records")


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _sku_exists(df: pd.DataFrame, sku: str, exclude_sku: str | None = None) -> bool:
    sku_norm = _normalize_text(sku).upper()
    if not sku_norm:
        return False

    work = df.copy()
    work["sku"] = work["sku"].astype(str).str.upper().str.strip()

    if exclude_sku:
        work = work[work["sku"] != _normalize_text(exclude_sku).upper()]

    return sku_norm in work["sku"].tolist()


def _build_margin_pct(precio: float, costo: float) -> float:
    if float(precio or 0) <= 0:
        return 0.0
    return ((float(precio) - float(costo)) / float(precio)) * 100


def _filter_catalog(
    df: pd.DataFrame,
    query: str,
    categoria: str,
    estado: str,
    canal: str,
) -> pd.DataFrame:
    filtrado = df.copy()

    if query.strip():
        q = query.strip().lower()
        mask = (
            filtrado["sku"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["nombre"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["categoria"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["subcategoria"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["descripcion"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["tags"].astype(str).str.lower().str.contains(q, na=False)
            | filtrado["proveedor_sugerido"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtrado = filtrado[mask]

    if categoria != "Todas":
        filtrado = filtrado[filtrado["categoria"] == categoria]

    if estado != "Todos":
        filtrado = filtrado[filtrado["estado"] == estado]

    if canal != "Todos":
        filtrado = filtrado[filtrado["canal"] == canal]

    return filtrado


# ============================================================
# UI HELPERS
# ============================================================

def _render_metrics(df: pd.DataFrame) -> None:
    activos = df[df["estado"] == "Activo"].copy()

    if activos.empty:
        items_publicados = 0
        margen_promedio = 0.0
        ticket_promedio = 0.0
        canales_activos = 0
        destacados = 0
    else:
        margen_series = activos.apply(lambda r: _build_margin_pct(r["precio"], r["costo"]), axis=1)
        items_publicados = len(activos)
        margen_promedio = float(margen_series.mean())
        ticket_promedio = float(activos["precio"].mean())
        canales_activos = int(activos["canal"].nunique())
        destacados = int(activos["destacado"].fillna(False).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Items publicados", items_publicados)
    c2.metric("Margen promedio", f"{margen_promedio:.1f}%")
    c3.metric("Ticket promedio", f"${ticket_promedio:.2f}")
    c4.metric("Canales activos", canales_activos)
    c5.metric("Destacados", destacados)


def _render_portafolio(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay items para mostrar con los filtros actuales.")
        return

    table_df = df.copy()
    table_df["margen_pct"] = table_df.apply(lambda r: round(_build_margin_pct(r["precio"], r["costo"]), 1), axis=1)

    st.dataframe(
        table_df[
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


def _render_editor(df: pd.DataFrame) -> None:
    st.markdown("### 🛠️ Editor de catálogo")

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

            submitted = st.form_submit_button("Guardar item")

            if submitted:
                sku_norm = _normalize_text(sku)
                nombre_norm = _normalize_text(nombre)
                categoria_norm = _normalize_text(categoria)

                if not sku_norm or not nombre_norm or not categoria_norm:
                    st.error("SKU, nombre y categoría son obligatorios.")
                elif _sku_exists(df, sku_norm):
                    st.error("Ya existe un item con ese SKU.")
                else:
                    nuevo = pd.DataFrame(
                        [
                            {
                                "sku": sku_norm,
                                "nombre": nombre_norm,
                                "categoria": categoria_norm,
                                "subcategoria": _normalize_text(subcategoria),
                                "tipo": tipo,
                                "descripcion": _normalize_text(descripcion),
                                "unidad": _normalize_text(unidad),
                                "precio": float(precio),
                                "costo": float(costo),
                                "tiempo_entrega_dias": int(entrega),
                                "canal": canal,
                                "estado": estado,
                                "proveedor_sugerido": _normalize_text(proveedor_sugerido),
                                "tags": _normalize_text(tags),
                                "destacado": bool(destacado),
                            }
                        ]
                    )
                    actualizado = pd.concat([df, nuevo], ignore_index=True)
                    _save_catalog_df(actualizado)
                    st.success("Ítem agregado al catálogo.")
                    st.rerun()

    with subtabs[1]:
        if df.empty:
            st.info("No hay items para editar.")
        else:
            sku_edit = st.selectbox(
                "Selecciona un item",
                options=df["sku"].tolist(),
                format_func=lambda x: f"{x} · {df[df['sku'] == x]['nombre'].iloc[0]}",
                key="catalogo_edit_sku",
            )
            row = df[df["sku"] == sku_edit].iloc[0]

            with st.form("catalogo_editar_item"):
                c1, c2, c3, c4 = st.columns(4)
                sku_new = c1.text_input("SKU", value=str(row["sku"]))
                nombre_new = c2.text_input("Nombre", value=str(row["nombre"]))
                categoria_new = c3.text_input("Categoría", value=str(row["categoria"]))
                subcategoria_new = c4.text_input("Subcategoría", value=str(row["subcategoria"]))

                c5, c6, c7 = st.columns(3)
                tipo_new = c5.selectbox(
                    "Tipo",
                    ["Producto", "Servicio", "Paquete"],
                    index=["Producto", "Servicio", "Paquete"].index(str(row["tipo"])),
                )
                unidad_new = c6.text_input("Unidad", value=str(row["unidad"]))
                proveedor_new = c7.text_input("Proveedor sugerido", value=str(row["proveedor_sugerido"]))

                descripcion_new = st.text_area("Descripción", value=str(row["descripcion"]))

                c8, c9, c10, c11 = st.columns(4)
                precio_new = c8.number_input("Precio", min_value=0.0, value=float(row["precio"]), step=1.0)
                costo_new = c9.number_input("Costo", min_value=0.0, value=float(row["costo"]), step=1.0)
                entrega_new = c10.number_input("Entrega (días)", min_value=0, value=int(row["tiempo_entrega_dias"]), step=1)
                canal_new = c11.selectbox(
                    "Canal",
                    ["WhatsApp", "Instagram", "Web", "Sucursal"],
                    index=["WhatsApp", "Instagram", "Web", "Sucursal"].index(str(row["canal"])),
                )

                c12, c13 = st.columns(2)
                estado_new = c12.selectbox(
                    "Estado",
                    ["Activo", "Borrador", "Pausado", "Descontinuado"],
                    index=["Activo", "Borrador", "Pausado", "Descontinuado"].index(str(row["estado"])),
                )
                destacado_new = c13.checkbox("Destacado", value=bool(row["destacado"]))

                tags_new = st.text_input("Tags", value=str(row["tags"]))

                submitted = st.form_submit_button("Actualizar item")

                if submitted:
                    sku_norm = _normalize_text(sku_new)
                    nombre_norm = _normalize_text(nombre_new)
                    categoria_norm = _normalize_text(categoria_new)

                    if not sku_norm or not nombre_norm or not categoria_norm:
                        st.error("SKU, nombre y categoría son obligatorios.")
                    elif _sku_exists(df, sku_norm, exclude_sku=sku_edit):
                        st.error("Ya existe otro item con ese SKU.")
                    else:
                        actualizado = df.copy()
                        idx = actualizado[actualizado["sku"] == sku_edit].index[0]

                        actualizado.loc[idx, "sku"] = sku_norm
                        actualizado.loc[idx, "nombre"] = nombre_norm
                        actualizado.loc[idx, "categoria"] = categoria_norm
                        actualizado.loc[idx, "subcategoria"] = _normalize_text(subcategoria_new)
                        actualizado.loc[idx, "tipo"] = tipo_new
                        actualizado.loc[idx, "descripcion"] = _normalize_text(descripcion_new)
                        actualizado.loc[idx, "unidad"] = _normalize_text(unidad_new)
                        actualizado.loc[idx, "precio"] = float(precio_new)
                        actualizado.loc[idx, "costo"] = float(costo_new)
                        actualizado.loc[idx, "tiempo_entrega_dias"] = int(entrega_new)
                        actualizado.loc[idx, "canal"] = canal_new
                        actualizado.loc[idx, "estado"] = estado_new
                        actualizado.loc[idx, "proveedor_sugerido"] = _normalize_text(proveedor_new)
                        actualizado.loc[idx, "tags"] = _normalize_text(tags_new)
                        actualizado.loc[idx, "destacado"] = bool(destacado_new)

                        _save_catalog_df(actualizado)
                        st.success("Ítem actualizado.")
                        st.rerun()

    with subtabs[2]:
        if df.empty:
            st.info("No hay items para eliminar.")
        else:
            sku_delete = st.selectbox(
                "Selecciona item a eliminar",
                options=df["sku"].tolist(),
                format_func=lambda x: f"{x} · {df[df['sku'] == x]['nombre'].iloc[0]}",
                key="catalogo_delete_sku",
            )

            if st.button("🗑 Eliminar item", use_container_width=True):
                actualizado = df[df["sku"] != sku_delete].copy()
                _save_catalog_df(actualizado)
                st.success("Ítem eliminado.")
                st.rerun()


def _render_copy_comercial(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No hay registros con ese filtro.")
        return

    sku_copy = st.selectbox(
        "Selecciona item para generar copy",
        options=df["sku"].tolist(),
        format_func=lambda x: f"{x} · {df[df['sku'] == x]['nombre'].iloc[0]}",
        key="catalogo_copy_sku",
    )
    item = df[df["sku"] == sku_copy].iloc[0]

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
    st.markdown("## 🛍️ Catálogo comercial 360")
    if usuario:
        st.caption(f"Gestión de catálogo para {usuario} · versión mejorada")

    df = _get_catalog_df()

    _render_metrics(df)

    st.markdown("### 🎯 Filtros inteligentes")
    f0, f1, f2, f3 = st.columns(4)

    query = f0.text_input("Buscar", placeholder="SKU, nombre, tags, proveedor...")
    categorias = ["Todas"] + sorted(df["categoria"].dropna().astype(str).unique().tolist())
    estados = ["Todos"] + sorted(df["estado"].dropna().astype(str).unique().tolist())
    canales = ["Todos"] + sorted(df["canal"].dropna().astype(str).unique().tolist())

    categoria = f1.selectbox("Categoría", categorias)
    estado = f2.selectbox("Estado", estados)
    canal = f3.selectbox("Canal", canales)

    filtrado = _filter_catalog(df, query, categoria, estado, canal)

    tab_portafolio, tab_editor, tab_copy = st.tabs(
        ["🧾 Portafolio", "🛠️ Editor", "📲 Copy comercial"]
    )

    with tab_portafolio:
        _render_portafolio(filtrado)

    with tab_editor:
        _render_editor(df)

    with tab_copy:
        _render_copy_comercial(filtrado)
