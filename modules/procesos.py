from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _ensure_historial_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS historial_procesos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo TEXT,
            cantidad REAL,
            costo REAL,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _ensure_activos_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo TEXT NOT NULL,
            categoria TEXT,
            unidad TEXT,
            desgaste REAL NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def render_otros_procesos(usuario: str):
    st.title("🛠️ Calculadora de Procesos Especiales")
    st.info("Cálculo de costos de procesos que no usan tinta: corte, laminado, planchado, etc.")

    if "datos_proceso_desde_cmyk" in st.session_state:
        p_cmyk = st.session_state.get("datos_proceso_desde_cmyk", {})
        st.success(f"Trabajo recibido desde CMYK: {p_cmyk.get('trabajo', 'N/D')} ({p_cmyk.get('unidades', 0)} uds)")
        st.caption(str(p_cmyk.get("observacion", "")))
        if st.button("Limpiar envío CMYK (Procesos)", key="btn_clear_cmyk_proc"):
            st.session_state.pop("datos_proceso_desde_cmyk", None)
            st.rerun()

    try:
        with db_transaction() as conn:
            _ensure_historial_table(conn)
            _ensure_activos_table(conn)
            df_act_db = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste FROM activos WHERE COALESCE(activo,1)=1",
                conn,
            )
    except Exception as e:
        st.error(f"Error cargando activos: {e}")
        return

    if df_act_db.empty:
        st.warning("⚠️ No hay activos disponibles.")
        return

    mask_no_tinta = ~(
        df_act_db["categoria"].fillna("").str.contains("impres|tinta", case=False, na=False)
        | df_act_db["unidad"].fillna("").str.contains("impres", case=False, na=False)
    )
    otros_equipos = df_act_db[mask_no_tinta].copy()
    otros_equipos["desgaste"] = pd.to_numeric(otros_equipos["desgaste"], errors="coerce").fillna(0.0)

    if otros_equipos.empty:
        st.warning("⚠️ No hay equipos registrados para procesos especiales.")
        return

    records = otros_equipos.to_dict("records")
    nombres_eq = [e["equipo"] for e in records]

    if "lista_procesos" not in st.session_state:
        st.session_state.lista_procesos = []

    with st.container(border=True):
        c1, c2 = st.columns(2)
        eq_sel = c1.selectbox("Selecciona el Proceso/Equipo:", nombres_eq)
        datos_eq = next(e for e in records if e["equipo"] == eq_sel)

        cantidad = c2.number_input(
            f"Cantidad de {datos_eq.get('unidad') or 'unidades'}:",
            min_value=1.0,
            value=1.0,
        )

        costo_unitario = float(datos_eq.get("desgaste", 0.0))
        costo_total = costo_unitario * float(cantidad)

        st.divider()
        r1, r2 = st.columns(2)
        r1.metric("Costo Unitario", f"$ {costo_unitario:.4f}")
        r2.metric("Costo Total", f"$ {costo_total:.2f}")

        if st.button("➕ Agregar Proceso", use_container_width=True):
            st.session_state.lista_procesos.append(
                {
                    "equipo": eq_sel,
                    "cantidad": float(cantidad),
                    "costo_unitario": float(costo_unitario),
                    "costo": float(costo_total),
                    "fecha": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                }
            )
            st.toast("Proceso añadido")

    if st.session_state.lista_procesos:
        st.subheader("📋 Procesos Acumulados")
        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, use_container_width=True, hide_index=True)

        total = float(df_proc["costo"].sum())
        st.metric("Total Procesos", f"$ {total:.2f}")

        p1, p2, p3 = st.columns(3)
        p1.metric("Procesos cargados", int(len(df_proc)))
        p2.metric("Costo promedio por proceso", f"$ {float(df_proc['costo'].mean()):.2f}")
        moda = df_proc["equipo"].mode()
        p3.metric("Equipo más usado", str(moda.iloc[0]) if not moda.empty else "N/D")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📝 Enviar a Cotización", use_container_width=True):
                st.session_state["datos_pre_cotizacion"] = {
                    "trabajo": " + ".join(df_proc["equipo"].tolist()),
                    "costo_base": total,
                    "unidades": 1,
                    "es_proceso_extra": True,
                }
                st.success("Enviado a cotización")
                st.session_state.lista_procesos = []
                st.rerun()

        with col2:
            if st.button("🧹 Limpiar", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

        with col3:
            limpiar_tras_guardar = st.checkbox("Limpiar lista tras guardar", value=True, key="proc_limpiar_tras_guardar")
            if st.button("💾 Guardar en historial", use_container_width=True):
                try:
                    with db_transaction() as conn:
                        _ensure_historial_table(conn)
                        conn.executemany(
                            "INSERT INTO historial_procesos (equipo, cantidad, costo) VALUES (?,?,?)",
                            [
                                (str(r["equipo"]), float(r["cantidad"]), float(r["costo"]))
                                for _, r in df_proc.iterrows()
                            ],
                        )
                    st.success("Procesos guardados en historial.")
                    if limpiar_tras_guardar:
                        st.session_state.lista_procesos = []
                        st.rerun()
                except Exception as e:
                    st.error(f"No se pudo guardar historial: {e}")

    with st.expander("📜 Historial de Procesos"):
        try:
            with db_transaction() as conn:
                _ensure_historial_table(conn)
                df_hist = pd.read_sql_query("SELECT * FROM historial_procesos ORDER BY fecha DESC", conn)

            if df_hist.empty:
                st.info("Sin registros aún.")
            else:
                st.dataframe(df_hist, use_container_width=True, hide_index=True)

        except Exception:
            st.info("Historial no disponible.")



