from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    nombre: str
    categoria: str
    tipo: str
    precio: float
    costo: float
    tiempo_entrega_dias: int
    canal: str
    estado: str

    @property
    def margen_pct(self) -> float:
        if self.precio <= 0:
            return 0.0
        return ((self.precio - self.costo) / self.precio) * 100


DEFAULT_ITEMS: tuple[CatalogItem, ...] = (
    CatalogItem("CAT-001", "Tarjeta PVC Premium", "Impresión", "Producto", 22.0, 11.5, 2, "WhatsApp", "Activo"),
    CatalogItem("CAT-002", "Sticker troquelado", "Sublimación", "Producto", 18.0, 8.7, 1, "Instagram", "Activo"),
    CatalogItem("CAT-003", "Kit Branding Express", "Paquetes", "Paquete", 125.0, 61.0, 4, "Web", "Activo"),
    CatalogItem("CAT-004", "Diseño para gran formato", "Servicios", "Servicio", 60.0, 22.0, 2, "WhatsApp", "Borrador"),
)


def _get_catalog_df() -> pd.DataFrame:
    if "catalogo_items" not in st.session_state:
        st.session_state["catalogo_items"] = [item.__dict__ for item in DEFAULT_ITEMS]
    return pd.DataFrame(st.session_state["catalogo_items"])


def _save_catalog_df(df: pd.DataFrame) -> None:
    st.session_state["catalogo_items"] = df.to_dict(orient="records")


def render_catalogo_hub(usuario: str | None = None) -> None:
    st.markdown("## 🛍️ Catálogo comercial 360")
    if usuario:
        st.caption(f"Gestión de catálogo para {usuario} · versión avanzada")

    df = _get_catalog_df()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Items publicados", int((df["estado"] == "Activo").sum()))
    c2.metric("Margen promedio", f"{((df['precio'] - df['costo']) / df['precio']).fillna(0).mean() * 100:.1f}%")
    c3.metric("Ticket promedio", f"${df['precio'].mean():.2f}")
    c4.metric("Canales activos", df["canal"].nunique())

    st.markdown("### 🎯 Filtros inteligentes")
    f1, f2, f3 = st.columns(3)
    categorias = ["Todas"] + sorted(df["categoria"].dropna().unique().tolist())
    estados = ["Todos"] + sorted(df["estado"].dropna().unique().tolist())
    canales = ["Todos"] + sorted(df["canal"].dropna().unique().tolist())

    categoria = f1.selectbox("Categoría", categorias)
    estado = f2.selectbox("Estado", estados)
    canal = f3.selectbox("Canal", canales)

    filtrado = df.copy()
    if categoria != "Todas":
        filtrado = filtrado[filtrado["categoria"] == categoria]
    if estado != "Todos":
        filtrado = filtrado[filtrado["estado"] == estado]
    if canal != "Todos":
        filtrado = filtrado[filtrado["canal"] == canal]

    tab_portafolio, tab_editor, tab_copy = st.tabs(["🧾 Portafolio", "🛠️ Editor rápido", "📲 Copy comercial"])

    with tab_portafolio:
        st.dataframe(
            filtrado.assign(
                margen_pct=lambda x: ((x["precio"] - x["costo"]) / x["precio"]).fillna(0).mul(100).round(1),
                precio=lambda x: x["precio"].map(lambda v: f"${v:,.2f}"),
                costo=lambda x: x["costo"].map(lambda v: f"${v:,.2f}"),
            ),
            use_container_width=True,
            hide_index=True,
        )

        csv_buffer = io.StringIO()
        filtrado.to_csv(csv_buffer, index=False)
        st.download_button(
            "⬇️ Exportar catálogo filtrado",
            data=csv_buffer.getvalue(),
            file_name="catalogo_filtrado.csv",
            mime="text/csv",
        )

    with tab_editor:
        with st.form("nuevo_item_catalogo", clear_on_submit=True):
            st.markdown("### Nuevo ítem")
            e1, e2, e3 = st.columns(3)
            sku = e1.text_input("SKU")
            nombre = e2.text_input("Nombre")
            categoria_new = e3.text_input("Categoría")
            e4, e5, e6 = st.columns(3)
            tipo = e4.selectbox("Tipo", ["Producto", "Servicio", "Paquete"])
            precio = e5.number_input("Precio", min_value=0.0, step=1.0)
            costo = e6.number_input("Costo", min_value=0.0, step=1.0)
            e7, e8, e9 = st.columns(3)
            entrega = e7.number_input("Entrega (días)", min_value=0, step=1)
            canal_new = e8.selectbox("Canal", ["WhatsApp", "Instagram", "Web", "Sucursal"])
            estado_new = e9.selectbox("Estado", ["Activo", "Borrador", "Pausado"])

            submitted = st.form_submit_button("Guardar ítem")
            if submitted and sku and nombre and categoria_new:
                nuevo = pd.DataFrame(
                    [
                        {
                            "sku": sku.strip(),
                            "nombre": nombre.strip(),
                            "categoria": categoria_new.strip(),
                            "tipo": tipo,
                            "precio": float(precio),
                            "costo": float(costo),
                            "tiempo_entrega_dias": int(entrega),
                            "canal": canal_new,
                            "estado": estado_new,
                        }
                    ]
                )
                actualizado = pd.concat([df, nuevo], ignore_index=True)
                _save_catalog_df(actualizado)
                st.success("Ítem agregado al catálogo.")
                st.rerun()

    with tab_copy:
        if filtrado.empty:
            st.info("No hay registros con ese filtro.")
        else:
            item = filtrado.iloc[0]
            copy = (
                f"🔥 {item['nombre']} ({item['sku']})\n"
                f"Categoría: {item['categoria']} · Tipo: {item['tipo']}\n"
                f"Precio desde: ${item['precio']:.2f}\n"
                f"Entrega estimada: {int(item['tiempo_entrega_dias'])} día(s)\n"
                "¿Te cotizo ahora mismo?"
            )
            st.text_area("Mensaje listo para WhatsApp/Instagram", value=copy, height=140)
            st.code(copy)
