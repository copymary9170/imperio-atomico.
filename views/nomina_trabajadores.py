from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.rrhh_service import RRHHService

ESTADOS_NOMINA = ["Pendiente", "Aprobada", "Pagada", "Cancelada"]
TIPOS_MOVIMIENTO = ["Bono", "Hora extra", "Comisión", "Deducción", "Descuento", "Ajuste"]


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_tables() -> None:
    RRHHService()  # asegura empleados/asistencia/solicitudes
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nomina_configuracion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL UNIQUE,
                pago_base_usd REAL NOT NULL DEFAULT 0,
                seguro_usd REAL NOT NULL DEFAULT 0,
                pension_usd REAL NOT NULL DEFAULT 0,
                otros_beneficios_usd REAL NOT NULL DEFAULT 0,
                modalidad TEXT NOT NULL DEFAULT 'Mensual',
                estado TEXT NOT NULL DEFAULT 'Activa',
                observaciones TEXT,
                updated_by TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nomina_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL,
                periodo TEXT NOT NULL,
                tipo TEXT NOT NULL,
                concepto TEXT NOT NULL,
                monto_usd REAL NOT NULL DEFAULT 0,
                aprobado INTEGER NOT NULL DEFAULT 0,
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nomina_cierres (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo TEXT NOT NULL,
                empleado_id INTEGER NOT NULL,
                pago_base_usd REAL NOT NULL DEFAULT 0,
                seguro_usd REAL NOT NULL DEFAULT 0,
                pension_usd REAL NOT NULL DEFAULT 0,
                beneficios_usd REAL NOT NULL DEFAULT 0,
                extras_usd REAL NOT NULL DEFAULT 0,
                deducciones_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                usuario TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (periodo, empleado_id),
                FOREIGN KEY (empleado_id) REFERENCES empleados(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nomina_mov_periodo ON nomina_movimientos(periodo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nomina_cierres_periodo ON nomina_cierres(periodo)")


def _empleados_df(estado: str | None = None) -> pd.DataFrame:
    _ensure_tables()
    service = RRHHService()
    empleados = service.listar_empleados(estado=estado)
    return pd.DataFrame(empleados)


def _read_sql(sql: str, params: tuple = ()) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _periodo_actual() -> str:
    return date.today().strftime("%Y-%m")


def _guardar_config(empleado_id: int, pago_base: float, seguro: float, pension: float, beneficios: float, modalidad: str, estado: str, observaciones: str, usuario: str) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO nomina_configuracion (
                empleado_id, pago_base_usd, seguro_usd, pension_usd, otros_beneficios_usd,
                modalidad, estado, observaciones, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(empleado_id) DO UPDATE SET
                pago_base_usd=excluded.pago_base_usd,
                seguro_usd=excluded.seguro_usd,
                pension_usd=excluded.pension_usd,
                otros_beneficios_usd=excluded.otros_beneficios_usd,
                modalidad=excluded.modalidad,
                estado=excluded.estado,
                observaciones=excluded.observaciones,
                updated_by=excluded.updated_by,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(empleado_id), float(pago_base), float(seguro), float(pension), float(beneficios), modalidad, estado, observaciones, usuario),
        )


def _guardar_movimiento(empleado_id: int, periodo: str, tipo: str, concepto: str, monto: float, aprobado: bool, usuario: str) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO nomina_movimientos (empleado_id, periodo, tipo, concepto, monto_usd, aprobado, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(empleado_id), periodo, tipo, concepto, float(monto), 1 if aprobado else 0, usuario),
        )
        return int(cur.lastrowid)


def _nomina_calculada(periodo: str) -> pd.DataFrame:
    _ensure_tables()
    empleados = _empleados_df("activo")
    if empleados.empty:
        return pd.DataFrame()
    configs = _read_sql("SELECT * FROM nomina_configuracion")
    movimientos = _read_sql("SELECT * FROM nomina_movimientos WHERE periodo=? AND aprobado=1", (periodo,))

    df = empleados.merge(configs, left_on="id", right_on="empleado_id", how="left", suffixes=("", "_nomina"))
    for col in ["pago_base_usd", "seguro_usd", "pension_usd", "otros_beneficios_usd"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["modalidad"] = df.get("modalidad", "Mensual").fillna("Mensual") if "modalidad" in df.columns else "Mensual"
    df["estado_nomina"] = df.get("estado_nomina", df.get("estado", "Activa")).fillna("Activa") if "estado_nomina" in df.columns else "Activa"

    extras = []
    if not movimientos.empty:
        mov = movimientos.copy()
        mov["monto_usd"] = pd.to_numeric(mov["monto_usd"], errors="coerce").fillna(0.0)
        mov["signo"] = mov["tipo"].isin(["Deducción", "Descuento"]).map({True: -1, False: 1})
        mov["monto_firmado"] = mov["monto_usd"] * mov["signo"]
        resumen = mov.groupby("empleado_id", as_index=False).agg(
            extras_usd=("monto_firmado", lambda s: float(s[s > 0].sum())),
            deducciones_usd=("monto_firmado", lambda s: abs(float(s[s < 0].sum()))),
            ajuste_neto_usd=("monto_firmado", "sum"),
        )
        df = df.merge(resumen, left_on="id", right_on="empleado_id", how="left", suffixes=("", "_mov"))
    for col in ["extras_usd", "deducciones_usd", "ajuste_neto_usd"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["total_usd"] = df["pago_base_usd"] + df["seguro_usd"] + df["pension_usd"] + df["otros_beneficios_usd"] + df["extras_usd"] - df["deducciones_usd"]
    cols = [
        "id", "nombre", "documento", "puesto", "area", "estado", "pago_base_usd", "seguro_usd",
        "pension_usd", "otros_beneficios_usd", "extras_usd", "deducciones_usd", "total_usd", "modalidad"
    ]
    return df[[c for c in cols if c in df.columns]].rename(columns={"id": "empleado_id", "estado": "estado_empleado"})


def _cerrar_nomina(periodo: str, usuario: str) -> int:
    df = _nomina_calculada(periodo)
    if df.empty:
        return 0
    with db_transaction() as conn:
        count = 0
        for _, row in df.iterrows():
            conn.execute(
                """
                INSERT INTO nomina_cierres (
                    periodo, empleado_id, pago_base_usd, seguro_usd, pension_usd, beneficios_usd,
                    extras_usd, deducciones_usd, total_usd, estado, usuario
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
                ON CONFLICT(periodo, empleado_id) DO UPDATE SET
                    pago_base_usd=excluded.pago_base_usd,
                    seguro_usd=excluded.seguro_usd,
                    pension_usd=excluded.pension_usd,
                    beneficios_usd=excluded.beneficios_usd,
                    extras_usd=excluded.extras_usd,
                    deducciones_usd=excluded.deducciones_usd,
                    total_usd=excluded.total_usd,
                    usuario=excluded.usuario
                """,
                (
                    periodo,
                    int(row["empleado_id"]),
                    float(row.get("pago_base_usd", 0)),
                    float(row.get("seguro_usd", 0)),
                    float(row.get("pension_usd", 0)),
                    float(row.get("otros_beneficios_usd", 0)),
                    float(row.get("extras_usd", 0)),
                    float(row.get("deducciones_usd", 0)),
                    float(row.get("total_usd", 0)),
                    usuario,
                ),
            )
            count += 1
    return count


def _render_resumen(periodo: str) -> None:
    st.subheader("📊 Resumen de nómina")
    empleados = _empleados_df("activo")
    df = _nomina_calculada(periodo)
    configs = _read_sql("SELECT * FROM nomina_configuracion")
    sin_config = 0 if empleados.empty else len(set(empleados["id"].astype(int)) - set(configs["empleado_id"].astype(int))) if not configs.empty else len(empleados)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trabajadores activos", len(empleados))
    c2.metric("Sin salario configurado", sin_config)
    c3.metric("Seguro + pensión", f"${(df['seguro_usd'].sum() + df['pension_usd'].sum()) if not df.empty else 0:,.2f}")
    c4.metric("Total mensual", f"${df['total_usd'].sum() if not df.empty else 0:,.2f}")
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay empleados activos para calcular nómina.")


def _render_trabajadores() -> None:
    st.subheader("👥 Trabajadores / empleados")
    st.caption("La fuente oficial de trabajadores es RRHH. Este módulo no duplica empleados.")
    df = _empleados_df()
    if df.empty:
        st.warning("No hay empleados registrados. Regístralos en RRHH primero.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_configuracion(usuario: str) -> None:
    st.subheader("💵 Configuración salarial")
    empleados = _empleados_df("activo")
    if empleados.empty:
        st.warning("No hay empleados activos.")
        return
    opciones = {f"#{r.id} · {r.nombre} · {r.puesto}": int(r.id) for r in empleados.itertuples()}
    configs = _read_sql("SELECT * FROM nomina_configuracion")
    empleado_label = st.selectbox("Empleado", list(opciones.keys()), key="nomina_config_empleado")
    empleado_id = opciones[empleado_label]
    actual = configs[configs["empleado_id"].eq(empleado_id)].iloc[0].to_dict() if not configs.empty and empleado_id in configs["empleado_id"].tolist() else {}
    with st.form("nomina_config_form"):
        a, b, c, d = st.columns(4)
        pago_base = a.number_input("Pago base USD", min_value=0.0, value=float(actual.get("pago_base_usd", 0) or 0), step=1.0)
        seguro = b.number_input("Seguro USD", min_value=0.0, value=float(actual.get("seguro_usd", 0) or 0), step=1.0)
        pension = c.number_input("Pensión USD", min_value=0.0, value=float(actual.get("pension_usd", 0) or 0), step=1.0)
        beneficios = d.number_input("Otros beneficios USD", min_value=0.0, value=float(actual.get("otros_beneficios_usd", 0) or 0), step=1.0)
        e, f = st.columns(2)
        modalidad = e.selectbox("Modalidad", ["Mensual", "Quincenal", "Semanal", "Por hora", "Por producción"], index=0)
        estado = f.selectbox("Estado nómina", ["Activa", "Pausada", "Inactiva"], index=0)
        observaciones = st.text_area("Observaciones", value=str(actual.get("observaciones", "") or ""))
        guardar = st.form_submit_button("Guardar configuración", type="primary")
    if guardar:
        _guardar_config(empleado_id, pago_base, seguro, pension, beneficios, modalidad, estado, observaciones, usuario)
        st.success("Configuración salarial guardada.")
        st.rerun()
    if not configs.empty:
        st.markdown("#### Configuraciones actuales")
        st.dataframe(configs.merge(empleados, left_on="empleado_id", right_on="id", how="left"), use_container_width=True, hide_index=True)


def _render_movimientos(periodo: str, usuario: str) -> None:
    st.subheader("➕ Extras / bonos / deducciones")
    empleados = _empleados_df("activo")
    if empleados.empty:
        st.warning("No hay empleados activos.")
        return
    opciones = {f"#{r.id} · {r.nombre}": int(r.id) for r in empleados.itertuples()}
    with st.form("nomina_mov_form"):
        a, b, c = st.columns(3)
        empleado_label = a.selectbox("Empleado", list(opciones.keys()))
        tipo = b.selectbox("Tipo", TIPOS_MOVIMIENTO)
        monto = c.number_input("Monto USD", min_value=0.0, value=0.0, step=1.0)
        concepto = st.text_input("Concepto", placeholder="Bono por meta, descuento, comisión...")
        aprobado = st.checkbox("Aprobado para nómina", value=True)
        guardar = st.form_submit_button("Guardar movimiento", type="primary")
    if guardar:
        if not concepto.strip() or monto <= 0:
            st.error("Concepto y monto son obligatorios.")
        else:
            mid = _guardar_movimiento(opciones[empleado_label], periodo, tipo, concepto.strip(), monto, aprobado, usuario)
            st.success(f"Movimiento #{mid} guardado.")
            st.rerun()
    movs = _read_sql("SELECT * FROM nomina_movimientos WHERE periodo=? ORDER BY id DESC", (periodo,))
    if movs.empty:
        st.info("No hay movimientos para este periodo.")
    else:
        st.dataframe(movs.merge(empleados, left_on="empleado_id", right_on="id", how="left"), use_container_width=True, hide_index=True)


def _render_nomina_mensual(periodo: str, usuario: str) -> None:
    st.subheader("🧾 Nómina mensual")
    df = _nomina_calculada(periodo)
    if df.empty:
        st.warning("No hay nómina calculable.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Exportar nómina CSV", data=df.to_csv(index=False).encode("utf-8-sig"), file_name=f"nomina_{periodo}.csv", mime="text/csv", use_container_width=True)
    if c2.button("Cerrar / generar nómina del periodo", type="primary", use_container_width=True, key="nomina_cerrar_periodo"):
        count = _cerrar_nomina(periodo, usuario)
        st.success(f"Nómina generada para {count} trabajadores.")
    cierres = _read_sql("SELECT * FROM nomina_cierres WHERE periodo=? ORDER BY id DESC", (periodo,))
    if not cierres.empty:
        st.markdown("#### Cierres generados")
        st.dataframe(cierres, use_container_width=True, hide_index=True)


def _render_alertas(periodo: str) -> None:
    st.subheader("🚨 Alertas de nómina")
    empleados = _empleados_df("activo")
    configs = _read_sql("SELECT * FROM nomina_configuracion")
    cierres = _read_sql("SELECT * FROM nomina_cierres WHERE periodo=?", (periodo,))
    movs_pend = _read_sql("SELECT * FROM nomina_movimientos WHERE periodo=? AND aprobado=0", (periodo,))
    alertas = []
    sin_config = pd.DataFrame()
    if not empleados.empty:
        configurados = set(configs["empleado_id"].astype(int)) if not configs.empty else set()
        sin_config = empleados[~empleados["id"].astype(int).isin(configurados)]
        if not sin_config.empty:
            alertas.append({"nivel": "Alta", "alerta": "Empleados activos sin configuración salarial", "cantidad": len(sin_config), "acción": "Configurar pago base, seguro y pensión."})
    if cierres.empty and not empleados.empty:
        alertas.append({"nivel": "Media", "alerta": "Nómina del periodo sin cerrar", "cantidad": 1, "acción": "Generar nómina mensual."})
    if not movs_pend.empty:
        alertas.append({"nivel": "Media", "alerta": "Extras/deducciones sin aprobar", "cantidad": len(movs_pend), "acción": "Aprobar o descartar movimientos."})
    if not configs.empty:
        sin_beneficios = configs[(pd.to_numeric(configs["seguro_usd"], errors="coerce").fillna(0) <= 0) & (pd.to_numeric(configs["pension_usd"], errors="coerce").fillna(0) <= 0)]
        if not sin_beneficios.empty:
            alertas.append({"nivel": "Baja", "alerta": "Empleados sin seguro/pensión configurados", "cantidad": len(sin_beneficios), "acción": "Verificar si aplica beneficio."})
    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas de nómina.")
    tabs = st.tabs(["Sin configuración", "Movimientos sin aprobar", "Cierres"])
    with tabs[0]:
        st.dataframe(sin_config, use_container_width=True, hide_index=True) if not sin_config.empty else st.success("Sin pendientes.")
    with tabs[1]:
        st.dataframe(movs_pend, use_container_width=True, hide_index=True) if not movs_pend.empty else st.success("Sin pendientes.")
    with tabs[2]:
        st.dataframe(cierres, use_container_width=True, hide_index=True) if not cierres.empty else st.info("No hay cierre para este periodo.")


def render_nomina_trabajadores(usuario="Sistema"):
    _ensure_tables()
    st.title("👨‍💼 Nómina y trabajadores")
    st.caption(f"Usuario activo: {usuario}. Empleados conectados desde RRHH; nómina, beneficios, extras y deducciones calculados aquí.")
    periodo = st.text_input("Periodo de nómina", value=_periodo_actual(), key="nomina_periodo")
    secciones = {
        "📊 Resumen nómina": lambda: _render_resumen(periodo),
        "👥 Trabajadores / Empleados": _render_trabajadores,
        "💵 Configuración salarial": lambda: _render_configuracion(usuario),
        "➕ Extras / Bonos / Deducciones": lambda: _render_movimientos(periodo, usuario),
        "🧾 Nómina mensual": lambda: _render_nomina_mensual(periodo, usuario),
        "🚨 Alertas nómina": lambda: _render_alertas(periodo),
    }
    seccion = st.radio("Sección de nómina", list(secciones.keys()), horizontal=True, key="nomina_seccion_activa")
    st.divider()
    secciones[seccion]()
