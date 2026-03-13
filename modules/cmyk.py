from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

from database.connection import db_transaction
from modules.engine import simular_ganancia_pre_impresion


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if float(b or 0) else 0.0


def _table_columns(conn, table: str) -> set[str]:
    try:
        return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _normalizar_imagenes(archivo) -> list[tuple[str, Image.Image]]:
    bytes_data = archivo.read()
    nombre = archivo.name

    if nombre.lower().endswith(".pdf"):
        try:
            import fitz  # type: ignore
        except ModuleNotFoundError:
            raise RuntimeError(
                "Falta PyMuPDF (fitz) para analizar PDF. "
                "Puedes subir PNG/JPG o instalar la dependencia."
            )

        paginas: list[tuple[str, Image.Image]] = []
        doc = fitz.open(stream=bytes_data, filetype="pdf")
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(colorspace=fitz.csCMYK, dpi=150)
            img = Image.frombytes("CMYK", [pix.width, pix.height], pix.samples)
            paginas.append((f"{nombre} (P{i + 1})", img))
        doc.close()
        return paginas

    img = Image.open(io.BytesIO(bytes_data)).convert("CMYK")
    return [(nombre, img)]


def _analizar_pagina(
    img_obj: Image.Image,
    ml_base_pagina: float,
    factor_general: float,
    factor_calidad: float,
    factor_papel: float,
    factor_k: float,
    auto_negro_inteligente: bool,
    refuerzo_negro: float,
) -> dict[str, float]:
    arr = np.array(img_obj)

    c_chan = arr[:, :, 0] / 255.0
    m_chan = arr[:, :, 1] / 255.0
    y_chan = arr[:, :, 2] / 255.0
    k_chan = arr[:, :, 3] / 255.0

    c_media = float(np.mean(c_chan))
    m_media = float(np.mean(m_chan))
    y_media = float(np.mean(y_chan))
    k_media = float(np.mean(k_chan))

    base = ml_base_pagina * factor_general * factor_calidad * factor_papel

    ml_c = c_media * base
    ml_m = m_media * base
    ml_y = y_media * base
    ml_k_base = k_media * base * factor_k

    if auto_negro_inteligente:
        cobertura_cmy = (c_chan + m_chan + y_chan) / 3.0
       neutral_mask = (np.abs(c_chan - m_chan) < 0.08) & (np.abs(m_chan - y_chan) < 0.08)
        shadow_mask = (k_chan > 0.45) | (cobertura_cmy > 0.60)
        rich_black_mask = shadow_mask & (cobertura_cmy > 0.35)

        ratio_extra = (
            float(np.mean(shadow_mask)) * 0.12
            + float(np.mean(neutral_mask)) * 0.10
            + float(np.mean(rich_black_mask)) * 0.18
        )
        k_extra_ml = ml_base_pagina * factor_general * ratio_extra
    else:
        promedio_color = (c_media + m_media + y_media) / 3.0
        k_extra_ml = promedio_color * refuerzo_negro * factor_general if promedio_color > 0.55 else 0.0

    ml_k = ml_k_base + k_extra_ml

    return {
        "C (ml)": float(ml_c),
        "M (ml)": float(ml_m),
        "Y (ml)": float(ml_y),
        "K (ml)": float(ml_k),
        "K extra auto (ml)": float(k_extra_ml),
    }


def _load_contexto_cmyk() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with db_transaction() as conn:
        cols_inv = _table_columns(conn, "inventario")
        df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)

        if "estado" in cols_inv and not df_inv.empty:
            df_inv = df_inv[df_inv["estado"].fillna("activo").str.lower() == "activo"].copy()

        cols_act = _table_columns(conn, "activos")
        if cols_act:
            campos = [c for c in ["id", "equipo", "nombre", "categoria", "unidad", "modelo", "estado", "activo"] if c in cols_act]
            df_act = pd.read_sql_query(f"SELECT {', '.join(campos)} FROM activos", conn)
            if "equipo" not in df_act.columns and "nombre" in df_act.columns:
                df_act = df_act.rename(columns={"nombre": "equipo"})
            if "estado" in df_act.columns:
                df_act = df_act[df_act["estado"].fillna("activo").str.lower() == "activo"]
            elif "activo" in df_act.columns:
                df_act = df_act[df_act["activo"].fillna(1).astype(int) == 1]
        else:
            df_act = pd.DataFrame(columns=["id", "equipo", "categoria", "unidad", "modelo"])

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_cmyk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                impresora TEXT,
                paginas INTEGER,
                costo REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        df_hist = pd.read_sql_query(
            "SELECT fecha, impresora, paginas, costo FROM historial_cmyk ORDER BY fecha DESC LIMIT 100",
            conn,
        )

    return df_inv, df_act, df_hist


def _detectar_impresoras(df_inv: pd.DataFrame, df_act: pd.DataFrame) -> list[str]:
    impresoras: list[str] = []
    if not df_act.empty and "equipo" in df_act.columns:
        for eq in df_act["equipo"].fillna("").astype(str).str.strip().tolist():
            if eq and eq not in impresoras:
                impresoras.append(eq)

    col_nom = "nombre" if "nombre" in df_inv.columns else ("item" if "item" in df_inv.columns else None)
    if col_nom:
        mask = df_inv[col_nom].fillna("").str.contains("impresora", case=False, na=False)
        for eq in df_inv.loc[mask, col_nom].astype(str).str.strip().tolist():
            if eq and eq not in impresoras:
                impresoras.append(eq)

    return impresoras or ["Impresora Principal", "Impresora Secundaria"]


def _col(df: pd.DataFrame, candidatos: list[str], default: Any = None):
    for c in candidatos:
        if c in df.columns:
            return c
    return default


def _filtrar_tintas(df_inv: pd.DataFrame, impresora_sel: str, usar_por_impresora: bool) -> pd.DataFrame:
    if df_inv.empty:
        return pd.DataFrame()

    col_nombre = _col(df_inv, ["nombre", "item"])
    col_categoria = _col(df_inv, ["categoria"])
    if not col_nombre:
        return pd.DataFrame()

    tintas = df_inv[col_nombre].fillna("").str.contains("tinta|ink|cian|magenta|amarillo|negro|black|cyan", case=False, na=False)
    if col_categoria:
        tintas = tintas | df_inv[col_categoria].fillna("").str.contains("tinta|insumo", case=False, na=False)
    base = df_inv[tintas].copy()

    if not usar_por_impresora or base.empty:
        return base

    aliases = [impresora_sel.lower().strip()]
    aliases.extend([x for x in aliases[0].split() if len(x) > 2])
    patron = "|".join(sorted(set(aliases)))
    filtro = base[col_nombre].fillna("").str.lower().str.contains(patron, na=False)
    return base[filtro].copy() if filtro.any() else base


def _costo_tinta_ml(df_tintas: pd.DataFrame, fallback: float) -> float:
    if df_tintas.empty:
        return fallback

    for c in ["costo_real_ml", "costo_unitario_usd", "precio_usd", "precio_venta_usd"]:
        if c in df_tintas.columns:
            s = pd.to_numeric(df_tintas[c], errors="coerce").dropna()
            s = s[s > 0]
            if not s.empty:
                return float(s.mean())
    return fallback


def _guardar_historial(impresora: str, paginas: int, costo: float) -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO historial_cmyk (impresora, paginas, costo) VALUES (?,?,?)",
            (impresora, int(paginas), float(costo)),
        )


def _render_kanban(usuario: str) -> None:
    st.subheader("🧩 Tablero de Taller (Kanban)")
    with db_transaction() as conn:
        df_k = pd.read_sql_query(
            "SELECT id, tipo, referencia, estado, fecha FROM ordenes_produccion ORDER BY fecha DESC LIMIT 80",
            conn,
        )

    if df_k.empty:
        st.info("No hay órdenes de producción activas.")
        return

    estados = ["Pendiente", "En proceso", "Completada", "Cancelada"]
    cols = st.columns(len(estados))
    for i, estado in enumerate(estados):
        with cols[i]:
            st.markdown(f"**{estado}**")
            sub = df_k[df_k["estado"].astype(str).str.lower() == estado.lower()].head(8)
            if sub.empty:
                st.caption("—")
            for _, row in sub.iterrows():
                st.caption(f"#{int(row['id'])} · {row['referencia']}")

    op_orden = st.selectbox("Orden a mover", df_k["id"].astype(int).tolist(), key="kanban_cmyk_orden")
    op_estado = st.selectbox("Nuevo estado", estados, key="kanban_cmyk_estado")
    if st.button("Mover orden", key="kanban_cmyk_move"):
        with db_transaction() as conn:
            conn.execute(
                "UPDATE ordenes_produccion SET estado=?, usuario=? WHERE id=?",
                (op_estado, usuario, int(op_orden)),
            )
        st.success(f"Orden #{op_orden} movida a {op_estado}")
        st.rerun()


def render_cmyk(usuario: str):
    st.title("🎨 Analizador Profesional de Cobertura CMYK")
    st.caption(f"Operador: {usuario}")

    try:
        df_inv, df_act, df_hist = _load_contexto_cmyk()
    except Exception as e:
        st.error(f"Error cargando datos CMYK: {e}")
        return

    impresoras_disponibles = _detectar_impresoras(df_inv, df_act)

    c_printer, c_file = st.columns([1, 2])
    with c_printer:
        impresora_sel = st.selectbox("🖨️ Equipo de Impresión", impresoras_disponibles)
        usar_stock_por_impresora = st.checkbox("Usar tintas del inventario solo de esta impresora", value=True)
        auto_negro_inteligente = st.checkbox("Conteo automático inteligente de negro (sombras y mezclas)", value=True)

        costo_desgaste = st.number_input("Costo desgaste por página ($)", min_value=0.0, value=0.02, step=0.005, format="%.3f")
        ml_base_pagina = st.number_input(
            "Consumo base por página a cobertura 100% (ml)",
            min_value=0.01,
            value=0.15,
            step=0.01,
            format="%.3f",
        )

        tintas_vinculadas = _filtrar_tintas(df_inv, impresora_sel, usar_stock_por_impresora)
        fallback_tinta_ml = float(st.session_state.get("costo_tinta_ml", 0.10))
        precio_tinta_ml = _costo_tinta_ml(tintas_vinculadas, fallback=fallback_tinta_ml)

        if not tintas_vinculadas.empty:
            st.success(f"💧 Costo dinámico tinta ({impresora_sel}): ${precio_tinta_ml:.4f}/ml")
            st.caption(f"Tintas detectadas: {len(tintas_vinculadas)}")
        else:
            st.info("No se encontraron tintas vinculadas; se usa costo base global.")

        st.subheader("⚙️ Ajustes de Calibración")
        factor_general = st.slider("Factor General de Consumo", 1.0, 3.0, 1.5, 0.1)

        calidad_map = {"Borrador": 0.85, "Normal": 1.0, "Alta": 1.18, "Foto": 1.32}
        papel_map = {"Bond 75g": 0.95, "Bond 90g": 1.0, "Fotográfico": 1.2, "Cartulina": 1.15}

        calidad_sel = st.selectbox("Calidad de impresión", list(calidad_map.keys()), index=1)
        papel_sel = st.selectbox("Tipo de papel (driver)", list(papel_map.keys()), index=1)

        factor_calidad = float(calidad_map[calidad_sel])
        factor_papel = float(papel_map[papel_sel])

        factor_k = 0.8
        refuerzo_negro = 0.06
        if not auto_negro_inteligente:
            factor_k = st.slider("Factor Especial para Negro (K)", 0.5, 1.2, 0.8, 0.05)
            refuerzo_negro = st.slider("Refuerzo de Negro en Mezclas Oscuras", 0.0, 0.2, 0.06, 0.01)

    with c_file:
        archivos_multiples = st.file_uploader("Carga tus diseños", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

    if not archivos_multiples:
        st.info("Sube uno o varios archivos para iniciar el análisis.")
    else:
        resultados = []
        totales = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}

        with st.spinner("🚀 Analizando cobertura real..."):
            total_pags = 0
            for archivo in archivos_multiples:
                try:
                    paginas = _normalizar_imagenes(archivo)
                except Exception as e:
                    st.error(f"Error en {archivo.name}: {e}")
                    continue

                for nombre_pag, img_obj in paginas:
                    total_pags += 1
                    analisis = _analizar_pagina(
                        img_obj=img_obj,
                        ml_base_pagina=float(ml_base_pagina),
                        factor_general=float(factor_general),
                        factor_calidad=factor_calidad,
                        factor_papel=factor_papel,
                        factor_k=float(factor_k),
                        auto_negro_inteligente=auto_negro_inteligente,
                        refuerzo_negro=float(refuerzo_negro),
                    )

                    consumo_total = sum(analisis[k] for k in ["C (ml)", "M (ml)", "Y (ml)", "K (ml)"])
                    desperdicio = float(st.session_state.get("factor_desperdicio_cmyk", 1.15))
                    desgaste_head_ml = float(st.session_state.get("desgaste_cabezal_ml", 0.005))
                    costo_limpieza = float(st.session_state.get("costo_limpieza_cabezal", 0.02))
                    consumo_ajustado = consumo_total * max(1.0, desperdicio)
                    costo = (consumo_ajustado * float(precio_tinta_ml)) + float(costo_desgaste) + (consumo_ajustado * desgaste_head_ml) + costo_limpieza

                    totales["C"] += analisis["C (ml)"]
                    totales["M"] += analisis["M (ml)"]
                    totales["Y"] += analisis["Y (ml)"]
                    totales["K"] += analisis["K (ml)"]

                    resultados.append(
                        {
                            "Archivo": nombre_pag,
                            **{k: round(v, 4) for k, v in analisis.items()},
                            "Total ml": round(consumo_ajustado, 4),
                            "Costo $": round(costo, 4),
                        }
                    )

        if resultados:
            df_resultados = pd.DataFrame(resultados)
            total_usd_lote = float(df_resultados["Costo $"].sum())
            total_ml_lote = float(sum(totales.values()))
            costo_promedio_pagina = _safe_div(total_usd_lote, total_pags)

            st.subheader("📋 Desglose por Archivo")
            st.dataframe(df_resultados, use_container_width=True, hide_index=True)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Cian", f"{totales['C']:.3f} ml")
            c2.metric("Magenta", f"{totales['M']:.3f} ml")
            c3.metric("Amarillo", f"{totales['Y']:.3f} ml")
            c4.metric("Negro", f"{totales['K']:.3f} ml")

            st.metric("💰 Costo Total Estimado de Producción", f"$ {total_usd_lote:.2f}", delta=f"$ {costo_promedio_pagina:.4f} por pág")

            k1, k2, k3 = st.columns(3)
            k1.metric("Consumo promedio", f"{_safe_div(total_ml_lote, total_pags):.4f} ml/pág")
            k2.metric("Rendimiento", f"{_safe_div(total_pags, total_usd_lote):.2f} pág/$")
            k3.metric("Participación K", f"{_safe_div(totales['K'], total_ml_lote) * 100:.1f}%")

            if costo_promedio_pagina > 0.35:
                st.warning("Costo por página alto: considera calidad Normal/Borrador o papel más económico.")
            elif _safe_div(totales["K"], total_ml_lote) > 0.55:
                st.info("Dominio de negro detectado: evalúa modo escala de grises para optimizar costos.")
            else:
                st.success("Parámetros de consumo estables para producción continua.")

            with st.expander("💸 Precio sugerido rápido", expanded=False):
                margen_objetivo = st.slider("Margen objetivo (%)", min_value=10, max_value=120, value=35, step=5)
                sugerido = simular_ganancia_pre_impresion(total_usd_lote, margen_objetivo)
                s1, s2 = st.columns(2)
                s1.metric("Precio sugerido", f"$ {sugerido['precio_sugerido']:.2f}")
                s2.metric("Ganancia estimada", f"$ {sugerido['ganancia_estimada']:.2f}")

            df_totales = pd.DataFrame([{"Color": c, "ml": totales[c]} for c in ["C", "M", "Y", "K"]])
            st.plotly_chart(px.pie(df_totales, names="Color", values="ml", title="Distribución de consumo CMYK"), use_container_width=True)

            st.download_button(
                "📥 Descargar desglose CMYK (CSV)",
                data=df_resultados.to_csv(index=False).encode("utf-8"),
                file_name="analisis_cmyk.csv",
                mime="text/csv",
            )

            trabajo_subl = {
                "trabajo": f"CMYK - {impresora_sel}",
                "costo_transfer_total": float(total_usd_lote),
                "cantidad": int(total_pags),
                "costo_transfer_unitario": _safe_div(total_usd_lote, total_pags),
                "impresora": impresora_sel,
                "calidad": calidad_sel,
                "papel": papel_sel,
                "fecha": datetime.now().isoformat(),
            }
            if st.button("📤 Enviar a Sublimación", use_container_width=True):
                cola = st.session_state.setdefault("cola_sublimacion", [])
                cola.append(trabajo_subl)
                st.success("Trabajo enviado a cola de Sublimación.")

            if st.button("🏭 Enviar a Producción", use_container_width=True):
                with db_transaction() as conn:
                    cur = conn.execute(
                        """
                        INSERT INTO ordenes_produccion (usuario, tipo, referencia, costo_estimado, estado)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (usuario, "CMYK", f"{impresora_sel} | {total_pags} pág | {calidad_sel}/{papel_sel}", float(total_usd_lote), "Pendiente"),
                    )
                    oid = int(cur.lastrowid)
                st.success(f"Orden de producción creada #{oid}")

            if st.button("📝 Enviar a Cotización", use_container_width=True):
                st.session_state["datos_pre_cotizacion"] = {
                    "tipo": "Impresión CMYK",
                    "trabajo": f"CMYK - {impresora_sel}",
                    "cantidad": int(total_pags),
                    "costo_base": float(total_usd_lote),
                    "consumos_cmyk": {k: float(v) for k, v in totales.items()},
                    "archivos": resultados,
                    "impresora": impresora_sel,
                    "papel": papel_sel,
                    "calidad": calidad_sel,
                    "precio_tinta_ml": float(precio_tinta_ml),
                    "factor_consumo": float(factor_general),
                    "fecha": pd.Timestamp.now(),
                }
                _guardar_historial(impresora_sel, total_pags, total_usd_lote)
                st.success("✅ Datos enviados correctamente al módulo de Cotizaciones")

    st.divider()
    st.subheader("🕘 Historial reciente CMYK")
    if df_hist.empty:
        st.info("Aún no hay análisis guardados en el historial.")
    else:
        df_hist_view = df_hist.copy()
        df_hist_view["fecha"] = pd.to_datetime(df_hist_view["fecha"], errors="coerce")
        st.dataframe(df_hist_view, use_container_width=True, hide_index=True)

        hist_dia = (
            df_hist_view.dropna(subset=["fecha"]).assign(dia=lambda d: d["fecha"].dt.date.astype(str)).groupby("dia", as_index=False)["costo"].sum()
        )
        if not hist_dia.empty:
            fig_hist = px.line(hist_dia, x="dia", y="costo", markers=True, title="Costo CMYK por día (historial)")
            fig_hist.update_layout(xaxis_title="Día", yaxis_title="Costo ($)")
            st.plotly_chart(fig_hist, use_container_width=True)

    _render_kanban(usuario)
