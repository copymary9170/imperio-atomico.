from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.cmyk.context import _load_contexto_cmyk


def _num(df: pd.DataFrame, column: str) -> pd.Series:
    if df.empty or column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _column_match(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _tintas_disponibles(df_inv: pd.DataFrame) -> pd.DataFrame:
    if df_inv.empty:
        return pd.DataFrame()
    df = df_inv.copy()
    col_nombre = _column_match(df, ["nombre", "item", "sku"])
    col_categoria = _column_match(df, ["categoria", "familia", "tipo"])
    col_stock = _column_match(df, ["stock_actual", "stock", "cantidad"])
    col_min = _column_match(df, ["stock_minimo", "minimo", "min"])
    col_costo = _column_match(df, ["costo_unitario_usd", "costo", "precio_usd"])
    if not col_nombre:
        return pd.DataFrame()

    nombres = df[col_nombre].fillna("").astype(str)
    categorias = df[col_categoria].fillna("").astype(str) if col_categoria else ""
    mask = nombres.str.contains("tinta|ink|cmyk|cyan|magenta|amarillo|yellow|negro|black", case=False, na=False)
    if col_categoria:
        mask = mask | categorias.str.contains("tinta|insumo impres", case=False, na=False)
    df = df[mask].copy()
    if df.empty:
        return df
    df["material"] = df[col_nombre].astype(str)
    df["stock"] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0.0) if col_stock else 0.0
    df["stock_minimo"] = pd.to_numeric(df[col_min], errors="coerce").fillna(0.0) if col_min else 0.0
    df["costo_unitario"] = pd.to_numeric(df[col_costo], errors="coerce").fillna(0.0) if col_costo else 0.0
    df["estado"] = "normal"
    df.loc[df["stock"] <= df["stock_minimo"], "estado"] = "bajo mínimo"
    df.loc[df["stock"] <= 0, "estado"] = "agotado"
    return df[["material", "stock", "stock_minimo", "costo_unitario", "estado"]]


def _historial_normalizado(df_hist: pd.DataFrame) -> pd.DataFrame:
    if df_hist is None or df_hist.empty:
        return pd.DataFrame()
    df = df_hist.copy()
    for col in ["paginas", "costo"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for color in ["C", "M", "Y", "K"]:
        if color in df.columns:
            df[color] = pd.to_numeric(df[color], errors="coerce").fillna(0.0)
    return df


def render_cmyk_control(usuario: str = "Sistema") -> None:
    st.subheader("📊 Control CMYK")
    st.caption("Historial, consumo, alertas de tinta, costo por página y recomendaciones de producción.")

    df_inv, df_act, df_hist = _load_contexto_cmyk()
    hist = _historial_normalizado(df_hist)
    tintas = _tintas_disponibles(df_inv)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Análisis guardados", len(hist) if not hist.empty else 0)
    c2.metric("Páginas analizadas", int(_num(hist, "paginas").sum()) if not hist.empty else 0)
    c3.metric("Costo histórico", f"${float(_num(hist, 'costo').sum()):,.2f}" if not hist.empty else "$0.00")
    costo_pag = float(_num(hist, "costo").sum()) / float(_num(hist, "paginas").sum()) if not hist.empty and float(_num(hist, "paginas").sum()) > 0 else 0.0
    c4.metric("Costo promedio/pág.", f"${costo_pag:,.4f}")

    t1, t2, t3, t4 = st.columns(4)
    if not hist.empty and all(c in hist.columns for c in ["C", "M", "Y", "K"]):
        t1.metric("Cyan ml", f"{float(hist['C'].sum()):,.2f}")
        t2.metric("Magenta ml", f"{float(hist['M'].sum()):,.2f}")
        t3.metric("Yellow ml", f"{float(hist['Y'].sum()):,.2f}")
        t4.metric("Black ml", f"{float(hist['K'].sum()):,.2f}")
    else:
        t1.metric("Cyan ml", "0.00")
        t2.metric("Magenta ml", "0.00")
        t3.metric("Yellow ml", "0.00")
        t4.metric("Black ml", "0.00")

    st.divider()

    tab_hist, tab_tintas, tab_rentabilidad, tab_reco = st.tabs([
        "Historial",
        "Tintas e inventario",
        "Rentabilidad técnica",
        "Recomendaciones",
    ])

    with tab_hist:
        if hist.empty:
            st.info("Todavía no hay historial CMYK guardado.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
            if "fecha" in hist.columns and "costo" in hist.columns:
                chart = hist.copy()
                chart["fecha"] = pd.to_datetime(chart["fecha"], errors="coerce")
                chart = chart.dropna(subset=["fecha"]).sort_values("fecha")
                if not chart.empty:
                    st.line_chart(chart.set_index("fecha")["costo"])

    with tab_tintas:
        if tintas.empty:
            st.warning("No detecté tintas en inventario. Registra tintas como Cyan, Magenta, Yellow/Amarillo y Black/Negro.")
        else:
            st.dataframe(tintas, use_container_width=True, hide_index=True)
            bajas = tintas[tintas["estado"].isin(["bajo mínimo", "agotado"])]
            if not bajas.empty:
                st.warning(f"Hay {len(bajas)} tinta(s) agotadas o bajo mínimo.")
            else:
                st.success("Tintas sin alertas críticas de stock.")

    with tab_rentabilidad:
        if hist.empty:
            st.info("Guarda análisis CMYK para calcular tendencias.")
        else:
            resumen = pd.DataFrame([
                {"Indicador": "Costo total histórico", "Valor": float(_num(hist, "costo").sum())},
                {"Indicador": "Páginas históricas", "Valor": float(_num(hist, "paginas").sum())},
                {"Indicador": "Costo promedio por página", "Valor": costo_pag},
            ])
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            if all(c in hist.columns for c in ["C", "M", "Y", "K"]):
                consumo = pd.DataFrame({
                    "Color": ["C", "M", "Y", "K"],
                    "ml": [float(hist["C"].sum()), float(hist["M"].sum()), float(hist["Y"].sum()), float(hist["K"].sum())],
                })
                st.bar_chart(consumo.set_index("Color")["ml"])

    with tab_reco:
        recomendaciones = []
        if tintas.empty:
            recomendaciones.append("Registrar tintas CMYK en inventario para activar alertas reales de stock.")
        elif not tintas[tintas["estado"].isin(["bajo mínimo", "agotado"])].empty:
            recomendaciones.append("Comprar o recargar tintas que estén bajo mínimo antes de aceptar trabajos grandes.")
        if hist.empty:
            recomendaciones.append("Guardar historial después de cada análisis para medir consumo real por impresora.")
        if costo_pag > 0:
            recomendaciones.append(f"Usar costo base mínimo de ${costo_pag:,.4f} por página antes de margen, papel e impuestos.")
        recomendaciones.append("Comparar CMYK contra cotizaciones para evitar vender trabajos de impresión por debajo del costo.")
        recomendaciones.append("Registrar impresoras en Activos con vida útil para sumar desgaste real al costo técnico.")
        for reco in recomendaciones:
            st.write(f"- {reco}")
