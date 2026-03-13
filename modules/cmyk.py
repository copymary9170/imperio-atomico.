from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if float(b or 0) else 0.0


def _normalizar_imagenes(archivo) -> list[tuple[str, Image.Image]]:
    """Convierte un archivo subido (pdf o imagen) en una lista de páginas CMYK."""

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


def render_cmyk(usuario: str):
    st.title("🎨 Analizador Profesional de Cobertura CMYK")

    st.caption(f"Operador: {usuario}")

    c_printer, c_file = st.columns([1, 2])

    with c_printer:
        impresora_sel = st.text_input("🖨️ Equipo de Impresión", value="Impresora Principal")

        auto_negro_inteligente = st.checkbox(
            "Conteo automático inteligente de negro (sombras y mezclas)",
            value=True,
        )

        costo_desgaste = st.number_input(
            "Costo desgaste por página ($)", min_value=0.0, value=0.02, step=0.005, format="%.3f"
        )
        ml_base_pagina = st.number_input(
            "Consumo base por página a cobertura 100% (ml)",
            min_value=0.01,
            value=0.15,
            step=0.01,
            format="%.3f",
        )
        precio_tinta_ml = st.number_input(
            "Costo tinta por ml ($)", min_value=0.0, value=0.10, step=0.005, format="%.4f"
        )

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
        archivos_multiples = st.file_uploader(
            "Carga tus diseños", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True
        )

    if not archivos_multiples:
        st.info("Sube uno o varios archivos para iniciar el análisis.")
        return

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

                consumo_total = analisis["C (ml)"] + analisis["M (ml)"] + analisis["Y (ml)"] + analisis["K (ml)"]
                costo = consumo_total * float(precio_tinta_ml) + float(costo_desgaste)

                totales["C"] += analisis["C (ml)"]
                totales["M"] += analisis["M (ml)"]
                totales["Y"] += analisis["Y (ml)"]
                totales["K"] += analisis["K (ml)"]

                resultados.append(
                    {
                        "Archivo": nombre_pag,
                        **{k: round(v, 4) for k, v in analisis.items()},
                        "Total ml": round(consumo_total, 4),
                        "Costo $": round(costo, 4),
                    }
                )

    if not resultados:
        st.warning("No hubo resultados válidos para mostrar.")
        return

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

    df_totales = pd.DataFrame(
        [
            {"Color": "C", "ml": totales["C"]},
            {"Color": "M", "ml": totales["M"]},
            {"Color": "Y", "ml": totales["Y"]},
            {"Color": "K", "ml": totales["K"]},
        ]
    )
    st.plotly_chart(px.pie(df_totales, names="Color", values="ml", title="Distribución de consumo CMYK"), use_container_width=True)

    st.download_button(
        "📥 Descargar desglose CMYK (CSV)",
        data=df_resultados.to_csv(index=False).encode("utf-8"),
        file_name="analisis_cmyk.csv",
        mime="text/csv",
    )

    with st.expander("💸 Precio sugerido rápido", expanded=False):
        margen_objetivo = st.slider("Margen objetivo (%)", min_value=10, max_value=120, value=35, step=5)
        precio_sugerido = total_usd_lote * (1 + margen_objetivo / 100)
        st.metric("Precio sugerido", f"$ {precio_sugerido:.2f}")
        st.metric("Ganancia estimada", f"$ {precio_sugerido - total_usd_lote:.2f}")

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
