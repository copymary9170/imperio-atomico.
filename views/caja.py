from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission


METODOS_PAGO = ["efectivo", "transferencia", "zelle", "binance"]


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


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
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO movimientos_tesoreria (
                fecha,
                tipo,
                origen,
                referencia_id,
                descripcion,
                monto_usd,
                moneda,
                monto_moneda,
                tasa_cambio,
                metodo_pago,
                usuario,
                estado,
                metadata
            )
            VALUES (
                CURRENT_TIMESTAMP,
                ?, ?, ?, ?, ?,
                'USD',
                ?, 1,
                ?, ?, 'confirmado', ?
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


def _get_movimientos_caja_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                fecha,
                tipo,
                origen,
                descripcion,
                monto_usd,
                metodo_pago,
                usuario,
                estado
            FROM movimientos_tesoreria
            WHERE metodo_pago IN ('efectivo', 'transferencia', 'zelle', 'binance')
            ORDER BY id DESC
            LIMIT 200
            """,
            conn,
        )


def _get_resumen_caja() -> dict:
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'efectivo' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingresos_efectivo,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'transferencia' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingresos_transferencia,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'zelle' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingresos_zelle,
                SUM(CASE WHEN tipo = 'ingreso' AND metodo_pago = 'binance' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS ingresos_binance,
                SUM(CASE WHEN tipo = 'egreso' AND metodo_pago = 'efectivo' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egresos_efectivo,
                SUM(CASE WHEN tipo = 'egreso' AND metodo_pago = 'transferencia' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egresos_transferencia,
                SUM(CASE WHEN tipo = 'egreso' AND metodo_pago = 'zelle' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egresos_zelle,
                SUM(CASE WHEN tipo = 'egreso' AND metodo_pago = 'binance' AND estado = 'confirmado' THEN monto_usd ELSE 0 END) AS egresos_binance
            FROM movimientos_tesoreria
            """
        ).fetchone()

    return {
        "ingresos_efectivo": _safe_float(row["ingresos_efectivo"]) if row else 0.0,
        "ingresos_transferencia": _safe_float(row["ingresos_transferencia"]) if row else 0.0,
        "ingresos_zelle": _safe_float(row["ingresos_zelle"]) if row else 0.0,
        "ingresos_binance": _safe_float(row["ingresos_binance"]) if row else 0.0,
        "egresos_efectivo": _safe_float(row["egresos_efectivo"]) if row else 0.0,
        "egresos_transferencia": _safe_float(row["egresos_transferencia"]) if row else 0.0,
        "egresos_zelle": _safe_float(row["egresos_zelle"]) if row else 0.0,
        "egresos_binance": _safe_float(row["egresos_binance"]) if row else 0.0,
    }


def _get_ultimo_cierre():
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM cierres_caja
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    return row


def _guardar_cierre_caja(
    *,
    usuario: str,
    cash_start: float,
    sales_cash: float,
    sales_transfer: float,
    sales_zelle: float,
    sales_binance: float,
    expenses_cash: float,
    expenses_transfer: float,
    cash_end: float,
    observaciones: str,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO cierres_caja (
                fecha,
                usuario,
                estado,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                cash_end,
                observaciones
            )
            VALUES (
                CURRENT_TIMESTAMP,
                ?,
                'cerrado',
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                usuario,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                cash_end,
                observaciones,
            ),
        )

    # Tu schema exige monto_usd > 0
    _registrar_movimiento_tesoreria(
        tipo="egreso",
        origen="cierre_caja",
        referencia_id=None,
        descripcion=f"Cierre de caja realizado por {usuario}",
        monto_usd=0.0001,
        metodo_pago="efectivo",
        usuario=usuario,
        metadata=observaciones or None,
    )


def _get_cierres_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                fecha,
                usuario,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                cash_end,
                observaciones
            FROM cierres_caja
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
    puede_cerrar_caja = has_permission("caja.close")

    solo_lectura = not any(
        [
            puede_registrar_cobros,
            puede_registrar_pagos,
            puede_cerrar_caja,
        ]
    )

    st.subheader("🏦 Caja empresarial")
    st.info("Control de ingresos, egresos y cierres de caja.")

    if solo_lectura:
        st.warning("Modo solo lectura: puedes consultar caja, pero no registrar movimientos ni cerrar caja.")

    resumen = _get_resumen_caja()

    saldo_efectivo = resumen["ingresos_efectivo"] - resumen["egresos_efectivo"]
    saldo_transferencia = resumen["ingresos_transferencia"] - resumen["egresos_transferencia"]
    saldo_zelle = resumen["ingresos_zelle"] - resumen["egresos_zelle"]
    saldo_binance = resumen["ingresos_binance"] - resumen["egresos_binance"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Efectivo", f"$ {saldo_efectivo:,.2f}")
    c2.metric("Transferencia", f"$ {saldo_transferencia:,.2f}")
    c3.metric("Zelle", f"$ {saldo_zelle:,.2f}")
    c4.metric("Binance", f"$ {saldo_binance:,.2f}")

    st.divider()

    tab1, tab2, tab3 = st.tabs(
        [
            "💵 Registrar cobro",
            "💸 Registrar pago",
            "🔒 Cierre de caja",
        ]
    )

    with tab1:
        st.markdown("### Registrar cobro manual")

        with st.form("form_caja_cobro"):
            descripcion_in = st.text_input(
                "Descripción del cobro",
                placeholder="Ej: Cobro manual, anticipo cliente, ajuste positivo",
                disabled=not puede_registrar_cobros,
            )
            c_in_1, c_in_2 = st.columns(2)
            monto_in = c_in_1.number_input(
                "Monto USD",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                disabled=not puede_registrar_cobros,
            )
            metodo_in = c_in_2.selectbox(
                "Método de pago",
                METODOS_PAGO,
                disabled=not puede_registrar_cobros,
            )

            guardar_cobro = st.form_submit_button(
                "💾 Registrar cobro",
                disabled=not puede_registrar_cobros,
            )

        if guardar_cobro:
            if not descripcion_in.strip():
                st.warning("Debes indicar una descripción.")
            elif monto_in <= 0:
                st.warning("El monto debe ser mayor a cero.")
            else:
                try:
                    _registrar_movimiento_tesoreria(
                        tipo="ingreso",
                        origen="ajuste_manual",
                        referencia_id=None,
                        descripcion=descripcion_in.strip(),
                        monto_usd=float(monto_in),
                        metodo_pago=metodo_in,
                        usuario=usuario,
                        metadata="caja.payment_in",
                    )
                    st.success("✅ Cobro registrado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error("No se pudo registrar el cobro.")
                    st.exception(e)

    with tab2:
        st.markdown("### Registrar pago manual")

        with st.form("form_caja_pago"):
            descripcion_out = st.text_input(
                "Descripción del pago",
                placeholder="Ej: Pago menor, retiro operativo, ajuste negativo",
                disabled=not puede_registrar_pagos,
            )
            c_out_1, c_out_2 = st.columns(2)
            monto_out = c_out_1.number_input(
                "Monto USD",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="monto_pago_caja",
                disabled=not puede_registrar_pagos,
            )
            metodo_out = c_out_2.selectbox(
                "Método de pago",
                METODOS_PAGO,
                key="metodo_pago_caja",
                disabled=not puede_registrar_pagos,
            )

            guardar_pago = st.form_submit_button(
                "💾 Registrar pago",
                disabled=not puede_registrar_pagos,
            )

        if guardar_pago:
            if not descripcion_out.strip():
                st.warning("Debes indicar una descripción.")
            elif monto_out <= 0:
                st.warning("El monto debe ser mayor a cero.")
            else:
                try:
                    _registrar_movimiento_tesoreria(
                        tipo="egreso",
                        origen="ajuste_manual",
                        referencia_id=None,
                        descripcion=descripcion_out.strip(),
                        monto_usd=float(monto_out),
                        metodo_pago=metodo_out,
                        usuario=usuario,
                        metadata="caja.payment_out",
                    )
                    st.success("✅ Pago registrado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error("No se pudo registrar el pago.")
                    st.exception(e)

    with tab3:
        st.markdown("### Cierre de caja")

        ultimo_cierre = _get_ultimo_cierre()
        cash_start_default = _safe_float(ultimo_cierre["cash_end"]) if ultimo_cierre else 0.0

        sales_cash = resumen["ingresos_efectivo"]
        sales_transfer = resumen["ingresos_transferencia"]
        sales_zelle = resumen["ingresos_zelle"]
        sales_binance = resumen["ingresos_binance"]
        expenses_cash = resumen["egresos_efectivo"]
        expenses_transfer = resumen["egresos_transferencia"]

        with st.form("form_cierre_caja"):
            cc1, cc2 = st.columns(2)

            cash_start = cc1.number_input(
                "Caja inicial ($)",
                min_value=0.0,
                value=float(cash_start_default),
                step=0.01,
                format="%.2f",
                disabled=not puede_cerrar_caja,
            )

            cash_end_sugerido = cash_start + sales_cash - expenses_cash
            cash_end = cc2.number_input(
                "Caja final declarada ($)",
                min_value=0.0,
                value=float(cash_end_sugerido),
                step=0.01,
                format="%.2f",
                disabled=not puede_cerrar_caja,
            )

            st.caption(
                f"Sugerido por sistema: Caja inicial ({cash_start:,.2f}) + "
                f"ingresos efectivo ({sales_cash:,.2f}) - egresos efectivo ({expenses_cash:,.2f}) = "
                f"{cash_end_sugerido:,.2f}"
            )

            observaciones = st.text_area(
                "Observaciones del cierre",
                placeholder="Diferencias, retiros, incidencias, notas del turno",
                disabled=not puede_cerrar_caja,
            )

            cerrar_caja = st.form_submit_button(
                "🔒 Registrar cierre de caja",
                disabled=not puede_cerrar_caja,
            )

        if cerrar_caja:
            try:
                _guardar_cierre_caja(
                    usuario=usuario,
                    cash_start=float(cash_start),
                    sales_cash=float(sales_cash),
                    sales_transfer=float(sales_transfer),
                    sales_zelle=float(sales_zelle),
                    sales_binance=float(sales_binance),
                    expenses_cash=float(expenses_cash),
                    expenses_transfer=float(expenses_transfer),
                    cash_end=float(cash_end),
                    observaciones=observaciones.strip(),
                )
                diferencia = float(cash_end) - float(cash_end_sugerido)
                if abs(diferencia) > 0.009:
                    st.warning(f"⚠️ Cierre registrado con diferencia de $ {diferencia:,.2f}")
                else:
                    st.success("✅ Cierre de caja registrado correctamente.")
                st.rerun()
            except Exception as e:
                st.error("No se pudo registrar el cierre de caja.")
                st.exception(e)

    st.divider()

    st.subheader("📋 Movimientos recientes de caja")
    try:
        df_mov = _get_movimientos_caja_df()
        if df_mov.empty:
            st.info("No hay movimientos registrados.")
        else:
            st.dataframe(df_mov, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error("No se pudieron cargar los movimientos de caja.")
        st.exception(e)

    with st.expander("📜 Ver cierres de caja"):
        try:
            df_cierres = _get_cierres_df()
            if df_cierres.empty:
                st.info("Aún no hay cierres registrados.")
            else:
                st.dataframe(df_cierres, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("No se pudieron cargar los cierres de caja.")
            st.exception(e)
