from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contadores_clics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                turno TEXT NOT NULL DEFAULT 'Dia',
                usuario TEXT NOT NULL,
                equipo TEXT NOT NULL,
                operador TEXT,
                contador_inicial INTEGER NOT NULL DEFAULT 0,
                contador_final INTEGER NOT NULL DEFAULT 0,
                clics_reales INTEGER NOT NULL DEFAULT 0,
                clics_cobrados_pos INTEGER NOT NULL DEFAULT 0,
                paginas_cola INTEGER NOT NULL DEFAULT 0,
                diferencia INTEGER NOT NULL DEFAULT 0,
                tolerancia INTEGER NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'OK',
                observaciones TEXT,
                fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contadores_fecha ON contadores_clics(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contadores_equipo ON contadores_clics(equipo)")


def _sum_pos_clicks(fecha: str) -> int:
    with db_transaction() as conn:
        if not _table_exists(conn, "pos_ventas") or not _table_exists(conn, "pos_venta_detalle"):
            return 0
        row = conn.execute(
            """
            SELECT COALESCE(SUM(d.clics_cobrados),0)
            FROM pos_venta_detalle d
            JOIN pos_ventas v ON v.id = d.venta_id
            WHERE date(v.fecha)=date(?) AND COALESCE(v.estado,'pagada') NOT IN ('anulada','cancelada')
            """,
            (fecha,),
        ).fetchone()
        return int(row[0] or 0)


def _sum_queue_pages(fecha: str) -> int:
    with db_transaction() as conn:
        if not _table_exists(conn, "cola_impresion"):
            return 0
        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_paginas),0)
            FROM cola_impresion
            WHERE date(fecha)=date(?) AND estado NOT IN ('Cancelado')
            """,
            (fecha,),
        ).fetchone()
        return int(row[0] or 0)


def _save_counter(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO contadores_clics(
                fecha, turno, usuario, equipo, operador, contador_inicial, contador_final,
                clics_reales, clics_cobrados_pos, paginas_cola, diferencia, tolerancia,
                estado, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["fecha"], data["turno"], data["usuario"], data["equipo"], data.get("operador"),
                int(data["contador_inicial"]), int(data["contador_final"]), int(data["clics_reales"]),
                int(data["clics_cobrados_pos"]), int(data["paginas_cola"]), int(data["diferencia"]),
                int(data["tolerancia"]), data["estado"], data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def _load_counters() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM contadores_clics ORDER BY fecha DESC, id DESC LIMIT 500", conn)


def render_contadores_clics(usuario: str = "Sistema") -> None:
    st.subheader("🖨️ Contadores y clics")
    st.caption("Control anti-fugas: compara contador real de impresoras contra clics cobrados en POS y páginas recibidas en cola.")
    _ensure_tables()

    df = _load_counters()
    fugas = df[df["estado"].eq("Diferencia")] if not df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros", len(df))
    c2.metric("Clics reales", int(pd.to_numeric(df.get("clics_reales", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if not df.empty else 0)
    c3.metric("Clics POS", int(pd.to_numeric(df.get("clics_cobrados_pos", pd.Series(dtype=int)), errors="coerce").fillna(0).sum()) if not df.empty else 0)
    c4.metric("Alertas", len(fugas))

    tab_registro, tab_historial, tab_alertas = st.tabs(["Registrar contador", "Historial", "Alertas"])

    with tab_registro:
        fecha = st.date_input("Fecha", value=date.today())
        fecha_str = fecha.isoformat()
        pos_clicks = _sum_pos_clicks(fecha_str)
        queue_pages = _sum_queue_pages(fecha_str)

        st.info(f"Clics cobrados POS para {fecha_str}: {pos_clicks} · Páginas en cola: {queue_pages}")
        with st.form("form_contadores_clics"):
            a, b, c = st.columns(3)
            equipo = a.text_input("Equipo / impresora")
            turno = b.selectbox("Turno", ["Manana", "Tarde", "Noche", "Dia", "Otro"])
            operador = c.text_input("Operador", value=usuario)
            d, e, f = st.columns(3)
            inicial = d.number_input("Contador inicial", min_value=0, value=0, step=1)
            final = e.number_input("Contador final", min_value=0, value=0, step=1)
            tolerancia = f.number_input("Tolerancia clics", min_value=0, value=0, step=1)
            m1, m2 = st.columns(2)
            clics_pos_manual = m1.number_input("Clics cobrados POS", min_value=0, value=int(pos_clicks), step=1)
            paginas_cola_manual = m2.number_input("Páginas cola impresión", min_value=0, value=int(queue_pages), step=1)
            observaciones = st.text_area("Observaciones")
            guardar = st.form_submit_button("Guardar control")

        clics_reales = max(0, int(final) - int(inicial))
        referencia = int(clics_pos_manual)
        diferencia = clics_reales - referencia
        estado = "OK" if abs(diferencia) <= int(tolerancia) else "Diferencia"
        st.metric("Clics reales calculados", clics_reales)
        st.metric("Diferencia vs POS", diferencia, estado)

        if guardar:
            if not equipo.strip():
                st.error("El equipo es obligatorio.")
            elif int(final) < int(inicial):
                st.error("El contador final no puede ser menor que el inicial.")
            else:
                control_id = _save_counter({
                    "fecha": fecha_str,
                    "turno": turno,
                    "usuario": usuario,
                    "equipo": equipo.strip(),
                    "operador": operador.strip(),
                    "contador_inicial": int(inicial),
                    "contador_final": int(final),
                    "clics_reales": clics_reales,
                    "clics_cobrados_pos": int(clics_pos_manual),
                    "paginas_cola": int(paginas_cola_manual),
                    "diferencia": diferencia,
                    "tolerancia": int(tolerancia),
                    "estado": estado,
                    "observaciones": observaciones.strip(),
                })
                if estado == "Diferencia":
                    st.warning(f"Control #{control_id} guardado con diferencia de {diferencia} clics.")
                else:
                    st.success(f"Control #{control_id} guardado sin diferencias críticas.")
                st.rerun()

    with tab_historial:
        if df.empty:
            st.info("Sin registros de contadores.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            resumen = df.groupby("equipo", as_index=False).agg(
                registros=("id", "count"),
                clics_reales=("clics_reales", "sum"),
                clics_pos=("clics_cobrados_pos", "sum"),
                diferencia=("diferencia", "sum"),
            )
            st.markdown("#### Resumen por equipo")
            st.dataframe(resumen, use_container_width=True, hide_index=True)

    with tab_alertas:
        if fugas.empty:
            st.success("No hay diferencias críticas registradas.")
        else:
            st.warning(f"Hay {len(fugas)} registro(s) con diferencia fuera de tolerancia.")
            st.dataframe(fugas, use_container_width=True, hide_index=True)
            st.write("- Revisar ventas no registradas en POS.")
            st.write("- Revisar archivos impresos sin ticket.")
            st.write("- Revisar pruebas, reimpresiones y mermas no documentadas.")
            st.write("- Comparar con cola de impresión y control de mermas.")
