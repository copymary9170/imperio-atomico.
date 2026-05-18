from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

UNIDADES_COMPRA = ["rollo", "resma", "caja", "paquete", "litro", "galon", "kg", "metro", "unidad"]
UNIDADES_CONSUMO = ["cm", "metro", "hoja", "unidad", "pieza", "ml", "g", "kg"]
TIPOS_MATERIAL = ["Vinil", "Papel", "Tinta", "Tela", "Sublimacion", "Empaque", "Otro"]

PRESETS = {
    "rollo_50m_a_cm": ("rollo", "cm", 5000.0),
    "rollo_30m_a_cm": ("rollo", "cm", 3000.0),
    "metro_a_cm": ("metro", "cm", 100.0),
    "resma_a_hoja": ("resma", "hoja", 500.0),
    "litro_a_ml": ("litro", "ml", 1000.0),
    "kg_a_g": ("kg", "g", 1000.0),
    "caja_12_a_unidad": ("caja", "unidad", 12.0),
    "paquete_100_a_unidad": ("paquete", "unidad", 100.0),
}


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unidades_fraccionadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                material TEXT NOT NULL,
                tipo_material TEXT NOT NULL DEFAULT 'Otro',
                inventario_id INTEGER,
                unidad_compra TEXT NOT NULL,
                unidad_consumo TEXT NOT NULL,
                factor_conversion REAL NOT NULL DEFAULT 1,
                costo_compra_usd REAL NOT NULL DEFAULT 0,
                costo_consumo_usd REAL NOT NULL DEFAULT 0,
                stock_compra REAL NOT NULL DEFAULT 0,
                stock_consumo REAL NOT NULL DEFAULT 0,
                merma_estandar_pct REAL NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_unidades_fraccionadas_material ON unidades_fraccionadas(material)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_unidades_fraccionadas_inventario ON unidades_fraccionadas(inventario_id)")


def _load_units() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM unidades_fraccionadas ORDER BY id DESC LIMIT 500", conn)


def _create_unit(data: dict[str, Any]) -> int:
    _ensure_tables()
    factor = float(data.get("factor_conversion") or 1)
    costo_compra = float(data.get("costo_compra_usd") or 0)
    stock_compra = float(data.get("stock_compra") or 0)
    costo_consumo = costo_compra / factor if factor else 0.0
    stock_consumo = stock_compra * factor
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO unidades_fraccionadas(
                usuario, material, tipo_material, inventario_id, unidad_compra, unidad_consumo,
                factor_conversion, costo_compra_usd, costo_consumo_usd, stock_compra,
                stock_consumo, merma_estandar_pct, activo, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["material"], data.get("tipo_material", "Otro"), data.get("inventario_id"),
                data["unidad_compra"], data["unidad_consumo"], factor, costo_compra, costo_consumo,
                stock_compra, stock_consumo, float(data.get("merma_estandar_pct") or 0),
                int(data.get("activo", 1)), data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def _update_stock(unit_id: int, stock_compra: float, costo_compra: float) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        row = conn.execute("SELECT factor_conversion FROM unidades_fraccionadas WHERE id=?", (unit_id,)).fetchone()
        factor = float(row[0] if row else 1)
        costo_consumo = float(costo_compra or 0) / factor if factor else 0.0
        stock_consumo = float(stock_compra or 0) * factor
        conn.execute(
            """
            UPDATE unidades_fraccionadas
            SET stock_compra=?, costo_compra_usd=?, stock_consumo=?, costo_consumo_usd=?
            WHERE id=?
            """,
            (float(stock_compra), float(costo_compra), stock_consumo, costo_consumo, unit_id),
        )


def render_unidades_fraccionadas(usuario: str = "Sistema") -> None:
    st.subheader("📏 Unidades fraccionadas")
    st.caption("Convierte compras grandes en consumo real: rollo→cm, resma→hoja, litro→ml, kg→g, caja→unidad.")
    _ensure_tables()

    df = _load_units()
    activos = df[df["activo"].eq(1)] if not df.empty and "activo" in df.columns else df

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Conversiones", len(df))
    c2.metric("Activas", len(activos))
    c3.metric("Stock consumo", f"{float(pd.to_numeric(df.get('stock_consumo', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not df.empty else 0:,.2f}")
    c4.metric("Valor estimado", f"${float((pd.to_numeric(df.get('stock_consumo', pd.Series(dtype=float)), errors='coerce').fillna(0) * pd.to_numeric(df.get('costo_consumo_usd', pd.Series(dtype=float)), errors='coerce').fillna(0)).sum()) if not df.empty else 0:,.2f}")

    tab_nueva, tab_listado, tab_simulador, tab_actualizar = st.tabs([
        "Nueva conversión",
        "Listado",
        "Simulador consumo",
        "Actualizar stock/costo",
    ])

    with tab_nueva:
        preset = st.selectbox("Plantilla rápida", ["Personalizada"] + list(PRESETS.keys()))
        preset_compra, preset_consumo, preset_factor = ("rollo", "cm", 1.0)
        if preset != "Personalizada":
            preset_compra, preset_consumo, preset_factor = PRESETS[preset]

        with st.form("form_unidad_fraccionada"):
            a, b, c = st.columns(3)
            material = a.text_input("Material")
            tipo = b.selectbox("Tipo material", TIPOS_MATERIAL)
            inventario_id = c.number_input("Inventario ID opcional", min_value=0, value=0, step=1)
            d, e, f = st.columns(3)
            unidad_compra = d.selectbox("Unidad compra", UNIDADES_COMPRA, index=UNIDADES_COMPRA.index(preset_compra) if preset_compra in UNIDADES_COMPRA else 0)
            unidad_consumo = e.selectbox("Unidad consumo", UNIDADES_CONSUMO, index=UNIDADES_CONSUMO.index(preset_consumo) if preset_consumo in UNIDADES_CONSUMO else 0)
            factor = f.number_input("Factor conversión", min_value=0.0001, value=float(preset_factor), step=1.0)
            g, h, i = st.columns(3)
            costo_compra = g.number_input("Costo por unidad compra USD", min_value=0.0, value=0.0, step=0.01)
            stock_compra = h.number_input("Stock en unidad compra", min_value=0.0, value=0.0, step=1.0)
            merma = i.number_input("Merma estándar %", min_value=0.0, value=0.0, step=0.5)
            observaciones = st.text_area("Observaciones")
            st.metric("Costo por unidad consumo", f"${(costo_compra / factor) if factor else 0:,.6f}")
            st.metric("Stock equivalente consumo", f"{stock_compra * factor:,.2f} {unidad_consumo}")
            guardar = st.form_submit_button("Guardar conversión")
        if guardar:
            if not material.strip():
                st.error("El material es obligatorio.")
            else:
                unit_id = _create_unit({
                    "usuario": usuario,
                    "material": material.strip(),
                    "tipo_material": tipo,
                    "inventario_id": int(inventario_id) or None,
                    "unidad_compra": unidad_compra,
                    "unidad_consumo": unidad_consumo,
                    "factor_conversion": factor,
                    "costo_compra_usd": costo_compra,
                    "stock_compra": stock_compra,
                    "merma_estandar_pct": merma,
                    "observaciones": observaciones.strip(),
                })
                st.success(f"Conversión #{unit_id} creada.")
                st.rerun()

    with tab_listado:
        if df.empty:
            st.info("No hay conversiones de unidades registradas.")
        else:
            filtro = st.text_input("Buscar material")
            vista = df.copy()
            if filtro.strip():
                mask = vista.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False)).any(axis=1)
                vista = vista[mask]
            st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_simulador:
        if df.empty:
            st.info("Crea conversiones para simular consumo.")
        else:
            unit_id = st.selectbox(
                "Material",
                df["id"].astype(int).tolist(),
                format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'material'].iloc[0]} ({df.loc[df['id'].eq(x), 'unidad_compra'].iloc[0]}→{df.loc[df['id'].eq(x), 'unidad_consumo'].iloc[0]})",
            )
            row = df[df["id"].eq(unit_id)].iloc[0]
            consumo = st.number_input(f"Consumo en {row['unidad_consumo']}", min_value=0.0, value=1.0, step=1.0)
            merma_pct = float(row.get("merma_estandar_pct") or 0)
            consumo_con_merma = consumo * (1 + merma_pct / 100)
            factor = float(row.get("factor_conversion") or 1)
            costo_unit = float(row.get("costo_consumo_usd") or 0)
            compra_equiv = consumo_con_merma / factor if factor else 0
            costo = consumo_con_merma * costo_unit
            s1, s2, s3 = st.columns(3)
            s1.metric("Consumo + merma", f"{consumo_con_merma:,.2f} {row['unidad_consumo']}")
            s2.metric("Equiv. compra", f"{compra_equiv:,.4f} {row['unidad_compra']}")
            s3.metric("Costo estimado", f"${costo:,.4f}")

    with tab_actualizar:
        if df.empty:
            st.info("No hay conversiones para actualizar.")
        else:
            unit_id = st.selectbox("Conversión", df["id"].astype(int).tolist(), key="upd_unidad")
            row = df[df["id"].eq(unit_id)].iloc[0]
            with st.form("form_actualizar_unidad"):
                stock = st.number_input("Nuevo stock compra", min_value=0.0, value=float(row.get("stock_compra") or 0), step=1.0)
                costo = st.number_input("Nuevo costo compra USD", min_value=0.0, value=float(row.get("costo_compra_usd") or 0), step=0.01)
                actualizar = st.form_submit_button("Actualizar")
            if actualizar:
                _update_stock(int(unit_id), stock, costo)
                st.success("Stock/costo actualizado.")
                st.rerun()
