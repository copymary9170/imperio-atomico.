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


def _col(df: pd.DataFrame, candidatos: list[str], default: Any = None):
    for c in candidatos:
        if c in df.columns:
            return c
    return default


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
        elif "activo" in cols_inv and not df_inv.empty:
            df_inv = df_inv[df_inv["activo"].fillna(1).astype(int) == 1].copy()

        cols_act = _table_columns(conn, "activos")
        if cols_act:
            campos = [
                c
                for c in ["id", "equipo", "nombre", "categoria", "unidad", "modelo", "estado", "activo"]
                if c in cols_act
            ]
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
        cols_hist = _table_columns(conn, "historial_cmyk")
        for c in ["c_ml", "m_ml", "y_ml", "k_ml"]:
            if c not in cols_hist:
                conn.execute(f"ALTER TABLE historial_cmyk ADD COLUMN {c} REAL")

        df_hist = pd.read_sql_query(
            "SELECT fecha, impresora, paginas, costo, c_ml, m_ml, y_ml, k_ml FROM historial_cmyk ORDER BY fecha DESC LIMIT 100",
            conn,
        )

    return df_inv, df_act, df_hist


def _detectar_impresoras(df_inv: pd.DataFrame, df_act: pd.DataFrame) -> list[str]:
    impresoras: list[str] = []
    if not df_act.empty and "equipo" in df_act.columns:
        for eq in df_act["equipo"].dropna().astype(str).str.strip().tolist():
            if eq and eq not in impresoras:
                impresoras.append(eq)

    col_nom = _col(df_inv, ["item", "nombre"])
    if col_nom:
        mask = df_inv[col_nom].fillna("").str.contains("impresora", case=False, na=False)
        for eq in df_inv.loc[mask, col_nom].astype(str).str.strip().tolist():
            if eq and eq not in impresoras:
                impresoras.append(eq)

    return impresoras or ["Impresora Principal", "Impresora Secundaria"]


def _filtrar_tintas(df_inv: pd.DataFrame, impresora_sel: str, usar_por_impresora: bool) -> pd.DataFrame:
    if df_inv.empty:
        return pd.DataFrame()

    col_nombre = _col(df_inv, ["item", "nombre"])
    col_categoria = _col(df_inv, ["categoria"])
    if not col_nombre:
        return pd.DataFrame()

    tintas = df_inv[col_nombre].fillna("").str.contains(
        "tinta|ink|cian|magenta|amarillo|negro|black|cyan", case=False, na=False
    )
    if col_categoria:
        tintas = tintas | df_inv[col_categoria].fillna("").str.contains("tinta|insumo", case=False, na=False)
    base = df_inv[tintas].copy()

    if not usar_por_impresora or base.empty:
        return base

    aliases = [impresora_sel.lower().strip()]
    aliases.extend([x for x in aliases[0].split() if len(x) > 2])
    patron = "|".join(sorted(set(a for a in aliases if a)))
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


def _simular_papel_calidad(df_inv: pd.DataFrame, total_pags: int, costo_tinta_base: float, costo_desgaste: float) -> pd.DataFrame:
    col_nombre = _col(df_inv, ["item", "nombre"])
    col_precio = _col(df_inv, ["precio_usd", "costo_unitario_usd", "precio_venta_usd"])
    perfiles_papel: dict[str, float] = {}

    if col_nombre and col_precio:
        papeles = df_inv[df_inv[col_nombre].fillna("").str.contains(
            "papel|bond|fotograf|cartulina|adhesivo|opalina|sulfato", case=False, na=False
        )].copy()
        if not papeles.empty:
            papeles["_precio"] = pd.to_numeric(papeles[col_precio], errors="coerce")
            papeles = papeles[papeles["_precio"] > 0]
            for _, row in papeles.iterrows():
                perfiles_papel[str(row[col_nombre]).strip()] = float(row["_precio"])

    if not perfiles_papel:
        perfiles_papel = {
            "Bond 75g": 0.03,
            "Bond 90g": 0.05,
            "Fotográfico Brillante": 0.22,
            "Fotográfico Mate": 0.20,
            "Cartulina": 0.12,
            "Adhesivo": 0.16,
        }

    perfiles_calidad = {
        "Borrador": {"ink_mult": 0.82, "wear_mult": 0.90},
        "Normal": {"ink_mult": 1.00, "wear_mult": 1.00},
        "Alta": {"ink_mult": 1.18, "wear_mult": 1.10},
        "Foto": {"ink_mult": 1.32, "wear_mult": 1.15},
    }

    simulaciones: list[dict[str, Any]] = []
    for papel, costo_hoja in perfiles_papel.items():
        for calidad, cfg in perfiles_calidad.items():
            tinta_q = costo_tinta_base * float(cfg["ink_mult"])
            desgaste_q = float(costo_desgaste) * float(total_pags) * float(cfg["wear_mult"])
            papel_q = float(total_pags) * float(costo_hoja)
            total_q = tinta_q + desgaste_q + papel_q
            simulaciones.append(
                {
                    "Papel": papel,
                    "Calidad": calidad,
                    "Páginas": int(total_pags),
                    "Tinta ($)": round(tinta_q, 2),
                    "Desgaste ($)": round(desgaste_q, 2),
                    "Papel ($)": round(papel_q, 2),
                    "Total ($)": round(total_q, 2),
                    "Costo por pág ($)": round(_safe_div(total_q, total_pags), 4),
                }
            )

    return pd.DataFrame(simulaciones).sort_values("Total ($)")


def _mapear_consumo_ids(df_tintas: pd.DataFrame, totales: dict[str, float]) -> dict[int, float]:
    if df_tintas.empty or "id" not in df_tintas.columns:
        return {}

    col_nombre = _col(df_tintas, ["item", "nombre"])
    if not col_nombre:
        return {}

    alias = {
        "C": ["cian", "cyan"],
        "M": ["magenta"],
        "Y": ["amarillo", "yellow"],
        "K": ["negro", "black"],
    }
    consumos: dict[int, float] = {}

    for color, ml in totales.items():
        keys = alias.get(color, [])
        if not keys or ml <= 0:
            continue
        sub = df_tintas[df_tintas[col_nombre].fillna("").str.lower().str.contains("|".join(keys), na=False)]
        if sub.empty:
            continue

        row = sub.iloc[0]
        item_id = int(row["id"])
        consumos[item_id] = float(consumos.get(item_id, 0.0) + ml)

    return consumos


def _validar_stock(df_base: pd.DataFrame, consumos_ids: dict[int, float]) -> list[str]:
    if df_base.empty or not consumos_ids:
        return []

    col_nombre = _col(df_base, ["item", "nombre"]) or "id"
    col_cantidad = _col(df_base, ["cantidad", "stock", "existencia"]) or "cantidad"
    if col_cantidad not in df_base.columns or "id" not in df_base.columns:
        return []

    alertas: list[str] = []
    for item_id, requerido in consumos_ids.items():
        fila = df_base[df_base["id"].astype(int) == int(item_id)]
        if fila.empty:
            alertas.append(f"⚠️ No se encontró inventario ID {item_id} para validar stock.")
            continue
        disponible = float(pd.to_numeric(fila[col_cantidad], errors="coerce").fillna(0).sum())
        if requerido > disponible:
            nombre = str(fila.iloc[0].get(col_nombre, f"ID {item_id}"))
            alertas.append(
                f"⚠️ Stock insuficiente para {nombre}: necesitas {requerido:.2f} ml y hay {disponible:.2f} ml"
            )
    return alertas


def _descontar_inventario(consumos_ids: dict[int, float]) -> tuple[bool, str]:
    if not consumos_ids:
        return False, "No se encontraron tintas vinculadas para descontar."

    with db_transaction() as conn:
        cols_inv = _table_columns(conn, "inventario")
        col_cantidad = "cantidad" if "cantidad" in cols_inv else ("stock" if "stock" in cols_inv else None)
        if not col_cantidad:
            return False, "Inventario sin columna de cantidad/stock para descontar."

        for item_id, ml in consumos_ids.items():
            row = conn.execute(f"SELECT {col_cantidad} FROM inventario WHERE id=?", (int(item_id),)).fetchone()
            if not row:
                return False, f"No existe item ID {item_id} en inventario."
            disponible = float(row[0] or 0)
            if ml > disponible:
                return False, f"Stock insuficiente en ID {item_id}: req {ml:.2f} ml, disp {disponible:.2f} ml"

        for item_id, ml in consumos_ids.items():
            conn.execute(
                f"UPDATE inventario SET {col_cantidad}={col_cantidad}-? WHERE id=?",
                (float(ml), int(item_id)),
            )

    return True, "✅ Inventario actualizado correctamente."


def _guardar_historial(impresora: str, paginas: int, costo: float, totales: dict[str, float]) -> None:
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO historial_cmyk (impresora, paginas, costo, c_ml, m_ml, y_ml, k_ml) VALUES (?,?,?,?,?,?,?)",
            (
                impresora,
                int(paginas),
                float(costo),
                float(totales.get("C", 0.0)),
                float(totales.get("M", 0.0)),
                float(totales.get("Y", 0.0)),
                float(totales.get("K", 0.0)),
            ),
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
        if auto_negro_inteligente:
            st.caption("🧠 Modo automático de negro activo.")
        else:
            factor_k = st.slider("Factor Especial para Negro (K)", 0.5, 1.2, 0.8, 0.05)
            refuerzo_negro = st.slider("Refuerzo de Negro en Mezclas Oscuras", 0.0, 0.2, 0.06, 0.01)

    with c_file:
        archivos_multiples = st.file_uploader(
            "Carga tus diseños", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True
        )

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
                    costo = (
                        (consumo_ajustado * float(precio_tinta_ml))
                        + float(costo_desgaste)
                        + (consumo_ajustado * desgaste_head_ml)
                        + costo_limpieza
                    )

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

            st.metric(
                "💰 Costo Total Estimado de Producción",
                f"$ {total_usd_lote:.2f}",
                delta=f"$ {costo_promedio_pagina:.4f} por pág",
            )

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
            st.plotly_chart(
                px.pie(df_totales, names="Color", values="ml", title="Distribución de consumo CMYK"),
                use_container_width=True,
            )

            st.download_button(
                "📥 Descargar desglose CMYK (CSV)",
                data=df_resultados.to_csv(index=False).encode("utf-8"),
                file_name="analisis_cmyk.csv",
                mime="text/csv",
            )

            st.subheader("🧾 Simulación automática por Papel y Calidad")
            costo_tinta_base = total_ml_lote * float(precio_tinta_ml)
            df_sim = _simular_papel_calidad(df_inv, total_pags, costo_tinta_base, float(costo_desgaste))
            st.dataframe(df_sim, use_container_width=True, hide_index=True)
            st.plotly_chart(
                px.bar(
                    df_sim.head(12),
                    x="Papel",
                    y="Total ($)",
                    color="Calidad",
                    barmode="group",
                    title="Comparativo de costos (top 12 más económicos)",
                ),
                use_container_width=True,
            )
            mejor = df_sim.iloc[0]
            st.success(
                f"Mejor costo automático: {mejor['Papel']} | {mejor['Calidad']} → ${mejor['Total ($)']:.2f} "
                f"(${mejor['Costo por pág ($)']:.4f}/pág)"
            )

            consumos_ids = _mapear_consumo_ids(tintas_vinculadas, totales)
            alertas = _validar_stock(tintas_vinculadas, consumos_ids)
            st.subheader("📦 Verificación de Inventario")
            if alertas:
                for alerta in alertas:
                    st.error(alerta)
            else:
                st.success("✅ Hay suficiente tinta para producir")

            if st.button("📦 Enviar a Inventario", use_container_width=True):
                ok, msg = _descontar_inventario(consumos_ids)
                st.success(msg) if ok else st.warning(msg)

            if st.button("📤 Enviar a Sublimación", use_container_width=True):
                cola = st.session_state.setdefault("cola_sublimacion", [])
                cola.append(
                    {
                        "trabajo": f"CMYK - {impresora_sel}",
                        "costo_transfer_total": float(total_usd_lote),
                        "cantidad": int(total_pags),
                        "costo_transfer_unitario": _safe_div(total_usd_lote, total_pags),
                        "impresora": impresora_sel,
                        "calidad": calidad_sel,
                        "papel": papel_sel,
                        "fecha": datetime.now().isoformat(),
                    }
                )
                st.success("Trabajo enviado a cola de Sublimación.")

            if st.button("🏭 Enviar a Producción", use_container_width=True):
                with db_transaction() as conn:
                    cur = conn.execute(
                        """
                        INSERT INTO ordenes_produccion (usuario, tipo, referencia, costo_estimado, estado)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            usuario,
                            "CMYK",
                            f"{impresora_sel} | {total_pags} pág | {calidad_sel}/{papel_sel}",
                            float(total_usd_lote),
                            "Pendiente",
                        ),
                    )
                    oid = int(cur.lastrowid)
                st.success(f"Orden de producción creada #{oid}")

            if st.button("📝 Enviar a Cotización", use_container_width=True):
                st.session_state["datos_pre_cotizacion"] = {
                    "tipo": "Impresión CMYK",
                    "trabajo": f"CMYK - {impresora_sel}",
                    "cantidad": int(total_pags),
                    "costo_base": float(df_sim.iloc[0]["Total ($)"]),
                    "consumos_cmyk": {k: float(v) for k, v in totales.items()},
                    "consumos_ids": {int(k): float(v) for k, v in consumos_ids.items()},
                    "archivos": resultados,
                    "impresora": impresora_sel,
                    "papel": str(mejor["Papel"]),
                    "calidad": str(mejor["Calidad"]),
                    "precio_tinta_ml": float(precio_tinta_ml),
                    "factor_consumo": float(factor_general),
                    "factor_negro": float(factor_k),
                    "refuerzo_negro": float(refuerzo_negro),
                    "fecha": pd.Timestamp.now(),
                }
                _guardar_historial(impresora_sel, total_pags, total_usd_lote, totales)
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

