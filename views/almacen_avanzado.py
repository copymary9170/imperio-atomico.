from pathlib import Path

import pandas as pd
import streamlit as st

from views.stock_minimo import render_stock_minimo

BASE_DIR = Path(__file__).resolve().parents[1]
ALMACEN_DIR = BASE_DIR / "almacen"

ARCHIVOS_ALMACEN = {
    "Kardex histórico CSV": "kardex_materiales.csv",
    "Entradas históricas CSV": "entradas_almacen.csv",
    "Salidas históricas CSV": "salidas_almacen.csv",
    "Stock mínimo/máximo legado CSV": "stock_minimo_maximo.csv",
    "Ubicaciones físicas CSV": "ubicaciones_almacen.csv",
    "Inventario físico CSV": "inventario_fisico.csv",
    "Reservas CSV": "material_reservado_pedidos.csv",
    "Mermas CSV": "mermas_almacen.csv",
    "Herramientas CSV": "herramientas_equipo_menor.csv",
}

PLANTILLAS = {
    "entradas_almacen.csv": "entrada_id,fecha,proveedor,material_id,material,cantidad,unidad,costo_unitario,costo_total,orden_compra,comprobante,responsable_revision,estado,observaciones\n",
    "salidas_almacen.csv": "salida_id,fecha,area_solicitante,pedido_id,material_id,material,cantidad,unidad,solicitado_por,autorizado_por,entregado_por,estado,observaciones\n",
    "stock_minimo_maximo.csv": "material_id,material,categoria,unidad,stock_minimo,stock_maximo,existencia_actual,punto_reorden,cantidad_sugerida_compra,proveedor_preferido,estado,observaciones\n",
    "ubicaciones_almacen.csv": "ubicacion_id,zona,estante,nivel,caja_o_contenedor,descripcion,material_id,material,cantidad_actual,unidad,responsable,observaciones\n",
    "inventario_fisico.csv": "conteo_id,fecha,material_id,material,existencia_sistema,conteo_fisico,diferencia,unidad,responsable_conteo,responsable_revision,accion_correctiva,observaciones\n",
    "material_reservado_pedidos.csv": "reserva_id,fecha,pedido_id,cliente,material_id,material,cantidad_reservada,unidad,estado_pedido,fecha_liberacion,responsable,observaciones\n",
    "mermas_almacen.csv": "merma_id,fecha,material_id,material,cantidad_perdida,unidad,motivo,costo_estimado,responsable,accion_correctiva,observaciones\n",
    "herramientas_equipo_menor.csv": "herramienta_id,nombre,categoria,ubicacion,estado,asignado_a,fecha_asignacion,fecha_devolucion,valor_estimado,responsable,observaciones\n",
}


def _ensure_archivos() -> None:
    ALMACEN_DIR.mkdir(parents=True, exist_ok=True)
    for filename, header in PLANTILLAS.items():
        path = ALMACEN_DIR / filename
        if not path.exists():
            path.write_text(header, encoding="utf-8")


def _read_csv(filename: str) -> pd.DataFrame:
    path = ALMACEN_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.read_csv(path, encoding="latin-1")


def _metric_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _render_df(title: str, filename: str) -> None:
    df = _read_csv(filename)
    st.subheader(title)
    st.caption("Vista conservada como archivo histórico/plantilla CSV. La operación principal debe moverse a tablas SQLite cuando aplique.")
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
    st.caption(f"Archivo: almacen/{filename}")


def render_almacen_avanzado(usuario: str = "Sistema") -> None:
    _ensure_archivos()

    st.title("🏬 Almacén físico / Históricos CSV")
    st.caption("Conserva ubicaciones, conteos, reservas, mermas, entradas, salidas y plantillas CSV. Stock mínimo real vive en SQLite.")

    stock_df = _read_csv("stock_minimo_maximo.csv")
    reservas_df = _read_csv("material_reservado_pedidos.csv")
    mermas_df = _read_csv("mermas_almacen.csv")
    ubicaciones_df = _read_csv("ubicaciones_almacen.csv")
    entradas_df = _read_csv("entradas_almacen.csv")
    salidas_df = _read_csv("salidas_almacen.csv")

    total_materiales_legado = len(stock_df) if not stock_df.empty else 0
    ubicaciones = len(ubicaciones_df) if not ubicaciones_df.empty else 0
    entradas = len(entradas_df) if not entradas_df.empty else 0
    salidas = len(salidas_df) if not salidas_df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Materiales legado CSV", total_materiales_legado)
    col2.metric("Ubicaciones CSV", ubicaciones)
    col3.metric("Entradas CSV", entradas)
    col4.metric("Salidas CSV", salidas)

    col5, col6, col7 = st.columns(3)
    col5.metric("Reservado CSV", round(_metric_sum(reservas_df, "cantidad_reservada"), 2))
    col6.metric("Merma CSV", round(_metric_sum(mermas_df, "cantidad_perdida"), 2))
    col7.metric("Costo merma CSV", f"${_metric_sum(mermas_df, 'costo_estimado'):,.2f}")

    st.info("Se salvaron los archivos CSV valiosos como históricos/plantillas. Para alertas operativas usa la pestaña Stock mínimo / Reposición.")

    tabs = st.tabs([
        "📉 Stock mínimo / Reposición",
        "Ubicaciones CSV",
        "Reservas CSV",
        "Conteo físico CSV",
        "Kardex histórico CSV",
        "Entradas CSV",
        "Salidas CSV",
        "Mermas CSV",
        "Herramientas CSV",
        "Plantillas guardadas",
    ])

    with tabs[0]:
        render_stock_minimo(usuario)
    with tabs[1]:
        _render_df("Ubicaciones físicas", "ubicaciones_almacen.csv")
    with tabs[2]:
        _render_df("Material reservado para pedidos", "material_reservado_pedidos.csv")
    with tabs[3]:
        conteo = _read_csv("inventario_fisico.csv")
        st.subheader("Inventario físico CSV")
        st.caption("Histórico/plantilla para conteos físicos. No reemplaza el inventario operativo.")
        if conteo.empty:
            st.info("Sin conteos físicos todavía.")
        else:
            df = conteo.copy()
            if {"existencia_sistema", "conteo_fisico"}.issubset(df.columns):
                df["diferencia_calculada"] = pd.to_numeric(df["conteo_fisico"], errors="coerce").fillna(0) - pd.to_numeric(df["existencia_sistema"], errors="coerce").fillna(0)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar inventario_fisico.csv", data=df.to_csv(index=False).encode("utf-8-sig"), file_name="inventario_fisico.csv", mime="text/csv", use_container_width=True)
    with tabs[4]:
        _render_df("Kardex histórico de materiales", "kardex_materiales.csv")
    with tabs[5]:
        _render_df("Entradas históricas de almacén", "entradas_almacen.csv")
    with tabs[6]:
        _render_df("Salidas históricas de almacén", "salidas_almacen.csv")
    with tabs[7]:
        _render_df("Mermas históricas de almacén", "mermas_almacen.csv")
    with tabs[8]:
        _render_df("Herramientas y equipo menor", "herramientas_equipo_menor.csv")
    with tabs[9]:
        resumen = pd.DataFrame([
            {"nombre": nombre, "archivo": archivo, "ruta": f"almacen/{archivo}"}
            for nombre, archivo in ARCHIVOS_ALMACEN.items()
        ])
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar índice de plantillas CSV", data=resumen.to_csv(index=False).encode("utf-8-sig"), file_name="indice_plantillas_almacen.csv", mime="text/csv", use_container_width=True)
