from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

ESTADOS = [
    "Por empaquetar",
    "Listo para despacho",
    "En ruta",
    "Entregado",
    "Devuelto",
    "Incidencia",
]

TIPOS_ENTREGA = ["Retiro en tienda", "Delivery propio", "Agencia de envios"]
AGENCIAS = ["N/A", "Zoom", "Tealca", "MRW", "Domesa", "Otro"]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
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
                tracking_url TEXT,
                motorizado TEXT,
                costo_envio_usd REAL NOT NULL DEFAULT 0,
                cobrado_cliente_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Por empaquetar',
                fecha_listo TEXT,
                fecha_despacho TEXT,
                fecha_entregado TEXT,
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS despachos_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                despacho_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                FOREIGN KEY (despacho_id) REFERENCES despachos_entregas(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_despachos_estado ON despachos_entregas(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_despachos_fecha ON despachos_entregas(fecha_creacion)")


def _load_despachos() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            "SELECT * FROM despachos_entregas ORDER BY id DESC LIMIT 500",
            conn,
        )


def _load_eventos(despacho_id: int | None = None) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if despacho_id:
            return pd.read_sql_query(
                "SELECT * FROM despachos_eventos WHERE despacho_id=? ORDER BY id DESC",
                conn,
                params=(despacho_id,),
            )
        return pd.read_sql_query("SELECT * FROM despachos_eventos ORDER BY id DESC LIMIT 500", conn)


def _crear_despacho(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO despachos_entregas(
                usuario_creacion, cliente, telefono, venta_id, orden_produccion_id, referencia,
                tipo_entrega, direccion_entrega, persona_recibe, telefono_recibe,
                agencia_envio, numero_guia, tracking_url, motorizado,
                costo_envio_usd, cobrado_cliente_usd, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["cliente"], data.get("telefono"), data.get("venta_id"), data.get("orden_produccion_id"),
                data.get("referencia"), data["tipo_entrega"], data.get("direccion_entrega"), data.get("persona_recibe"),
                data.get("telefono_recibe"), data.get("agencia_envio"), data.get("numero_guia"), data.get("tracking_url"),
                data.get("motorizado"), float(data.get("costo_envio_usd") or 0), float(data.get("cobrado_cliente_usd") or 0),
                data.get("estado", "Por empaquetar"), data.get("observaciones"),
            ),
        )
        despacho_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO despachos_eventos(despacho_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)",
            (despacho_id, data["usuario"], data.get("estado", "Por empaquetar"), "Despacho creado"),
        )
        return despacho_id


def _actualizar_estado(despacho_id: int, estado: str, usuario: str, comentario: str) -> None:
    _ensure_tables()
    fecha_col = None
    if estado == "Listo para despacho":
        fecha_col = "fecha_listo"
    elif estado == "En ruta":
        fecha_col = "fecha_despacho"
    elif estado == "Entregado":
        fecha_col = "fecha_entregado"
    with db_transaction() as conn:
        if fecha_col:
            conn.execute(
                f"UPDATE despachos_entregas SET estado=?, {fecha_col}=COALESCE({fecha_col}, CURRENT_TIMESTAMP) WHERE id=?",
                (estado, despacho_id),
            )
        else:
            conn.execute("UPDATE despachos_entregas SET estado=? WHERE id=?", (estado, despacho_id))
        conn.execute(
            "INSERT INTO despachos_eventos(despacho_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)",
            (despacho_id, usuario, estado, comentario),
        )


def render_despacho_entregas(usuario: str = "Sistema") -> None:
    st.subheader("🚚 Despacho / Entregas")
    st.caption("Entrega posterior a calidad: retiro en tienda, delivery propio, agencia, tracking, costos y estados.")
    _ensure_tables()

    df = _load_despachos()
    abiertos = df[~df["estado"].isin(["Entregado", "Devuelto"]) ] if not df.empty else pd.DataFrame()
    entregados = df[df["estado"].eq("Entregado")] if not df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Despachos", len(df))
    c2.metric("Abiertos", len(abiertos))
    c3.metric("Entregados", len(entregados))
    c4.metric("Costo envios", f"${float(pd.to_numeric(df.get('costo_envio_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not df.empty else 0:,.2f}")

    tab_nuevo, tab_tablero, tab_estados, tab_eventos = st.tabs([
        "Nuevo despacho",
        "Tablero",
        "Actualizar estado",
        "Eventos",
    ])

    with tab_nuevo:
        with st.form("form_nuevo_despacho"):
            a, b, c = st.columns(3)
            cliente = a.text_input("Cliente")
            telefono = b.text_input("Telefono cliente")
            referencia = c.text_input("Referencia / pedido")
            d, e = st.columns(2)
            venta_id = d.number_input("Venta ID", min_value=0, value=0, step=1)
            orden_id = e.number_input("Orden produccion ID", min_value=0, value=0, step=1)
            tipo = st.selectbox("Tipo de entrega", TIPOS_ENTREGA)
            direccion = st.text_area("Direccion de entrega")
            r1, r2 = st.columns(2)
            persona_recibe = r1.text_input("Persona que recibe")
            telefono_recibe = r2.text_input("Telefono de quien recibe")
            g1, g2, g3 = st.columns(3)
            agencia = g1.selectbox("Agencia", AGENCIAS)
            guia = g2.text_input("Numero de guia / tracking")
            motorizado = g3.text_input("Motorizado / delivery")
            tracking_url = st.text_input("URL tracking")
            p1, p2, p3 = st.columns(3)
            costo = p1.number_input("Costo envio USD", min_value=0.0, value=0.0, step=0.25)
            cobrado = p2.number_input("Cobrado al cliente USD", min_value=0.0, value=0.0, step=0.25)
            estado = p3.selectbox("Estado inicial", ESTADOS, index=0)
            obs = st.text_area("Observaciones")
            guardar = st.form_submit_button("Crear despacho")
        if guardar:
            if not cliente.strip():
                st.error("El cliente es obligatorio.")
            else:
                despacho_id = _crear_despacho({
                    "usuario": usuario,
                    "cliente": cliente.strip(),
                    "telefono": telefono.strip(),
                    "venta_id": int(venta_id) or None,
                    "orden_produccion_id": int(orden_id) or None,
                    "referencia": referencia.strip(),
                    "tipo_entrega": tipo,
                    "direccion_entrega": direccion.strip(),
                    "persona_recibe": persona_recibe.strip(),
                    "telefono_recibe": telefono_recibe.strip(),
                    "agencia_envio": agencia,
                    "numero_guia": guia.strip(),
                    "tracking_url": tracking_url.strip(),
                    "motorizado": motorizado.strip(),
                    "costo_envio_usd": costo,
                    "cobrado_cliente_usd": cobrado,
                    "estado": estado,
                    "observaciones": obs.strip(),
                })
                st.success(f"Despacho #{despacho_id} creado.")
                st.rerun()

    with tab_tablero:
        if df.empty:
            st.info("No hay despachos registrados.")
        else:
            estado_filter = st.selectbox("Filtrar estado", ["Todos"] + ESTADOS)
            vista = df.copy()
            if estado_filter != "Todos":
                vista = vista[vista["estado"].eq(estado_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            resumen = df.groupby("estado", as_index=False).agg(cantidad=("id", "count"), costo=("costo_envio_usd", "sum"))
            st.bar_chart(resumen.set_index("estado")["cantidad"])

    with tab_estados:
        if df.empty:
            st.info("No hay despachos para actualizar.")
        else:
            ids = df["id"].astype(int).tolist()
            despacho_id = st.selectbox("Despacho", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'cliente'].iloc[0]} · {df.loc[df['id'].eq(x), 'estado'].iloc[0]}")
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS)
            comentario = st.text_area("Comentario de actualización")
            if st.button("Actualizar estado", type="primary"):
                _actualizar_estado(int(despacho_id), nuevo_estado, usuario, comentario.strip())
                st.success("Estado actualizado.")
                st.rerun()

    with tab_eventos:
        eventos = _load_eventos()
        if eventos.empty:
            st.info("Sin eventos de despacho.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)
