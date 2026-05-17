from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _read_table(table: str, order: str = "id DESC", limit: int = 500) -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return pd.DataFrame()
        try:
            return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY {order} LIMIT {int(limit)}", conn)
        except Exception:
            return pd.read_sql_query(f"SELECT * FROM {table} LIMIT {int(limit)}", conn)


def _insert_provider(data: dict[str, Any]) -> None:
    with db_transaction() as conn:
        cols = _columns(conn, "proveedores")
        if not cols:
            st.error("No existe la tabla proveedores.")
            return
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        placeholders = ",".join(["?"] * len(keys))
        conn.execute(
            f"INSERT INTO proveedores ({','.join(keys)}) VALUES ({placeholders})",
            [payload[k] for k in keys],
        )


def _safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def render_proveedores(usuario: str = "Sistema") -> None:
    st.subheader("👥 Proveedores")
    st.caption("Ficha maestra de proveedores, condiciones comerciales, crédito, bancos y documentos relacionados.")

    proveedores = _read_table("proveedores", "id DESC", 1000)
    compras = _read_table("historial_compras", "id DESC", 1000)
    docs = _read_table("proveedor_documentos", "id DESC", 500)
    evaluaciones = _read_table("evaluaciones_proveedor", "id DESC", 500)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proveedores", len(proveedores))
    c2.metric("Activos", int(proveedores.get("activo", pd.Series(dtype=int)).fillna(1).astype(int).sum()) if not proveedores.empty and "activo" in proveedores.columns else len(proveedores))
    c3.metric("Compras históricas", f"${_safe_sum(compras, 'costo_total_usd'):,.2f}")
    c4.metric("Documentos", len(docs))

    tab_lista, tab_nuevo, tab_historial, tab_docs, tab_eval = st.tabs([
        "Listado",
        "Nuevo proveedor",
        "Historial de compras",
        "Documentos",
        "Evaluaciones",
    ])

    with tab_lista:
        if proveedores.empty:
            st.info("No hay proveedores registrados.")
        else:
            filtro = st.text_input("Buscar proveedor", key="buscar_proveedor")
            vista = proveedores.copy()
            if filtro.strip():
                mask = vista.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False)).any(axis=1)
                vista = vista[mask]
            st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_nuevo:
        with st.form("form_nuevo_proveedor"):
            col_a, col_b = st.columns(2)
            nombre = col_a.text_input("Nombre / Razón social")
            rif = col_b.text_input("RIF / Identificación fiscal")
            telefono = col_a.text_input("Teléfono")
            email = col_b.text_input("Email")
            contacto = col_a.text_input("Contacto / vendedor")
            tipo = col_b.selectbox("Tipo proveedor", ["Insumos", "Servicios", "Maquinaria", "Papelería", "Transporte", "Otro"])
            direccion = st.text_area("Dirección")
            col_c, col_d, col_e = st.columns(3)
            dias_credito = col_c.number_input("Días de crédito", min_value=0, value=0, step=1)
            moneda = col_d.selectbox("Moneda default", ["USD", "VES", "COP", "EUR"])
            lead_time = col_e.number_input("Lead time días", min_value=0, value=0, step=1)
            banco = st.text_input("Banco / Datos bancarios")
            observaciones = st.text_area("Observaciones")
            guardar = st.form_submit_button("Guardar proveedor")
        if guardar:
            if not nombre.strip():
                st.error("El nombre del proveedor es obligatorio.")
            else:
                _insert_provider({
                    "nombre": nombre.strip(),
                    "rif": rif.strip(),
                    "telefono": telefono.strip(),
                    "email": email.strip(),
                    "contacto": contacto.strip(),
                    "tipo_proveedor": tipo,
                    "direccion": direccion.strip(),
                    "dias_credito_default": int(dias_credito),
                    "moneda_default": moneda,
                    "lead_time_dias": int(lead_time),
                    "banco": banco.strip(),
                    "datos_bancarios": banco.strip(),
                    "observaciones": observaciones.strip(),
                    "activo": 1,
                })
                st.success("Proveedor guardado.")
                st.rerun()

    with tab_historial:
        if compras.empty:
            st.info("No hay historial de compras.")
        else:
            st.dataframe(compras, use_container_width=True, hide_index=True)

    with tab_docs:
        if docs.empty:
            st.info("No hay documentos de proveedor registrados.")
        else:
            st.dataframe(docs, use_container_width=True, hide_index=True)

    with tab_eval:
        if evaluaciones.empty:
            st.info("No hay evaluaciones de proveedor registradas.")
        else:
            st.dataframe(evaluaciones, use_container_width=True, hide_index=True)


def render_compras_suministro(usuario: str = "Sistema") -> None:
    st.subheader("🛒 Compras / Órdenes de suministro")
    st.caption("Órdenes de compra, recepciones, delivery de compra, costos promedio, historial y obligaciones con proveedores.")

    ordenes = _read_table("ordenes_compra", "id DESC", 500)
    detalle = _read_table("ordenes_compra_detalle", "id DESC", 1000)
    recepciones = _read_table("recepciones_orden_compra", "id DESC", 500)
    historial = _read_table("historial_compras", "id DESC", 1000)
    cxp = _read_table("cuentas_por_pagar_proveedores", "id DESC", 500)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes", len(ordenes))
    c2.metric("Recepciones", len(recepciones))
    c3.metric("Compras históricas", f"${_safe_sum(historial, 'costo_total_usd'):,.2f}")
    c4.metric("CxP proveedores", f"${_safe_sum(cxp, 'saldo_pendiente_usd'):,.2f}" if "saldo_pendiente_usd" in cxp.columns else f"${_safe_sum(cxp, 'monto_usd'):,.2f}")

    tab_oc, tab_det, tab_rec, tab_hist, tab_cxp, tab_alertas = st.tabs([
        "Órdenes",
        "Detalle OC",
        "Recepciones",
        "Historial compras",
        "CxP proveedores",
        "Alertas",
    ])

    with tab_oc:
        if ordenes.empty:
            st.info("No hay órdenes de compra registradas.")
        else:
            st.dataframe(ordenes, use_container_width=True, hide_index=True)
    with tab_det:
        if detalle.empty:
            st.info("No hay detalle de órdenes.")
        else:
            st.dataframe(detalle, use_container_width=True, hide_index=True)
    with tab_rec:
        if recepciones.empty:
            st.info("No hay recepciones registradas.")
        else:
            st.dataframe(recepciones, use_container_width=True, hide_index=True)
    with tab_hist:
        if historial.empty:
            st.info("No hay historial de compras.")
        else:
            st.dataframe(historial, use_container_width=True, hide_index=True)
    with tab_cxp:
        if cxp.empty:
            st.info("No hay cuentas por pagar de proveedores.")
        else:
            st.dataframe(cxp, use_container_width=True, hide_index=True)
    with tab_alertas:
        alertas = []
        if not ordenes.empty and "estado" in ordenes.columns:
            abiertas = ordenes[ordenes["estado"].fillna("").astype(str).str.lower().isin(["borrador", "aprobada", "enviada", "parcial"])]
            if not abiertas.empty:
                alertas.append({"nivel": "Media", "alerta": f"Hay {len(abiertas)} orden(es) abiertas o parciales.", "accion": "Revisar recepción o cierre."})
        if not cxp.empty:
            estado_col = "estado" if "estado" in cxp.columns else None
            if estado_col:
                vencidas = cxp[cxp[estado_col].fillna("").astype(str).str.lower().eq("vencida")]
                if not vencidas.empty:
                    alertas.append({"nivel": "Alta", "alerta": f"Hay {len(vencidas)} CxP de proveedores vencidas.", "accion": "Priorizar pago o negociación."})
        if alertas:
            st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
        else:
            st.success("Sin alertas críticas de compras/proveedores con la información disponible.")
