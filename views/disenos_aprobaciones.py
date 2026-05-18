from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

ESTADOS = [
    "En diseño", "Enviado a cliente", "Modificar", "Aprobado por cliente",
    "Listo para imprimir", "Listo para sublimar", "Listo para cortar", "Archivado", "Cancelado",
]
TIPOS_TRABAJO = ["Impresión", "Sublimación", "Corte", "Papelería creativa", "Diseño digital", "Otro"]
ORIGENES = ["Cotización", "Venta", "POS", "WhatsApp", "Mostrador", "Otro"]
ESTADOS_LIBERADOS = {"Aprobado por cliente", "Listo para imprimir", "Listo para sublimar", "Listo para cortar", "Archivado"}


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS disenos_aprobaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cliente TEXT NOT NULL,
                telefono TEXT,
                referencia TEXT,
                origen TEXT NOT NULL DEFAULT 'Mostrador',
                cotizacion_id INTEGER,
                venta_id INTEGER,
                orden_produccion_id INTEGER,
                tipo_trabajo TEXT NOT NULL DEFAULT 'Impresión',
                nombre_diseno TEXT NOT NULL,
                archivo_editable TEXT,
                archivo_final TEXT,
                version TEXT NOT NULL DEFAULT '1.0',
                responsable_diseno TEXT,
                estado TEXT NOT NULL DEFAULT 'En diseño',
                fecha_enviado_cliente TEXT,
                fecha_aprobacion_cliente TEXT,
                aprobado_por TEXT,
                bloqueo_produccion INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS disenos_aprobaciones_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diseno_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                archivo_referencia TEXT,
                FOREIGN KEY (diseno_id) REFERENCES disenos_aprobaciones(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_disenos_estado ON disenos_aprobaciones(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_disenos_cliente ON disenos_aprobaciones(cliente)")


def _blocked(estado: str) -> int:
    return 0 if estado in ESTADOS_LIBERADOS else 1


def _load(table: str) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1000", conn)


def _create_design(data: dict[str, Any]) -> int:
    estado = data.get("estado", "En diseño")
    with db_transaction() as conn:
        cur = conn.execute("""
            INSERT INTO disenos_aprobaciones(
                usuario, cliente, telefono, referencia, origen, cotizacion_id, venta_id,
                orden_produccion_id, tipo_trabajo, nombre_diseno, archivo_editable, archivo_final,
                version, responsable_diseno, estado, fecha_enviado_cliente, fecha_aprobacion_cliente,
                aprobado_por, bloqueo_produccion, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["usuario"], data["cliente"], data.get("telefono"), data.get("referencia"), data.get("origen"),
            data.get("cotizacion_id"), data.get("venta_id"), data.get("orden_produccion_id"), data.get("tipo_trabajo"),
            data["nombre_diseno"], data.get("archivo_editable"), data.get("archivo_final"), data.get("version", "1.0"),
            data.get("responsable_diseno"), estado, data.get("fecha_enviado_cliente"), data.get("fecha_aprobacion_cliente"),
            data.get("aprobado_por"), _blocked(estado), data.get("observaciones"),
        ))
        diseno_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO disenos_aprobaciones_eventos(diseno_id, usuario, estado, comentario, archivo_referencia) VALUES (?, ?, ?, ?, ?)",
            (diseno_id, data["usuario"], estado, "Diseño creado", data.get("archivo_final") or data.get("archivo_editable")),
        )
        return diseno_id


def _update_state(diseno_id: int, estado: str, usuario: str, comentario: str, archivo: str, aprobado_por: str) -> None:
    with db_transaction() as conn:
        bloquea = _blocked(estado)
        if estado == "Enviado a cliente":
            conn.execute(
                "UPDATE disenos_aprobaciones SET estado=?, bloqueo_produccion=?, fecha_enviado_cliente=COALESCE(fecha_enviado_cliente, CURRENT_TIMESTAMP) WHERE id=?",
                (estado, bloquea, diseno_id),
            )
        elif estado in ESTADOS_LIBERADOS:
            conn.execute(
                "UPDATE disenos_aprobaciones SET estado=?, bloqueo_produccion=?, fecha_aprobacion_cliente=COALESCE(fecha_aprobacion_cliente, CURRENT_TIMESTAMP), aprobado_por=COALESCE(NULLIF(?, ''), aprobado_por) WHERE id=?",
                (estado, bloquea, aprobado_por, diseno_id),
            )
        else:
            conn.execute("UPDATE disenos_aprobaciones SET estado=?, bloqueo_produccion=? WHERE id=?", (estado, bloquea, diseno_id))
        conn.execute(
            "INSERT INTO disenos_aprobaciones_eventos(diseno_id, usuario, estado, comentario, archivo_referencia) VALUES (?, ?, ?, ?, ?)",
            (diseno_id, usuario, estado, comentario, archivo),
        )


def render_disenos_aprobaciones(usuario: str = "Sistema") -> None:
    st.subheader("📁 Diseños y aprobaciones")
    st.caption("Control de archivos, versiones, aprobación del cliente y bloqueo antes de imprimir, sublimar o cortar.")
    _ensure_tables()
    df = _load("disenos_aprobaciones")
    eventos = _load("disenos_aprobaciones_eventos")
    bloqueados = df[df["bloqueo_produccion"].eq(1)] if not df.empty else pd.DataFrame()
    liberados = df[df["bloqueo_produccion"].eq(0)] if not df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Diseños", len(df))
    c2.metric("Bloqueados", len(bloqueados))
    c3.metric("Aprobados/listos", len(liberados))
    c4.metric("Modificar", int(df["estado"].eq("Modificar").sum()) if not df.empty else 0)

    tab_nuevo, tab_tablero, tab_estado, tab_eventos = st.tabs(["Nuevo diseño", "Tablero", "Actualizar estado", "Eventos"])

    with tab_nuevo:
        with st.form("form_diseno_aprobacion"):
            a, b, c = st.columns(3)
            cliente = a.text_input("Cliente")
            telefono = b.text_input("Teléfono")
            referencia = c.text_input("Referencia / pedido")
            d, e, f = st.columns(3)
            origen = d.selectbox("Origen", ORIGENES)
            tipo = e.selectbox("Tipo de trabajo", TIPOS_TRABAJO)
            responsable = f.text_input("Responsable diseño", value=usuario)
            g, h, i = st.columns(3)
            cotizacion_id = g.number_input("Cotización ID", min_value=0, value=0, step=1)
            venta_id = h.number_input("Venta ID", min_value=0, value=0, step=1)
            orden_id = i.number_input("Orden producción ID", min_value=0, value=0, step=1)
            nombre_diseno = st.text_input("Nombre del diseño")
            archivo_editable = st.text_input("Archivo editable / ruta / URL")
            archivo_final = st.text_input("Archivo final / PDF / plantilla / URL")
            j, k, l = st.columns(3)
            version = j.text_input("Versión", value="1.0")
            estado = k.selectbox("Estado inicial", ESTADOS)
            aprobado_por = l.text_input("Aprobado por")
            obs = st.text_area("Observaciones")
            guardar = st.form_submit_button("Guardar diseño")
        if guardar:
            if not cliente.strip() or not nombre_diseno.strip():
                st.error("Cliente y nombre del diseño son obligatorios.")
            else:
                diseno_id = _create_design({
                    "usuario": usuario,
                    "cliente": cliente.strip(),
                    "telefono": telefono.strip(),
                    "referencia": referencia.strip(),
                    "origen": origen,
                    "cotizacion_id": int(cotizacion_id) or None,
                    "venta_id": int(venta_id) or None,
                    "orden_produccion_id": int(orden_id) or None,
                    "tipo_trabajo": tipo,
                    "nombre_diseno": nombre_diseno.strip(),
                    "archivo_editable": archivo_editable.strip(),
                    "archivo_final": archivo_final.strip(),
                    "version": version.strip() or "1.0",
                    "responsable_diseno": responsable.strip(),
                    "estado": estado,
                    "fecha_enviado_cliente": date.today().isoformat() if estado == "Enviado a cliente" else None,
                    "fecha_aprobacion_cliente": date.today().isoformat() if estado in ESTADOS_LIBERADOS else None,
                    "aprobado_por": aprobado_por.strip(),
                    "observaciones": obs.strip(),
                })
                st.success(f"Diseño #{diseno_id} guardado.")
                st.rerun()

    with tab_tablero:
        if df.empty:
            st.info("No hay diseños registrados.")
        else:
            estado_filter = st.selectbox("Filtrar estado", ["Todos"] + ESTADOS)
            vista = df if estado_filter == "Todos" else df[df["estado"].eq(estado_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            resumen = df.groupby("estado", as_index=False).agg(cantidad=("id", "count"))
            st.bar_chart(resumen.set_index("estado")["cantidad"])
            if not bloqueados.empty:
                st.warning(f"Hay {len(bloqueados)} diseño(s) bloqueando producción por falta de aprobación.")

    with tab_estado:
        if df.empty:
            st.info("No hay diseños para actualizar.")
        else:
            ids = df["id"].astype(int).tolist()
            diseno_id = st.selectbox("Diseño", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'cliente'].iloc[0]} · {df.loc[df['id'].eq(x), 'estado'].iloc[0]}")
            nuevo_estado = st.selectbox("Nuevo estado", ESTADOS)
            aprobado_por = st.text_input("Aprobado por cliente / responsable")
            archivo_ref = st.text_input("Archivo referencia actualizado")
            comentario = st.text_area("Comentario")
            if st.button("Actualizar diseño", type="primary"):
                _update_state(int(diseno_id), nuevo_estado, usuario, comentario.strip(), archivo_ref.strip(), aprobado_por.strip())
                st.success("Estado de diseño actualizado.")
                st.rerun()

    with tab_eventos:
        if eventos.empty:
            st.info("Sin eventos de diseño.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)
