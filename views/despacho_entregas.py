from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission
from services.audit_service import log_audit_event

ESTADOS = ["Por empaquetar", "Listo para despacho", "En ruta", "Entregado", "Devuelto", "Incidencia"]
TIPOS_ENTREGA = ["Retiro en tienda", "Delivery propio", "Agencia de envios"]
AGENCIAS = ["N/A", "Zoom", "Tealca", "MRW", "Domesa", "Otro"]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS despachos_entregas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario_creacion TEXT NOT NULL,
                cliente TEXT NOT NULL,
                telefono TEXT,
                venta_id INTEGER,
                orden_produccion_id INTEGER,
                referencia TEXT,
                tipo_entrega TEXT NOT NULL,
                direccion_entrega TEXT,
                persona_recibe TEXT,
                telefono_recibe TEXT,
                agencia_envio TEXT,
                numero_guia TEXT,
                motorizado TEXT,
                costo_envio_usd REAL NOT NULL DEFAULT 0,
                cobrado_cliente_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Por empaquetar',
                fecha_listo TEXT,
                fecha_despacho TEXT,
                fecha_entregado TEXT,
                observaciones TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS despachos_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                despacho_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                FOREIGN KEY (despacho_id) REFERENCES despachos_entregas(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_despachos_estado ON despachos_entregas(estado)")


def _load_despachos() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM despachos_entregas ORDER BY id DESC LIMIT 500", conn)


def _load_eventos() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM despachos_eventos ORDER BY id DESC LIMIT 500", conn)


def _crear_despacho(data: dict[str, Any]) -> int:
    with db_transaction() as conn:
        cur = conn.execute("""
            INSERT INTO despachos_entregas(
                usuario_creacion, cliente, telefono, venta_id, orden_produccion_id, referencia,
                tipo_entrega, direccion_entrega, persona_recibe, telefono_recibe, agencia_envio,
                numero_guia, motorizado, costo_envio_usd, cobrado_cliente_usd, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["usuario"], data["cliente"], data.get("telefono"), data.get("venta_id"), data.get("orden_produccion_id"),
            data.get("referencia"), data["tipo_entrega"], data.get("direccion_entrega"), data.get("persona_recibe"),
            data.get("telefono_recibe"), data.get("agencia_envio"), data.get("numero_guia"), data.get("motorizado"),
            float(data.get("costo_envio_usd") or 0), float(data.get("cobrado_cliente_usd") or 0),
            data.get("estado", "Por empaquetar"), data.get("observaciones"),
        ))
        despacho_id = int(cur.lastrowid)
        conn.execute("INSERT INTO despachos_eventos(despacho_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)", (despacho_id, data["usuario"], data.get("estado", "Por empaquetar"), "Despacho creado"))
        return despacho_id


def _actualizar_estado(despacho_id: int, estado: str, usuario: str, comentario: str) -> None:
    fecha_col = {"Listo para despacho": "fecha_listo", "En ruta": "fecha_despacho", "Entregado": "fecha_entregado"}.get(estado)
    with db_transaction() as conn:
        if fecha_col:
            conn.execute(f"UPDATE despachos_entregas SET estado=?, {fecha_col}=COALESCE({fecha_col}, CURRENT_TIMESTAMP) WHERE id=?", (estado, despacho_id))
        else:
            conn.execute("UPDATE despachos_entregas SET estado=? WHERE id=?", (estado, despacho_id))
        conn.execute("INSERT INTO despachos_eventos(despacho_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)", (despacho_id, usuario, estado, comentario))


def render_despacho_entregas(usuario: str = "Sistema") -> None:
    if not require_any_permission(["despacho.view", "despacho.edit", "produccion.plan", "produccion.execute"], "🚫 No tienes acceso a despacho y entregas."):
        return
    puede_editar = has_permission("despacho.edit")

    st.subheader("🚚 Despacho / Entregas")
    st.caption("Retiro en tienda, delivery propio, agencia, costos y estados de entrega.")
    if not puede_editar:
        st.info("Modo consulta: puedes ver despachos y eventos, pero no crear ni actualizar estados.")
    _ensure_tables()

    df = _load_despachos()
    abiertos = df[~df["estado"].isin(["Entregado", "Devuelto"])] if not df.empty else pd.DataFrame()
    entregados = df[df["estado"].eq("Entregado")] if not df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Despachos", len(df))
    c2.metric("Abiertos", len(abiertos))
    c3.metric("Entregados", len(entregados))
    c4.metric("Costo envios", f"${float(pd.to_numeric(df.get('costo_envio_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not df.empty else 0:,.2f}")

    tab_nuevo, tab_tablero, tab_estados, tab_eventos = st.tabs(["Nuevo despacho", "Tablero", "Actualizar estado", "Eventos"])

    with tab_nuevo:
        with st.form("form_nuevo_despacho"):
            a, b, c = st.columns(3)
            cliente = a.text_input("Cliente", disabled=not puede_editar)
            telefono = b.text_input("Telefono cliente", disabled=not puede_editar)
            referencia = c.text_input("Referencia / pedido", disabled=not puede_editar)
            d, e = st.columns(2)
            venta_id = d.number_input("Venta ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            orden_id = e.number_input("Orden produccion ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            tipo = st.selectbox("Tipo de entrega", TIPOS_ENTREGA, disabled=not puede_editar)
            direccion = st.text_area("Direccion de entrega", disabled=not puede_editar)
            r1, r2 = st.columns(2)
            persona_recibe = r1.text_input("Persona que recibe", disabled=not puede_editar)
            telefono_recibe = r2.text_input("Telefono de quien recibe", disabled=not puede_editar)
            g1, g2, g3 = st.columns(3)
            agencia = g1.selectbox("Agencia", AGENCIAS, disabled=not puede_editar)
            guia = g2.text_input("Numero de guia", disabled=not puede_editar)
            motorizado = g3.text_input("Motorizado / delivery", disabled=not puede_editar)
            p1, p2, p3 = st.columns(3)
            costo = p1.number_input("Costo envio USD", min_value=0.0, value=0.0, step=0.25, disabled=not puede_editar)
            cobrado = p2.number_input("Cobrado al cliente USD", min_value=0.0, value=0.0, step=0.25, disabled=not puede_editar)
            estado = p3.selectbox("Estado inicial", ESTADOS, index=0, disabled=not puede_editar)
            obs = st.text_area("Observaciones", disabled=not puede_editar)
            guardar = st.form_submit_button("Crear despacho", disabled=not puede_editar)
        if guardar:
            if not cliente.strip():
                st.error("El cliente es obligatorio.")
            else:
                despacho_id = _crear_despacho({"usuario": usuario, "cliente": cliente.strip(), "telefono": telefono.strip(), "venta_id": int(venta_id) or None, "orden_produccion_id": int(orden_id) or None, "referencia": referencia.strip(), "tipo_entrega": tipo, "direccion_entrega": direccion.strip(), "persona_recibe": persona_recibe.strip(), "telefono_recibe": telefono_recibe.strip(), "agencia_envio": agencia, "numero_guia": guia.strip(), "motorizado": motorizado.strip(), "costo_envio_usd": costo, "cobrado_cliente_usd": cobrado, "estado": estado, "observaciones": obs.strip()})
                log_audit_event(usuario=usuario, modulo="Despacho", accion="crear_despacho", entidad="despachos_entregas", entidad_id=despacho_id, detalle=f"Despacho creado para {cliente.strip()} - {tipo}", metadata={"cliente": cliente.strip(), "estado": estado, "tipo_entrega": tipo, "agencia": agencia, "numero_guia": guia.strip(), "costo_envio_usd": costo})
                st.success(f"Despacho #{despacho_id} creado.")
                st.rerun()

    with tab_tablero:
        if df.empty:
            st.info("No hay despachos registrados.")
        else:
            estado_filter = st.selectbox("Filtrar estado", ["Todos"] + ESTADOS)
            vista = df.copy() if estado_filter == "Todos" else df[df["estado"].eq(estado_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            resumen = df.groupby("estado", as_index=False).agg(cantidad=("id", "count"))
            st.bar_chart(resumen.set_index("estado")["cantidad"])

    with tab_estados:
        if df.empty:
            st.info("No hay despachos para actualizar.")
        else:
            ids = df["id"].astype(int).tolist()
            despacho_id = st.selectbox("Despacho", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'cliente'].iloc[0]} · {df.loc[df['id'].eq(x), 'estado'].iloc[0]}", disabled=not puede_editar)
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS, disabled=not puede_editar)
            comentario = st.text_area("Comentario de actualización", disabled=not puede_editar)
            if st.button("Actualizar estado", type="primary", disabled=not puede_editar):
                _actualizar_estado(int(despacho_id), nuevo_estado, usuario, comentario.strip())
                log_audit_event(usuario=usuario, modulo="Despacho", accion="actualizar_estado_despacho", entidad="despachos_entregas", entidad_id=despacho_id, detalle=f"Despacho actualizado a {nuevo_estado}", metadata={"estado": nuevo_estado, "comentario": comentario.strip()})
                st.success("Estado actualizado.")
                st.rerun()

    with tab_eventos:
        eventos = _load_eventos()
        if eventos.empty:
            st.info("Sin eventos de despacho.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)
