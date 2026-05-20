from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]
ACTIVOS_DIR = BASE_DIR / "activos"

ARCHIVOS_ACTIVOS = {
    "Documentos CSV": "documentos_activos.csv",
    "Garantías CSV": "garantias_activos.csv",
    "Asignaciones CSV": "asignaciones_activos.csv",
    "Ubicaciones CSV": "ubicaciones_activos.csv",
    "Bajas CSV": "bajas_activos.csv",
    "Depreciación CSV": "depreciacion_activos.csv",
    "Seguros CSV": "seguros_activos.csv",
    "Plan preventivo CSV": "plan_mantenimiento_preventivo.csv",
    "Costos mantenimiento CSV": "costos_mantenimiento_activos.csv",
}

PLANTILLAS = {
    "documentos_activos.csv": "documento_id,activo_id,activo,tipo_documento,nombre_documento,archivo_o_url,fecha_documento,responsable,estado,observaciones\n",
    "garantias_activos.csv": "garantia_id,activo_id,activo,proveedor,fecha_compra,fecha_inicio,fecha_fin,cobertura,estado,documento_garantia,observaciones\n",
    "asignaciones_activos.csv": "asignacion_id,activo_id,activo,responsable,area,fecha_asignacion,fecha_devolucion,estado,condicion_entrega,condicion_devolucion,observaciones\n",
    "ubicaciones_activos.csv": "activo_id,activo,area,zona,ubicacion_exacta,responsable,fecha_actualizacion,observaciones\n",
    "bajas_activos.csv": "baja_id,activo_id,activo,fecha_baja,motivo,valor_en_libros,valor_recuperado,responsable,autorizado_por,estado,observaciones\n",
    "depreciacion_activos.csv": "activo_id,activo,fecha_compra,costo_original,vida_util_meses,depreciacion_mensual,depreciacion_acumulada,valor_en_libros,estado,observaciones\n",
    "seguros_activos.csv": "seguro_id,activo_id,activo,aseguradora,poliza,fecha_inicio,fecha_fin,cobertura,monto_asegurado,costo_seguro,estado,observaciones\n",
    "plan_mantenimiento_preventivo.csv": "plan_id,activo_id,activo,tipo_mantenimiento,frecuencia,cada_cuantos,unidad_frecuencia,proxima_fecha,proximo_uso,responsable,estado,observaciones\n",
    "costos_mantenimiento_activos.csv": "activo_id,activo,periodo,mantenimiento_preventivo,mantenimiento_correctivo,repuestos,mano_obra,total_mantenimiento,observaciones\n",
}


def _ensure_archivos() -> None:
    ACTIVOS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, header in PLANTILLAS.items():
        path = ACTIVOS_DIR / filename
        if not path.exists():
            path.write_text(header, encoding="utf-8")


def _read_csv(filename: str) -> pd.DataFrame:
    path = ACTIVOS_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.read_csv(path, encoding="latin-1")


def _sum_column(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _render_table(title: str, filename: str) -> None:
    df = _read_csv(filename)
    st.subheader(title)
    st.caption("Histórico/plantilla CSV. La operación principal de activos vive en Equipos / Operación y Mantenimiento operativo.")
    if df.empty:
        st.info("Sin registros todavía.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            f"⬇️ Descargar {filename}",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=filename,
            mime="text/csv",
            use_container_width=True,
        )
    st.caption(f"Archivo: activos/{filename}")


def render_activos_patrimonial(usuario: str = "Sistema") -> None:
    _ensure_archivos()

    st.title("🧾 Patrimonio / Históricos CSV de activos")
    st.caption("Documentos, garantías, responsables, ubicaciones, bajas, depreciación, seguros y costos conservados como archivos históricos/plantillas.")

    documentos = _read_csv("documentos_activos.csv")
    garantias = _read_csv("garantias_activos.csv")
    asignaciones = _read_csv("asignaciones_activos.csv")
    ubicaciones = _read_csv("ubicaciones_activos.csv")
    bajas = _read_csv("bajas_activos.csv")
    depreciacion = _read_csv("depreciacion_activos.csv")
    seguros = _read_csv("seguros_activos.csv")
    costos = _read_csv("costos_mantenimiento_activos.csv")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documentos CSV", len(documentos) if not documentos.empty else 0)
    col2.metric("Garantías CSV", len(garantias) if not garantias.empty else 0)
    col3.metric("Asignaciones CSV", len(asignaciones) if not asignaciones.empty else 0)
    col4.metric("Ubicaciones CSV", len(ubicaciones) if not ubicaciones.empty else 0)

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Bajas CSV", len(bajas) if not bajas.empty else 0)
    col6.metric("Valor en libros CSV", f"${_sum_column(depreciacion, 'valor_en_libros'):,.2f}")
    col7.metric("Monto asegurado CSV", f"${_sum_column(seguros, 'monto_asegurado'):,.2f}")
    col8.metric("Costo mant. CSV", f"${_sum_column(costos, 'total_mantenimiento'):,.2f}")

    st.info("Se salvaron estos archivos como históricos/plantillas. El mantenimiento operativo ahora está en la pestaña 🛠️ Mantenimiento operativo.")

    alertas = []
    if not garantias.empty and "estado" in garantias.columns:
        vencidas = garantias[garantias["estado"].fillna("").astype(str).str.lower().isin(["vencida", "vencido", "expirada", "expirado"])]
        if not vencidas.empty:
            alertas.append(f"Garantías vencidas en CSV: {len(vencidas)}")
    if not documentos.empty and "estado" in documentos.columns:
        pendientes = documentos[documentos["estado"].fillna("").astype(str).str.lower().isin(["pendiente", "faltante", "por subir"])]
        if not pendientes.empty:
            alertas.append(f"Documentos pendientes en CSV: {len(pendientes)}")
    if not asignaciones.empty and "estado" in asignaciones.columns:
        asignados = asignaciones[asignaciones["estado"].fillna("").astype(str).str.lower().eq("asignado")]
        if not asignados.empty:
            alertas.append(f"Activos asignados en CSV: {len(asignados)}")
    if not bajas.empty and "estado" in bajas.columns:
        borradores = bajas[bajas["estado"].fillna("").astype(str).str.lower().isin(["borrador", "pendiente", "por aprobar"])]
        if not borradores.empty:
            alertas.append(f"Bajas pendientes en CSV: {len(borradores)}")

    if alertas:
        st.warning(" · ".join(alertas))
    else:
        st.success("Sin alertas patrimoniales críticas registradas en CSV.")

    tabs = st.tabs([
        "Documentos CSV",
        "Garantías CSV",
        "Asignaciones CSV",
        "Ubicaciones CSV",
        "Bajas CSV",
        "Depreciación CSV",
        "Seguros CSV",
        "Plan preventivo CSV",
        "Costos mant. CSV",
        "Plantillas guardadas",
    ])

    with tabs[0]:
        _render_table("Documentos del activo", "documentos_activos.csv")
    with tabs[1]:
        _render_table("Garantías de activos", "garantias_activos.csv")
    with tabs[2]:
        _render_table("Asignación de responsables", "asignaciones_activos.csv")
    with tabs[3]:
        _render_table("Ubicación física de activos", "ubicaciones_activos.csv")
    with tabs[4]:
        _render_table("Bajas y retiros", "bajas_activos.csv")
    with tabs[5]:
        _render_table("Depreciación contable", "depreciacion_activos.csv")
    with tabs[6]:
        _render_table("Seguros de activos", "seguros_activos.csv")
    with tabs[7]:
        _render_table("Plan de mantenimiento preventivo legado", "plan_mantenimiento_preventivo.csv")
    with tabs[8]:
        _render_table("Costos acumulados de mantenimiento legado", "costos_mantenimiento_activos.csv")
    with tabs[9]:
        resumen = pd.DataFrame([
            {"nombre": nombre, "archivo": archivo, "ruta": f"activos/{archivo}"}
            for nombre, archivo in ARCHIVOS_ACTIVOS.items()
        ])
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar índice de plantillas de activos",
            data=resumen.to_csv(index=False).encode("utf-8-sig"),
            file_name="indice_plantillas_activos.csv",
            mime="text/csv",
            use_container_width=True,
        )
