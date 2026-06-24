from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


PROCESOS_PREDEFINIDOS = {
    "✨ Acabados": [
        "Aplicación de foil",
        "Laminado mate",
        "Laminado brillante",
        "Plastificado",
        "Barniz o protección",
        "Relieve / embossing",
        "Redondeado de esquinas",
    ],
    "✂️ Corte y preparación": [
        "Corte manual",
        "Corte en Cameo",
        "Troquelado",
        "Depilado de vinil",
        "Perforado",
        "Hendido / marcado para doblar",
    ],
    "🧩 Ensamblaje": [
        "Pegado por capas",
        "Colocación de palitos",
        "Armado de topper",
        "Armado de caja",
        "Armado de carpeta",
        "Armado de souvenir",
        "Montaje de piezas",
    ],
    "📦 Terminación": [
        "Control visual final",
        "Limpieza del producto",
        "Etiquetado",
        "Empaque",
        "Preparación para entrega",
    ],
}


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


def _cargar_equipos() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            _ensure_historial_table(conn)
            _ensure_activos_table(conn)
            df = pd.read_sql_query(
                "SELECT equipo, categoria, unidad, desgaste "
                "FROM activos WHERE COALESCE(activo,1)=1",
                conn,
            )
    except Exception:
        return pd.DataFrame(columns=["equipo", "categoria", "unidad", "desgaste"])

    if df.empty:
        return df

    mask_no_tinta = ~(
        df["categoria"].fillna("").str.contains("impres|tinta", case=False, na=False)
        | df["unidad"].fillna("").str.contains("impres", case=False, na=False)
    )
    equipos = df[mask_no_tinta].copy()
    equipos["desgaste"] = pd.to_numeric(
        equipos["desgaste"], errors="coerce"
    ).fillna(0.0)
    return equipos


def render_otros_procesos(usuario: str, integrado_en_produccion: bool = False):
    if not integrado_en_produccion:
        st.title("🛠️ Acabados y ensamblaje")

    st.info(
        "Registra los procesos posteriores a la impresión o corte: foil, laminado, "
        "pegado, armado, control final y empaque."
    )

    if "datos_proceso_desde_cmyk" in st.session_state:
        p_cmyk = st.session_state.get("datos_proceso_desde_cmyk", {})
        st.success(
            f"Trabajo recibido desde CMYK: {p_cmyk.get('trabajo', 'N/D')} "
            f"({p_cmyk.get('unidades', 0)} uds)"
        )
        st.caption(str(p_cmyk.get("observacion", "")))
        if st.button("Limpiar envío CMYK", key="btn_clear_cmyk_proc"):
            st.session_state.pop("datos_proceso_desde_cmyk", None)
            st.rerun()

    equipos = _cargar_equipos()
    if "lista_procesos" not in st.session_state:
        st.session_state.lista_procesos = []

    with st.container(border=True):
        st.subheader("➕ Agregar etapa al trabajo")
        c1, c2 = st.columns(2)
        categoria = c1.selectbox(
            "Etapa del proceso",
            list(PROCESOS_PREDEFINIDOS.keys()) + ["🛠️ Equipo registrado", "➕ Personalizado"],
        )

        if categoria in PROCESOS_PREDEFINIDOS:
            proceso = c2.selectbox("Proceso", PROCESOS_PREDEFINIDOS[categoria])
            costo_sugerido = 0.0
            unidad_sugerida = "unidades"
        elif categoria == "🛠️ Equipo registrado" and not equipos.empty:
            proceso = c2.selectbox("Equipo o proceso", equipos["equipo"].tolist())
            fila = equipos[equipos["equipo"] == proceso].iloc[0]
            costo_sugerido = float(fila.get("desgaste", 0.0) or 0.0)
            unidad_sugerida = str(fila.get("unidad") or "unidades")
        elif categoria == "🛠️ Equipo registrado":
            c2.warning("No hay equipos especiales registrados. Usa un proceso personalizado.")
            proceso = "Proceso sin equipo"
            costo_sugerido = 0.0
            unidad_sugerida = "unidades"
        else:
            proceso = c2.text_input("Nombre del proceso", placeholder="Ej.: colocación de cinta doble faz")
            costo_sugerido = 0.0
            unidad_sugerida = "unidades"

        c3, c4, c5 = st.columns(3)
        cantidad = c3.number_input(
            f"Cantidad ({unidad_sugerida})",
            min_value=1.0,
            value=1.0,
            step=1.0,
        )
        costo_unitario = c4.number_input(
            "Costo unitario ($)",
            min_value=0.0,
            value=float(costo_sugerido),
            step=0.01,
            format="%.4f",
        )
        minutos = c5.number_input(
            "Tiempo estimado (min)",
            min_value=0.0,
            value=0.0,
            step=1.0,
        )

        observacion = st.text_input(
            "Detalle u observación",
            placeholder="Ej.: foil dorado, pegado en 3 capas o empaque individual",
        )
        costo_total = float(costo_unitario) * float(cantidad)
        m1, m2 = st.columns(2)
        m1.metric("Costo de la etapa", f"$ {costo_total:.2f}")
        m2.metric("Tiempo estimado", f"{float(minutos):.0f} min")

        if st.button("➕ Agregar al flujo de producción", use_container_width=True):
            if not str(proceso).strip():
                st.warning("Escribe o selecciona un proceso.")
            else:
                st.session_state.lista_procesos.append(
                    {
                        "etapa": categoria,
                        "proceso": str(proceso).strip(),
                        "cantidad": float(cantidad),
                        "costo_unitario": float(costo_unitario),
                        "costo": costo_total,
                        "tiempo_min": float(minutos),
                        "observacion": observacion,
                        "fecha": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                    }
                )
                st.toast("Etapa añadida al flujo")

    if st.session_state.lista_procesos:
        st.subheader("🔄 Flujo de acabados y ensamblaje")
        df_proc = pd.DataFrame(st.session_state.lista_procesos)
        st.dataframe(df_proc, use_container_width=True, hide_index=True)

        total = float(df_proc["costo"].sum())
        tiempo_total = float(df_proc.get("tiempo_min", pd.Series(dtype=float)).sum())
        p1, p2, p3 = st.columns(3)
        p1.metric("Etapas cargadas", int(len(df_proc)))
        p2.metric("Costo total", f"$ {total:.2f}")
        p3.metric("Tiempo total", f"{tiempo_total:.0f} min")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📝 Enviar a cotización", use_container_width=True):
                st.session_state["datos_pre_cotizacion"] = {
                    "trabajo": " + ".join(df_proc["proceso"].tolist()),
                    "costo_base": total,
                    "unidades": 1,
                    "es_proceso_extra": True,
                }
                st.success("Flujo enviado a cotización")

        with col2:
            if st.button("🧹 Limpiar flujo", use_container_width=True):
                st.session_state.lista_procesos = []
                st.rerun()

        with col3:
            if st.button("💾 Guardar historial", use_container_width=True):
                try:
                    with db_transaction() as conn:
                        _ensure_historial_table(conn)
                        conn.executemany(
                            "INSERT INTO historial_procesos (equipo, cantidad, costo) VALUES (?,?,?)",
                            [
                                (str(r["proceso"]), float(r["cantidad"]), float(r["costo"]))
                                for _, r in df_proc.iterrows()
                            ],
                        )
                    st.success("Flujo guardado en el historial.")
                except Exception as e:
                    st.error(f"No se pudo guardar el historial: {e}")

    with st.expander("📜 Historial de acabados y ensamblaje"):
        try:
            with db_transaction() as conn:
                _ensure_historial_table(conn)
                df_hist = pd.read_sql_query(
                    "SELECT * FROM historial_procesos ORDER BY fecha DESC", conn
                )
            if df_hist.empty:
                st.info("Sin registros todavía.")
            else:
                st.dataframe(df_hist, use_container_width=True, hide_index=True)
        except Exception:
            st.info("Historial no disponible.")
