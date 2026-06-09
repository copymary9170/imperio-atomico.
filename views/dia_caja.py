from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _ensure_dia_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dias_operacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_inicio TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_fin TEXT,
                usuario_inicio TEXT,
                usuario_fin TEXT,
                estado TEXT NOT NULL DEFAULT 'abierto',
                fondo_inicial_usd REAL DEFAULT 0,
                fondo_final_usd REAL DEFAULT 0,
                observaciones_inicio TEXT,
                observaciones_fin TEXT
            )
            """
        )


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _get_dia_abierto():
    _ensure_dia_tables()
    with db_transaction() as conn:
        return conn.execute("SELECT * FROM dias_operacion WHERE estado='abierto' ORDER BY id DESC LIMIT 1").fetchone()


def _get_resumen_operacion() -> dict:
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN tipo = 'ingreso' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingresos,
                SUM(CASE WHEN tipo = 'egreso' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egresos,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'efectivo' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingreso_efectivo,
                SUM(CASE WHEN tipo = 'egreso' AND metodo_pago = 'efectivo' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egreso_efectivo,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'transferencia' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingreso_transferencia,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'zelle' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingreso_zelle,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'binance' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingreso_binance
            FROM movimientos_tesoreria
            """
        ).fetchone()
    return {key: _safe_float(row[key]) if row else 0.0 for key in ["ingresos", "egresos", "ingreso_efectivo", "egreso_efectivo", "ingreso_transferencia", "ingreso_zelle", "ingreso_binance"]}


def _get_config_rates() -> dict:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "configuracion"):
                return {"bcv": 0.0, "binance": 0.0}
            rows = conn.execute("SELECT parametro, valor FROM configuracion WHERE parametro IN ('tasa_bcv','tasa_binance')").fetchall()
        data = {r["parametro"]: _safe_float(r["valor"]) for r in rows}
        return {"bcv": data.get("tasa_bcv", 0.0), "binance": data.get("tasa_binance", 0.0)}
    except Exception:
        return {"bcv": 0.0, "binance": 0.0}


def _count_table(table: str, where: str | None = None) -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0
            sql = f"SELECT COUNT(*) AS total FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return 0


def _safe_query(sql: str, table: str) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def _ventas_por_hora() -> pd.DataFrame:
    return _safe_query("""
        SELECT strftime('%H:00', fecha) AS hora, SUM(monto_usd) AS ventas_usd
        FROM movimientos_tesoreria
        WHERE tipo='ingreso' AND estado='confirmado' AND date(fecha)=date('now')
        GROUP BY strftime('%H', fecha)
        ORDER BY hora
    """, "movimientos_tesoreria")


def _top_productos() -> pd.DataFrame:
    return _safe_query("""
        SELECT descripcion AS producto, COUNT(*) AS veces, SUM(monto_usd) AS total_usd
        FROM movimientos_tesoreria
        WHERE tipo='ingreso' AND estado='confirmado' AND date(fecha)=date('now')
        GROUP BY descripcion
        ORDER BY total_usd DESC
        LIMIT 10
    """, "movimientos_tesoreria")


def _ultimas_ventas() -> pd.DataFrame:
    return _safe_query("""
        SELECT fecha, descripcion, monto_usd, metodo_pago, usuario
        FROM movimientos_tesoreria
        WHERE tipo='ingreso'
        ORDER BY id DESC
        LIMIT 10
    """, "movimientos_tesoreria")


def _ultimos_clientes() -> pd.DataFrame:
    return _safe_query("""
        SELECT * FROM clientes
        ORDER BY id DESC
        LIMIT 10
    """, "clientes")


def _inventario_bajo() -> pd.DataFrame:
    return _safe_query("""
        SELECT * FROM inventario
        WHERE COALESCE(stock_actual, 0) <= COALESCE(stock_minimo, 0)
        ORDER BY stock_actual ASC
        LIMIT 15
    """, "inventario")


def _get_movimientos_df() -> pd.DataFrame:
    return _safe_query("""
        SELECT fecha, tipo, origen, descripcion, monto_usd, metodo_pago, usuario, estado
        FROM movimientos_tesoreria
        ORDER BY id DESC
        LIMIT 120
    """, "movimientos_tesoreria")


def _get_dias_df() -> pd.DataFrame:
    _ensure_dia_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT id, fecha_inicio, fecha_fin, usuario_inicio, usuario_fin, estado, fondo_inicial_usd, fondo_final_usd, observaciones_inicio, observaciones_fin FROM dias_operacion ORDER BY id DESC LIMIT 80", conn)


def _iniciar_dia(usuario: str, fondo_inicial: float, observaciones: str) -> None:
    _ensure_dia_tables()
    with db_transaction() as conn:
        conn.execute("INSERT INTO dias_operacion (usuario_inicio, estado, fondo_inicial_usd, observaciones_inicio) VALUES (?, 'abierto', ?, ?)", (usuario, fondo_inicial, observaciones))


def _finalizar_dia(usuario: str, fondo_final: float, observaciones: str) -> None:
    dia = _get_dia_abierto()
    if not dia:
        return
    with db_transaction() as conn:
        conn.execute("UPDATE dias_operacion SET estado='cerrado', fecha_fin=CURRENT_TIMESTAMP, usuario_fin=?, fondo_final_usd=?, observaciones_fin=? WHERE id=?", (usuario, fondo_final, observaciones, dia["id"]))


def _pos_status(diferencia: float) -> tuple[str, str]:
    abs_diff = abs(diferencia)
    if abs_diff <= 0.01:
        return "🟢", "Caja cuadrada"
    if abs_diff <= 1.0:
        return "🟡", "Diferencia menor"
    return "🔴", "Revisar caja"


def render_dia_caja(usuario: str) -> None:
    st.markdown("""
        <style>
            .pos-hero {border-radius:28px;padding:1.35rem 1.45rem;background:linear-gradient(135deg,#071f3a,#0f4c81 55%,#20b8b8);color:white;box-shadow:0 18px 45px rgba(15,76,129,.22);margin-bottom:1rem;}
            .pos-title {font-size:1.45rem;font-weight:950;letter-spacing:-.03em;}
            .pos-time {font-size:2.65rem;font-weight:950;letter-spacing:-.06em;line-height:1;margin-top:.35rem;}
            .pos-sub {opacity:.86;font-size:.9rem;margin-top:.35rem;}
            .pos-pill {display:inline-block;padding:.45rem .75rem;border-radius:999px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.2);font-weight:800;margin-top:.35rem;}
            .quick-title {font-weight:850;color:#334155;margin:.3rem 0 .4rem;}
        </style>
    """, unsafe_allow_html=True)

    dia = _get_dia_abierto()
    resumen = _get_resumen_operacion()
    rates = _get_config_rates()
    fondo_inicial = _safe_float(dia["fondo_inicial_usd"]) if dia else 0.0
    ventas_dia = resumen["ingresos"]
    gastos_dia = resumen["egresos"]
    saldo_efectivo = resumen["ingreso_efectivo"] - resumen["egreso_efectivo"]
    caja_esperada = fondo_inicial + saldo_efectivo
    now = datetime.now()
    estado_turno = "Abierto" if dia else "Cerrado"

    st.markdown(f"""
        <div class="pos-hero">
            <div class="pos-title">🖨️ Copy Mary · Centro de operaciones</div>
            <div class="pos-time">{now.strftime('%I:%M %p')}</div>
            <div class="pos-sub">{now.strftime('%d/%m/%Y')} · BCV {rates['bcv']:.2f} Bs/$ · Binance {rates['binance']:.2f} Bs/$</div>
            <div class="pos-pill">Turno: {estado_turno}</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="quick-title">Accesos rápidos</div>', unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    if q1.button("💰 Nueva venta", use_container_width=True):
        st.session_state["menu_principal_superior"] = "💰 Ventas"
        st.rerun()
    if q2.button("📝 Nueva cotización", use_container_width=True):
        st.session_state["menu_principal_superior"] = "📝 Cotizaciones"
        st.rerun()
    if q3.button("👥 Cliente", use_container_width=True):
        st.session_state["menu_principal_superior"] = "👥 Clientes"
        st.rerun()
    q4.button("💵 Abrir cajón", use_container_width=True)

    st.divider()
    st.markdown("### Estado de caja")
    caja_contada = st.number_input("Caja contada USD", min_value=0.0, step=0.25, format="%.2f", value=float(max(caja_esperada, 0)))
    diferencia = caja_contada - caja_esperada
    semaforo, semaforo_texto = _pos_status(diferencia)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Estado del turno", estado_turno)
    k2.metric("Fondo inicial", f"$ {fondo_inicial:,.2f}")
    k3.metric("Ventas del día", f"$ {ventas_dia:,.2f}")
    k4.metric("Gastos del día", f"$ {gastos_dia:,.2f}")
    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Caja esperada", f"$ {caja_esperada:,.2f}")
    k6.metric("Caja contada", f"$ {caja_contada:,.2f}")
    k7.metric("Diferencia", f"$ {diferencia:,.2f}")
    k8.metric("Semáforo", f"{semaforo} {semaforo_texto}")

    st.markdown("### Operación del día")
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Ventas en Bs BCV", f"Bs {ventas_dia * rates['bcv']:,.2f}")
    o2.metric("Órdenes en producción", _count_table("ordenes_trabajo", "estado NOT IN ('Finalizada','Cerrada','Cancelada','Entregada')"))
    o3.metric("Cotizaciones pendientes", _count_table("cotizaciones", "estado NOT IN ('Aprobada','Rechazada','Vencida','Cerrada')"))
    o4.metric("Clientes atendidos", _count_table("ventas", "date(fecha)=date('now')"))

    ventas_hora = _ventas_por_hora()
    if not ventas_hora.empty:
        st.markdown("#### Ventas por hora")
        st.bar_chart(ventas_hora.set_index("hora"))

    st.markdown("### Resumen comercial")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🏆 Productos / servicios más vendidos hoy")
        top = _top_productos()
        st.dataframe(top, use_container_width=True, hide_index=True) if not top.empty else st.info("Aún no hay ventas registradas hoy.")
    with c2:
        st.markdown("#### ⚠️ Alertas de inventario bajo")
        bajo = _inventario_bajo()
        st.dataframe(bajo, use_container_width=True, hide_index=True) if not bajo.empty else st.success("No hay inventario bajo detectado.")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("#### 🧾 Últimas 10 ventas")
        ult = _ultimas_ventas()
        st.dataframe(ult, use_container_width=True, hide_index=True) if not ult.empty else st.info("No hay ventas recientes.")
    with c4:
        st.markdown("#### 👥 Últimos clientes registrados")
        cli = _ultimos_clientes()
        st.dataframe(cli, use_container_width=True, hide_index=True) if not cli.empty else st.info("No hay clientes recientes.")

    tab_inicio, tab_operacion, tab_valores, tab_cajon, tab_fin = st.tabs(["🌅 Iniciar día", "🏦 Caja / Fondos / Operación", "📊 Valores acumulados", "💵 Cajón de dinero", "🌙 Finalizar día"])

    with tab_inicio:
        st.subheader("🌅 Iniciar día")
        if dia:
            st.success(f"Ya hay un día abierto desde {dia['fecha_inicio']} por {dia['usuario_inicio']}.")
        else:
            fondo = st.number_input("Fondo inicial en caja USD", min_value=0.0, step=0.25, format="%.2f", key="fondo_inicio_pos")
            obs = st.text_area("Observaciones de apertura", placeholder="Ejemplo: fondo inicial entregado, efectivo disponible, novedades...")
            if st.button("Iniciar día", type="primary", use_container_width=True):
                _iniciar_dia(usuario, fondo, obs)
                st.success("Día iniciado correctamente.")
                st.rerun()

    with tab_operacion:
        st.subheader("🏦 Caja / Fondos / Operación")
        cols = st.columns(4)
        cols[0].metric("Efectivo", f"$ {saldo_efectivo:,.2f}")
        cols[1].metric("Transferencia", f"$ {resumen['ingreso_transferencia']:,.2f}")
        cols[2].metric("Zelle", f"$ {resumen['ingreso_zelle']:,.2f}")
        cols[3].metric("Binance", f"$ {resumen['ingreso_binance']:,.2f}")
        df = _get_movimientos_df()
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay movimientos registrados todavía.")

    with tab_valores:
        st.subheader("📊 Valores acumulados")
        st.dataframe(_get_dias_df(), use_container_width=True, hide_index=True)

    with tab_cajon:
        st.subheader("💵 Abrir cajón de dinero")
        st.info("Este botón registra la acción visualmente. Para abrir un cajón físico real se necesita integración con impresora POS o hardware compatible.")
        motivo = st.text_input("Motivo de apertura", placeholder="Cambio, cobro en efectivo, revisión de fondo...")
        if st.button("Abrir cajón de dinero", use_container_width=True, key="abrir_cajon_tab"):
            st.success(f"Solicitud de apertura registrada. Motivo: {motivo or 'Sin motivo indicado'}")

    with tab_fin:
        st.subheader("🌙 Finalizar día")
        if not dia:
            st.warning("No hay un día abierto para finalizar.")
        else:
            fondo_final = st.number_input("Fondo final contado USD", min_value=0.0, step=0.25, format="%.2f", value=float(max(caja_contada, 0)), key="fondo_final_pos")
            obs_fin = st.text_area("Observaciones de cierre", placeholder="Ejemplo: diferencia de caja, efectivo entregado, cierre normal...")
            if st.button("Finalizar día", type="primary", use_container_width=True):
                _finalizar_dia(usuario, fondo_final, obs_fin)
                st.success("Día finalizado correctamente.")
                st.rerun()
        st.divider()
        st.subheader("🚪 Cerrar programa")
        if st.button("Cerrar sesión / salir del sistema", use_container_width=True):
            snapshot_path = Path(__file__).resolve().parents[1] / "data" / "session_snapshot.json"
            try:
                snapshot_path.unlink(missing_ok=True)
            except Exception:
                pass
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
