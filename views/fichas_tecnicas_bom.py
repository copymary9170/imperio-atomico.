from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission

UNIDADES = ["unidad", "hoja", "metro", "cm", "ml", "litro", "kg", "g", "minuto", "hora", "pieza", "rollo", "resma", "caja"]
TIPOS_COMPONENTE = ["material", "mano_obra", "maquina", "servicio", "empaque", "otro"]
ESTADOS = ["Borrador", "Activa", "En revisión", "Obsoleta"]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fichas_tecnicas_bom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                codigo TEXT NOT NULL,
                producto TEXT NOT NULL,
                categoria TEXT,
                version TEXT NOT NULL DEFAULT '1.0',
                cantidad_base REAL NOT NULL DEFAULT 1,
                unidad_base TEXT NOT NULL DEFAULT 'unidad',
                tiempo_estandar_min REAL NOT NULL DEFAULT 0,
                merma_estandar_pct REAL NOT NULL DEFAULT 0,
                costo_materiales_usd REAL NOT NULL DEFAULT 0,
                costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
                costo_indirecto_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                margen_sugerido_pct REAL NOT NULL DEFAULT 30,
                precio_sugerido_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Borrador',
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fichas_tecnicas_bom_componentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ficha_id INTEGER NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'material',
                item TEXT NOT NULL,
                inventario_id INTEGER,
                cantidad REAL NOT NULL DEFAULT 1,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                merma_pct REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                orden INTEGER NOT NULL DEFAULT 1,
                notas TEXT,
                FOREIGN KEY (ficha_id) REFERENCES fichas_tecnicas_bom(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bom_codigo ON fichas_tecnicas_bom(codigo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bom_componentes_ficha ON fichas_tecnicas_bom_componentes(ficha_id)")


def _read_fichas() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM fichas_tecnicas_bom ORDER BY id DESC LIMIT 500", conn)


def _read_componentes(ficha_id: int | None = None) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if ficha_id:
            return pd.read_sql_query(
                "SELECT * FROM fichas_tecnicas_bom_componentes WHERE ficha_id=? ORDER BY orden, id",
                conn,
                params=(ficha_id,),
            )
        return pd.read_sql_query("SELECT * FROM fichas_tecnicas_bom_componentes ORDER BY ficha_id DESC, orden, id LIMIT 1000", conn)


def _create_ficha(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO fichas_tecnicas_bom(
                usuario, codigo, producto, categoria, version, cantidad_base, unidad_base,
                tiempo_estandar_min, merma_estandar_pct, margen_sugerido_pct, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["codigo"], data["producto"], data.get("categoria"), data.get("version", "1.0"),
                float(data.get("cantidad_base", 1)), data.get("unidad_base", "unidad"),
                float(data.get("tiempo_estandar_min", 0)), float(data.get("merma_estandar_pct", 0)),
                float(data.get("margen_sugerido_pct", 30)), data.get("estado", "Borrador"), data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def _add_component(data: dict[str, Any]) -> None:
    _ensure_tables()
    cantidad = float(data.get("cantidad", 0))
    costo_unit = float(data.get("costo_unitario_usd", 0))
    merma = float(data.get("merma_pct", 0))
    costo_total = cantidad * costo_unit * (1 + merma / 100)
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO fichas_tecnicas_bom_componentes(
                ficha_id, tipo, item, inventario_id, cantidad, unidad, costo_unitario_usd,
                merma_pct, costo_total_usd, orden, notas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(data["ficha_id"]), data.get("tipo", "material"), data["item"], data.get("inventario_id"),
                cantidad, data.get("unidad", "unidad"), costo_unit, merma, costo_total,
                int(data.get("orden", 1)), data.get("notas"),
            ),
        )
    _recalculate_ficha(int(data["ficha_id"]))


def _recalculate_ficha(ficha_id: int) -> None:
    comps = _read_componentes(ficha_id)
    if comps.empty:
        materiales = mano_obra = indirecto = total = precio = 0.0
    else:
        comps["costo_total_usd"] = pd.to_numeric(comps["costo_total_usd"], errors="coerce").fillna(0.0)
        materiales = float(comps[comps["tipo"].eq("material")]["costo_total_usd"].sum())
        mano_obra = float(comps[comps["tipo"].eq("mano_obra")]["costo_total_usd"].sum())
        indirecto = float(comps[~comps["tipo"].isin(["material", "mano_obra"])]["costo_total_usd"].sum())
        total = materiales + mano_obra + indirecto
        with db_transaction() as conn:
            row = conn.execute("SELECT margen_sugerido_pct FROM fichas_tecnicas_bom WHERE id=?", (ficha_id,)).fetchone()
        margen = float(row[0] if row else 30)
        precio = total * (1 + margen / 100)
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE fichas_tecnicas_bom
            SET costo_materiales_usd=?, costo_mano_obra_usd=?, costo_indirecto_usd=?, costo_total_usd=?, precio_sugerido_usd=?
            WHERE id=?
            """,
            (materiales, mano_obra, indirecto, total, precio, ficha_id),
        )


def _delete_component(component_id: int, ficha_id: int) -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM fichas_tecnicas_bom_componentes WHERE id=?", (component_id,))
    _recalculate_ficha(ficha_id)


def render_fichas_tecnicas_bom(usuario: str = "Sistema") -> None:
    if not require_any_permission(["bom.view", "bom.edit", "produccion.route", "costeo.view"], "🚫 No tienes acceso a fichas técnicas / BOM."):
        return
    puede_editar = has_permission("bom.edit")

    st.subheader("📝 Fichas técnicas / BOM")
    st.caption("Recetas de producto: materiales, unidades fraccionadas, mano de obra, merma estándar, costo y precio sugerido.")
    if not puede_editar:
        st.info("Modo consulta: puedes ver y simular recetas, pero no crear ni modificar fichas/componentes.")
    _ensure_tables()

    fichas = _read_fichas()
    componentes = _read_componentes()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fichas", len(fichas))
    c2.metric("Activas", int(fichas["estado"].eq("Activa").sum()) if not fichas.empty else 0)
    c3.metric("Componentes", len(componentes))
    c4.metric("Costo recetas", f"${float(pd.to_numeric(fichas.get('costo_total_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not fichas.empty else 0:,.2f}")

    tab_nueva, tab_componentes, tab_listado, tab_simulador = st.tabs([
        "Nueva ficha",
        "Componentes",
        "Listado",
        "Simulador",
    ])

    with tab_nueva:
        with st.form("form_nueva_bom"):
            a, b, c = st.columns(3)
            codigo = a.text_input("Código ficha", disabled=not puede_editar)
            producto = b.text_input("Producto", disabled=not puede_editar)
            categoria = c.text_input("Categoría", disabled=not puede_editar)
            d, e, f = st.columns(3)
            version = d.text_input("Versión", value="1.0", disabled=not puede_editar)
            cantidad_base = e.number_input("Cantidad base", min_value=0.01, value=1.0, step=1.0, disabled=not puede_editar)
            unidad_base = f.selectbox("Unidad base", UNIDADES, disabled=not puede_editar)
            g, h, i = st.columns(3)
            tiempo = g.number_input("Tiempo estándar min", min_value=0.0, value=0.0, step=1.0, disabled=not puede_editar)
            merma = h.number_input("Merma estándar %", min_value=0.0, value=0.0, step=0.5, disabled=not puede_editar)
            margen = i.number_input("Margen sugerido %", min_value=0.0, value=30.0, step=1.0, disabled=not puede_editar)
            estado = st.selectbox("Estado", ESTADOS, disabled=not puede_editar)
            observaciones = st.text_area("Observaciones", disabled=not puede_editar)
            guardar = st.form_submit_button("Crear ficha", disabled=not puede_editar)
        if guardar:
            if not codigo.strip() or not producto.strip():
                st.error("Código y producto son obligatorios.")
            else:
                ficha_id = _create_ficha({
                    "usuario": usuario,
                    "codigo": codigo.strip(),
                    "producto": producto.strip(),
                    "categoria": categoria.strip(),
                    "version": version.strip() or "1.0",
                    "cantidad_base": cantidad_base,
                    "unidad_base": unidad_base,
                    "tiempo_estandar_min": tiempo,
                    "merma_estandar_pct": merma,
                    "margen_sugerido_pct": margen,
                    "estado": estado,
                    "observaciones": observaciones.strip(),
                })
                st.success(f"Ficha técnica #{ficha_id} creada.")
                st.rerun()

    with tab_componentes:
        if fichas.empty:
            st.info("Primero crea una ficha técnica.")
        else:
            opciones = fichas["id"].astype(int).tolist()
            ficha_id = st.selectbox(
                "Ficha",
                opciones,
                format_func=lambda x: f"#{x} · {fichas.loc[fichas['id'].eq(x), 'codigo'].iloc[0]} · {fichas.loc[fichas['id'].eq(x), 'producto'].iloc[0]}",
            )
            with st.form("form_componente_bom"):
                a, b, c = st.columns(3)
                tipo = a.selectbox("Tipo", TIPOS_COMPONENTE, disabled=not puede_editar)
                item = b.text_input("Item / material / recurso", disabled=not puede_editar)
                unidad = c.selectbox("Unidad consumo", UNIDADES, disabled=not puede_editar)
                d, e, f, g = st.columns(4)
                cantidad = d.number_input("Cantidad por base", min_value=0.0, value=1.0, step=0.1, disabled=not puede_editar)
                costo_unit = e.number_input("Costo unitario USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
                merma_comp = f.number_input("Merma %", min_value=0.0, value=0.0, step=0.5, disabled=not puede_editar)
                orden = g.number_input("Orden", min_value=1, value=1, step=1, disabled=not puede_editar)
                inventario_id = st.number_input("Inventario ID opcional", min_value=0, value=0, step=1, disabled=not puede_editar)
                notas = st.text_area("Notas del componente", disabled=not puede_editar)
                agregar = st.form_submit_button("Agregar componente", disabled=not puede_editar)
            if agregar:
                if not item.strip():
                    st.error("El item es obligatorio.")
                else:
                    _add_component({
                        "ficha_id": int(ficha_id),
                        "tipo": tipo,
                        "item": item.strip(),
                        "inventario_id": int(inventario_id) or None,
                        "cantidad": cantidad,
                        "unidad": unidad,
                        "costo_unitario_usd": costo_unit,
                        "merma_pct": merma_comp,
                        "orden": int(orden),
                        "notas": notas.strip(),
                    })
                    st.success("Componente agregado y costo recalculado.")
                    st.rerun()

            comps = _read_componentes(int(ficha_id))
            if comps.empty:
                st.info("Esta ficha todavía no tiene componentes.")
            else:
                st.dataframe(comps, use_container_width=True, hide_index=True)
                eliminar = st.selectbox("Eliminar componente", [0] + comps["id"].astype(int).tolist(), format_func=lambda x: "No eliminar" if x == 0 else f"Componente #{x}", disabled=not puede_editar)
                if eliminar and st.button("Eliminar componente seleccionado", disabled=not puede_editar):
                    _delete_component(int(eliminar), int(ficha_id))
                    st.success("Componente eliminado.")
                    st.rerun()

    with tab_listado:
        if fichas.empty:
            st.info("No hay fichas técnicas registradas.")
        else:
            filtro = st.text_input("Buscar ficha")
            vista = fichas.copy()
            if filtro.strip():
                mask = vista.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False)).any(axis=1)
                vista = vista[mask]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            if not componentes.empty:
                st.markdown("#### Componentes registrados")
                st.dataframe(componentes, use_container_width=True, hide_index=True)

    with tab_simulador:
        if fichas.empty:
            st.info("Crea fichas para simular costos por cantidad.")
        else:
            ficha_id_sim = st.selectbox(
                "Ficha a simular",
                fichas["id"].astype(int).tolist(),
                key="sim_bom_ficha",
                format_func=lambda x: f"#{x} · {fichas.loc[fichas['id'].eq(x), 'codigo'].iloc[0]} · {fichas.loc[fichas['id'].eq(x), 'producto'].iloc[0]}",
            )
            cantidad_sim = st.number_input("Cantidad a producir", min_value=1.0, value=1.0, step=1.0)
            ficha = fichas[fichas["id"].eq(ficha_id_sim)].iloc[0]
            costo_unit = float(ficha.get("costo_total_usd") or 0)
            precio_unit = float(ficha.get("precio_sugerido_usd") or 0)
            merma_std = float(ficha.get("merma_estandar_pct") or 0)
            costo_total = costo_unit * cantidad_sim * (1 + merma_std / 100)
            precio_total = precio_unit * cantidad_sim
            s1, s2, s3 = st.columns(3)
            s1.metric("Costo estimado", f"${costo_total:,.2f}")
            s2.metric("Precio sugerido", f"${precio_total:,.2f}")
            s3.metric("Margen estimado", f"${precio_total - costo_total:,.2f}")
            comps = _read_componentes(int(ficha_id_sim))
            if not comps.empty:
                req = comps.copy()
                req["cantidad_requerida"] = pd.to_numeric(req["cantidad"], errors="coerce").fillna(0) * float(cantidad_sim) * (1 + pd.to_numeric(req["merma_pct"], errors="coerce").fillna(0) / 100)
                st.markdown("#### Requerimiento de materiales / recursos")
                st.dataframe(req[["tipo", "item", "cantidad_requerida", "unidad", "costo_unitario_usd", "costo_total_usd"]], use_container_width=True, hide_index=True)
