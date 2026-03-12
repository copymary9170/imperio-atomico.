from __future__ import annotations

import re
from typing import Any

import cv2
import numpy as np
import pandas as pd
import pytesseract
import streamlit as st
from pdf2image import convert_from_bytes

from services.diagnostics_service import (
    DiagnosticsService,
    analizar_hoja_diagnostico,
    aplicar_resultado_diagnostico,
    extraer_texto_diagnostico,
    listar_impresoras_activas,
)


def _obtener_capacidad_default(nombre_impresora: str) -> dict[str, float]:
    nombre = (nombre_impresora or "").upper()
    if "L805" in nombre:
        return {"Black": 70.0, "Cyan": 70.0, "Magenta": 70.0, "Yellow": 70.0}
    if "L3250" in nombre or "122" in nombre:
        return {"Black": 12.4, "Cyan": 14.0, "Magenta": 14.0, "Yellow": 14.0}
    return {"Black": 70.0, "Cyan": 70.0, "Magenta": 70.0, "Yellow": 70.0}


def _convertir_archivo_a_imagen(file_obj) -> np.ndarray | None:
    if file_obj is None:
        return None

    file_bytes = file_obj.read()
    if not file_bytes:
        return None

    if file_obj.type == "application/pdf":
        pages = convert_from_bytes(file_bytes, dpi=250)
        return cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR) if pages else None

    return cv2.imdecode(np.frombuffer(file_bytes, np.uint8), cv2.IMREAD_COLOR)


def _ocr_texto(img: np.ndarray | None) -> str:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoise = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binaria = cv2.threshold(denoise, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    texto = pytesseract.image_to_string(binaria, lang="eng+spa")
    return str(texto or "")


def _detectar_vida_cabezal(texto: str) -> float | None:
    if not texto:
        return None
    match = re.search(r"(?:head|cabezal)[^\d]{0,15}(\d{1,3})\s*%", texto, flags=re.IGNORECASE)
    if not match:
        return None
    return max(0.0, min(100.0, float(match.group(1))))


def _detectar_niveles_por_foto(img: np.ndarray | None) -> dict[str, float]:
    if img is None or len(img.shape) < 3:
        return {}

    h, w, _ = img.shape
    if h <= 0 or w <= 0:
        return {}

    zonas = {
        "Black": img[:, 0: int(w * 0.25)],
        "Cyan": img[:, int(w * 0.25): int(w * 0.50)],
        "Magenta": img[:, int(w * 0.50): int(w * 0.75)],
        "Yellow": img[:, int(w * 0.75): w],
    }

    niveles: dict[str, float] = {}
    for color, zona in zonas.items():
        if zona.size == 0:
            continue

        gray = cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        cobertura = float(np.sum(thresh > 0) / max(1, thresh.size))
        niveles[color] = max(0.0, min(100.0, cobertura * 100.0))

    return niveles


def _mostrar_resultados(resultados: dict[str, float | None], resumen: dict[str, Any]) -> None:
    st.subheader("Resultado final")
    st.dataframe(
        pd.DataFrame(
            [
                {"Color": c, "Nivel (ml)": v if v is not None else "No detectado"}
                for c, v in resultados.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Vida cabezal", f"{resumen['vida_cabezal_pct']:.2f}%")
    m2.metric("Estado tintas", str(resumen.get("estado_tintas", "N/D")))
    m3.metric("Estado cabezal", str(resumen.get("estado_cabezal", "N/D")))
    m4.metric("Mín tinta (ml)", f"{float(resumen.get('min_ml', 0.0)):.2f}")


def render_diagnostico(usuario: str) -> None:
    st.caption(f"Usuario activo: {usuario}")

    impresoras_activas = listar_impresoras_activas()
    if impresoras_activas:
        mapa_impresoras = {
            f"#{row['id']} · {row.get('equipo') or 'Impresora'} {('(' + str(row.get('modelo')) + ')') if row.get('modelo') else ''}".strip(): row
            for row in impresoras_activas
        }
        etiqueta_sel = st.selectbox("Impresora (desde activos)", list(mapa_impresoras.keys()), index=0)
        impresora_data = mapa_impresoras[etiqueta_sel]
        impresora_sel = str(impresora_data.get("modelo") or impresora_data.get("equipo") or "Otra")
        activo_id_sel = int(impresora_data["id"])
    else:
        st.warning("No hay impresoras activas en Activos. Se usará selección manual.")
        impresora_sel = st.selectbox(
            "Impresora",
            ["EPSON L805", "EPSON L3250", "Otra"],
            index=0,
        )
        activo_id_sel = None

    st.subheader("Entrada de diagnóstico")
    archivo_diag = st.file_uploader(
        "📄 Hoja diagnóstico (PDF/imagen)",
        type=["pdf", "png", "jpg", "jpeg"],
        key="diag_file",
    )
    archivo_tanque = st.file_uploader(
        "🖼 Foto de tanques",
        type=["png", "jpg", "jpeg"],
        key="tank_file",
    )

    texto_manual = st.text_area(
        "Texto OCR (editable)",
        placeholder="Puedes pegar/corregir el OCR aquí antes de analizar.",
        height=140,
    )

    capacidad_default = _obtener_capacidad_default(impresora_sel)
    st.subheader("⚙️ Capacidad de tanques (ml)")
    c1, c2, c3, c4 = st.columns(4)
    capacidad = {
        "Cyan": c1.number_input("Cyan (ml)", min_value=0.0, value=float(capacidad_default["Cyan"]), step=1.0),
        "Magenta": c2.number_input("Magenta (ml)", min_value=0.0, value=float(capacidad_default["Magenta"]), step=1.0),
        "Yellow": c3.number_input("Yellow (ml)", min_value=0.0, value=float(capacidad_default["Yellow"]), step=1.0),
        "Black": c4.number_input("Black (ml)", min_value=0.0, value=float(capacidad_default["Black"]), step=1.0),
    }

    analizar = st.button("🚀 Analizar", type="primary")
    if analizar:
        img_diag = _convertir_archivo_a_imagen(archivo_diag) if archivo_diag else None
        img_tanque = _convertir_archivo_a_imagen(archivo_tanque) if archivo_tanque else None

        texto_ocr = texto_manual.strip()
        if not texto_ocr and img_diag is not None:
            try:
                texto_ocr = _ocr_texto(img_diag)
            except Exception as exc:
                st.warning(f"No fue posible ejecutar OCR automático: {exc}")
                texto_ocr = ""

        porcentajes_foto = _detectar_niveles_por_foto(img_tanque)
        porcentajes_texto = extraer_texto_diagnostico(texto_ocr).get("porcentajes", [])
        vida_detectada = _detectar_vida_cabezal(texto_ocr)

        analisis = analizar_hoja_diagnostico(
            texto_ocr=texto_ocr,
            capacidad=capacidad,
            porcentajes_foto=porcentajes_foto,
            vida_cabezal_detectada=vida_detectada,
        )

        resultados = analisis["resultados"]
        resumen = DiagnosticsService.summarize(
            resultados=resultados,
            vida_cabezal_pct=analisis["vida_cabezal_pct"],
        )
        st.session_state["diag_last_analysis"] = {
            "impresora": impresora_sel,
            "activo_id": activo_id_sel,
            "resultados": resultados,
            "resumen": resumen,
            "contador_impresiones": int(analisis.get("contador_impresiones", 0)),
            "vida_cabezal_pct": float(analisis["vida_cabezal_pct"]),
            "desgaste_componentes": dict(analisis.get("desgaste_componentes", {})),
            "texto_ocr": texto_ocr,
            "porcentajes_foto": porcentajes_foto,
            "porcentajes_texto": porcentajes_texto,
        }

    datos = st.session_state.get("diag_last_analysis")
    if not datos or datos.get("impresora") != impresora_sel:
        return

    _mostrar_resultados(datos["resultados"], datos["resumen"])
    st.info("Análisis listo. Usa el botón para enviarlo a Activos e Inventario.")

    if st.button("📨 Enviar análisis a Activos e Inventario"):
        try:
            sync = aplicar_resultado_diagnostico(
                usuario=usuario,
                impresora=impresora_sel,
                resultados=datos["resultados"],
                vida_cabezal_pct=float(datos["vida_cabezal_pct"]),
                contador_impresiones=int(datos.get("contador_impresiones", 0)),
                activo_id=datos.get("activo_id"),
                desgaste_componentes=datos.get("desgaste_componentes"),
            )
            st.success("✅ Diagnóstico enviado y sincronizado con Activos/Inventario.")
            if sync.get("movimientos_tinta"):
                st.caption(
                    "Consumo de tintas aplicado en inventario: "
                    + ", ".join(
                        [f"{m['color']} ({float(m['consumo_ml']):.2f} ml)" for m in sync["movimientos_tinta"]]
                    )
                )
            else:
                st.caption("No se detectó consumo adicional de tintas respecto al diagnóstico anterior.")
        except Exception as exc:
            st.error(f"No fue posible sincronizar diagnóstico con Activos/Inventario: {exc}")

    st.markdown("#### Señales detectadas")
    s1, s2 = st.columns(2)
    s1.markdown("**Porcentajes desde OCR:**")
    s1.write([round(float(v), 2) for v in datos.get("porcentajes_texto", [])])
    s2.markdown("**Porcentajes desde foto:**")
    s2.write({k: round(float(v), 2) for k, v in datos.get("porcentajes_foto", {}).items()})

    contador_imp = int(datos.get("contador_impresiones", 0))
    if contador_imp > 0:
        st.info(f"📌 Total de páginas impresas detectado: {contador_imp}")
    if datos.get("texto_ocr"):
        with st.expander("Ver texto OCR usado"):
            st.code(str(datos["texto_ocr"]))

    if not datos.get("texto_ocr") and not datos.get("porcentajes_foto"):
        st.warning("No se detectaron datos automáticos. Ingresa texto OCR o una foto más clara para mejores resultados.")
