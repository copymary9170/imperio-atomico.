from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


# ============================================================
# CONFIG
# ============================================================

TIPOS_PRODUCTO = [
    "Tela",
    "Taza",
    "Gorra",
    "Mousepad",
    "Rompecabezas",
    "Metal",
    "Madera",
    "Otro",
]

ESTADOS_LOTE = [
    "pendiente",
    "en_proceso",
    "completado",
    "con_merma",
    "rechazado",
]

RESULTADOS_CALIDAD = [
    "aprobado",
    "reproceso",
    "rechazado",
]

PRESIONES = [
    "baja",
    "media",
    "alta",
]

MAQUINAS_DEFAULT = [
    "Plancha 1",
    "Plancha 2",
    "Horno",
    "Sublimadora automática",
]


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _ensure_sublimacion_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_lotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                origen TEXT,
                referencia_origen TEXT,
                cliente TEXT,
                producto TEXT NOT NULL,
                tipo_producto TEXT DEFAULT 'Otro',
                diseno TEXT,
                cantidad_programada REAL NOT NULL DEFAULT 0,
                cantidad_producida REAL NOT NULL DEFAULT 0,
                cantidad_aprobada REAL NOT NULL DEFAULT 0,
                cantidad_reproceso REAL NOT NULL DEFAULT 0,
                cantidad_merma REAL NOT NULL DEFAULT 0,
                cantidad_rechazada REAL NOT NULL DEFAULT 0,
                maquina TEXT,
                temperatura_c REAL DEFAULT 0,
                tiempo_seg REAL DEFAULT 0,
                presion TEXT,
                papel_tipo TEXT,
                tinta_tipo TEXT,
                observaciones TEXT,
                costo_transfer_total REAL DEFAULT 0,
                costo_transfer_unit REAL DEFAULT 0,
                costo_energia_unit REAL DEFAULT 0,
                costo_mano_obra_unit REAL DEFAULT 0,
                costo_depreciacion_unit REAL DEFAULT 0,
                costo_indirecto_unit REAL DEFAULT 0,
                costo_unitario_final REAL DEFAULT 0,
                costo_total_final REAL DEFAULT 0,
                merma_pct REAL DEFAULT 0,
                estado TEXT DEFAULT 'pendiente'
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_control_calidad (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                color_correcto INTEGER DEFAULT 1,
                transferencia_completa INTEGER DEFAULT 1,
                sin_manchas INTEGER DEFAULT 1,
                sin_ghosting INTEGER DEFAULT 1,
                sin_quemado INTEGER DEFAULT 1,
                observaciones TEXT,
                resultado TEXT DEFAULT 'aprobado',
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sublimacion_mermas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                lote_id INTEGER NOT NULL,
                usuario TEXT,
                tipo_falla TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                costo_estimado_usd REAL DEFAULT 0,
                observaciones TEXT,
                FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_fecha ON sublimacion_lotes(fecha)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_estado ON sublimacion_lotes(estado)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_qc_lote ON sublimacion_control_calidad(lote_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sublimacion_mermas_lote ON sublimacion_mermas(lote_id)"
        )


def _load_queue_df() -> pd.DataFrame:
    cola = st.session_state.get("cola_sublimacion", [])
    if not cola:
        return pd.DataFrame()

    df = pd.DataFrame(cola).copy()

    if "cantidad" not in df.columns:
        df["cantidad"] = 0.0
    if "costo_transfer_total" not in df.columns:
        df["costo_transfer_total"] = 0.0
    if "producto" not in df.columns:
        if "nombre" in df.columns:
            df["producto"] = df["nombre"]
        elif "descripcion" in df.columns:
            df["producto"] = df["descripcion"]
        else:
            df["producto"] = "Trabajo sin nombre"

    if "cliente" not in df.columns:
        df["cliente"] = ""
    if "diseno" not in df.columns:
        df["diseno"] = ""
    if "tipo_producto" not in df.columns:
        df["tipo_producto"] = "Otro"

    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0.0)
    df["costo_transfer_total"] = pd.to_numeric(df["costo_transfer_total"], errors="coerce").fillna(0.0)
    return df


def _load_lotes_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                cliente,
                producto,
                tipo_producto,
                diseno,
                cantidad_programada,
                cantidad_producida,
                cantidad_aprobada,
                cantidad_reproceso,
                cantidad_merma,
                cantidad_rechazada,
                maquina,
                temperatura_c,
                tiempo_seg,
                presion,
                costo_transfer_total,
                costo_transfer_unit,
                costo_energia_unit,
                costo_mano_obra_unit,
                costo_depreciacion_unit,
                costo_indirecto_unit,
                costo_unitario_final,
                costo_total_final,
                merma_pct,
                estado,
                observaciones
            FROM sublimacion_lotes
            ORDER BY id DESC
            """,
            conn,
        )
    return df


def _load_qc_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                qc.id,
                qc.fecha,
                qc.lote_id,
                l.producto,
                l.cliente,
                qc.usuario,
                qc.color_correcto,
                qc.transferencia_completa,
                qc.sin_manchas,
                qc.sin_ghosting,
                qc.sin_quemado,
                qc.resultado,
                qc.observaciones
            FROM sublimacion_control_calidad qc
            JOIN sublimacion_lotes l ON l.id = qc.lote_id
            ORDER BY qc.id DESC
            """,
            conn,
        )
    return df


def _load_mermas_df() -> pd.DataFrame:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                m.id,
                m.fecha,
                m.lote_id,
                l.producto,
                l.cliente,
                m.usuario,
                m.tipo_falla,
                m.cantidad,
                m.costo_estimado_usd,
                m.observaciones
            FROM sublimacion_mermas m
            JOIN sublimacion_lotes l ON l.id = m.lote_id
            ORDER BY m.id DESC
            """,
            conn,
        )
    return df


def _calc_costs(
    cantidad_total: float,
    costo_transfer_total: float,
    potencia_kw: float,
    minutos_unidad: float,
    costo_kwh: float,
    salario_hora: float,
    unidades_hora: float,
    valor_maquina: float,
    vida_horas: float,
    costo_indirecto_unit: float,
) -> dict[str, float]:
    qty = max(float(cantidad_total or 0.0), 0.0001)

    costo_transfer_unit = float(costo_transfer_total or 0.0) / qty
    costo_energia_unit = (float(potencia_kw or 0.0) * (float(minutos_unidad or 0.0) / 60.0)) * float(costo_kwh or 0.0)
    costo_mano_obra_unit = float(salario_hora or 0.0) / max(float(unidades_hora or 1.0), 0.0001)
    costo_depreciacion_unit = (float(valor_maquina or 0.0) / max(float(vida_horas or 1.0), 0.0001)) / max(float(unidades_hora or 1.0), 0.0001)
    costo_indirecto_unit = float(costo_indirecto_unit or 0.0)

    costo_unitario_final = (
        costo_transfer_unit
        + costo_energia_unit
        + costo_mano_obra_unit
        + costo_depreciacion_unit
        + costo_indirecto_unit
    )
    costo_total_final = costo_unitario_final * qty

    return {
        "costo_transfer_unit": round(costo_transfer_unit, 6),
        "costo_energia_unit": round(costo_energia_unit, 6),
        "costo_mano_obra_unit": round(costo_mano_obra_unit, 6),
        "costo_depreciacion_unit": round(costo_depreciacion_unit, 6),
        "costo_indirecto_unit": round(costo_indirecto_unit, 6),
        "costo_unitario_final": round(costo_unitario_final, 6),
        "costo_total_final": round(costo_total_final, 4),
    }


def _registrar_lote(
    usuario: str,
    producto: str,
    cliente: str,
    tipo_producto: str,
    diseno: str,
    cantidad_programada: float,
    maquina: str,
    temperatura_c: float,
    tiempo_seg: float,
    presion: str,
    papel_tipo: str,
    tinta_tipo: str,
    observaciones: str,
    costo_transfer_total: float,
    costos: dict[str, float],
    origen: str = "manual",
    referencia_origen: str = "",
) -> int:
    _ensure_sublimacion_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO sublimacion_lotes (
                usuario, origen, referencia_origen, cliente, producto, tipo_producto, diseno,
                cantidad_programada, cantidad_producida, cantidad_aprobada, cantidad_reproceso,
                cantidad_merma, cantidad_rechazada, maquina, temperatura_c, tiempo_seg, presion,
                papel_tipo, tinta_tipo, observaciones, costo_transfer_total,
                costo_transfer_unit, costo_energia_unit, costo_mano_obra_unit,
                costo_depreciacion_unit, costo_indirecto_unit, costo_unitario_final,
                costo_total_final, merma_pct, estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pendiente')
            """,
            (
                usuario,
                origen,
                referencia_origen,
                cliente,
                producto,
                tipo_producto,
                diseno,
                float(cantidad_programada),
                maquina,
                float(temperatura_c),
                float(tiempo_seg),
                presion,
                papel_tipo,
                tinta_tipo,
                observaciones,
                float(costo_transfer_total),
                float(costos["costo_transfer_unit"]),
                float(costos["costo_energia_unit"]),
                float(costos["costo_mano_obra_unit"]),
                float(costos["costo_depreciacion_unit"]),
                float(costos["costo_indirecto_unit"]),
                float(costos["costo_unitario_final"]),
                float(costos["costo_total_final"]),
            ),
        )
        return int(cur.lastrowid)


def _actualizar_resultado_lote(
    lote_id: int,
    producida: float,
    aprobada: float,
    reproceso: float,
    merma: float,
    rechazada: float,
    observaciones: str,
) -> None:
    qty_prog = max(producida, 0.0)
    merma_pct = (float(merma or 0.0) / max(float(producida or 0.0), 0.0001)) * 100.0 if producida > 0 else 0.0

    if rechazada > 0 and aprobada <= 0:
        estado = "rechazado"
    elif merma > 0:
        estado = "con_merma"
    elif aprobada > 0:
        estado = "completado"
    else:
        estado = "en_proceso"

    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE sublimacion_lotes
            SET cantidad_producida=?,
                cantidad_aprobada=?,
                cantidad_reproceso=?,
                cantidad_merma=?,
                cantidad_rechazada=?,
                merma_pct=?,
                observaciones=?,
                estado=?,
                actualizado_en=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                float(qty_prog),
                float(aprobada),
                float(reproceso),
                float(merma),
                float(rechazada),
                round(merma_pct, 4),
                _clean_text(observaciones),
                estado,
                int(lote_id),
            ),
        )


def _registrar_control_calidad(
    lote_id: int,
    usuario: str,
    color_correcto: bool,
    transferencia_completa: bool,
    sin_manchas: bool,
    sin_ghosting: bool,
    sin_quemado: bool,
    observaciones: str,
    resultado: str,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO sublimacion_control_calidad (
                lote_id, usuario, color_correcto, transferencia_completa,
                sin_manchas, sin_ghosting, sin_quemado, observaciones, resultado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(lote_id),
                usuario,
                1 if color_correcto else 0,
                1 if transferencia_completa else 0,
                1 if sin_manchas else 0,
                1 if sin_ghosting else 0,
                1 if sin_quemado else 0,
                _clean_text(observaciones),
                resultado,
            ),
        )


def _registrar_merma(
    lote_id: int,
    usuario: str,
    tipo_falla: str,
    cantidad: float,
    costo_estimado_usd: float,
    observaciones: str,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO sublimacion_mermas (
                lote_id, usuario, tipo_falla, cantidad, costo_estimado_usd, observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(lote_id),
                usuario,
                _clean_text(tipo_falla),
                float(cantidad),
                float(costo_estimado_usd),
                _clean_text(observaciones),
            ),
        )


# ============================================================
# UI
# ============================================================

def _render_cola() -> None:
    st.subheader("📥 Cola recibida desde CMYK")
    df_cola = _load_queue_df()

    if df_cola.empty:
        st.info("No hay trabajos pendientes en cola.")
        return

    total_transfer = float(df_cola["costo_transfer_total"].sum())
    total_unidades = float(df_cola["cantidad"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Trabajos en cola", len(df_cola))
    c2.metric("Unidades pendientes", f"{total_unidades:,.2f}")
    c3.metric("Costo transfer total", f"$ {total_transfer:,.2f}")

    st.dataframe(df_cola, use_container_width=True, hide_index=True)

    if st.button("🧹 Vaciar cola de sublimación", use_container_width=True):
        st.session_state["cola_sublimacion"] = []
        st.success("Cola vaciada.")
        st.rerun()


def _render_registro(usuario: str) -> None:
    st.subheader("⚙️ Registrar lote de sublimación")

    df_cola = _load_queue_df()
    usar_cola = st.checkbox("Usar datos desde la cola de CMYK", value=not df_cola.empty)

    trabajo_sel = None
    if usar_cola and not df_cola.empty:
        opciones = df_cola.index.tolist()
        idx = st.selectbox(
            "Trabajo en cola",
            options=opciones,
            format_func=lambda i: f"{df_cola.loc[i, 'producto']} · {df_cola.loc[i, 'cantidad']} uds",
        )
        trabajo_sel = df_cola.loc[idx]

    c1, c2, c3 = st.columns(3)
    producto = c1.text_input("Producto", value=_clean_text(trabajo_sel["producto"]) if trabajo_sel is not None else "")
    cliente = c2.text_input("Cliente", value=_clean_text(trabajo_sel["cliente"]) if trabajo_sel is not None else "")
    tipo_producto = c3.selectbox(
        "Tipo de producto",
        TIPOS_PRODUCTO,
        index=TIPOS_PRODUCTO.index(_clean_text(trabajo_sel["tipo_producto"])) if trabajo_sel is not None and _clean_text(trabajo_sel["tipo_producto"]) in TIPOS_PRODUCTO else len(TIPOS_PRODUCTO) - 1,
    )

    c4, c5 = st.columns(2)
    diseno = c4.text_input("Diseño / referencia", value=_clean_text(trabajo_sel["diseno"]) if trabajo_sel is not None else "")
    cantidad_programada = c5.number_input(
        "Cantidad programada",
        min_value=1.0,
        value=float(_safe_float(trabajo_sel["cantidad"], 1.0)) if trabajo_sel is not None else 1.0,
        step=1.0,
    )

    st.markdown("### Parámetros de sublimación")
    p1, p2, p3, p4 = st.columns(4)
    maquina = p1.selectbox("Máquina", MAQUINAS_DEFAULT + ["Otra"])
    temperatura_c = p2.number_input("Temperatura (°C)", min_value=0.0, value=180.0, step=1.0)
    tiempo_seg = p3.number_input("Tiempo (seg)", min_value=0.0, value=60.0, step=1.0)
    presion = p4.selectbox("Presión", PRESIONES, index=1)

    p5, p6 = st.columns(2)
    papel_tipo = p5.text_input("Tipo de papel", value="Papel sublimación")
    tinta_tipo = p6.text_input("Tipo de tinta", value="Tinta sublimación")

    st.markdown("### Costos del lote")
    total_transfer_default = float(_safe_float(trabajo_sel["costo_transfer_total"], 0.0)) if trabajo_sel is not None else 0.0
    k1, k2, k3 = st.columns(3)
    costo_transfer_total = k1.number_input("Costo transfer total USD", min_value=0.0, value=total_transfer_default, format="%.4f")
    potencia_kw = k2.number_input("Potencia máquina (kW)", min_value=0.0, value=1.5, format="%.4f")
    costo_kwh = k3.number_input("Costo kWh USD", min_value=0.0, value=0.15, format="%.4f")

    k4, k5, k6 = st.columns(3)
    minutos_unidad = k4.number_input("Minutos por unidad", min_value=0.0, value=5.0, format="%.4f")
    salario_hora = k5.number_input("Salario/hora operador", min_value=0.0, value=3.0, format="%.4f")
    unidades_hora = k6.number_input("Unidades por hora", min_value=0.1, value=12.0, format="%.4f")

    k7, k8, k9 = st.columns(3)
    valor_maquina = k7.number_input("Valor máquina USD", min_value=0.0, value=1500.0, format="%.2f")
    vida_horas = k8.number_input("Vida útil máquina (horas)", min_value=1.0, value=5000.0, format="%.2f")
    costo_indirecto_unit = k9.number_input("Costo indirecto unitario USD", min_value=0.0, value=0.0, format="%.4f")

    costos = _calc_costs(
        cantidad_total=float(cantidad_programada),
        costo_transfer_total=float(costo_transfer_total),
        potencia_kw=float(potencia_kw),
        minutos_unidad=float(minutos_unidad),
        costo_kwh=float(costo_kwh),
        salario_hora=float(salario_hora),
        unidades_hora=float(unidades_hora),
        valor_maquina=float(valor_maquina),
        vida_horas=float(vida_horas),
        costo_indirecto_unit=float(costo_indirecto_unit),
    )

    st.markdown("### Resumen de costo")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Transfer unitario", f"$ {costos['costo_transfer_unit']:.4f}")
    m2.metric("Energía unitaria", f"$ {costos['costo_energia_unit']:.4f}")
    m3.metric("Mano de obra unitaria", f"$ {costos['costo_mano_obra_unit']:.4f}")
    m4.metric("Depreciación unitaria", f"$ {costos['costo_depreciacion_unit']:.4f}")

    m5, m6 = st.columns(2)
    m5.metric("Costo unitario final", f"$ {costos['costo_unitario_final']:.4f}")
    m6.metric("Costo total final", f"$ {costos['costo_total_final']:.2f}")

    observaciones = st.text_area("Observaciones del lote")

    if st.button("✅ Registrar lote de sublimación", use_container_width=True):
        if not _clean_text(producto):
            st.error("Debes indicar el producto.")
            return

        lote_id = _registrar_lote(
            usuario=usuario,
            producto=producto,
            cliente=cliente,
            tipo_producto=tipo_producto,
            diseno=diseno,
            cantidad_programada=float(cantidad_programada),
            maquina=maquina,
            temperatura_c=float(temperatura_c),
            tiempo_seg=float(tiempo_seg),
            presion=presion,
            papel_tipo=papel_tipo,
            tinta_tipo=tinta_tipo,
            observaciones=observaciones,
            costo_transfer_total=float(costo_transfer_total),
            costos=costos,
            origen="cola_cmyk" if trabajo_sel is not None else "manual",
            referencia_origen=str(trabajo_sel.name) if trabajo_sel is not None else "",
        )

        st.success(f"Lote registrado correctamente. ID #{lote_id}")
        st.rerun()


def _render_control_produccion(usuario: str) -> None:
    st.subheader("🧪 Producción, calidad y merma")

    df_lotes = _load_lotes_df()
    if df_lotes.empty:
        st.info("No hay lotes registrados.")
        return

    lote_id = st.selectbox(
        "Selecciona lote",
        options=df_lotes["id"].tolist(),
        format_func=lambda x: f"Lote #{x} · {df_lotes.loc[df_lotes['id'] == x, 'producto'].iloc[0]}",
    )

    row = df_lotes[df_lotes["id"] == lote_id].iloc[0]

    st.markdown("### Datos del lote")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Programada", f"{float(row['cantidad_programada']):,.2f}")
    a2.metric("Costo unitario", f"$ {float(row['costo_unitario_final']):,.4f}")
    a3.metric("Estado", str(row["estado"]).title())
    a4.metric("Merma actual", f"{float(row['merma_pct']):,.2f}%")

    st.markdown("### Resultado de producción")
    r1, r2, r3, r4 = st.columns(4)
    producida = r1.number_input("Cantidad producida", min_value=0.0, value=float(row["cantidad_programada"] or 0.0), step=1.0)
    aprobada = r2.number_input("Cantidad aprobada", min_value=0.0, value=float(row["cantidad_aprobada"] or 0.0), step=1.0)
    reproceso = r3.number_input("Cantidad reproceso", min_value=0.0, value=float(row["cantidad_reproceso"] or 0.0), step=1.0)
    rechazada = r4.number_input("Cantidad rechazada", min_value=0.0, value=float(row["cantidad_rechazada"] or 0.0), step=1.0)

    merma = max(float(producida) - float(aprobada) - float(reproceso), 0.0)
    st.caption(f"Merma calculada sugerida: {merma:,.2f} unidades")

    prod_obs = st.text_area("Observaciones de producción", value=_clean_text(row["observaciones"]), key="sub_prod_obs")

    if st.button("💾 Guardar resultado de producción", use_container_width=True):
        _actualizar_resultado_lote(
            lote_id=int(lote_id),
            producida=float(producida),
            aprobada=float(aprobada),
            reproceso=float(reproceso),
            merma=float(merma),
            rechazada=float(rechazada),
            observaciones=prod_obs,
        )
        st.success("Resultado de producción actualizado.")
        st.rerun()

    st.divider()
    st.markdown("### Control de calidad")

    q1, q2, q3, q4, q5 = st.columns(5)
    color_correcto = q1.checkbox("Color correcto", value=True)
    transferencia_completa = q2.checkbox("Transferencia completa", value=True)
    sin_manchas = q3.checkbox("Sin manchas", value=True)
    sin_ghosting = q4.checkbox("Sin ghosting", value=True)
    sin_quemado = q5.checkbox("Sin quemado", value=True)

    qc_resultado = st.selectbox("Resultado calidad", RESULTADOS_CALIDAD)
    qc_obs = st.text_area("Observaciones calidad", key="sub_qc_obs")

    if st.button("✅ Registrar control de calidad", use_container_width=True):
        _registrar_control_calidad(
            lote_id=int(lote_id),
            usuario=usuario,
            color_correcto=bool(color_correcto),
            transferencia_completa=bool(transferencia_completa),
            sin_manchas=bool(sin_manchas),
            sin_ghosting=bool(sin_ghosting),
            sin_quemado=bool(sin_quemado),
            observaciones=qc_obs,
            resultado=qc_resultado,
        )
        st.success("Control de calidad registrado.")
        st.rerun()

    st.divider()
    st.markdown("### Registrar merma / desperdicio")

    mm1, mm2 = st.columns(2)
    tipo_falla = mm1.text_input("Tipo de falla", value="Falla de calor")
    cantidad_merma = mm2.number_input("Cantidad dañada", min_value=0.0, value=0.0, step=1.0)

    costo_estimado = float(cantidad_merma) * float(_safe_float(row["costo_unitario_final"], 0.0))
    st.metric("Costo estimado merma", f"$ {costo_estimado:,.2f}")

    merma_obs = st.text_area("Observaciones merma", key="sub_merma_obs")
    if st.button("♻️ Registrar merma", use_container_width=True):
        if float(cantidad_merma) <= 0:
            st.error("La cantidad de merma debe ser mayor a cero.")
            return

        _registrar_merma(
            lote_id=int(lote_id),
            usuario=usuario,
            tipo_falla=tipo_falla,
            cantidad=float(cantidad_merma),
            costo_estimado_usd=float(costo_estimado),
            observaciones=merma_obs,
        )
        st.success("Merma registrada.")
        st.rerun()


def _render_historial() -> None:
    st.subheader("📚 Historial de sublimación")

    df_lotes = _load_lotes_df()
    if df_lotes.empty:
        st.info("No hay historial todavía.")
        return

    b1, b2 = st.columns(2)
    buscar = b1.text_input("Buscar producto / cliente")
    estado = b2.selectbox("Estado", ["Todos"] + ESTADOS_LOTE)

    view = df_lotes.copy()
    if buscar:
        mask = (
            view["producto"].astype(str).str.contains(buscar, case=False, na=False)
            | view["cliente"].astype(str).str.contains(buscar, case=False, na=False)
            | view["diseno"].astype(str).str.contains(buscar, case=False, na=False)
        )
        view = view[mask]

    if estado != "Todos":
        view = view[view["estado"].astype(str).str.lower() == estado.lower()]

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad_programada": st.column_config.NumberColumn("Programada", format="%.2f"),
            "cantidad_producida": st.column_config.NumberColumn("Producida", format="%.2f"),
            "cantidad_aprobada": st.column_config.NumberColumn("Aprobada", format="%.2f"),
            "cantidad_reproceso": st.column_config.NumberColumn("Reproceso", format="%.2f"),
            "cantidad_merma": st.column_config.NumberColumn("Merma", format="%.2f"),
            "costo_unitario_final": st.column_config.NumberColumn("Costo unitario", format="%.4f"),
            "costo_total_final": st.column_config.NumberColumn("Costo total", format="%.2f"),
            "merma_pct": st.column_config.NumberColumn("Merma %", format="%.2f"),
        },
    )

    df_qc = _load_qc_df()
    if not df_qc.empty:
        st.markdown("### Controles de calidad")
        st.dataframe(df_qc, use_container_width=True, hide_index=True)

    df_mermas = _load_mermas_df()
    if not df_mermas.empty:
        st.markdown("### Mermas registradas")
        st.dataframe(df_mermas, use_container_width=True, hide_index=True)


def _render_metricas() -> None:
    st.subheader("📊 Métricas de sublimación")

    df_lotes = _load_lotes_df()
    df_mermas = _load_mermas_df()
    df_qc = _load_qc_df()

    if df_lotes.empty:
        st.info("No hay datos para métricas.")
        return

    total_lotes = len(df_lotes)
    total_programado = float(df_lotes["cantidad_programada"].sum())
    total_aprobado = float(df_lotes["cantidad_aprobada"].sum())
    total_merma = float(df_lotes["cantidad_merma"].sum())
    costo_total = float(df_lotes["costo_total_final"].sum())
    merma_pct_global = (total_merma / max(total_programado, 0.0001)) * 100.0 if total_programado > 0 else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Lotes", total_lotes)
    m2.metric("Unidades programadas", f"{total_programado:,.2f}")
    m3.metric("Unidades aprobadas", f"{total_aprobado:,.2f}")
    m4.metric("Merma global", f"{merma_pct_global:,.2f}%")
    m5.metric("Costo total", f"$ {costo_total:,.2f}")

    if not df_lotes.empty:
        por_producto = (
            df_lotes.groupby("producto", as_index=False)[["cantidad_programada", "cantidad_aprobada", "cantidad_merma", "costo_total_final"]]
            .sum()
            .sort_values("costo_total_final", ascending=False)
        )
        st.markdown("### Producción por producto")
        st.dataframe(por_producto, use_container_width=True, hide_index=True)

    if not df_mermas.empty:
        st.markdown("### Mermas por tipo de falla")
        por_falla = (
            df_mermas.groupby("tipo_falla", as_index=False)[["cantidad", "costo_estimado_usd"]]
            .sum()
            .sort_values("costo_estimado_usd", ascending=False)
        )
        st.dataframe(por_falla, use_container_width=True, hide_index=True)

    if not df_qc.empty:
        st.markdown("### Resultados de calidad")
        resumen_qc = (
            df_qc.groupby("resultado", as_index=False)["id"]
            .count()
            .rename(columns={"id": "cantidad"})
            .sort_values("cantidad", ascending=False)
        )
        st.dataframe(resumen_qc, use_container_width=True, hide_index=True)


# ============================================================
# ENTRYPOINT
# ============================================================

def render_sublimacion(usuario: str) -> None:
    _ensure_sublimacion_tables()

    st.title("🔥 Sublimación Industrial PRO")
    st.caption(f"Operador: {usuario}")

    tabs = st.tabs(
        [
            "📥 Cola",
            "⚙️ Registro de lote",
            "🧪 Producción / Calidad / Merma",
            "📚 Historial",
            "📊 Métricas",
        ]
    )

    with tabs[0]:
        _render_cola()

    with tabs[1]:
        _render_registro(usuario)

    with tabs[2]:
        _render_control_produccion(usuario)

    with tabs[3]:
        _render_historial()

    with tabs[4]:
        _render_metricas()
