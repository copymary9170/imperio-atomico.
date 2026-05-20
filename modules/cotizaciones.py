from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.integration_hub import render_module_inbox
from services.costeo_service import (
    calcular_costo_servicio,
    calcular_margen_estimado,
    guardar_costeo,
    obtener_parametros_costeo,
)

ESTADOS_COTIZACION = [
    "Cotización",
    "En revisión",
    "Aprobada",
    "Rechazada",
    "Convertida en orden",
]

TIPOS_TRABAJO = ["Impresión", "Copias", "Sublimación", "Corte", "Papelería creativa", "Diseño", "Bazar", "Otro"]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(out) or math.isinf(out):
        return float(default)
    return out


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
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cliente TEXT,
                telefono TEXT,
                email TEXT,
                descripcion TEXT NOT NULL,
                tipo_trabajo TEXT DEFAULT 'Otro',
                cantidad REAL NOT NULL DEFAULT 1,
                costo_estimado_usd REAL NOT NULL DEFAULT 0,
                margen_pct REAL NOT NULL DEFAULT 0,
                precio_final_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Cotización',
                vigencia_hasta TEXT,
                condiciones_pago TEXT,
                tiempo_entrega TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                observaciones TEXT,
                orden_trabajo_id INTEGER
            )
            """
        )
        cols = _columns(conn, "cotizaciones")
        extras = {
            "cliente": "ALTER TABLE cotizaciones ADD COLUMN cliente TEXT",
            "telefono": "ALTER TABLE cotizaciones ADD COLUMN telefono TEXT",
            "email": "ALTER TABLE cotizaciones ADD COLUMN email TEXT",
            "tipo_trabajo": "ALTER TABLE cotizaciones ADD COLUMN tipo_trabajo TEXT DEFAULT 'Otro'",
            "cantidad": "ALTER TABLE cotizaciones ADD COLUMN cantidad REAL NOT NULL DEFAULT 1",
            "vigencia_hasta": "ALTER TABLE cotizaciones ADD COLUMN vigencia_hasta TEXT",
            "condiciones_pago": "ALTER TABLE cotizaciones ADD COLUMN condiciones_pago TEXT",
            "tiempo_entrega": "ALTER TABLE cotizaciones ADD COLUMN tiempo_entrega TEXT",
            "version": "ALTER TABLE cotizaciones ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
            "observaciones": "ALTER TABLE cotizaciones ADD COLUMN observaciones TEXT",
            "orden_trabajo_id": "ALTER TABLE cotizaciones ADD COLUMN orden_trabajo_id INTEGER",
        }
        for col, ddl in extras.items():
            if col not in cols:
                conn.execute(ddl)


def _normalizar_payload(payload: dict) -> tuple[str, float, str, str, float]:
    descripcion = (
        payload.get("descripcion")
        or payload.get("trabajo")
        or payload.get("tipo")
        or payload.get("tipo_produccion")
        or "Trabajo personalizado"
    )
    costo_base = _safe_float(payload.get("costo_estimado") or payload.get("costo_base"), 0.0)
    cantidad = _safe_float(payload.get("cantidad") or payload.get("unidades"), 1.0)
    if cantidad > 1 and costo_base > 0 and payload.get("costo_estimado") is None:
        costo_base *= cantidad
    cliente = str(payload.get("cliente") or payload.get("nombre") or "")
    telefono = str(payload.get("telefono") or payload.get("whatsapp") or "")
    return str(descripcion), round(_safe_float(costo_base, 0.0), 2), cliente, telefono, cantidad or 1.0


def _insertar_cotizacion(data: dict) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cols = _columns(conn, "cotizaciones")
        allowed = {k: v for k, v in data.items() if k in cols}
        keys = list(allowed.keys())
        placeholders = ",".join(["?"] * len(keys))
        cur = conn.execute(
            f"INSERT INTO cotizaciones ({','.join(keys)}) VALUES ({placeholders})",
            [allowed[k] for k in keys],
        )
        return int(cur.lastrowid)


def _actualizar_estado(cotizacion_id: int, estado: str) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        conn.execute("UPDATE cotizaciones SET estado=? WHERE id=?", (estado, int(cotizacion_id)))


def _load_cotizaciones() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM cotizaciones ORDER BY id DESC", conn)


def _ensure_ot_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ordenes_trabajo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario_creacion TEXT NOT NULL,
            codigo TEXT NOT NULL,
            cliente TEXT NOT NULL,
            telefono TEXT,
            cotizacion_id INTEGER,
            tipo_trabajo TEXT NOT NULL DEFAULT 'Otro',
            prioridad TEXT NOT NULL DEFAULT 'Normal',
            descripcion TEXT NOT NULL,
            cantidad REAL NOT NULL DEFAULT 1,
            estado TEXT NOT NULL DEFAULT 'Nueva',
            bloqueo_produccion INTEGER NOT NULL DEFAULT 1,
            costo_estimado_usd REAL NOT NULL DEFAULT 0,
            costo_real_usd REAL NOT NULL DEFAULT 0,
            precio_venta_usd REAL NOT NULL DEFAULT 0,
            margen_estimado_usd REAL NOT NULL DEFAULT 0,
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
            archivo_referencia TEXT
        )
        """
    )
    cols = _columns(conn, "ordenes_trabajo")
    extras = {
        "cotizacion_id": "ALTER TABLE ordenes_trabajo ADD COLUMN cotizacion_id INTEGER",
        "tipo_trabajo": "ALTER TABLE ordenes_trabajo ADD COLUMN tipo_trabajo TEXT NOT NULL DEFAULT 'Otro'",
        "prioridad": "ALTER TABLE ordenes_trabajo ADD COLUMN prioridad TEXT NOT NULL DEFAULT 'Normal'",
        "cantidad": "ALTER TABLE ordenes_trabajo ADD COLUMN cantidad REAL NOT NULL DEFAULT 1",
        "bloqueo_produccion": "ALTER TABLE ordenes_trabajo ADD COLUMN bloqueo_produccion INTEGER NOT NULL DEFAULT 1",
        "costo_estimado_usd": "ALTER TABLE ordenes_trabajo ADD COLUMN costo_estimado_usd REAL NOT NULL DEFAULT 0",
        "costo_real_usd": "ALTER TABLE ordenes_trabajo ADD COLUMN costo_real_usd REAL NOT NULL DEFAULT 0",
        "precio_venta_usd": "ALTER TABLE ordenes_trabajo ADD COLUMN precio_venta_usd REAL NOT NULL DEFAULT 0",
        "margen_estimado_usd": "ALTER TABLE ordenes_trabajo ADD COLUMN margen_estimado_usd REAL NOT NULL DEFAULT 0",
        "observaciones": "ALTER TABLE ordenes_trabajo ADD COLUMN observaciones TEXT",
    }
    for col, ddl in extras.items():
        if col not in cols:
            conn.execute(ddl)


def _next_ot_code(conn) -> str:
    row = conn.execute("SELECT MAX(id) FROM ordenes_trabajo").fetchone()
    next_id = int(row[0] or 0) + 1 if row else 1
    return f"OT-{date.today().strftime('%Y%m%d')}-{next_id:04d}"


def _convertir_a_ot(cotizacion_id: int, usuario: str, responsable: str = "") -> int:
    _ensure_tables()
    with db_transaction() as conn:
        _ensure_ot_tables(conn)
        cot = conn.execute("SELECT * FROM cotizaciones WHERE id=?", (int(cotizacion_id),)).fetchone()
        if not cot:
            raise ValueError("Cotización no encontrada.")
        cols = [row[1] for row in conn.execute("PRAGMA table_info(cotizaciones)").fetchall()]
        data = dict(zip(cols, cot))
        if str(data.get("estado") or "") not in {"Aprobada", "Convertida en orden"}:
            raise ValueError("Solo puedes convertir cotizaciones aprobadas.")
        if data.get("orden_trabajo_id"):
            return int(data["orden_trabajo_id"])
        codigo = _next_ot_code(conn)
        costo = float(data.get("costo_estimado_usd") or 0)
        precio = float(data.get("precio_final_usd") or 0)
        cur = conn.execute(
            """
            INSERT INTO ordenes_trabajo(
                usuario_creacion, codigo, cliente, telefono, cotizacion_id, tipo_trabajo, prioridad,
                descripcion, cantidad, estado, bloqueo_produccion, costo_estimado_usd, costo_real_usd,
                precio_venta_usd, margen_estimado_usd, observaciones, responsable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Nueva', 1, ?, 0, ?, ?, ?, ?)
            """,
            (
                usuario,
                codigo,
                data.get("cliente") or "Cliente General",
                data.get("telefono") or "",
                int(cotizacion_id),
                data.get("tipo_trabajo") or "Otro",
                "Normal",
                data.get("descripcion") or "Trabajo cotizado",
                float(data.get("cantidad") or 1),
                costo,
                precio,
                precio - costo,
                f"Creada desde cotización #{cotizacion_id}. {data.get('observaciones') or ''}".strip(),
                responsable or usuario,
            ),
        )
        ot_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO ordenes_trabajo_eventos(orden_id, usuario, estado, comentario) VALUES (?, ?, ?, ?)",
            (ot_id, usuario, "Nueva", f"OT creada desde cotización #{cotizacion_id}"),
        )
        conn.execute(
            "UPDATE cotizaciones SET estado='Convertida en orden', orden_trabajo_id=? WHERE id=?",
            (ot_id, int(cotizacion_id)),
        )
        return ot_id


def _render_inbox() -> None:
    st.subheader("📥 Bandeja / Pre-cotizaciones")
    st.caption("Recibe datos enviados desde otros módulos para preparar una cotización.")

    def _apply_inbox(inbox: dict) -> None:
        st.session_state["datos_pre_cotizacion"] = dict(inbox.get("payload_data", {}))

    render_module_inbox("cotizaciones", apply_callback=_apply_inbox, clear_after_apply=False)
    datos_pre = st.session_state.get("datos_pre_cotizacion", {})
    if datos_pre:
        st.success("Hay una pre-cotización cargada para usar en Nueva cotización.")
        st.json(datos_pre)
        if st.button("🧹 Limpiar pre-cotización", use_container_width=True, key="cot_limpiar_pre"):
            del st.session_state["datos_pre_cotizacion"]
            st.rerun()
    else:
        st.info("No hay pre-cotizaciones cargadas en este momento.")


def _render_nueva_cotizacion(usuario: str) -> None:
    st.subheader("🧾 Nueva cotización")
    st.caption("Crea cotizaciones manuales o calculadas con el motor de costeo. Cotizaciones = precio comercial para el cliente; Costeo = cálculo técnico.")
    datos_pre = st.session_state.get("datos_pre_cotizacion", {})
    descripcion_pre, costo_base_pre, cliente_pre, telefono_pre, cantidad_pre = _normalizar_payload(datos_pre) if datos_pre else ("", 0.0, "", "", 1.0)

    costeo_calculado: dict | None = None
    modo_precio = st.radio("Modo de cotización", options=["Manual", "Calculada (costeo)"], horizontal=True, key="cot_modo_precio")
    a, b, c = st.columns([1.5, 1, 1])
    cliente = a.text_input("Cliente", value=cliente_pre, key="cot_cliente")
    telefono = b.text_input("Teléfono / WhatsApp", value=telefono_pre, key="cot_telefono")
    email = c.text_input("Email", key="cot_email")
    d, e, f = st.columns(3)
    tipo_trabajo = d.selectbox("Tipo de trabajo", TIPOS_TRABAJO, index=TIPOS_TRABAJO.index("Otro"), key="cot_tipo_trabajo")
    cantidad_general = e.number_input("Cantidad", min_value=0.01, value=float(cantidad_pre or 1), step=1.0, key="cot_cantidad_general")
    vigencia_hasta = f.date_input("Vigencia hasta", value=date.today() + timedelta(days=7), key="cot_vigencia")
    descripcion = st.text_area("Descripción del trabajo", value=descripcion_pre, placeholder="Ej: Impresión CMYK 200 páginas + corte vinil", height=110, key="cot_descripcion")

    c1, c2 = st.columns([2, 1])
    with c1:
        condiciones_pago = st.text_input("Condiciones de pago", value="50% anticipo / 50% contra entrega", key="cot_condiciones")
        tiempo_entrega = st.text_input("Tiempo estimado de entrega", value="A convenir", key="cot_tiempo")
        observaciones = st.text_area("Observaciones comerciales", key="cot_observaciones")
    with c2:
        costo_estimado = st.number_input("Costo estimado USD", min_value=0.0, value=max(_safe_float(costo_base_pre, 0.0), 0.0), step=0.5, format="%.2f", key="cot_costo_manual")
        if modo_precio == "Manual":
            margen_pct = st.slider("Margen (%)", min_value=0, max_value=250, value=65, step=1, key="cot_margen_manual")
        else:
            margen_pct = 0.0
        ajuste_usd = st.number_input("Ajustes extras USD", value=0.0, step=0.5, format="%.2f", help="Flete, urgencia o descuento negativo.", key="cot_ajuste")

    if modo_precio == "Calculada (costeo)":
        parametros_costeo = obtener_parametros_costeo()
        st.markdown("#### Costeo técnico")
        k1, k2, k3, k4 = st.columns(4)
        tipo_proceso = k1.selectbox("Tipo proceso", options=["Servicio general", "Impresión", "Sublimación", "Corte", "Instalación"], key="cot_tipo_proceso")
        cantidad_costeo = k2.number_input("Cantidad costeo", min_value=0.01, value=float(cantidad_general or 1), step=1.0, key="cot_cantidad")
        costo_materiales = k3.number_input("Materiales USD", min_value=0.0, value=0.0, step=0.5, key="cot_mat")
        costo_mano_obra = k4.number_input("Mano de obra USD", min_value=0.0, value=0.0, step=0.5, key="cot_mo")
        costo_indirecto = st.number_input("Indirecto directo USD", min_value=0.0, value=0.0, step=0.5, key="cot_ind")
        margen_pct = st.number_input("Margen objetivo (%)", min_value=0.0, max_value=300.0, value=float(parametros_costeo.get("margen_objetivo_pct", 35.0)), step=1.0, key="cot_margen_calc")
        costeo = calcular_costo_servicio(tipo_proceso=tipo_proceso, cantidad=float(cantidad_costeo), costo_materiales_usd=float(costo_materiales), costo_mano_obra_usd=float(costo_mano_obra), costo_indirecto_usd=float(costo_indirecto), parametros_override=parametros_costeo)
        costo_estimado = float(costeo["costo_total_usd"])
        if costo_estimado <= 0:
            precio_final = round(_safe_float(ajuste_usd, 0.0), 2)
            st.warning("El costo total calculado es 0. Ingresa al menos un costo (> 0).")
        else:
            margen = calcular_margen_estimado(costo_total_usd=float(costeo["costo_total_usd"]), margen_pct=float(margen_pct))
            precio_final = round(float(margen["precio_sugerido_usd"]) + _safe_float(ajuste_usd, 0.0), 2)
            costeo_calculado = {"tipo_proceso": tipo_proceso, "cantidad": float(cantidad_costeo), "costo_materiales_usd": float(costo_materiales), "costo_mano_obra_usd": float(costo_mano_obra), "costo_indirecto_usd": float(costo_indirecto), "margen_pct": float(margen_pct), "precio_sugerido_usd": float(precio_final)}
        desglose = pd.DataFrame([("Materiales", costeo["componentes"]["materiales_usd"]), ("Mano de obra", costeo["componentes"]["mano_obra_usd"]), ("Indirecto directo", costeo["componentes"]["indirecto_directo_usd"]), ("Imprevistos", costeo["componentes"]["imprevistos_usd"]), ("Indirecto factor", costeo["componentes"]["indirecto_factor_usd"])], columns=["Concepto", "Monto USD"])
        st.dataframe(desglose, use_container_width=True, hide_index=True)
    else:
        subtotal = _safe_float(costo_estimado, 0.0) * (1 + _safe_float(margen_pct, 0.0) / 100)
        precio_final = round(subtotal + _safe_float(ajuste_usd, 0.0), 2)

    estado_nuevo = st.selectbox("Estado inicial", ESTADOS_COTIZACION, index=0, key="cot_estado_inicial")
    m1, m2, m3 = st.columns(3)
    m1.metric("Costo base", f"$ {float(costo_estimado):,.2f}")
    m2.metric("Margen aplicado", f"{float(margen_pct):,.0f}%")
    m3.metric("Precio recomendado", f"$ {precio_final:,.2f}")

    if st.button("💾 Guardar cotización", use_container_width=True, type="primary", key="cot_guardar"):
        if not descripcion.strip():
            st.warning("Agrega una descripción para guardar la cotización.")
        else:
            cid = _insertar_cotizacion({"usuario": usuario, "cliente": cliente.strip(), "telefono": telefono.strip(), "email": email.strip(), "descripcion": descripcion.strip(), "tipo_trabajo": tipo_trabajo, "cantidad": float(cantidad_general), "costo_estimado_usd": _safe_float(costo_estimado, 0.0), "margen_pct": _safe_float(margen_pct, 0.0), "precio_final_usd": _safe_float(precio_final, 0.0), "estado": estado_nuevo, "vigencia_hasta": vigencia_hasta.isoformat(), "condiciones_pago": condiciones_pago.strip(), "tiempo_entrega": tiempo_entrega.strip(), "version": 1, "observaciones": observaciones.strip()})
            if modo_precio == "Calculada (costeo)" and costeo_calculado is not None:
                guardar_costeo(usuario=usuario, tipo_proceso=str(costeo_calculado["tipo_proceso"]), descripcion=descripcion.strip(), cantidad=float(costeo_calculado["cantidad"]), costo_materiales_usd=float(costeo_calculado["costo_materiales_usd"]), costo_mano_obra_usd=float(costeo_calculado["costo_mano_obra_usd"]), costo_indirecto_usd=float(costeo_calculado["costo_indirecto_usd"]), margen_pct=float(costeo_calculado["margen_pct"]), precio_sugerido_usd=float(costeo_calculado["precio_sugerido_usd"]), origen="cotizacion", referencia_id=int(cid), cotizacion_id=int(cid), estado="cotizado")
            if "datos_pre_cotizacion" in st.session_state:
                del st.session_state["datos_pre_cotizacion"]
            st.success(f"Cotización #{cid} registrada correctamente.")
            st.rerun()


def _render_historial() -> pd.DataFrame:
    st.subheader("📋 Historial")
    df = _load_cotizaciones()
    if df.empty:
        st.info("No hay cotizaciones registradas.")
        if st.button("🧪 Insertar cotización de ejemplo", use_container_width=True, key="cot_demo"):
            cid = _insertar_cotizacion({"usuario": "Sistema", "cliente": "Cliente demo", "descripcion": "Cotización demo · Impresión y acabado", "costo_estimado_usd": 25.0, "margen_pct": 65.0, "precio_final_usd": 41.25, "estado": "Cotización", "vigencia_hasta": (date.today() + timedelta(days=7)).isoformat()})
            st.success(f"Cotización demo #{cid} creada.")
            st.rerun()
        return df
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    f1, f2, f3 = st.columns([1.5, 1, 1])
    q = f1.text_input("Buscar", placeholder="Cliente, descripción, usuario...", key="cot_buscar")
    estados_disponibles = sorted(df["estado"].dropna().unique().tolist())
    estados_filtrados = f2.multiselect("Estado", options=estados_disponibles, default=estados_disponibles, key="cot_filtro_estado")
    solo_abiertas = f3.checkbox("Solo abiertas", value=False, key="cot_solo_abiertas")
    vista = df.copy()
    if q.strip():
        qlow = q.lower()
        vista = vista[vista.astype(str).apply(lambda c: c.str.lower().str.contains(qlow, na=False)).any(axis=1)]
    if estados_filtrados:
        vista = vista[vista["estado"].isin(estados_filtrados)]
    if solo_abiertas:
        vista = vista[~vista["estado"].isin(["Rechazada", "Convertida en orden"])]
    st.dataframe(vista, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Exportar CSV", data=vista.to_csv(index=False).encode("utf-8"), file_name="cotizaciones_filtradas.csv", mime="text/csv", use_container_width=True, key="cot_exportar")
    return df


def _render_estados() -> None:
    st.subheader("✅ Aprobaciones / Estados")
    df = _load_cotizaciones()
    if df.empty:
        st.info("No hay cotizaciones para actualizar.")
        return
    ids = df["id"].astype(int).tolist()
    cot_id = st.selectbox("Cotización", ids, format_func=lambda x: f"#{x} · {df.loc[df['id'].eq(x), 'cliente'].fillna('').iloc[0]} · {df.loc[df['id'].eq(x), 'estado'].iloc[0]} · ${float(df.loc[df['id'].eq(x), 'precio_final_usd'].iloc[0] or 0):,.2f}", key="cot_estado_id")
    nuevo_estado = st.selectbox("Nuevo estado", ESTADOS_COTIZACION, index=0, key="cot_nuevo_estado")
    if st.button("Actualizar estado", use_container_width=True, key="cot_actualizar_estado"):
        _actualizar_estado(int(cot_id), nuevo_estado)
        st.success(f"Cotización #{int(cot_id)} actualizada a '{nuevo_estado}'.")
        st.rerun()


def _render_conversion(usuario: str) -> None:
    st.subheader("🔁 Convertir a Orden de Trabajo")
    st.caption("Convierte cotizaciones aprobadas en OT. La venta/comprobante puede generarse después desde Ventas o POS.")
    df = _load_cotizaciones()
    if df.empty:
        st.info("No hay cotizaciones para convertir.")
        return
    elegibles = df[df["estado"].isin(["Aprobada", "Convertida en orden"])]
    if elegibles.empty:
        st.info("No hay cotizaciones aprobadas. Aprueba una cotización antes de convertirla.")
        return
    ids = elegibles["id"].astype(int).tolist()
    cot_id = st.selectbox("Cotización aprobada", ids, format_func=lambda x: f"#{x} · {elegibles.loc[elegibles['id'].eq(x), 'cliente'].fillna('Cliente General').iloc[0]} · ${float(elegibles.loc[elegibles['id'].eq(x), 'precio_final_usd'].iloc[0] or 0):,.2f}", key="cot_convertir_id")
    responsable = st.text_input("Responsable inicial de la OT", value=usuario, key="cot_responsable_ot")
    if st.button("Crear / ver Orden de Trabajo", type="primary", use_container_width=True, key="cot_convertir_ot"):
        try:
            ot_id = _convertir_a_ot(int(cot_id), usuario, responsable.strip())
            st.success(f"Cotización #{int(cot_id)} convertida/vinculada a OT #{ot_id}.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_inteligencia() -> None:
    st.subheader("📊 Inteligencia")
    df = _load_cotizaciones()
    if df.empty:
        st.info("No hay cotizaciones para analizar.")
        return
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    total_cot = int(len(df))
    total_monto = float(pd.to_numeric(df["precio_final_usd"], errors="coerce").fillna(0).sum())
    ticket_prom = float(pd.to_numeric(df["precio_final_usd"], errors="coerce").fillna(0).mean()) if total_cot else 0.0
    aprobadas = int((df["estado"] == "Aprobada").sum())
    tasa_aprob = (aprobadas / total_cot * 100) if total_cot else 0.0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cotizaciones", f"{total_cot:,}")
    k2.metric("Monto proyectado", f"$ {total_monto:,.2f}")
    k3.metric("Ticket promedio", f"$ {ticket_prom:,.2f}")
    k4.metric("Tasa de aprobación", f"{tasa_aprob:,.1f}%")
    c1, c2 = st.columns(2)
    with c1:
        estado_chart = df.groupby("estado", as_index=False).size().rename(columns={"size": "cantidad"})
        if not estado_chart.empty:
            st.plotly_chart(px.pie(estado_chart, names="estado", values="cantidad", title="Distribución por estado"), use_container_width=True)
    with c2:
        trend = df.dropna(subset=["fecha"]).assign(dia=lambda d: d["fecha"].dt.date.astype(str)).groupby("dia", as_index=False)["precio_final_usd"].sum()
        if not trend.empty:
            fig = px.line(trend, x="dia", y="precio_final_usd", markers=True, title="Monto cotizado por día")
            fig.update_layout(yaxis_title="USD", xaxis_title="Fecha")
            st.plotly_chart(fig, use_container_width=True)


def _render_alertas() -> None:
    st.subheader("🚨 Alertas de cotizaciones")
    df = _load_cotizaciones()
    if df.empty:
        st.info("No hay cotizaciones para evaluar.")
        return
    today = pd.Timestamp.today().normalize()
    vig = pd.to_datetime(df.get("vigencia_hasta"), errors="coerce") if "vigencia_hasta" in df.columns else pd.Series(pd.NaT, index=df.index)
    abiertas = ~df["estado"].isin(["Rechazada", "Convertida en orden"])
    vencidas = df[abiertas & vig.notna() & (vig < today)]
    aprobadas_sin_ot = df[(df["estado"] == "Aprobada") & (pd.to_numeric(df.get("orden_trabajo_id", pd.Series(dtype=float)), errors="coerce").fillna(0) <= 0)]
    costo = pd.to_numeric(df["costo_estimado_usd"], errors="coerce").fillna(0)
    precio = pd.to_numeric(df["precio_final_usd"], errors="coerce").fillna(0)
    margen_bajo = df[(precio > 0) & (costo > 0) & (((precio - costo) / precio) < 0.15)]
    precio_menor_costo = df[(precio > 0) & (costo > 0) & (precio < costo)]
    sin_cliente = df[df.get("cliente", pd.Series(dtype=str)).fillna("").astype(str).str.strip().eq("")]
    revision_antigua = df[(df["estado"] == "En revisión") & pd.to_datetime(df["fecha"], errors="coerce").lt(pd.Timestamp.today() - pd.Timedelta(days=7))]
    alertas = []
    for nivel, nombre, tabla, accion in [
        ("Alta", "Cotizaciones vencidas", vencidas, "Actualizar vigencia o cerrar seguimiento."),
        ("Alta", "Aprobadas sin OT", aprobadas_sin_ot, "Convertir a Orden de Trabajo."),
        ("Alta", "Precio menor al costo", precio_menor_costo, "Revisar costo/precio antes de enviar."),
        ("Media", "Margen bajo", margen_bajo, "Revisar margen objetivo."),
        ("Media", "Sin cliente", sin_cliente, "Completar cliente/teléfono."),
        ("Media", "En revisión por más de 7 días", revision_antigua, "Dar seguimiento comercial."),
    ]:
        if not tabla.empty:
            alertas.append({"nivel": nivel, "alerta": nombre, "cantidad": len(tabla), "acción": accion})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Vencidas", len(vencidas))
    c2.metric("Aprobadas sin OT", len(aprobadas_sin_ot))
    c3.metric("Margen bajo", len(margen_bajo))
    c4.metric("Sin cliente", len(sin_cliente))
    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas críticas de cotizaciones.")
    tabs = st.tabs(["Vencidas", "Aprobadas sin OT", "Margen / costo", "Sin cliente", "Revisión antigua"])
    with tabs[0]: st.dataframe(vencidas, use_container_width=True, hide_index=True) if not vencidas.empty else st.success("Sin vencidas.")
    with tabs[1]: st.dataframe(aprobadas_sin_ot, use_container_width=True, hide_index=True) if not aprobadas_sin_ot.empty else st.success("Sin aprobadas pendientes de OT.")
    with tabs[2]:
        if not precio_menor_costo.empty: st.dataframe(precio_menor_costo, use_container_width=True, hide_index=True)
        elif not margen_bajo.empty: st.dataframe(margen_bajo, use_container_width=True, hide_index=True)
        else: st.success("Sin alertas de margen/costo.")
    with tabs[3]: st.dataframe(sin_cliente, use_container_width=True, hide_index=True) if not sin_cliente.empty else st.success("Sin cotizaciones sin cliente.")
    with tabs[4]: st.dataframe(revision_antigua, use_container_width=True, hide_index=True) if not revision_antigua.empty else st.success("Sin revisiones antiguas.")


def render_cotizaciones(usuario: str):
    _ensure_tables()
    st.caption("Flujo comercial: pre-cotización → cotización → aprobación → Orden de Trabajo → venta/producción/despacho.")
    tab_nueva, tab_inbox, tab_historial, tab_estados, tab_conversion, tab_inteligencia, tab_alertas = st.tabs([
        "🧾 Nueva cotización",
        "📥 Bandeja / Pre-cotizaciones",
        "📋 Historial",
        "✅ Aprobaciones / Estados",
        "🔁 Convertir a OT",
        "📊 Inteligencia",
        "🚨 Alertas",
    ])
    with tab_nueva:
        _render_nueva_cotizacion(usuario)
    with tab_inbox:
        _render_inbox()
    with tab_historial:
        _render_historial()
    with tab_estados:
        _render_estados()
    with tab_conversion:
        _render_conversion(usuario)
    with tab_inteligencia:
        _render_inteligencia()
    with tab_alertas:
        _render_alertas()
