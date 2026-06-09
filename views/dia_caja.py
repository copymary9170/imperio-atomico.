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


def _get_dia_abierto():
    _ensure_dia_tables()
    with db_transaction() as conn:
        return conn.execute(
            """
            SELECT * FROM dias_operacion
            WHERE estado = 'abierto'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


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
    return {key: _safe_float(row[key]) if row else 0.0 for key in [
        "ingresos", "egresos", "ingreso_efectivo", "egreso_efectivo", "ingreso_transferencia", "ingreso_zelle", "ingreso_binance"
    ]}


def _get_movimientos_df() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(
                """
                SELECT fecha, tipo, origen, descripcion, monto_usd, metodo_pago, usuario, estado
                FROM movimientos_tesoreria
                ORDER BY id DESC
                LIMIT 120
                """,
                conn,
            )
    except Exception:
        return pd.DataFrame()


def _get_dias_df() -> pd.DataFrame:
    _ensure_dia_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_inicio, fecha_fin, usuario_inicio, usuario_fin, estado, fondo_inicial_usd, fondo_final_usd, observaciones_inicio, observaciones_fin
            FROM dias_operacion
            ORDER BY id DESC
            LIMIT 80
            """,
            conn,
        )


def _iniciar_dia(usuario: str, fondo_inicial: float, observaciones: str) -> None:
    _ensure_dia_tables()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO dias_operacion (usuario_inicio, estado, fondo_inicial_usd, observaciones_inicio)
            VALUES (?, 'abierto', ?, ?)
            """,
            (usuario, fondo_inicial, observaciones),
        )


def _finalizar_dia(usuario: str, fondo_final: float, observaciones: str) -> None:
    dia = _get_dia_abierto()
    if not dia:
        return
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE dias_operacion
            SET estado='cerrado', fecha_fin=CURRENT_TIMESTAMP, usuario_fin=?, fondo_final_usd=?, observaciones_fin=?
            WHERE id=?
            """,
            (usuario, fondo_final, observaciones, dia["id"]),
        )


def render_dia_caja(usuario: str) -> None:
    st.title("🌅 Día / Caja")
    st.caption("Ventana diaria para iniciar operación, revisar fondos, controlar caja y finalizar el día.")

    dia = _get_dia_abierto()
    resumen = _get_resumen_operacion()
    saldo_efectivo = resumen["ingreso_efectivo"] - resumen["egreso_efectivo"]
    saldo_total = resumen["ingresos"] - resumen["egresos"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estado del día", "Abierto" if dia else "Cerrado")
    c2.metric("Fondo inicial", f"$ {_safe_float(dia['fondo_inicial_usd']) if dia else 0:,.2f}")
    c3.metric("Saldo efectivo", f"$ {saldo_efectivo:,.2f}")
    c4.metric("Operación acumulada", f"$ {saldo_total:,.2f}")

    tab_inicio, tab_operacion, tab_valores, tab_cajon, tab_fin = st.tabs([
        "🌅 Iniciar día",
        "🏦 Caja / Fondos / Operación",
        "📊 Valores acumulados",
        "💵 Cajón de dinero",
        "🌙 Finalizar día",
    ])

    with tab_inicio:
        st.subheader("🌅 Iniciar día")
        if dia:
            st.success(f"Ya hay un día abierto desde {dia['fecha_inicio']} por {dia['usuario_inicio']}.")
        else:
            fondo = st.number_input("Fondo inicial en caja USD", min_value=0.0, step=0.25, format="%.2f")
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
        st.caption("Movimientos recientes de tesorería/caja.")
        df = _get_movimientos_df()
        if df.empty:
            st.info("No hay movimientos registrados todavía.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_valores:
        st.subheader("📊 Valores acumulados")
        a1, a2, a3 = st.columns(3)
        a1.metric("Ingresos acumulados", f"$ {resumen['ingresos']:,.2f}")
        a2.metric("Egresos acumulados", f"$ {resumen['egresos']:,.2f}")
        a3.metric("Saldo operativo", f"$ {saldo_total:,.2f}")
        st.markdown("#### Historial de días")
        dias_df = _get_dias_df()
        st.dataframe(dias_df, use_container_width=True, hide_index=True)

    with tab_cajon:
        st.subheader("💵 Abrir cajón de dinero")
        st.info("Este botón registra la acción visualmente. Para abrir un cajón físico real se necesita integración con impresora POS o hardware compatible.")
        motivo = st.text_input("Motivo de apertura", placeholder="Cambio, cobro en efectivo, revisión de fondo...")
        if st.button("Abrir cajón de dinero", use_container_width=True):
            st.success(f"Solicitud de apertura registrada. Motivo: {motivo or 'Sin motivo indicado'}")

    with tab_fin:
        st.subheader("🌙 Finalizar día")
        if not dia:
            st.warning("No hay un día abierto para finalizar.")
        else:
            fondo_final = st.number_input("Fondo final contado USD", min_value=0.0, step=0.25, format="%.2f", value=float(max(saldo_efectivo, 0)))
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
