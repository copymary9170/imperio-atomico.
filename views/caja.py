from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission
from utils.timezone import now_caracas
from views.cierre_caja_turnos import render_cierre_caja_turnos


METODOS_PAGO = ["efectivo", "transferencia", "pago_movil", "zelle", "binance"]


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _get_dia_abierto():
    with db_transaction() as conn:
        if not _table_exists(conn, "dias_operacion"):
            return None
        return conn.execute(
            "SELECT * FROM dias_operacion WHERE estado='abierto' ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _periodo_operativo() -> tuple[str, tuple, str]:
    dia = _get_dia_abierto()
    if dia:
        return "fecha >= ?", (dia["fecha_inicio"],), f"Día abierto desde {dia['fecha_inicio']}"
    hoy = now_caracas().strftime("%Y-%m-%d")
    return "date(fecha)=date(?)", (hoy,), f"Hoy {hoy} (sin día abierto)"


def _registrar_movimiento_tesoreria(
    *,
    tipo: str,
    origen: str,
    referencia_id: int | None,
    descripcion: str,
    monto_usd: float,
    metodo_pago: str,
    usuario: str,
    metadata: str | None = None,
) -> None:
    if metodo_pago not in METODOS_PAGO:
        raise ValueError("Método de pago no válido")
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO movimientos_tesoreria (
                fecha, tipo, origen, referencia_id, descripcion, monto_usd,
                moneda, monto_moneda, tasa_cambio, metodo_pago, usuario,
                estado, metadata
            ) VALUES (
                CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, 'USD', ?, 1, ?, ?, 'confirmado', ?
            )
            """,
            (
                tipo,
                origen,
                referencia_id,
                descripcion,
                monto_usd,
                monto_usd,
                metodo_pago,
                usuario,
                metadata,
            ),
        )


def _get_resumen_caja() -> dict:
    filtro, params, _ = _periodo_operativo()
    with db_transaction() as conn:
        row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ingresos_efectivo,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egresos_efectivo,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='transferencia' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ingresos_transferencia,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='transferencia' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egresos_transferencia,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago IN ('pago_movil','pago móvil','pagomovil') AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ingresos_pago_movil,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago IN ('pago_movil','pago móvil','pagomovil') AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egresos_pago_movil,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='zelle' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ingresos_zelle,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='zelle' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egresos_zelle,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='binance' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ingresos_binance,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='binance' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egresos_binance
            FROM movimientos_tesoreria
            WHERE {filtro}
            """,
            params,
        ).fetchone()

    campos = [
        "ingresos_efectivo", "egresos_efectivo",
        "ingresos_transferencia", "egresos_transferencia",
        "ingresos_pago_movil", "egresos_pago_movil",
        "ingresos_zelle", "egresos_zelle",
        "ingresos_binance", "egresos_binance",
    ]
    return {campo: _safe_float(row[campo]) if row else 0.0 for campo in campos}


def _get_movimientos_caja_df() -> pd.DataFrame:
    filtro, params, _ = _periodo_operativo()
    with db_transaction() as conn:
        return pd.read_sql_query(
            f"""
            SELECT fecha, tipo, origen, descripcion, monto_usd, metodo_pago, usuario, estado
            FROM movimientos_tesoreria
            WHERE {filtro}
              AND metodo_pago IN ('efectivo','transferencia','pago_movil','pago móvil','pagomovil','zelle','binance')
            ORDER BY id DESC
            LIMIT 200
            """,
            conn,
            params=params,
        )


def _get_cierres_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "dias_operacion"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT id, fecha_inicio, fecha_fin, usuario_inicio, usuario_fin, estado,
                   fondo_inicial_usd, fondo_final_usd, ventas_usd, gastos_usd,
                   caja_esperada_usd, diferencia_usd, estatus_cierre,
                   observaciones_inicio, observaciones_fin
            FROM dias_operacion
            WHERE estado='cerrado'
            ORDER BY id DESC
            LIMIT 100
            """,
            conn,
        )


def render_caja(usuario: str) -> None:
    if not require_permission("caja.view", "🚫 No tienes acceso al módulo Caja empresarial."):
        return

    puede_registrar_cobros = has_permission("caja.payment_in")
    puede_registrar_pagos = has_permission("caja.payment_out")
    dia = _get_dia_abierto()
    resumen = _get_resumen_caja()
    _, _, etiqueta_periodo = _periodo_operativo()

    st.subheader("🏦 Caja empresarial")
    st.info(
        "Caja trabaja únicamente con el periodo operativo actual. "
        "El cierre oficial del día se realiza desde Día y Caja."
    )
    st.caption(f"Periodo consultado: {etiqueta_periodo}")

    if not dia:
        st.warning("No hay un día operativo abierto. Puedes consultar hoy, pero abre el día antes de registrar movimientos.")

    saldos = {
        "Efectivo": resumen["ingresos_efectivo"] - resumen["egresos_efectivo"],
        "Transferencia": resumen["ingresos_transferencia"] - resumen["egresos_transferencia"],
        "Pago móvil": resumen["ingresos_pago_movil"] - resumen["egresos_pago_movil"],
        "Zelle": resumen["ingresos_zelle"] - resumen["egresos_zelle"],
        "Binance": resumen["ingresos_binance"] - resumen["egresos_binance"],
    }

    columnas = st.columns(5)
    for columna, (nombre, saldo) in zip(columnas, saldos.items()):
        columna.metric(nombre, f"$ {saldo:,.2f}")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["💵 Registrar cobro", "💸 Registrar pago", "🧾 Cierre por turno", "📜 Historial diario"]
    )

    with tab1:
        st.markdown("### Registrar cobro manual")
        habilitado = puede_registrar_cobros and dia is not None
        with st.form("form_caja_cobro"):
            descripcion = st.text_input(
                "Descripción del cobro",
                placeholder="Ejemplo: anticipo, ajuste positivo o cobro manual",
                disabled=not habilitado,
            )
            c1, c2 = st.columns(2)
            monto = c1.number_input("Monto USD", min_value=0.0, step=0.01, format="%.2f", disabled=not habilitado)
            metodo = c2.selectbox("Método de pago", METODOS_PAGO, disabled=not habilitado)
            guardar = st.form_submit_button("💾 Registrar cobro", disabled=not habilitado)
        if guardar:
            if not descripcion.strip():
                st.warning("Debes indicar una descripción.")
            elif monto <= 0:
                st.warning("El monto debe ser mayor a cero.")
            else:
                _registrar_movimiento_tesoreria(
                    tipo="ingreso", origen="ajuste_manual", referencia_id=None,
                    descripcion=descripcion.strip(), monto_usd=float(monto),
                    metodo_pago=metodo, usuario=usuario, metadata="caja.payment_in",
                )
                st.success("✅ Cobro registrado correctamente.")
                st.rerun()

    with tab2:
        st.markdown("### Registrar pago manual")
        habilitado = puede_registrar_pagos and dia is not None
        with st.form("form_caja_pago"):
            descripcion = st.text_input(
                "Descripción del pago",
                placeholder="Ejemplo: compra menor, retiro operativo o ajuste negativo",
                disabled=not habilitado,
            )
            c1, c2 = st.columns(2)
            monto = c1.number_input("Monto USD", min_value=0.0, step=0.01, format="%.2f", key="monto_pago_caja", disabled=not habilitado)
            metodo = c2.selectbox("Método de pago", METODOS_PAGO, key="metodo_pago_caja", disabled=not habilitado)
            guardar = st.form_submit_button("💾 Registrar pago", disabled=not habilitado)
        if guardar:
            if not descripcion.strip():
                st.warning("Debes indicar una descripción.")
            elif monto <= 0:
                st.warning("El monto debe ser mayor a cero.")
            else:
                _registrar_movimiento_tesoreria(
                    tipo="egreso", origen="ajuste_manual", referencia_id=None,
                    descripcion=descripcion.strip(), monto_usd=float(monto),
                    metodo_pago=metodo, usuario=usuario, metadata="caja.payment_out",
                )
                st.success("✅ Pago registrado correctamente.")
                st.rerun()

    with tab3:
        render_cierre_caja_turnos(usuario)

    with tab4:
        cierres = _get_cierres_df()
        if cierres.empty:
            st.info("Aún no hay días cerrados.")
        else:
            st.dataframe(cierres, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📋 Movimientos del periodo")
    movimientos = _get_movimientos_caja_df()
    if movimientos.empty:
        st.info("No hay movimientos registrados en este periodo.")
    else:
        st.dataframe(movimientos, use_container_width=True, hide_index=True)
