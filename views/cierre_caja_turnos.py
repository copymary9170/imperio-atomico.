from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission
from services.audit_service import log_audit_event


TURNOS = ["Mañana", "Tarde", "Noche", "Completo", "Otro"]


def _ensure_column(conn, table_name: str, column_name: str, column_sql: str) -> None:
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


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
        for col, sql in [
            ("pago_movil_usd", "REAL NOT NULL DEFAULT 0"),
            ("transferencia_egresos_usd", "REAL NOT NULL DEFAULT 0"),
            ("pago_movil_egresos_usd", "REAL NOT NULL DEFAULT 0"),
            ("zelle_egresos_usd", "REAL NOT NULL DEFAULT 0"),
            ("binance_egresos_usd", "REAL NOT NULL DEFAULT 0"),
        ]:
            _ensure_column(conn, "cierres_caja_turnos", col, sql)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_turno_fecha ON cierres_caja_turnos(fecha_operativa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cierres_turno_cajero ON cierres_caja_turnos(cajero)")


def _sum_movimientos(fecha_desde: str, fecha_hasta: str) -> dict[str, float]:
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_efectivo,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='efectivo' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_efectivo,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='transferencia' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_transferencia,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='transferencia' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_transferencia,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago IN ('pago_movil','pago móvil','pagomovil') AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_pago_movil,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago IN ('pago_movil','pago móvil','pagomovil') AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_pago_movil,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='zelle' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_zelle,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='zelle' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_zelle,
                SUM(CASE WHEN tipo='ingreso' AND metodo_pago='binance' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS ing_binance,
                SUM(CASE WHEN tipo='egreso' AND metodo_pago='binance' AND estado='confirmado' THEN monto_usd ELSE 0 END) AS egr_binance
            FROM movimientos_tesoreria
            WHERE datetime(fecha) >= datetime(?) AND datetime(fecha) <= datetime(?)
            """,
            (fecha_desde, fecha_hasta),
        ).fetchone()
    nombres = [
        "ing_efectivo", "egr_efectivo", "ing_transferencia", "egr_transferencia",
        "ing_pago_movil", "egr_pago_movil", "ing_zelle", "egr_zelle",
        "ing_binance", "egr_binance",
    ]
    return {nombre: float(row[nombre] or 0) if row else 0.0 for nombre in nombres}


def _load_cierres() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM cierres_caja_turnos ORDER BY id DESC LIMIT 300", conn)


def _save_cierre(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        duplicado = conn.execute(
            """
            SELECT id FROM cierres_caja_turnos
            WHERE fecha_operativa=? AND turno=? AND hora_inicio=? AND hora_fin=?
            LIMIT 1
            """,
            (data["fecha_operativa"], data["turno"], data.get("hora_inicio"), data.get("hora_fin")),
        ).fetchone()
        if duplicado:
            raise ValueError(f"Ese periodo ya fue cerrado en el registro #{duplicado['id']}.")

        cur = conn.execute(
            """
            INSERT INTO cierres_caja_turnos(
                fecha_operativa, turno, cajero, usuario, hora_inicio, hora_fin,
                efectivo_inicial_usd, efectivo_ingresos_usd, efectivo_egresos_usd,
                efectivo_esperado_usd, efectivo_contado_usd, diferencia_efectivo_usd,
                transferencia_usd, pago_movil_usd, zelle_usd, binance_usd,
                transferencia_egresos_usd, pago_movil_egresos_usd, zelle_egresos_usd,
                binance_egresos_usd, total_sistema_usd, total_declarado_usd,
                diferencia_total_usd, estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["fecha_operativa"], data["turno"], data["cajero"], data["usuario"],
                data.get("hora_inicio"), data.get("hora_fin"), data["efectivo_inicial_usd"],
                data["efectivo_ingresos_usd"], data["efectivo_egresos_usd"],
                data["efectivo_esperado_usd"], data["efectivo_contado_usd"],
                data["diferencia_efectivo_usd"], data["transferencia_usd"],
                data["pago_movil_usd"], data["zelle_usd"], data["binance_usd"],
                data["transferencia_egresos_usd"], data["pago_movil_egresos_usd"],
                data["zelle_egresos_usd"], data["binance_egresos_usd"],
                data["total_sistema_usd"], data["total_declarado_usd"],
                data["diferencia_total_usd"], data["estado"], data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def render_cierre_caja_turnos(usuario: str = "Sistema") -> None:
    if not require_any_permission(["caja.view", "caja.turno_close", "caja.close"], "🚫 No tienes acceso al cierre de caja por turno."):
        return
    puede_cerrar = has_permission("caja.turno_close") or has_permission("caja.close")

    st.subheader("🔒 Cierre de caja por turno")
    st.caption("Concilia ingresos y egresos por cada método de pago dentro de un periodo definido.")
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
        fecha_op = st.date_input("Fecha operativa", value=date.today(), disabled=not puede_cerrar)
        h1, h2, h3 = st.columns(3)
        turno = h1.selectbox("Turno", TURNOS, disabled=not puede_cerrar)
        hora_inicio = h2.time_input("Hora inicio", value=time(8, 0), disabled=not puede_cerrar)
        hora_fin = h3.time_input("Hora fin", value=datetime.now().time().replace(second=0, microsecond=0), disabled=not puede_cerrar)
        fecha_desde = datetime.combine(fecha_op, hora_inicio).isoformat(sep=" ")
        fecha_hasta = datetime.combine(fecha_op, hora_fin).isoformat(sep=" ")

        if fecha_hasta <= fecha_desde:
            st.error("La hora final debe ser posterior a la hora inicial.")
            return

        resumen = _sum_movimientos(fecha_desde, fecha_hasta)
        st.info(f"Periodo calculado: {fecha_desde} → {fecha_hasta}")

        with st.form("form_cierre_caja_turno"):
            a, b, c = st.columns(3)
            cajero = a.text_input("Cajero", value=usuario, disabled=not puede_cerrar)
            efectivo_inicial = b.number_input("Efectivo inicial USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_cerrar)
            efectivo_contado = c.number_input("Efectivo contado USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_cerrar)

            efectivo_esperado = efectivo_inicial + resumen["ing_efectivo"] - resumen["egr_efectivo"]
            diferencia_efectivo = efectivo_contado - efectivo_esperado
            st.metric("Efectivo esperado", f"${efectivo_esperado:,.2f}")
            st.metric("Diferencia efectivo", f"${diferencia_efectivo:,.2f}")

            t1, t2, t3, t4 = st.columns(4)
            transferencia_sistema = resumen["ing_transferencia"] - resumen["egr_transferencia"]
            pago_movil_sistema = resumen["ing_pago_movil"] - resumen["egr_pago_movil"]
            zelle_sistema = resumen["ing_zelle"] - resumen["egr_zelle"]
            binance_sistema = resumen["ing_binance"] - resumen["egr_binance"]
            transferencia_decl = t1.number_input("Transferencia declarada", min_value=0.0, value=float(max(transferencia_sistema, 0)), step=0.01, disabled=not puede_cerrar)
            pago_movil_decl = t2.number_input("Pago móvil declarado", min_value=0.0, value=float(max(pago_movil_sistema, 0)), step=0.01, disabled=not puede_cerrar)
            zelle_decl = t3.number_input("Zelle declarado", min_value=0.0, value=float(max(zelle_sistema, 0)), step=0.01, disabled=not puede_cerrar)
            binance_decl = t4.number_input("Binance declarado", min_value=0.0, value=float(max(binance_sistema, 0)), step=0.01, disabled=not puede_cerrar)

            total_sistema = efectivo_esperado + transferencia_sistema + pago_movil_sistema + zelle_sistema + binance_sistema
            total_declarado = efectivo_contado + transferencia_decl + pago_movil_decl + zelle_decl + binance_decl
            diferencia_total = total_declarado - total_sistema
            estado = "OK" if abs(diferencia_efectivo) < 0.01 and abs(diferencia_total) < 0.01 else "Con diferencia"
            st.metric("Total sistema", f"${total_sistema:,.2f}")
            st.metric("Total declarado", f"${total_declarado:,.2f}")
            st.metric("Diferencia total", f"${diferencia_total:,.2f}")
            obs = st.text_area("Observaciones / incidencias", disabled=not puede_cerrar)
            guardar = st.form_submit_button("Registrar cierre de turno", disabled=not puede_cerrar)

        if guardar:
            try:
                cierre_id = _save_cierre({
                    "fecha_operativa": fecha_op.isoformat(), "turno": turno,
                    "cajero": cajero.strip(), "usuario": usuario,
                    "hora_inicio": hora_inicio.isoformat(), "hora_fin": hora_fin.isoformat(),
                    "efectivo_inicial_usd": efectivo_inicial,
                    "efectivo_ingresos_usd": resumen["ing_efectivo"],
                    "efectivo_egresos_usd": resumen["egr_efectivo"],
                    "efectivo_esperado_usd": efectivo_esperado,
                    "efectivo_contado_usd": efectivo_contado,
                    "diferencia_efectivo_usd": diferencia_efectivo,
                    "transferencia_usd": transferencia_decl,
                    "pago_movil_usd": pago_movil_decl,
                    "zelle_usd": zelle_decl, "binance_usd": binance_decl,
                    "transferencia_egresos_usd": resumen["egr_transferencia"],
                    "pago_movil_egresos_usd": resumen["egr_pago_movil"],
                    "zelle_egresos_usd": resumen["egr_zelle"],
                    "binance_egresos_usd": resumen["egr_binance"],
                    "total_sistema_usd": total_sistema,
                    "total_declarado_usd": total_declarado,
                    "diferencia_total_usd": diferencia_total,
                    "estado": estado, "observaciones": obs.strip(),
                })
                log_audit_event(
                    usuario=usuario, modulo="Caja", accion="cierre_turno",
                    entidad="cierres_caja_turnos", entidad_id=cierre_id,
                    detalle=f"Cierre de turno {turno} - {estado}",
                    metadata={"cajero": cajero, "fecha_operativa": fecha_op.isoformat(), "diferencia_total_usd": diferencia_total},
                )
                st.success(f"Cierre #{cierre_id} registrado: {estado}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error("No se pudo registrar el cierre de turno.")
                st.exception(exc)

    with tab_historial:
        st.dataframe(cierres, use_container_width=True, hide_index=True) if not cierres.empty else st.info("No hay cierres por turno registrados.")

    with tab_alertas:
        st.dataframe(diferencias, use_container_width=True, hide_index=True) if not diferencias.empty else st.success("No hay cierres con diferencias.")
