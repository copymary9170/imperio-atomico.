from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, require_text


METODOS_CAJA = [
    "efectivo",
    "transferencia",
    "pago móvil",
    "zelle",
    "binance",
    "kontigo",
    "tarjeta",
    "credito",
]

ROLES_ADMIN_CAJA = ["Admin", "Administration", "Administracion"]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_caja_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'cerrado',
                cash_start REAL DEFAULT 0,
                sales_cash REAL DEFAULT 0,
                sales_transfer REAL DEFAULT 0,
                sales_pago_movil REAL DEFAULT 0,
                sales_zelle REAL DEFAULT 0,
                sales_binance REAL DEFAULT 0,
                sales_kontigo REAL DEFAULT 0,
                sales_tarjeta REAL DEFAULT 0,
                sales_credito REAL DEFAULT 0,
                other_income_cash REAL DEFAULT 0,
                other_income_transfer REAL DEFAULT 0,
                expenses_cash REAL DEFAULT 0,
                expenses_transfer REAL DEFAULT 0,
                expenses_pago_movil REAL DEFAULT 0,
                expenses_zelle REAL DEFAULT 0,
                expenses_binance REAL DEFAULT 0,
                expenses_kontigo REAL DEFAULT 0,
                expenses_tarjeta REAL DEFAULT 0,
                expected_cash_end REAL DEFAULT 0,
                counted_cash_end REAL DEFAULT 0,
                diferencia_cash REAL DEFAULT 0,
                observaciones TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS caja_movimientos_manual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                tipo TEXT NOT NULL,
                metodo_pago TEXT NOT NULL,
                concepto TEXT NOT NULL,
                monto_usd REAL NOT NULL DEFAULT 0,
                referencia TEXT,
                observaciones TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_caja_fecha ON cierres_caja(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_caja_estado ON cierres_caja(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caja_mov_manual_fecha ON caja_movimientos_manual(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caja_mov_manual_tipo ON caja_movimientos_manual(tipo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_caja_mov_manual_estado ON caja_movimientos_manual(estado)")

        cols = {r[1] for r in conn.execute("PRAGMA table_info(cierres_caja)").fetchall()}

        missing_columns = {
            "sales_pago_movil": "ALTER TABLE cierres_caja ADD COLUMN sales_pago_movil REAL DEFAULT 0",
            "sales_kontigo": "ALTER TABLE cierres_caja ADD COLUMN sales_kontigo REAL DEFAULT 0",
            "sales_tarjeta": "ALTER TABLE cierres_caja ADD COLUMN sales_tarjeta REAL DEFAULT 0",
            "sales_credito": "ALTER TABLE cierres_caja ADD COLUMN sales_credito REAL DEFAULT 0",
            "other_income_cash": "ALTER TABLE cierres_caja ADD COLUMN other_income_cash REAL DEFAULT 0",
            "other_income_transfer": "ALTER TABLE cierres_caja ADD COLUMN other_income_transfer REAL DEFAULT 0",
            "expenses_pago_movil": "ALTER TABLE cierres_caja ADD COLUMN expenses_pago_movil REAL DEFAULT 0",
            "expenses_zelle": "ALTER TABLE cierres_caja ADD COLUMN expenses_zelle REAL DEFAULT 0",
            "expenses_binance": "ALTER TABLE cierres_caja ADD COLUMN expenses_binance REAL DEFAULT 0",
            "expenses_kontigo": "ALTER TABLE cierres_caja ADD COLUMN expenses_kontigo REAL DEFAULT 0",
            "expenses_tarjeta": "ALTER TABLE cierres_caja ADD COLUMN expenses_tarjeta REAL DEFAULT 0",
            "expected_cash_end": "ALTER TABLE cierres_caja ADD COLUMN expected_cash_end REAL DEFAULT 0",
            "counted_cash_end": "ALTER TABLE cierres_caja ADD COLUMN counted_cash_end REAL DEFAULT 0",
            "diferencia_cash": "ALTER TABLE cierres_caja ADD COLUMN diferencia_cash REAL DEFAULT 0",
            "created_at": "ALTER TABLE cierres_caja ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "ALTER TABLE cierres_caja ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        }

        for col, sql in missing_columns.items():
            if col not in cols:
                conn.execute(sql)


# ============================================================
# HELPERS
# ============================================================

def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _sum_method(df: pd.DataFrame, method: str, column: str) -> float:
    if df.empty or column not in df.columns or "metodo_pago" not in df.columns:
        return 0.0
    return float(
        df[df["metodo_pago"].fillna("").astype(str).str.lower() == method.lower()][column].fillna(0).sum()
    )


def _safe_read_sql(query: str, conn, params: tuple | None = None) -> pd.DataFrame:
    try:
        return pd.read_sql_query(query, conn, params=params or ())
    except Exception:
        return pd.DataFrame()


def _money(value: float) -> str:
    return f"$ {float(value or 0.0):,.2f}"


def _load_resumen_dia(fecha_str: str) -> dict[str, object]:
    _ensure_caja_tables()

    with db_transaction() as conn:
        ventas = _safe_read_sql(
            """
            SELECT id, fecha, metodo_pago, total_usd
            FROM ventas
            WHERE LOWER(COALESCE(estado, '')) = 'registrada'
              AND date(fecha) = ?
            """,
            conn,
            (fecha_str,),
        )

        gastos = _safe_read_sql(
            """
            SELECT id, fecha, metodo_pago, monto_usd
            FROM gastos
            WHERE LOWER(COALESCE(estado, '')) IN ('activo', 'registrado')
              AND date(fecha) = ?
            """,
            conn,
            (fecha_str,),
        )

        ingresos_tesoreria = _safe_read_sql(
            """
            SELECT id, fecha, metodo_pago, monto_usd, origen, descripcion
            FROM tesoreria_movimientos
            WHERE LOWER(COALESCE(tipo, '')) = 'ingreso'
              AND date(fecha) = ?
            """,
            conn,
            (fecha_str,),
        )

        egresos_tesoreria = _safe_read_sql(
            """
            SELECT id, fecha, metodo_pago, monto_usd, origen, descripcion
            FROM tesoreria_movimientos
            WHERE LOWER(COALESCE(tipo, '')) = 'egreso'
              AND date(fecha) = ?
            """,
            conn,
            (fecha_str,),
        )

        manuales = _safe_read_sql(
            """
            SELECT id, fecha, tipo, metodo_pago, concepto, monto_usd, referencia, observaciones
            FROM caja_movimientos_manual
            WHERE COALESCE(estado, 'activo') = 'activo'
              AND date(fecha) = ?
            ORDER BY fecha DESC, id DESC
            """,
            conn,
            (fecha_str,),
        )

        cierre_existente = conn.execute(
            """
            SELECT *
            FROM cierres_caja
            WHERE fecha = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (fecha_str,),
        ).fetchone()

    ventas["metodo_pago"] = ventas.get("metodo_pago", pd.Series(dtype=str)).fillna("sin definir")
    gastos["metodo_pago"] = gastos.get("metodo_pago", pd.Series(dtype=str)).fillna("sin definir")
    ingresos_tesoreria["metodo_pago"] = ingresos_tesoreria.get("metodo_pago", pd.Series(dtype=str)).fillna("sin definir")
    egresos_tesoreria["metodo_pago"] = egresos_tesoreria.get("metodo_pago", pd.Series(dtype=str)).fillna("sin definir")
    if not manuales.empty:
        manuales["metodo_pago"] = manuales["metodo_pago"].fillna("sin definir")
        manuales["tipo"] = manuales["tipo"].fillna("sin definir")

    ingresos_manual = manuales[manuales["tipo"].astype(str).str.lower() == "ingreso"].copy() if not manuales.empty else pd.DataFrame()
    egresos_manual = manuales[manuales["tipo"].astype(str).str.lower() == "egreso"].copy() if not manuales.empty else pd.DataFrame()

    sales_cash = _sum_method(ventas, "efectivo", "total_usd")
    sales_transfer = _sum_method(ventas, "transferencia", "total_usd")
    sales_pago_movil = _sum_method(ventas, "pago móvil", "total_usd") + _sum_method(ventas, "pago_movil", "total_usd")
    sales_zelle = _sum_method(ventas, "zelle", "total_usd")
    sales_binance = _sum_method(ventas, "binance", "total_usd")
    sales_kontigo = _sum_method(ventas, "kontigo", "total_usd")
    sales_tarjeta = _sum_method(ventas, "tarjeta", "total_usd")
    sales_credito = _sum_method(ventas, "credito", "total_usd")

    expenses_cash = _sum_method(gastos, "efectivo", "monto_usd")
    expenses_transfer = _sum_method(gastos, "transferencia", "monto_usd")
    expenses_pago_movil = _sum_method(gastos, "pago móvil", "monto_usd") + _sum_method(gastos, "pago_movil", "monto_usd")
    expenses_zelle = _sum_method(gastos, "zelle", "monto_usd")
    expenses_binance = _sum_method(gastos, "binance", "monto_usd")
    expenses_kontigo = _sum_method(gastos, "kontigo", "monto_usd")
    expenses_tarjeta = _sum_method(gastos, "tarjeta", "monto_usd")

    other_income_cash = _sum_method(ingresos_manual, "efectivo", "monto_usd")
    other_income_transfer = float(
        ingresos_manual[
            ingresos_manual["metodo_pago"].astype(str).str.lower().isin(
                ["transferencia", "pago móvil", "pago_movil", "zelle", "binance", "kontigo", "tarjeta"]
            )
        ]["monto_usd"].sum()
    ) if not ingresos_manual.empty else 0.0

    manual_expenses_cash = _sum_method(egresos_manual, "efectivo", "monto_usd")
    manual_expenses_transfer = float(
        egresos_manual[
            egresos_manual["metodo_pago"].astype(str).str.lower().isin(
                ["transferencia", "pago móvil", "pago_movil", "zelle", "binance", "kontigo", "tarjeta"]
            )
        ]["monto_usd"].sum()
    ) if not egresos_manual.empty else 0.0

    expenses_cash += manual_expenses_cash
    expenses_transfer += manual_expenses_transfer

    total_ventas = float(ventas["total_usd"].sum()) if not ventas.empty else 0.0
    total_gastos = float(gastos["monto_usd"].sum()) if not gastos.empty else 0.0
    total_ingresos_manual = float(ingresos_manual["monto_usd"].sum()) if not ingresos_manual.empty else 0.0
    total_egresos_manual = float(egresos_manual["monto_usd"].sum()) if not egresos_manual.empty else 0.0
    total_ingresos_tesoreria = float(ingresos_tesoreria["monto_usd"].sum()) if not ingresos_tesoreria.empty else 0.0
    total_egresos_tesoreria = float(egresos_tesoreria["monto_usd"].sum()) if not egresos_tesoreria.empty else 0.0

    return {
        "ventas": ventas,
        "gastos": gastos,
        "ingresos_tesoreria": ingresos_tesoreria,
        "egresos_tesoreria": egresos_tesoreria,
        "manuales": manuales,
        "cierre_existente": cierre_existente,
        "sales_cash": sales_cash,
        "sales_transfer": sales_transfer,
        "sales_pago_movil": sales_pago_movil,
        "sales_zelle": sales_zelle,
        "sales_binance": sales_binance,
        "sales_kontigo": sales_kontigo,
        "sales_tarjeta": sales_tarjeta,
        "sales_credito": sales_credito,
        "expenses_cash": expenses_cash,
        "expenses_transfer": expenses_transfer,
        "expenses_pago_movil": expenses_pago_movil,
        "expenses_zelle": expenses_zelle,
        "expenses_binance": expenses_binance,
        "expenses_kontigo": expenses_kontigo,
        "expenses_tarjeta": expenses_tarjeta,
        "other_income_cash": other_income_cash,
        "other_income_transfer": other_income_transfer,
        "total_ventas": total_ventas,
        "total_gastos": total_gastos,
        "total_ingresos_manual": total_ingresos_manual,
        "total_egresos_manual": total_egresos_manual,
        "total_ingresos_tesoreria": total_ingresos_tesoreria,
        "total_egresos_tesoreria": total_egresos_tesoreria,
    }


def _load_historial_cierres(limit: int = 120) -> pd.DataFrame:
    _ensure_caja_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                estado,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_pago_movil,
                sales_zelle,
                sales_binance,
                sales_kontigo,
                sales_tarjeta,
                sales_credito,
                other_income_cash,
                other_income_transfer,
                expenses_cash,
                expenses_transfer,
                expenses_pago_movil,
                expenses_zelle,
                expenses_binance,
                expenses_kontigo,
                expenses_tarjeta,
                expected_cash_end,
                counted_cash_end,
                diferencia_cash,
                observaciones,
                created_at,
                updated_at
            FROM cierres_caja
            ORDER BY fecha DESC, id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )


# ============================================================
# CAJA MANUAL
# ============================================================

def _render_tab_movimientos_manuales(usuario: str) -> None:
    st.subheader("➕ Movimientos manuales de caja")

    with st.form("form_caja_mov_manual", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tipo = c1.selectbox("Tipo", ["ingreso", "egreso"])
        metodo = c2.selectbox("Método de pago", [m for m in METODOS_CAJA if m != "credito"])
        monto = c3.number_input("Monto USD", min_value=0.01, value=0.01, format="%.2f")

        c4, c5 = st.columns(2)
        concepto = c4.text_input("Concepto")
        referencia = c5.text_input("Referencia")

        observaciones = st.text_area("Observaciones")
        guardar = st.form_submit_button("Guardar movimiento manual", use_container_width=True)

    if guardar:
        try:
            concepto_ok = require_text(concepto, "Concepto")
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO caja_movimientos_manual (
                        usuario, tipo, metodo_pago, concepto, monto_usd, referencia, observaciones, estado
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')
                    """,
                    (
                        usuario,
                        tipo,
                        metodo,
                        concepto_ok,
                        float(monto),
                        clean_text(referencia),
                        clean_text(observaciones),
                    ),
                )
            st.success("Movimiento manual guardado")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar el movimiento manual: {exc}")

    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT id, fecha, usuario, tipo, metodo_pago, concepto, monto_usd, referencia, observaciones
            FROM caja_movimientos_manual
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY fecha DESC, id DESC
            LIMIT 100
            """,
            conn,
        )

    if df.empty:
        st.caption("No hay movimientos manuales registrados.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    opciones = {f"#{int(r['id'])} · {r['tipo']} · {r['concepto']} · {_money(r['monto_usd'])}": int(r["id"]) for _, r in df.iterrows()}
    seleccionado = st.selectbox("Movimiento a anular", list(opciones.keys()), key="caja_mov_manual_anular")

    if st.button("Anular movimiento manual", key="btn_anular_mov_manual", use_container_width=True):
        try:
            mov_id = opciones[seleccionado]
            with db_transaction() as conn:
                conn.execute(
                    "UPDATE caja_movimientos_manual SET estado='anulado' WHERE id=?",
                    (int(mov_id),),
                )
            st.success("Movimiento manual anulado")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo anular el movimiento: {exc}")


# ============================================================
# CIERRE
# ============================================================

def _render_tab_cierre(usuario: str) -> None:
    st.subheader("🏁 Cierre de caja diario")

    fecha_cierre = st.date_input("Seleccionar fecha", value=date.today(), key="caja_fecha_cierre")
    fecha_str = fecha_cierre.strftime("%Y-%m-%d")
    resumen = _load_resumen_dia(fecha_str)
    cierre_existente = resumen["cierre_existente"]

    if cierre_existente:
        st.warning(f"Ya existe un cierre para {fecha_str}. Estado actual: {cierre_existente['estado']}")

    cash_start_default = _to_float(cierre_existente["cash_start"], 0.0) if cierre_existente else 0.0
    counted_default = _to_float(cierre_existente["counted_cash_end"], 0.0) if cierre_existente else 0.0
    obs_default = str(cierre_existente["observaciones"] or "") if cierre_existente else ""

    c1, c2 = st.columns(2)
    cash_start = c1.number_input("Fondo inicial de caja (USD)", min_value=0.0, value=float(cash_start_default), step=1.0, key="caja_cash_start")
    counted_cash_end = c2.number_input("Efectivo contado al cierre (USD)", min_value=0.0, value=float(counted_default), step=1.0, key="caja_counted_cash_end")

    observaciones = st.text_area("Observaciones del cierre", value=obs_default, placeholder="Incidencias, faltantes, sobrantes, notas...", key="caja_obs")

    expected_cash_end = round(
        float(cash_start)
        + float(resumen["sales_cash"])
        + float(resumen["other_income_cash"])
        - float(resumen["expenses_cash"]),
        2,
    )
    diferencia_cash = round(float(counted_cash_end) - float(expected_cash_end), 2)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas del día", _money(resumen["total_ventas"]))
    m2.metric("Gastos del día", _money(resumen["total_gastos"]))
    m3.metric("Efectivo esperado", _money(expected_cash_end))
    m4.metric("Diferencia arqueo", _money(diferencia_cash))

    with st.expander("Ver desglose completo del día", expanded=True):
        i1, i2 = st.columns(2)

        with i1:
            st.markdown("**Ingresos por ventas**")
            st.write(f"Efectivo: {_money(resumen['sales_cash'])}")
            st.write(f"Transferencia: {_money(resumen['sales_transfer'])}")
            st.write(f"Pago móvil: {_money(resumen['sales_pago_movil'])}")
            st.write(f"Zelle: {_money(resumen['sales_zelle'])}")
            st.write(f"Binance: {_money(resumen['sales_binance'])}")
            st.write(f"Kontigo: {_money(resumen['sales_kontigo'])}")
            st.write(f"Tarjeta: {_money(resumen['sales_tarjeta'])}")
            st.write(f"Crédito: {_money(resumen['sales_credito'])}")

            st.markdown("**Otros ingresos manuales**")
            st.write(f"Efectivo: {_money(resumen['other_income_cash'])}")
            st.write(f"No efectivo: {_money(resumen['other_income_transfer'])}")

        with i2:
            st.markdown("**Egresos por gastos**")
            st.write(f"Efectivo: {_money(resumen['expenses_cash'])}")
            st.write(f"Transferencia: {_money(resumen['expenses_transfer'])}")
            st.write(f"Pago móvil: {_money(resumen['expenses_pago_movil'])}")
            st.write(f"Zelle: {_money(resumen['expenses_zelle'])}")
            st.write(f"Binance: {_money(resumen['expenses_binance'])}")
            st.write(f"Kontigo: {_money(resumen['expenses_kontigo'])}")
            st.write(f"Tarjeta: {_money(resumen['expenses_tarjeta'])}")

    b1, b2 = st.columns(2)

    if b1.button("💾 Guardar / actualizar cierre", use_container_width=True):
        try:
            with db_transaction() as conn:
                if cierre_existente:
                    conn.execute(
                        """
                        UPDATE cierres_caja
                        SET usuario=?,
                            estado='cerrado',
                            cash_start=?,
                            sales_cash=?,
                            sales_transfer=?,
                            sales_pago_movil=?,
                            sales_zelle=?,
                            sales_binance=?,
                            sales_kontigo=?,
                            sales_tarjeta=?,
                            sales_credito=?,
                            other_income_cash=?,
                            other_income_transfer=?,
                            expenses_cash=?,
                            expenses_transfer=?,
                            expenses_pago_movil=?,
                            expenses_zelle=?,
                            expenses_binance=?,
                            expenses_kontigo=?,
                            expenses_tarjeta=?,
                            expected_cash_end=?,
                            counted_cash_end=?,
                            diferencia_cash=?,
                            observaciones=?,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                        """,
                        (
                            usuario,
                            float(cash_start),
                            float(resumen["sales_cash"]),
                            float(resumen["sales_transfer"]),
                            float(resumen["sales_pago_movil"]),
                            float(resumen["sales_zelle"]),
                            float(resumen["sales_binance"]),
                            float(resumen["sales_kontigo"]),
                            float(resumen["sales_tarjeta"]),
                            float(resumen["sales_credito"]),
                            float(resumen["other_income_cash"]),
                            float(resumen["other_income_transfer"]),
                            float(resumen["expenses_cash"]),
                            float(resumen["expenses_transfer"]),
                            float(resumen["expenses_pago_movil"]),
                            float(resumen["expenses_zelle"]),
                            float(resumen["expenses_binance"]),
                            float(resumen["expenses_kontigo"]),
                            float(resumen["expenses_tarjeta"]),
                            float(expected_cash_end),
                            float(counted_cash_end),
                            float(diferencia_cash),
                            clean_text(observaciones),
                            int(cierre_existente["id"]),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO cierres_caja (
                            fecha,
                            usuario,
                            estado,
                            cash_start,
                            sales_cash,
                            sales_transfer,
                            sales_pago_movil,
                            sales_zelle,
                            sales_binance,
                            sales_kontigo,
                            sales_tarjeta,
                            sales_credito,
                            other_income_cash,
                            other_income_transfer,
                            expenses_cash,
                            expenses_transfer,
                            expenses_pago_movil,
                            expenses_zelle,
                            expenses_binance,
                            expenses_kontigo,
                            expenses_tarjeta,
                            expected_cash_end,
                            counted_cash_end,
                            diferencia_cash,
                            observaciones
                        )
                        VALUES (?, ?, 'cerrado', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fecha_str,
                            usuario,
                            float(cash_start),
                            float(resumen["sales_cash"]),
                            float(resumen["sales_transfer"]),
                            float(resumen["sales_pago_movil"]),
                            float(resumen["sales_zelle"]),
                            float(resumen["sales_binance"]),
                            float(resumen["sales_kontigo"]),
                            float(resumen["sales_tarjeta"]),
                            float(resumen["sales_credito"]),
                            float(resumen["other_income_cash"]),
                            float(resumen["other_income_transfer"]),
                            float(resumen["expenses_cash"]),
                            float(resumen["expenses_transfer"]),
                            float(resumen["expenses_pago_movil"]),
                            float(resumen["expenses_zelle"]),
                            float(resumen["expenses_binance"]),
                            float(resumen["expenses_kontigo"]),
                            float(resumen["expenses_tarjeta"]),
                            float(expected_cash_end),
                            float(counted_cash_end),
                            float(diferencia_cash),
                            clean_text(observaciones),
                        ),
                    )
            st.success("Cierre guardado correctamente")
            st.rerun()
        except Exception as exc:
            st.error(f"Error guardando cierre: {exc}")

    if b2.button("🔓 Reabrir / anular cierre", use_container_width=True, disabled=not bool(cierre_existente)):
        try:
            if not cierre_existente:
                raise ValueError("No existe cierre para reabrir.")

            with db_transaction() as conn:
                conn.execute(
                    """
                    UPDATE cierres_caja
                    SET estado='reabierto',
                        updated_at=CURRENT_TIMESTAMP,
                        observaciones=COALESCE(observaciones, '') || ' | REABIERTO DESDE INTERFAZ'
                    WHERE id=?
                    """,
                    (int(cierre_existente["id"]),),
                )
            st.success("Cierre reabierto")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo reabrir el cierre: {exc}")


# ============================================================
# HISTORIAL
# ============================================================

def _render_tab_historial() -> None:
    st.subheader("📜 Historial de cierres")

    df = _load_historial_cierres(limit=365)

    if df.empty:
        st.info("Aún no hay cierres guardados.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["estado"] = df["estado"].fillna("sin definir")

    f1, f2, f3 = st.columns([1, 1, 2])
    desde = f1.date_input("Desde", date.today() - timedelta(days=30), key="caja_hist_desde")
    hasta = f2.date_input("Hasta", date.today(), key="caja_hist_hasta")
    estado = f3.selectbox("Estado", ["Todos"] + sorted(df["estado"].astype(str).unique().tolist()), key="caja_hist_estado")

    view = df[(df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)].copy()
    if estado != "Todos":
        view = view[view["estado"].astype(str) == estado]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cierres visibles", len(view))
    k2.metric("Efectivo esperado", _money(view["expected_cash_end"].fillna(0).sum() if not view.empty else 0))
    k3.metric("Efectivo contado", _money(view["counted_cash_end"].fillna(0).sum() if not view.empty else 0))
    k4.metric("Diferencia acumulada", _money(view["diferencia_cash"].fillna(0).sum() if not view.empty else 0))

    st.dataframe(view, use_container_width=True, hide_index=True)

    if not view.empty:
        tendencia = (
            view.assign(fecha_only=view["fecha"].dt.date)
            .groupby("fecha_only", as_index=False)[["expected_cash_end", "counted_cash_end", "diferencia_cash"]]
            .sum()
            .sort_values("fecha_only")
        )
        st.caption("Tendencia de cierres")
        st.line_chart(tendencia.set_index("fecha_only")[["expected_cash_end", "counted_cash_end"]])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        view.to_excel(writer, index=False, sheet_name="CierresCaja")

    st.download_button(
        "📥 Descargar historial de cierres",
        buffer.getvalue(),
        file_name="cierres_caja.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ============================================================
# RESUMEN EMPRESA
# ============================================================

def _render_tab_resumen_empresa() -> None:
    st.subheader("🏢 Caja a nivel empresa")

    df = _load_historial_cierres(limit=365)
    if df.empty:
        st.info("No hay cierres para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["mes"] = df["fecha"].dt.to_period("M").astype(str)

    total_expected = float(df["expected_cash_end"].fillna(0).sum())
    total_counted = float(df["counted_cash_end"].fillna(0).sum())
    total_diff = float(df["diferencia_cash"].fillna(0).sum())
    promedio_diff = float(df["diferencia_cash"].fillna(0).mean()) if not df.empty else 0.0

    resumen_mes = (
        df.groupby("mes", as_index=False)[["expected_cash_end", "counted_cash_end", "diferencia_cash"]]
        .sum()
        .sort_values("mes")
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Efectivo esperado acumulado", _money(total_expected))
    c2.metric("Efectivo contado acumulado", _money(total_counted))
    c3.metric("Diferencia acumulada", _money(total_diff))
    c4.metric("Diferencia promedio", _money(promedio_diff))

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Resumen mensual")
        st.bar_chart(resumen_mes.set_index("mes")[["expected_cash_end", "counted_cash_end"]])

    with g2:
        st.caption("Diferencia mensual")
        st.line_chart(resumen_mes.set_index("mes")[["diferencia_cash"]])

    st.markdown("### Cierres con diferencia relevante")
    relevantes = df[abs(df["diferencia_cash"].fillna(0)) >= 1].copy()
    if relevantes.empty:
        st.success("No hay diferencias relevantes registradas.")
    else:
        st.dataframe(
            relevantes[
                [
                    "fecha",
                    "usuario",
                    "estado",
                    "cash_start",
                    "expected_cash_end",
                    "counted_cash_end",
                    "diferencia_cash",
                    "observaciones",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# UI
# ============================================================

def render_caja(usuario: str, user_role: str) -> None:
    _ensure_caja_tables()

    st.subheader("🏦 Caja empresarial")
    st.caption("Cierre diario, arqueo, movimientos manuales, historial y control ejecutivo de caja.")

    if user_role not in ROLES_ADMIN_CAJA:
        st.warning("Solo usuarios de administración pueden gestionar caja.")
        return

    tabs = st.tabs(
        [
            "🏁 Cierre diario",
            "➕ Movimientos manuales",
            "📜 Historial",
            "🏢 Resumen empresa",
        ]
    )

    with tabs[0]:
        _render_tab_cierre(usuario)

    with tabs[1]:
        _render_tab_movimientos_manuales(usuario)

    with tabs[2]:
        _render_tab_historial()

    with tabs[3]:
        _render_tab_resumen_empresa()
