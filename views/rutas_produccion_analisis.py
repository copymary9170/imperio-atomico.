from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _load_rutas() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            return pd.read_sql_query(
                """
                SELECT id, codigo, nombre, version, version_activa, estado,
                       tiempo_total_min, tiempo_real_total_min,
                       costo_base_usd, costo_real_total_usd
                FROM rutas_produccion
                ORDER BY actualizado_en DESC, id DESC
                """,
                conn,
            )
        except Exception:
            return pd.DataFrame()


def _load_detalle(ruta_id: int) -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            return pd.read_sql_query(
                """
                SELECT d.id, d.secuencia, d.proceso, d.centro_trabajo, d.maquina,
                       d.operario, d.insumo_principal, d.depende_de_detalle_id,
                       dep.proceso AS depende_de_proceso,
                       d.tiempo_estimado_min, d.tiempo_real_min,
                       d.costo_estimado_usd, d.costo_real_usd,
                       d.punto_control, d.requiere_mantenimiento,
                       d.requiere_aprobacion_calidad, d.observaciones
                FROM rutas_produccion_detalle d
                LEFT JOIN rutas_produccion_detalle dep ON dep.id = d.depende_de_detalle_id
                WHERE d.ruta_id = ?
                ORDER BY d.secuencia ASC, d.id ASC
                """,
                conn,
                params=(int(ruta_id),),
            )
        except Exception:
            return pd.DataFrame()


def _load_recursos(ruta_id: int) -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            return pd.read_sql_query(
                """
                SELECT r.id, r.detalle_id, d.proceso, r.tipo_recurso, r.nombre,
                       r.cantidad, r.unidad, r.costo_unitario_usd, r.costo_total_usd
                FROM rutas_produccion_recursos r
                LEFT JOIN rutas_produccion_detalle d ON d.id = r.detalle_id
                WHERE r.ruta_id = ?
                ORDER BY r.tipo_recurso ASC, r.nombre ASC
                """,
                conn,
                params=(int(ruta_id),),
            )
        except Exception:
            return pd.DataFrame()


def _num(series, default: float = 0.0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _auditar_ruta(detalle: pd.DataFrame, recursos: pd.DataFrame) -> list[str]:
    problemas: list[str] = []
    if detalle.empty:
        return ["La ruta no tiene pasos registrados."]

    if (_num(detalle["tiempo_estimado_min"]) <= 0).any():
        problemas.append("Hay pasos sin tiempo estándar.")
    if (_num(detalle["costo_estimado_usd"]) <= 0).any():
        problemas.append("Hay pasos sin costo estándar.")
    if "operario" in detalle.columns and detalle["operario"].fillna("").astype(str).str.strip().eq("").any():
        problemas.append("Hay pasos sin operario/responsable.")
    if "maquina" in detalle.columns and detalle["maquina"].fillna("").astype(str).str.strip().eq("").any():
        problemas.append("Hay pasos sin máquina/equipo definido.")
    if "insumo_principal" in detalle.columns and detalle["insumo_principal"].fillna("").astype(str).str.strip().eq("").any():
        problemas.append("Hay pasos sin insumo principal.")

    ids = set(pd.to_numeric(detalle["id"], errors="coerce").dropna().astype(int).tolist())
    deps = pd.to_numeric(detalle["depende_de_detalle_id"], errors="coerce").dropna().astype(int).tolist()
    rotas = [dep for dep in deps if dep not in ids]
    if rotas:
        problemas.append(f"Hay dependencias rotas: {sorted(set(rotas))}.")

    if "requiere_aprobacion_calidad" in detalle.columns and (_num(detalle["requiere_aprobacion_calidad"]) == 1).any():
        if not ("punto_control" in detalle.columns and (_num(detalle["punto_control"]) == 1).any()):
            problemas.append("Hay pasos que bloquean por calidad, pero ningún punto de control marcado.")

    if not recursos.empty and "detalle_id" in recursos.columns:
        sin_paso = recursos["detalle_id"].isna().sum()
        if int(sin_paso) > 0:
            problemas.append(f"Hay {int(sin_paso)} recursos generales sin paso asociado.")

    return problemas


def _render_mapa(detalle: pd.DataFrame) -> None:
    st.subheader("🗺️ Mapa visual de ruta")
    if detalle.empty:
        st.info("No hay pasos para mostrar.")
        return

    for _, row in detalle.iterrows():
        badges = []
        if int(row.get("punto_control") or 0) == 1:
            badges.append("✅ Control")
        if int(row.get("requiere_mantenimiento") or 0) == 1:
            badges.append("🛠️ Mant.")
        if int(row.get("requiere_aprobacion_calidad") or 0) == 1:
            badges.append("🔒 Calidad")
        dep = row.get("depende_de_proceso") or "Sin dependencia"
        st.markdown(
            f"""
            <div style="border:1px solid rgba(128,128,128,.35); border-radius:14px; padding:12px; margin:8px 0;">
              <b>Paso {int(row.get('secuencia') or 0)} · {row.get('proceso') or ''}</b><br/>
              <span>Depende de: {dep}</span><br/>
              <span>Máquina: {row.get('maquina') or 'N/D'} · Operario: {row.get('operario') or 'N/D'} · Insumo: {row.get('insumo_principal') or 'N/D'}</span><br/>
              <span>Tiempo: {float(row.get('tiempo_estimado_min') or 0):.2f} min estándar / {float(row.get('tiempo_real_min') or 0):.2f} min real · Costo: ${float(row.get('costo_estimado_usd') or 0):.2f} estándar / ${float(row.get('costo_real_usd') or 0):.2f} real</span><br/>
              <span>{' · '.join(badges) if badges else 'Sin bloqueos especiales'}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_rutas_produccion_analisis(usuario: str = "Sistema") -> None:
    st.subheader("🧠 Análisis de ruta")
    st.caption("Mapa visual, auditoría, desviaciones estándar vs real y cuellos de botella.")

    rutas = _load_rutas()
    if rutas.empty:
        st.info("Primero crea una ruta de producción.")
        return

    ruta_id = st.selectbox(
        "Ruta a analizar",
        rutas["id"].tolist(),
        format_func=lambda x: f"{rutas[rutas['id'] == x]['codigo'].iloc[0]} v{int(rutas[rutas['id'] == x]['version'].iloc[0])} · {rutas[rutas['id'] == x]['nombre'].iloc[0]}",
        key="analisis_ruta_id",
    )

    detalle = _load_detalle(int(ruta_id))
    recursos = _load_recursos(int(ruta_id))

    if detalle.empty:
        st.warning("Esta ruta no tiene pasos. Agrega pasos para activar el análisis.")
        return

    detalle = detalle.copy()
    detalle["desviacion_tiempo_min"] = _num(detalle["tiempo_real_min"]) - _num(detalle["tiempo_estimado_min"])
    detalle["desviacion_costo_usd"] = _num(detalle["costo_real_usd"]) - _num(detalle["costo_estimado_usd"])
    detalle["desviacion_tiempo_pct"] = detalle.apply(
        lambda r: 0 if float(r["tiempo_estimado_min"] or 0) == 0 else (float(r["desviacion_tiempo_min"]) / float(r["tiempo_estimado_min"])) * 100,
        axis=1,
    )
    detalle["desviacion_costo_pct"] = detalle.apply(
        lambda r: 0 if float(r["costo_estimado_usd"] or 0) == 0 else (float(r["desviacion_costo_usd"]) / float(r["costo_estimado_usd"])) * 100,
        axis=1,
    )

    tiempo_est = float(_num(detalle["tiempo_estimado_min"]).sum())
    tiempo_real = float(_num(detalle["tiempo_real_min"]).sum())
    costo_est = float(_num(detalle["costo_estimado_usd"]).sum())
    costo_real = float(_num(detalle["costo_real_usd"]).sum())
    costo_recursos = float(_num(recursos["costo_total_usd"]).sum()) if not recursos.empty and "costo_total_usd" in recursos.columns else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pasos", len(detalle))
    c2.metric("Tiempo real vs estándar", f"{tiempo_real:.1f} / {tiempo_est:.1f} min", f"{tiempo_real - tiempo_est:.1f} min")
    c3.metric("Costo real vs estándar", f"${costo_real:,.2f} / ${costo_est:,.2f}", f"${costo_real - costo_est:,.2f}")
    c4.metric("Costo recursos", f"${costo_recursos:,.2f}")

    tab_mapa, tab_auditoria, tab_desviaciones, tab_cuellos = st.tabs([
        "🗺️ Mapa",
        "✅ Auditoría",
        "📉 Desviaciones",
        "🚧 Cuellos de botella",
    ])

    with tab_mapa:
        _render_mapa(detalle)

    with tab_auditoria:
        problemas = _auditar_ruta(detalle, recursos)
        if problemas:
            for problema in problemas:
                st.warning(problema)
        else:
            st.success("La ruta no presenta problemas básicos de configuración.")

    with tab_desviaciones:
        st.dataframe(
            detalle[[
                "secuencia", "proceso", "tiempo_estimado_min", "tiempo_real_min",
                "desviacion_tiempo_min", "desviacion_tiempo_pct",
                "costo_estimado_usd", "costo_real_usd", "desviacion_costo_usd", "desviacion_costo_pct",
            ]],
            use_container_width=True,
            hide_index=True,
        )

    with tab_cuellos:
        col_a, col_b = st.columns(2)
        mas_largo = detalle.sort_values("tiempo_estimado_min", ascending=False).head(5)
        mas_caro = detalle.sort_values("costo_estimado_usd", ascending=False).head(5)
        col_a.markdown("#### Pasos más largos")
        col_a.dataframe(mas_largo[["secuencia", "proceso", "tiempo_estimado_min", "maquina", "operario"]], use_container_width=True, hide_index=True)
        col_b.markdown("#### Pasos más caros")
        col_b.dataframe(mas_caro[["secuencia", "proceso", "costo_estimado_usd", "maquina", "insumo_principal"]], use_container_width=True, hide_index=True)

        st.markdown("#### Recomendaciones")
        if not mas_largo.empty:
            st.write(f"Revisar capacidad y tiempos del paso más largo: **{mas_largo.iloc[0]['proceso']}**.")
        if not mas_caro.empty:
            st.write(f"Revisar costo estándar del paso más caro: **{mas_caro.iloc[0]['proceso']}**.")
        calidad = detalle[_num(detalle["requiere_aprobacion_calidad"]) == 1]
        if not calidad.empty:
            st.write(f"Hay {len(calidad)} paso(s) que bloquean por calidad; asegúrate de tener criterios de aprobación definidos.")
