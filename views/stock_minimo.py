from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission
from services.audit_service import log_audit_event

ESTADOS_REPOSICION = ["OK", "Reponer pronto", "Crítico", "Agotado", "Sobrestock"]


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_minimo_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                material TEXT NOT NULL,
                inventario_id INTEGER,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                stock_actual REAL NOT NULL DEFAULT 0,
                stock_minimo REAL NOT NULL DEFAULT 0,
                stock_critico REAL NOT NULL DEFAULT 0,
                stock_maximo REAL NOT NULL DEFAULT 0,
                proveedor_sugerido TEXT,
                ultimo_costo_usd REAL NOT NULL DEFAULT 0,
                estado_reposicion TEXT NOT NULL DEFAULT 'OK',
                activo INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_minimo_material ON stock_minimo_config(material)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_minimo_estado ON stock_minimo_config(estado_reposicion)")


def _estado_stock(actual: float, minimo: float, critico: float, maximo: float) -> str:
    actual = float(actual or 0)
    minimo = float(minimo or 0)
    critico = float(critico or 0)
    maximo = float(maximo or 0)
    if actual <= 0:
        return "Agotado"
    if critico > 0 and actual <= critico:
        return "Crítico"
    if minimo > 0 and actual <= minimo:
        return "Reponer pronto"
    if maximo > 0 and actual > maximo:
        return "Sobrestock"
    return "OK"


def _load_config() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM stock_minimo_config ORDER BY id DESC LIMIT 1000", conn)


def _create_config(data: dict[str, Any]) -> int:
    estado = _estado_stock(data.get("stock_actual"), data.get("stock_minimo"), data.get("stock_critico"), data.get("stock_maximo"))
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO stock_minimo_config(
                usuario, material, inventario_id, unidad, stock_actual, stock_minimo,
                stock_critico, stock_maximo, proveedor_sugerido, ultimo_costo_usd,
                estado_reposicion, activo, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["material"], data.get("inventario_id"), data.get("unidad", "unidad"),
                float(data.get("stock_actual") or 0), float(data.get("stock_minimo") or 0),
                float(data.get("stock_critico") or 0), float(data.get("stock_maximo") or 0),
                data.get("proveedor_sugerido"), float(data.get("ultimo_costo_usd") or 0), estado,
                int(data.get("activo", 1)), data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def _update_stock(row_id: int, actual: float, costo: float, proveedor: str, obs: str) -> None:
    with db_transaction() as conn:
        row = conn.execute("SELECT stock_minimo, stock_critico, stock_maximo FROM stock_minimo_config WHERE id=?", (int(row_id),)).fetchone()
        minimo = float(row[0] or 0) if row else 0
        critico = float(row[1] or 0) if row else 0
        maximo = float(row[2] or 0) if row else 0
        estado = _estado_stock(actual, minimo, critico, maximo)
        conn.execute(
            """
            UPDATE stock_minimo_config
            SET stock_actual=?, ultimo_costo_usd=?, proveedor_sugerido=?, observaciones=?, estado_reposicion=?
            WHERE id=?
            """,
            (float(actual), float(costo), proveedor, obs, estado, int(row_id)),
        )


def _inventory_candidates() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "inventario"):
                return pd.DataFrame()
            cols = _columns(conn, "inventario")
            name_col = next((c for c in ["nombre", "producto", "item", "descripcion", "material"] if c in cols), None)
            stock_col = next((c for c in ["stock", "cantidad", "existencia", "stock_actual"] if c in cols), None)
            cost_col = next((c for c in ["costo_usd", "precio_compra_usd", "costo", "ultimo_costo_usd"] if c in cols), None)
            selected = ["id"] if "id" in cols else []
            if name_col:
                selected.append(f"{name_col} AS material")
            if stock_col:
                selected.append(f"{stock_col} AS stock_actual")
            if cost_col:
                selected.append(f"{cost_col} AS ultimo_costo_usd")
            if not selected or not name_col:
                return pd.DataFrame()
            sql = f"SELECT {', '.join(selected)} FROM inventario ORDER BY id DESC LIMIT 500"
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def render_stock_minimo(usuario: str = "Sistema") -> None:
    if not require_any_permission(["inventario.view", "inventario.edit", "inventario.adjust"], "🚫 No tienes acceso a stock mínimo."):
        return
    puede_editar = has_permission("inventario.edit") or has_permission("inventario.adjust") or has_permission("inventario.create")

    st.subheader("📉 Stock mínimo / Reposición")
    st.caption("Alertas para agotados, críticos, reposición próxima y sobrestock por material o producto.")
    _ensure_tables()

    df = _load_config()
    problemas = df[~df["estado_reposicion"].eq("OK")] if not df.empty else pd.DataFrame()
    criticos = df[df["estado_reposicion"].isin(["Agotado", "Crítico"])] if not df.empty else pd.DataFrame()
    valor_reponer = float((pd.to_numeric(problemas.get("stock_minimo", pd.Series(dtype=float)), errors="coerce").fillna(0) - pd.to_numeric(problemas.get("stock_actual", pd.Series(dtype=float)), errors="coerce").fillna(0)).clip(lower=0).mul(pd.to_numeric(problemas.get("ultimo_costo_usd", pd.Series(dtype=float)), errors="coerce").fillna(0)).sum()) if not problemas.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Materiales", len(df))
    c2.metric("Con alerta", len(problemas))
    c3.metric("Críticos/agotados", len(criticos))
    c4.metric("Compra sugerida", f"${valor_reponer:,.2f}")

    tab_alertas, tab_config, tab_actualizar, tab_importar = st.tabs(["Alertas", "Configurar", "Actualizar stock", "Desde inventario"])

    with tab_alertas:
        if df.empty:
            st.info("No hay reglas de stock mínimo configuradas.")
        else:
            estado_filter = st.selectbox("Estado", ["Todos"] + ESTADOS_REPOSICION)
            vista = df.copy()
            if estado_filter != "Todos":
                vista = vista[vista["estado_reposicion"].eq(estado_filter)]
            vista["cantidad_sugerida_compra"] = (pd.to_numeric(vista["stock_minimo"], errors="coerce").fillna(0) - pd.to_numeric(vista["stock_actual"], errors="coerce").fillna(0)).clip(lower=0)
            vista["valor_sugerido_usd"] = vista["cantidad_sugerida_compra"] * pd.to_numeric(vista["ultimo_costo_usd"], errors="coerce").fillna(0)
            st.dataframe(vista, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar alertas de stock CSV", data=vista.to_csv(index=False).encode("utf-8-sig"), file_name="alertas_stock_minimo.csv", mime="text/csv", use_container_width=True)

    with tab_config:
        with st.form("form_stock_minimo"):
            a, b, c = st.columns(3)
            material = a.text_input("Material / Producto", disabled=not puede_editar)
            unidad = b.text_input("Unidad", value="unidad", disabled=not puede_editar)
            inventario_id = c.number_input("Inventario ID opcional", min_value=0, value=0, step=1, disabled=not puede_editar)
            d, e, f, g = st.columns(4)
            actual = d.number_input("Stock actual", min_value=0.0, value=0.0, step=1.0, disabled=not puede_editar)
            minimo = e.number_input("Stock mínimo", min_value=0.0, value=0.0, step=1.0, disabled=not puede_editar)
            critico = f.number_input("Stock crítico", min_value=0.0, value=0.0, step=1.0, disabled=not puede_editar)
            maximo = g.number_input("Stock máximo", min_value=0.0, value=0.0, step=1.0, disabled=not puede_editar)
            h, i = st.columns(2)
            proveedor = h.text_input("Proveedor sugerido", disabled=not puede_editar)
            costo = i.number_input("Último costo USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
            obs = st.text_area("Observaciones", disabled=not puede_editar)
            guardar = st.form_submit_button("Crear regla", disabled=not puede_editar)
        if guardar:
            if not material.strip():
                st.error("El material es obligatorio.")
            else:
                payload = {"usuario": usuario, "material": material.strip(), "inventario_id": int(inventario_id) or None, "unidad": unidad.strip() or "unidad", "stock_actual": actual, "stock_minimo": minimo, "stock_critico": critico, "stock_maximo": maximo, "proveedor_sugerido": proveedor.strip(), "ultimo_costo_usd": costo, "observaciones": obs.strip()}
                rule_id = _create_config(payload)
                log_audit_event(usuario=usuario, modulo="Inventario", accion="crear_stock_minimo", entidad="stock_minimo_config", entidad_id=rule_id, detalle=f"Regla stock mínimo creada: {material.strip()}", metadata=payload)
                st.success(f"Regla #{rule_id} creada.")
                st.rerun()

    with tab_actualizar:
        if df.empty:
            st.info("No hay reglas para actualizar.")
        else:
            ids = df["id"].astype(int).tolist()
            row_id = st.selectbox("Regla", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'material'].iloc[0]} · {df.loc[df['id'].eq(x), 'estado_reposicion'].iloc[0]}", disabled=not puede_editar)
            row = df[df["id"].eq(row_id)].iloc[0]
            with st.form("form_update_stock_minimo"):
                a, b = st.columns(2)
                actual = a.number_input("Nuevo stock actual", min_value=0.0, value=float(row.get("stock_actual") or 0), step=1.0, disabled=not puede_editar)
                costo = b.number_input("Nuevo último costo USD", min_value=0.0, value=float(row.get("ultimo_costo_usd") or 0), step=0.01, disabled=not puede_editar)
                proveedor = st.text_input("Proveedor sugerido", value=str(row.get("proveedor_sugerido") or ""), disabled=not puede_editar)
                obs = st.text_area("Observaciones", value=str(row.get("observaciones") or ""), disabled=not puede_editar)
                actualizar = st.form_submit_button("Actualizar stock", disabled=not puede_editar)
            if actualizar:
                old_estado = str(row.get("estado_reposicion") or "")
                _update_stock(int(row_id), actual, costo, proveedor.strip(), obs.strip())
                new_estado = _estado_stock(actual, float(row.get("stock_minimo") or 0), float(row.get("stock_critico") or 0), float(row.get("stock_maximo") or 0))
                log_audit_event(usuario=usuario, modulo="Inventario", accion="actualizar_stock_minimo", entidad="stock_minimo_config", entidad_id=row_id, detalle=f"Stock actualizado: {row.get('material')} {old_estado}->{new_estado}", metadata={"stock_actual": actual, "ultimo_costo_usd": costo, "estado_anterior": old_estado, "estado_nuevo": new_estado})
                st.success("Stock actualizado.")
                st.rerun()

    with tab_importar:
        candidates = _inventory_candidates()
        if candidates.empty:
            st.info("No pude detectar productos importables desde la tabla inventario. Puedes configurar reglas manualmente.")
        else:
            st.caption("Vista de apoyo para copiar datos del inventario operativo hacia reglas de stock mínimo.")
            st.dataframe(candidates, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar candidatos CSV", data=candidates.to_csv(index=False).encode("utf-8-sig"), file_name="candidatos_stock_minimo.csv", mime="text/csv", use_container_width=True)
