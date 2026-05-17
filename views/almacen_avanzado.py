from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]
ALMACEN_DIR = BASE_DIR / "almacen"

ARCHIVOS_ALMACEN = {
    "Kardex": "kardex_materiales.csv",
    "Entradas": "entradas_almacen.csv",
    "Salidas": "salidas_almacen.csv",
    "Stock mínimo/máximo": "stock_minimo_maximo.csv",
    "Ubicaciones": "ubicaciones_almacen.csv",
    "Inventario físico": "inventario_fisico.csv",
    "Reservas": "material_reservado_pedidos.csv",
    "Mermas": "mermas_almacen.csv",
    "Herramientas": "herramientas_equipo_menor.csv",
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
    if df.empty:
        st.info("Sin registros todavía.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"Archivo: almacen/{filename}")


def render_almacen_avanzado(usuario: str = "Sistema") -> None:
    _ensure_archivos()

    st.title("📦 Almacén avanzado")
    st.caption("Control físico de inventario: alertas, ubicaciones, reservas, conteos, kardex, entradas, salidas y mermas.")

    stock_df = _read_csv("stock_minimo_maximo.csv")
    reservas_df = _read_csv("material_reservado_pedidos.csv")
    mermas_df = _read_csv("mermas_almacen.csv")
    ubicaciones_df = _read_csv("ubicaciones_almacen.csv")

    total_materiales = len(stock_df) if not stock_df.empty else 0
    criticos = 0
    comprar_pronto = 0
    if not stock_df.empty and "estado" in stock_df.columns:
        estados = stock_df["estado"].fillna("").astype(str).str.lower()
        criticos = int((estados == "critico").sum())
        comprar_pronto = int(estados.str.contains("comprar", na=False).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Materiales controlados", total_materiales)
    col2.metric("Críticos", criticos)
    col3.metric("Comprar pronto", comprar_pronto)
    col4.metric("Ubicaciones", len(ubicaciones_df) if not ubicaciones_df.empty else 0)

    col5, col6, col7 = st.columns(3)
    col5.metric("Reservado", round(_metric_sum(reservas_df, "cantidad_reservada"), 2))
    col6.metric("Merma registrada", round(_metric_sum(mermas_df, "cantidad_perdida"), 2))
    col7.metric("Costo merma", f"${_metric_sum(mermas_df, 'costo_estimado'):,.2f}")

    st.divider()

    tabs = st.tabs([
        "Alertas",
        "Ubicaciones",
        "Reservas",
        "Conteo físico",
        "Kardex",
        "Entradas",
        "Salidas",
        "Mermas",
        "Herramientas",
    ])

    with tabs[0]:
        st.subheader("Alertas de stock")
        if stock_df.empty:
            st.info("Agrega materiales en stock_minimo_maximo.csv para activar alertas.")
        else:
            df = stock_df.copy()
            if {"existencia_actual", "stock_minimo"}.issubset(df.columns):
                existencia = pd.to_numeric(df["existencia_actual"], errors="coerce").fillna(0)
                minimo = pd.to_numeric(df["stock_minimo"], errors="coerce").fillna(0)
                df["alerta_calculada"] = ["critico" if e <= m else "normal" for e, m in zip(existencia, minimo)]
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[1]:
        _render_df("Ubicaciones físicas", "ubicaciones_almacen.csv")

    with tabs[2]:
        _render_df("Material reservado para pedidos", "material_reservado_pedidos.csv")

    with tabs[3]:
        conteo = _read_csv("inventario_fisico.csv")
        st.subheader("Inventario físico")
        if conteo.empty:
            st.info("Sin conteos físicos todavía.")
        else:
            df = conteo.copy()
            if {"existencia_sistema", "conteo_fisico"}.issubset(df.columns):
                df["diferencia_calculada"] = pd.to_numeric(df["conteo_fisico"], errors="coerce").fillna(0) - pd.to_numeric(df["existencia_sistema"], errors="coerce").fillna(0)
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[4]:
        _render_df("Kardex de materiales", "kardex_materiales.csv")

    with tabs[5]:
        _render_df("Entradas de almacén", "entradas_almacen.csv")

    with tabs[6]:
        _render_df("Salidas de almacén", "salidas_almacen.csv")

    with tabs[7]:
        _render_df("Mermas de almacén", "mermas_almacen.csv")

    with tabs[8]:
        _render_df("Herramientas y equipo menor", "herramientas_equipo_menor.csv")
