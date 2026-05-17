from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

ESTADOS = ["Recibido", "En cola", "Imprimiendo", "Impreso", "Entregado", "Cancelado", "Error / Reimprimir"]
ORIGENES = ["WhatsApp", "Correo", "USB", "Drive", "Manual", "Otro"]
PAPELES = ["Bond", "Glace", "Opalina", "Fotografico", "Adhesivo", "Cartulina", "Otro"]
TAMANOS = ["Carta", "Oficio", "A4", "A3", "Personalizado"]
CARAS = ["Una cara", "Doble cara"]
COLOR = ["B/N", "Color"]


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cola_impresion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cliente TEXT NOT NULL DEFAULT 'Cliente General',
                telefono TEXT,
                venta_pos_id INTEGER,
                archivo_nombre TEXT,
                archivo_url_o_ruta TEXT,
                origen_archivo TEXT NOT NULL DEFAULT 'Manual',
                tipo_papel TEXT NOT NULL DEFAULT 'Bond',
                tamano TEXT NOT NULL DEFAULT 'Carta',
                caras TEXT NOT NULL DEFAULT 'Una cara',
                color TEXT NOT NULL DEFAULT 'B/N',
                cantidad_juegos INTEGER NOT NULL DEFAULT 1,
                paginas_por_juego INTEGER NOT NULL DEFAULT 1,
                total_paginas INTEGER NOT NULL DEFAULT 1,
                impresora TEXT,
                operador TEXT,
                estado TEXT NOT NULL DEFAULT 'Recibido',
                prioridad TEXT NOT NULL DEFAULT 'Normal',
                instrucciones TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cola_impresion_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cola_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                FOREIGN KEY (cola_id) REFERENCES cola_impresion(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cola_impresion_estado ON cola_impresion(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cola_impresion_fecha ON cola_impresion(fecha)")


def _load_queue() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM cola_impresion ORDER BY id DESC LIMIT 500", conn)


def _load_events() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM cola_impresion_eventos ORDER BY id DESC LIMIT 500", conn)


def _create_job(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cola_impresion(
                usuario, cliente, telefono, venta_pos_id, archivo_nombre, archivo_url_o_ruta,
                origen_archivo, tipo_papel, tamano, caras, color, cantidad_juegos,
                paginas_por_juego, total_paginas, impresora, operador, estado, prioridad, instrucciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["cliente"], data.get("telefono"), data.get("venta_pos_id"),
                data.get("archivo_nombre"), data.get("archivo_url_o_ruta"), data["origen_archivo"],
                data["tipo_papel"], data["tamano"], data["caras"], data["color"], int(data["cantidad_juegos"]),
                int(data["paginas_por_juego"]), int(data["total_paginas"]), data.get("impresora"),
                data.get("operador"), data["estado"], data["prioridad"], data.get("instrucciones"),
            ),
        )
        job_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO cola_impresion_eventos(cola_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)",
            (job_id, data["usuario"], data["estado"], "Trabajo recibido en cola"),
        )
        return job_id


def _update_job(job_id: int, estado: str, usuario: str, comentario: str) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        if estado == "Imprimiendo":
            conn.execute("UPDATE cola_impresion SET estado=?, fecha_inicio=COALESCE(fecha_inicio, CURRENT_TIMESTAMP) WHERE id=?", (estado, job_id))
        elif estado in {"Impreso", "Entregado", "Cancelado"}:
            conn.execute("UPDATE cola_impresion SET estado=?, fecha_fin=COALESCE(fecha_fin, CURRENT_TIMESTAMP) WHERE id=?", (estado, job_id))
        else:
            conn.execute("UPDATE cola_impresion SET estado=? WHERE id=?", (estado, job_id))
        conn.execute(
            "INSERT INTO cola_impresion_eventos(cola_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)",
            (job_id, usuario, estado, comentario),
        )


def render_cola_impresion(usuario: str = "Sistema") -> None:
    st.subheader("🗂️ Recepción de archivos / Cola de impresión")
    st.caption("Buzón operativo para archivos de mostrador: WhatsApp, correo, USB o manual, con especificaciones técnicas de impresión.")
    _ensure_tables()

    df = _load_queue()
    abiertos = df[~df["estado"].isin(["Entregado", "Cancelado"])] if not df.empty else pd.DataFrame()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trabajos", len(df))
    c2.metric("Abiertos", len(abiertos))
    c3.metric("En cola", int(df["estado"].eq("En cola").sum()) if not df.empty else 0)
    c4.metric("Paginas pendientes", int(pd.to_numeric(abiertos.get("total_paginas", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if not abiertos.empty else 0)

    tab_nuevo, tab_cola, tab_estado, tab_eventos = st.tabs(["Nuevo archivo", "Cola", "Actualizar estado", "Eventos"])

    with tab_nuevo:
        with st.form("form_cola_impresion"):
            a, b, c = st.columns(3)
            cliente = a.text_input("Cliente", value="Cliente General")
            telefono = b.text_input("Telefono")
            venta_pos_id = c.number_input("Venta POS ID", min_value=0, value=0, step=1)
            archivo_nombre = st.text_input("Nombre del archivo")
            archivo_url = st.text_input("Ruta / URL / referencia del archivo")
            p1, p2, p3 = st.columns(3)
            origen = p1.selectbox("Origen", ORIGENES)
            papel = p2.selectbox("Papel", PAPELES)
            tamano = p3.selectbox("Tamano", TAMANOS)
            q1, q2, q3, q4 = st.columns(4)
            caras = q1.selectbox("Caras", CARAS)
            color = q2.selectbox("Color", COLOR)
            juegos = q3.number_input("Juegos", min_value=1, value=1, step=1)
            paginas = q4.number_input("Paginas por juego", min_value=1, value=1, step=1)
            total_paginas = int(juegos) * int(paginas)
            r1, r2, r3 = st.columns(3)
            impresora = r1.text_input("Impresora")
            operador = r2.text_input("Operador", value=usuario)
            prioridad = r3.selectbox("Prioridad", ["Normal", "Alta", "Urgente"])
            estado = st.selectbox("Estado inicial", ESTADOS, index=0)
            instrucciones = st.text_area("Instrucciones tecnicas")
            st.metric("Total paginas", total_paginas)
            guardar = st.form_submit_button("Agregar a cola")
        if guardar:
            job_id = _create_job({
                "usuario": usuario,
                "cliente": cliente.strip() or "Cliente General",
                "telefono": telefono.strip(),
                "venta_pos_id": int(venta_pos_id) or None,
                "archivo_nombre": archivo_nombre.strip(),
                "archivo_url_o_ruta": archivo_url.strip(),
                "origen_archivo": origen,
                "tipo_papel": papel,
                "tamano": tamano,
                "caras": caras,
                "color": color,
                "cantidad_juegos": int(juegos),
                "paginas_por_juego": int(paginas),
                "total_paginas": total_paginas,
                "impresora": impresora.strip(),
                "operador": operador.strip(),
                "estado": estado,
                "prioridad": prioridad,
                "instrucciones": instrucciones.strip(),
            })
            st.success(f"Archivo agregado a cola #{job_id}.")
            st.rerun()

    with tab_cola:
        if df.empty:
            st.info("No hay trabajos de impresion en cola.")
        else:
            estado_filter = st.selectbox("Filtrar estado", ["Todos"] + ESTADOS)
            vista = df.copy()
            if estado_filter != "Todos":
                vista = vista[vista["estado"].eq(estado_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            resumen = df.groupby("estado", as_index=False).agg(trabajos=("id", "count"), paginas=("total_paginas", "sum"))
            st.bar_chart(resumen.set_index("estado")["trabajos"])

    with tab_estado:
        if df.empty:
            st.info("No hay trabajos para actualizar.")
        else:
            ids = df["id"].astype(int).tolist()
            job_id = st.selectbox("Trabajo", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'cliente'].iloc[0]} · {df.loc[df['id'].eq(x), 'estado'].iloc[0]}")
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS)
            comentario = st.text_area("Comentario")
            if st.button("Actualizar trabajo", type="primary"):
                _update_job(int(job_id), nuevo_estado, usuario, comentario.strip())
                st.success("Trabajo actualizado.")
                st.rerun()

    with tab_eventos:
        eventos = _load_events()
        if eventos.empty:
            st.info("Sin eventos de cola.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)
