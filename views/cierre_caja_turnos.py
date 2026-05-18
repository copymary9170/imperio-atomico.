from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

TURNOS = ["Mañana", "Tarde", "Noche", "Completo", "Otro"]
METODOS = ["efectivo", "transferencia", "zelle", "binance"]


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cierres_caja_turnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_operativa TEXT NOT NULL,
                turno TEXT NOT NULL,
                cajero TEXT NOT NULL,
                usuario TEXT NOT NULL,
                hora_inicio TEXT,
                hora_fin TEXT,
                efectivo_inicial_usd REAL NOT NULL DEFAULT 0,
                efectivo_ingresos_usd REAL NOT NULL DEFAULT 0,
                efectivo_egresos_usd REAL NOT NULL DEFAULT 0,
                efectivo_esperado_usd REAL NOT NULL DEFAULT 0,
                efectivo_contado_usd REAL NOT NULL DEFAULT 0,
                diferencia_efectivo_usd REAL NOT NULL DEFAULT 0,
                transferencia_usd REAL NOT NULL DEFAULT 0,
                zelle_usd REAL NOT NULL DEFAULT 0,
                binance_usd REAL NOT NULL DEFAULT 0,
                total_sistema_usd REAL NOT NULL DEFAULT 0,
                total_declarado_usd REAL NOT NULL DEFAULT 0,
                diferencia_total_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Cerrado',
                observaciones TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_turno_fecha ON cierres_caja_turnos(fecha_operativa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_turno_cajero ON cierres_caja_turnos(cajero)")


def _sum_movimientos(fecha_desde: str, fecha_hasta: str) -> dict[str, float]:
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_efectivo,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_efectivo,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='transferencia' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS transferencia,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='zelle' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS zelle,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='binance' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS binance
            FROM movimientos_tesoreria
            WHERE datetime(fecha) >= datetime(?) AND datetime(fecha) <= datetime(?)
            """,
            (fecha_desde, fecha_hasta),
        ).fetchone()
    return {
        "ing_efectivo": float(row["ing_efectivo"] or 0) if row else 0.0,
        "egr_efectivo": float(row["egr_efectivo"] or 0) if row else 0.0,
        "transferencia": float(row["transferencia"] or 0) if row else 0.0,
        "zelle": float(row["zelle"] or 0) if row else 0.0,
        "binance": float(row["binance"] or 0) if row else 0.0,
    }


def _load_cierres() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            "SELECT * FROM cierres_caja_turnos ORDER BY id DESC LIMIT 300",
            conn,
        )


def _save_cierre(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cierres_caja_turnos(
                fecha_operativa, turno, cajero, usuario, hora_inicio, hora_fin,
                efectivo_inicial_usd, efectivo_ingresos_usd, efectivo_egresos_usd,
                efectivo_esperado_usd, efectivo_contado_usd, diferencia_efectivo_usd,
                transferencia_usd, zelle_usd, binance_usd, total_sistema_usd,
                total_declarado_usd, diferencia_total_usd, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["fecha_operativa"], data["turno"], data["cajero"], data["usuario"],
                data.get("hora_inicio"), data.get("hora_fin"), float(data["efectivo_inicial_usd"]),
                float(data["efectivo_ingresos_usd"]), float(data["efectivo_egresos_usd"]),
                float(data["efectivo_esperado_usd"]), float(data["efectivo_contado_usd"]),
                float(data["diferencia_efectivo_usd"]), float(data["transferencia_usd"]),
                float(data["zelle_usd"]), float(data["binance_usd"]), float(data["total_sistema_usd"]),
                float(data["total_declarado_usd"]), float(data["diferencia_total_usd"]),
                data["estado"], data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def render_cierre_caja_turnos(usuario: str = "Sistema") -> None:
    st.subheader("🔒 Cierre de caja por turno")
    st.caption("Controla cajero, turno, efectivo esperado, efectivo contado y diferencias del día operativo.")
    _ensure_tables()

    cierres = _load_cierres()
    diferencias = cierres[cierres["estado"].eq("Con diferencia")] if not cierres.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cierres", len(cierres))
    c2.metric("Con diferencia", len(diferencias))
    c3.metric("Dif. efectivo acum.", f"${float(pd.to_numeric(cierres.get('diferencia_efectivo_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not cierres.empty else 0:,.2f}")
    c4.metric("Dif. total acum.", f"${float(pd.to_numeric(cierres.get('diferencia_total_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not cierres.empty else 0:,.2f}")

    tab_cerrar, tab_historial, tab_alertas = st.tabs(["Cerrar turno", "Historial", "Alertas"])

    with tab_cerrar:
        fecha_op = st.date_input("Fecha operativa", value=date.today())
        h1, h2, h3 = st.columns(3)
        turno = h1.selectbox("Turno", TURNOS)
        hora_inicio = h2.time_input("Hora inicio", value=time(8, 0))
        hora_fin = h3.time_input("Hora fin", value=datetime.now().time().replace(second=0, microsecond=0))

        fecha_desde = datetime.combine(fecha_op, hora_inicio).isoformat(sep=" ")
        fecha_hasta = datetime.combine(fecha_op, hora_fin).isoformat(sep=" ")
        resumen = _sum_movimientos(fecha_desde, fecha_hasta)

        st.info(
            f"Periodo calculado: {fecha_desde} → {fecha_hasta}. "
            f"Ingresos efectivo: ${resumen['ing_efectivo']:,.2f} · Egresos efectivo: ${resumen['egr_efectivo']:,.2f}"
        )

        with st.form("form_cierre_caja_turno"):
            a, b, c = st.columns(3)
            cajero = a.text_input("Cajero", value=usuario)
            efectivo_inicial = b.number_input("Efectivo inicial USD", min_value=0.0, value=0.0, step=0.01)
            efectivo_contado = c.number_input("Efectivo contado USD", min_value=0.0, value=0.0, step=0.01)

            efectivo_esperado = efectivo_inicial + resumen["ing_efectivo"] - resumen["egr_efectivo"]
            diferencia_efectivo = efectivo_contado - efectivo_esperado

            st.metric("Efectivo esperado", f"${efectivo_esperado:,.2f}")
            st.metric("Diferencia efectivo", f"${diferencia_efectivo:,.2f}")

            p1, p2, p3 = st.columns(3)
            transferencia_decl = p1.number_input("Transferencia declarada USD", min_value=0.0, value=float(resumen["transferencia"]), step=0.01)
            zelle_decl = p2.number_input("Zelle declarado USD", min_value=0.0, value=float(resumen["zelle"]), step=0.01)
            binance_decl = p3.number_input("Binance declarado USD", min_value=0.0, value=float(resumen["binance"]), step=0.01)

            total_sistema = efectivo_esperado + resumen["transferencia"] + resumen["zelle"] + resumen["binance"]
            total_declarado = efectivo_contado + transferencia_decl + zelle_decl + binance_decl
            diferencia_total = total_declarado - total_sistema
            estado = "OK" if abs(diferencia_efectivo) < 0.01 and abs(diferencia_total) < 0.01 else "Con diferencia"

            st.metric("Total sistema", f"${total_sistema:,.2f}")
            st.metric("Total declarado", f"${total_declarado:,.2f}")
            st.metric("Diferencia total", f"${diferencia_total:,.2f}")

            obs = st.text_area("Observaciones / incidencias")
            guardar = st.form_submit_button("Registrar cierre de turno")

        if guardar:
            if not cajero.strip():
                st.error("El cajero es obligatorio.")
            else:
                cierre_id = _save_cierre({
                    "fecha_operativa": fecha_op.isoformat(),
                    "turno": turno,
                    "cajero": cajero.strip(),
                    "usuario": usuario,
                    "hora_inicio": hora_inicio.isoformat(),
                    "hora_fin": hora_fin.isoformat(),
                    "efectivo_inicial_usd": efectivo_inicial,
                    "efectivo_ingresos_usd": resumen["ing_efectivo"],
                    "efectivo_egresos_usd": resumen["egr_efectivo"],
                    "efectivo_esperado_usd": efectivo_esperado,
                    "efectivo_contado_usd": efectivo_contado,
                    "diferencia_efectivo_usd": diferencia_efectivo,
                    "transferencia_usd": transferencia_decl,
                    "zelle_usd": zelle_decl,
                    "binance_usd": binance_decl,
                    "total_sistema_usd": total_sistema,
                    "total_declarado_usd": total_declarado,
                    "diferencia_total_usd": diferencia_total,
                    "estado": estado,
                    "observaciones": obs.strip(),
                })
                if estado == "Con diferencia":
                    st.warning(f"Cierre #{cierre_id} registrado con diferencia.")
                else:
                    st.success(f"Cierre #{cierre_id} registrado sin diferencias.")
                st.rerun()

    with tab_historial:
        if cierres.empty:
            st.info("No hay cierres por turno registrados.")
        else:
            st.dataframe(cierres, use_container_width=True, hide_index=True)
            resumen_cajero = cierres.groupby("cajero", as_index=False).agg(
                cierres=("id", "count"),
                diferencia_efectivo=("diferencia_efectivo_usd", "sum"),
                diferencia_total=("diferencia_total_usd", "sum"),
            )
            st.markdown("#### Resumen por cajero")
            st.dataframe(resumen_cajero, use_container_width=True, hide_index=True)

    with tab_alertas:
        if diferencias.empty:
            st.success("No hay cierres con diferencias.")
        else:
            st.warning(f"Hay {len(diferencias)} cierre(s) con diferencias.")
            st.dataframe(diferencias, use_container_width=True, hide_index=True)
