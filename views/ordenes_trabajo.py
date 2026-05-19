from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission
from services.audit_service import log_audit_event

ESTADOS_OT = ["Nueva", "Archivo recibido", "Diseño pendiente", "Diseño aprobado", "En producción", "Calidad", "Listo para despacho", "Despachado", "Entregado", "Cancelado"]
TIPOS_TRABAJO = ["Impresión", "Copias", "Sublimación", "Corte", "Papelería creativa", "Diseño", "Bazar", "Otro"]
PRIORIDADES = ["Normal", "Alta", "Urgente", "Baja"]
METODOS_PAGO = ["efectivo", "transferencia", "zelle", "binance", "mixto", "otro"]
ESTADOS_FINALES = {"Entregado", "Cancelado"}
ESTADOS_BLOQUEO_DISENO = {"Nueva", "Archivo recibido", "Diseño pendiente"}


def _table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_extra_columns(conn) -> None:
    cols = _table_columns(conn, "ordenes_trabajo")
    extras = [
        ("anticipo_usd", "ALTER TABLE ordenes_trabajo ADD COLUMN anticipo_usd REAL NOT NULL DEFAULT 0"),
        ("saldo_pendiente_usd", "ALTER TABLE ordenes_trabajo ADD COLUMN saldo_pendiente_usd REAL NOT NULL DEFAULT 0"),
        ("estado_pago", "ALTER TABLE ordenes_trabajo ADD COLUMN estado_pago TEXT NOT NULL DEFAULT 'Pendiente'"),
        ("bloqueo_entrega", "ALTER TABLE ordenes_trabajo ADD COLUMN bloqueo_entrega INTEGER NOT NULL DEFAULT 1"),
        ("margen_real_usd", "ALTER TABLE ordenes_trabajo ADD COLUMN margen_real_usd REAL NOT NULL DEFAULT 0"),
    ]
    for col, ddl in extras:
        if col not in cols:
            conn.execute(ddl)
            cols.add(col)
    conn.execute(
        """
        UPDATE ordenes_trabajo
        SET saldo_pendiente_usd = MAX(COALESCE(precio_venta_usd,0) - COALESCE(anticipo_usd,0), 0),
            estado_pago = CASE
                WHEN COALESCE(precio_venta_usd,0) <= 0 THEN 'Sin monto'
                WHEN COALESCE(anticipo_usd,0) <= 0 THEN 'Pendiente'
                WHEN COALESCE(anticipo_usd,0) >= COALESCE(precio_venta_usd,0) THEN 'Pagado'
                ELSE 'Abonado'
            END,
            bloqueo_entrega = CASE WHEN COALESCE(precio_venta_usd,0) - COALESCE(anticipo_usd,0) > 0 THEN 1 ELSE 0 END,
            margen_real_usd = COALESCE(precio_venta_usd,0) - COALESCE(costo_real_usd,0)
        """
    )


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_trabajo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario_creacion TEXT NOT NULL,
                codigo TEXT NOT NULL,
                cliente TEXT NOT NULL,
                telefono TEXT,
                venta_id INTEGER,
                cotizacion_id INTEGER,
                comprobante_id INTEGER,
                diseno_id INTEGER,
                despacho_id INTEGER,
                bom_id INTEGER,
                tipo_trabajo TEXT NOT NULL DEFAULT 'Impresión',
                prioridad TEXT NOT NULL DEFAULT 'Normal',
                descripcion TEXT NOT NULL,
                especificaciones TEXT,
                archivo_origen TEXT,
                archivo_final TEXT,
                cantidad REAL NOT NULL DEFAULT 1,
                fecha_promesa TEXT,
                responsable TEXT,
                estado TEXT NOT NULL DEFAULT 'Nueva',
                bloqueo_produccion INTEGER NOT NULL DEFAULT 1,
                costo_estimado_usd REAL NOT NULL DEFAULT 0,
                costo_real_usd REAL NOT NULL DEFAULT 0,
                precio_venta_usd REAL NOT NULL DEFAULT 0,
                anticipo_usd REAL NOT NULL DEFAULT 0,
                saldo_pendiente_usd REAL NOT NULL DEFAULT 0,
                estado_pago TEXT NOT NULL DEFAULT 'Pendiente',
                bloqueo_entrega INTEGER NOT NULL DEFAULT 1,
                margen_estimado_usd REAL NOT NULL DEFAULT 0,
                margen_real_usd REAL NOT NULL DEFAULT 0,
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_trabajo_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL,
                comentario TEXT,
                costo_real_usd REAL,
                archivo_referencia TEXT,
                FOREIGN KEY (orden_id) REFERENCES ordenes_trabajo(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes_trabajo_pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                metodo_pago TEXT NOT NULL,
                monto_usd REAL NOT NULL DEFAULT 0,
                referencia TEXT,
                observaciones TEXT,
                FOREIGN KEY (orden_id) REFERENCES ordenes_trabajo(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_estado ON ordenes_trabajo(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_cliente ON ordenes_trabajo(cliente)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_codigo ON ordenes_trabajo(codigo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ot_pagos ON ordenes_trabajo_pagos(orden_id)")
        _ensure_extra_columns(conn)


def _blocked(estado: str) -> int:
    return 1 if estado in ESTADOS_BLOQUEO_DISENO else 0


def _next_code() -> str:
    with db_transaction() as conn:
        row = conn.execute("SELECT MAX(id) FROM ordenes_trabajo").fetchone()
    next_id = int(row[0] or 0) + 1 if row else 1
    return f"OT-{datetime.now().strftime('%Y%m%d')}-{next_id:04d}"


def _payment_state(precio: float, abonado: float) -> tuple[str, float, int]:
    saldo = max(float(precio or 0) - float(abonado or 0), 0.0)
    if float(precio or 0) <= 0:
        return "Sin monto", 0.0, 0
    if abonado <= 0:
        return "Pendiente", saldo, 1
    if saldo <= 0.009:
        return "Pagado", 0.0, 0
    return "Abonado", saldo, 1


def _read_ordenes(limit: int = 500) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM ordenes_trabajo ORDER BY id DESC LIMIT ?", conn, params=(int(limit),))


def _read_eventos(orden_id: int | None = None) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if orden_id:
            return pd.read_sql_query("SELECT * FROM ordenes_trabajo_eventos WHERE orden_id=? ORDER BY id DESC", conn, params=(int(orden_id),))
        return pd.read_sql_query("SELECT * FROM ordenes_trabajo_eventos ORDER BY id DESC LIMIT 500", conn)


def _read_pagos(orden_id: int | None = None) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if orden_id:
            return pd.read_sql_query("SELECT * FROM ordenes_trabajo_pagos WHERE orden_id=? ORDER BY id DESC", conn, params=(int(orden_id),))
        return pd.read_sql_query("SELECT * FROM ordenes_trabajo_pagos ORDER BY id DESC LIMIT 500", conn)


def _create_orden(data: dict[str, Any]) -> int:
    _ensure_tables()
    estado = data.get("estado", "Nueva")
    costo_estimado = float(data.get("costo_estimado_usd") or 0)
    precio_venta = float(data.get("precio_venta_usd") or 0)
    anticipo = float(data.get("anticipo_usd") or 0)
    estado_pago, saldo, bloqueo_entrega = _payment_state(precio_venta, anticipo)
    margen = precio_venta - costo_estimado
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ordenes_trabajo(
                usuario_creacion, codigo, cliente, telefono, venta_id, cotizacion_id, comprobante_id,
                diseno_id, despacho_id, bom_id, tipo_trabajo, prioridad, descripcion,
                especificaciones, archivo_origen, archivo_final, cantidad, fecha_promesa,
                responsable, estado, bloqueo_produccion, costo_estimado_usd, costo_real_usd,
                precio_venta_usd, anticipo_usd, saldo_pendiente_usd, estado_pago, bloqueo_entrega,
                margen_estimado_usd, margen_real_usd, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario_creacion"], data["codigo"], data["cliente"], data.get("telefono"), data.get("venta_id"),
                data.get("cotizacion_id"), data.get("comprobante_id"), data.get("diseno_id"), data.get("despacho_id"),
                data.get("bom_id"), data.get("tipo_trabajo", "Impresión"), data.get("prioridad", "Normal"),
                data["descripcion"], data.get("especificaciones"), data.get("archivo_origen"), data.get("archivo_final"),
                float(data.get("cantidad") or 1), data.get("fecha_promesa"), data.get("responsable"), estado,
                _blocked(estado), costo_estimado, float(data.get("costo_real_usd") or 0), precio_venta,
                anticipo, saldo, estado_pago, bloqueo_entrega, margen, precio_venta - float(data.get("costo_real_usd") or 0),
                data.get("observaciones"),
            ),
        )
        orden_id = int(cur.lastrowid)
        conn.execute("INSERT INTO ordenes_trabajo_eventos(orden_id, usuario, estado, comentario, archivo_referencia) VALUES (?, ?, ?, ?, ?)", (orden_id, data["usuario_creacion"], estado, "Orden de trabajo creada", data.get("archivo_origen") or data.get("archivo_final")))
        if anticipo > 0:
            conn.execute("INSERT INTO ordenes_trabajo_pagos(orden_id, usuario, metodo_pago, monto_usd, referencia, observaciones) VALUES (?, ?, ?, ?, ?, ?)", (orden_id, data["usuario_creacion"], data.get("metodo_anticipo", "efectivo"), anticipo, data.get("referencia_anticipo"), "Anticipo inicial"))
        return orden_id


def _update_estado(orden_id: int, estado: str, usuario: str, comentario: str, costo_real: float, archivo_ref: str) -> tuple[bool, str]:
    with db_transaction() as conn:
        row = conn.execute("SELECT saldo_pendiente_usd, bloqueo_entrega FROM ordenes_trabajo WHERE id=?", (int(orden_id),)).fetchone()
        saldo = float(row[0] or 0) if row else 0.0
        if estado == "Entregado" and saldo > 0.009:
            return False, f"No se puede entregar: saldo pendiente ${saldo:,.2f}."
        updates = ["estado=?", "bloqueo_produccion=?"]
        params: list[Any] = [estado, _blocked(estado)]
        if costo_real > 0:
            updates.extend(["costo_real_usd=?", "margen_real_usd=COALESCE(precio_venta_usd,0)-?"])
            params.extend([float(costo_real), float(costo_real)])
        params.append(int(orden_id))
        conn.execute(f"UPDATE ordenes_trabajo SET {', '.join(updates)} WHERE id=?", tuple(params))
        conn.execute("INSERT INTO ordenes_trabajo_eventos(orden_id, usuario, estado, comentario, costo_real_usd, archivo_referencia) VALUES (?, ?, ?, ?, ?, ?)", (int(orden_id), usuario, estado, comentario, float(costo_real) if costo_real > 0 else None, archivo_ref))
    return True, "Orden actualizada."


def _add_pago(orden_id: int, usuario: str, metodo: str, monto: float, referencia: str, observaciones: str) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        row = conn.execute("SELECT precio_venta_usd, anticipo_usd FROM ordenes_trabajo WHERE id=?", (int(orden_id),)).fetchone()
        precio = float(row[0] or 0) if row else 0.0
        abonado_actual = float(row[1] or 0) if row else 0.0
        nuevo_abonado = abonado_actual + float(monto or 0)
        estado_pago, saldo, bloqueo = _payment_state(precio, nuevo_abonado)
        conn.execute("INSERT INTO ordenes_trabajo_pagos(orden_id, usuario, metodo_pago, monto_usd, referencia, observaciones) VALUES (?, ?, ?, ?, ?, ?)", (int(orden_id), usuario, metodo, float(monto), referencia, observaciones))
        conn.execute("UPDATE ordenes_trabajo SET anticipo_usd=?, saldo_pendiente_usd=?, estado_pago=?, bloqueo_entrega=? WHERE id=?", (nuevo_abonado, saldo, estado_pago, bloqueo, int(orden_id)))
        conn.execute("INSERT INTO ordenes_trabajo_eventos(orden_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)", (int(orden_id), usuario, estado_pago, f"Pago registrado: ${float(monto):,.2f} vía {metodo}"))


def _auto_stage(row: pd.Series) -> str:
    estado = str(row.get("estado") or "Nueva")
    if estado in ESTADOS_FINALES:
        return estado
    if int(row.get("bloqueo_entrega") or 0) and estado in {"Listo para despacho", "Despachado"}:
        return "Bloqueada por saldo"
    if int(row.get("bloqueo_produccion") or 0):
        return "Bloqueada por diseño"
    if estado in {"Diseño aprobado", "En producción", "Calidad"}:
        return "Producción"
    if estado in {"Listo para despacho", "Despachado"}:
        return "Entrega"
    return "Activa"


def render_ordenes_trabajo(usuario: str = "Sistema") -> None:
    if not require_any_permission(["produccion.plan", "produccion.execute", "dashboard.view"], "🚫 No tienes acceso a órdenes de trabajo."):
        return
    puede_editar = has_permission("produccion.plan") or has_permission("produccion.execute")
    st.subheader("🧾 Órdenes de trabajo")
    st.caption("Centro operativo: venta/cotización, archivos, diseño, producción, despacho, pagos, costos y estado.")
    _ensure_tables()
    ordenes = _read_ordenes()
    if not ordenes.empty:
        ordenes["etapa"] = ordenes.apply(_auto_stage, axis=1)
    abiertas = ordenes[~ordenes["estado"].isin(list(ESTADOS_FINALES))] if not ordenes.empty else pd.DataFrame()
    bloqueadas = ordenes[(ordenes["bloqueo_produccion"].eq(1)) | (ordenes["bloqueo_entrega"].eq(1))] if not ordenes.empty else pd.DataFrame()
    saldo_total = float(pd.to_numeric(ordenes.get("saldo_pendiente_usd", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not ordenes.empty else 0.0
    margen_real = float(pd.to_numeric(ordenes.get("margen_real_usd", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not ordenes.empty else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes", len(ordenes))
    c2.metric("Abiertas", len(abiertas))
    c3.metric("Bloqueadas", len(bloqueadas))
    c4.metric("Saldo pendiente", f"${saldo_total:,.2f}")
    tab_nueva, tab_tablero, tab_pagos, tab_estado, tab_eventos = st.tabs(["Nueva OT", "Tablero", "Pagos / anticipos", "Actualizar estado", "Eventos"])
    with tab_nueva:
        with st.form("form_nueva_ot"):
            a, b, c = st.columns(3)
            codigo = a.text_input("Código", value=_next_code(), disabled=not puede_editar)
            cliente = b.text_input("Cliente", disabled=not puede_editar)
            telefono = c.text_input("Teléfono", disabled=not puede_editar)
            d, e, f = st.columns(3)
            tipo = d.selectbox("Tipo de trabajo", TIPOS_TRABAJO, disabled=not puede_editar)
            prioridad = e.selectbox("Prioridad", PRIORIDADES, disabled=not puede_editar)
            responsable = f.text_input("Responsable", value=usuario, disabled=not puede_editar)
            descripcion = st.text_area("Descripción del trabajo", disabled=not puede_editar)
            especificaciones = st.text_area("Especificaciones técnicas", disabled=not puede_editar)
            g, h, i = st.columns(3)
            venta_id = g.number_input("Venta ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            cotizacion_id = h.number_input("Cotización ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            comprobante_id = i.number_input("Comprobante POS ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            j, k, l = st.columns(3)
            diseno_id = j.number_input("Diseño ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            despacho_id = k.number_input("Despacho ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            bom_id = l.number_input("BOM ID", min_value=0, value=0, step=1, disabled=not puede_editar)
            m, n, o = st.columns(3)
            cantidad = m.number_input("Cantidad", min_value=0.01, value=1.0, step=1.0, disabled=not puede_editar)
            costo_estimado = n.number_input("Costo estimado USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
            precio_venta = o.number_input("Precio venta USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
            p1, p2, p3 = st.columns(3)
            anticipo = p1.number_input("Anticipo inicial USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
            metodo_anticipo = p2.selectbox("Método anticipo", METODOS_PAGO, disabled=not puede_editar)
            referencia_anticipo = p3.text_input("Referencia anticipo", disabled=not puede_editar)
            archivo_origen = st.text_input("Archivo origen / URL", disabled=not puede_editar)
            archivo_final = st.text_input("Archivo final / URL", disabled=not puede_editar)
            fecha_promesa = st.date_input("Fecha promesa", value=None, disabled=not puede_editar)
            estado = st.selectbox("Estado inicial", ESTADOS_OT, disabled=not puede_editar)
            observaciones = st.text_area("Observaciones", disabled=not puede_editar)
            guardar = st.form_submit_button("Crear orden de trabajo", disabled=not puede_editar)
        if guardar:
            if not cliente.strip() or not descripcion.strip():
                st.error("Cliente y descripción son obligatorios.")
            else:
                payload = {"usuario_creacion": usuario, "codigo": codigo.strip() or _next_code(), "cliente": cliente.strip(), "telefono": telefono.strip(), "venta_id": int(venta_id) or None, "cotizacion_id": int(cotizacion_id) or None, "comprobante_id": int(comprobante_id) or None, "diseno_id": int(diseno_id) or None, "despacho_id": int(despacho_id) or None, "bom_id": int(bom_id) or None, "tipo_trabajo": tipo, "prioridad": prioridad, "descripcion": descripcion.strip(), "especificaciones": especificaciones.strip(), "archivo_origen": archivo_origen.strip(), "archivo_final": archivo_final.strip(), "cantidad": cantidad, "fecha_promesa": fecha_promesa.isoformat() if fecha_promesa else None, "responsable": responsable.strip(), "estado": estado, "costo_estimado_usd": costo_estimado, "precio_venta_usd": precio_venta, "anticipo_usd": anticipo, "metodo_anticipo": metodo_anticipo, "referencia_anticipo": referencia_anticipo.strip(), "observaciones": observaciones.strip()}
                orden_id = _create_orden(payload)
                log_audit_event(usuario=usuario, modulo="Producción", accion="crear_orden_trabajo", entidad="ordenes_trabajo", entidad_id=orden_id, detalle=f"OT creada: {payload['codigo']} - {cliente.strip()}", metadata=payload)
                st.success(f"Orden de trabajo #{orden_id} creada.")
                st.rerun()
    with tab_tablero:
        if ordenes.empty:
            st.info("No hay órdenes de trabajo registradas.")
        else:
            f1, f2, f3, f4 = st.columns(4)
            estado_filter = f1.selectbox("Estado", ["Todos"] + ESTADOS_OT)
            etapa_filter = f2.selectbox("Etapa", ["Todas"] + sorted(ordenes["etapa"].dropna().astype(str).unique().tolist()))
            prioridad_filter = f3.selectbox("Prioridad", ["Todas"] + PRIORIDADES)
            pago_filter = f4.selectbox("Pago", ["Todos"] + sorted(ordenes["estado_pago"].dropna().astype(str).unique().tolist()))
            vista = ordenes.copy()
            if estado_filter != "Todos": vista = vista[vista["estado"].astype(str).eq(estado_filter)]
            if etapa_filter != "Todas": vista = vista[vista["etapa"].astype(str).eq(etapa_filter)]
            if prioridad_filter != "Todas": vista = vista[vista["prioridad"].astype(str).eq(prioridad_filter)]
            if pago_filter != "Todos": vista = vista[vista["estado_pago"].astype(str).eq(pago_filter)]
            st.dataframe(vista, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar tablero OT CSV", data=vista.to_csv(index=False).encode("utf-8-sig"), file_name="ordenes_trabajo.csv", mime="text/csv", use_container_width=True)
            resumen = ordenes.groupby(["estado", "estado_pago"], as_index=False).agg(ordenes=("id", "count"), precio=("precio_venta_usd", "sum"), saldo=("saldo_pendiente_usd", "sum"), margen_real=("margen_real_usd", "sum"))
            st.markdown("#### Resumen por estado y pago")
            st.dataframe(resumen, use_container_width=True, hide_index=True)
    with tab_pagos:
        if ordenes.empty:
            st.info("No hay órdenes para registrar pagos.")
        else:
            ids = ordenes["id"].astype(int).tolist()
            orden_id = st.selectbox("Orden", ids, key="pago_ot", format_func=lambda x: f"#{x} · {ordenes.loc[ordenes['id'].eq(x), 'codigo'].iloc[0]} · Saldo ${float(ordenes.loc[ordenes['id'].eq(x), 'saldo_pendiente_usd'].iloc[0]):,.2f}", disabled=not puede_editar)
            row = ordenes[ordenes["id"].eq(orden_id)].iloc[0]
            st.info(f"Precio: ${float(row.get('precio_venta_usd') or 0):,.2f} · Abonado: ${float(row.get('anticipo_usd') or 0):,.2f} · Saldo: ${float(row.get('saldo_pendiente_usd') or 0):,.2f} · Estado pago: {row.get('estado_pago')}")
            with st.form("form_pago_ot"):
                a, b, c = st.columns(3)
                monto = a.number_input("Monto USD", min_value=0.0, value=float(row.get("saldo_pendiente_usd") or 0), step=0.01, disabled=not puede_editar)
                metodo = b.selectbox("Método", METODOS_PAGO, disabled=not puede_editar)
                referencia = c.text_input("Referencia", disabled=not puede_editar)
                obs_pago = st.text_area("Observaciones", disabled=not puede_editar)
                guardar_pago = st.form_submit_button("Registrar pago", disabled=not puede_editar)
            if guardar_pago:
                if monto <= 0:
                    st.error("El monto debe ser mayor que cero.")
                else:
                    _add_pago(int(orden_id), usuario, metodo, monto, referencia.strip(), obs_pago.strip())
                    log_audit_event(usuario=usuario, modulo="Producción", accion="registrar_pago_ot", entidad="ordenes_trabajo", entidad_id=orden_id, detalle=f"Pago OT registrado: ${monto:,.2f}", metadata={"metodo": metodo, "referencia": referencia.strip()})
                    st.success("Pago registrado.")
                    st.rerun()
            pagos = _read_pagos(int(orden_id))
            if not pagos.empty:
                st.dataframe(pagos, use_container_width=True, hide_index=True)
    with tab_estado:
        if ordenes.empty:
            st.info("No hay órdenes para actualizar.")
        else:
            ids = ordenes["id"].astype(int).tolist()
            orden_id = st.selectbox("Orden", ids, format_func=lambda x: f"#{x} · {ordenes.loc[ordenes['id'].eq(x), 'codigo'].iloc[0]} · {ordenes.loc[ordenes['id'].eq(x), 'cliente'].iloc[0]} · {ordenes.loc[ordenes['id'].eq(x), 'estado'].iloc[0]}", disabled=not puede_editar)
            col1, col2 = st.columns(2)
            nuevo_estado = col1.selectbox("Nuevo estado", ESTADOS_OT, disabled=not puede_editar)
            costo_real = col2.number_input("Costo real USD opcional", min_value=0.0, value=0.0, step=0.01, disabled=not puede_editar)
            archivo_ref = st.text_input("Archivo / referencia", disabled=not puede_editar)
            comentario = st.text_area("Comentario", disabled=not puede_editar)
            if st.button("Actualizar orden", type="primary", disabled=not puede_editar):
                ok, msg = _update_estado(int(orden_id), nuevo_estado, usuario, comentario.strip(), costo_real, archivo_ref.strip())
                if ok:
                    log_audit_event(usuario=usuario, modulo="Producción", accion="actualizar_orden_trabajo", entidad="ordenes_trabajo", entidad_id=orden_id, detalle=f"OT actualizada a {nuevo_estado}", metadata={"estado": nuevo_estado, "costo_real_usd": costo_real, "comentario": comentario.strip()})
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    with tab_eventos:
        eventos = _read_eventos()
        pagos = _read_pagos()
        if eventos.empty:
            st.info("No hay eventos de órdenes de trabajo.")
        else:
            st.dataframe(eventos, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar eventos OT CSV", data=eventos.to_csv(index=False).encode("utf-8-sig"), file_name="eventos_ordenes_trabajo.csv", mime="text/csv", use_container_width=True)
        if not pagos.empty:
            st.markdown("#### Pagos registrados")
            st.dataframe(pagos, use_container_width=True, hide_index=True)
