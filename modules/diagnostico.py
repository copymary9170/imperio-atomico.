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
    create_diagnostic_record,
    extraer_texto_diagnostico,
    get_tank_capacities,
    listar_activos_disponibles,
    listar_impresoras_activas,
    save_tank_capacities,
    save_uploaded_file,
)


def _obtener_capacidad_default(nombre_impresora: str) -> dict[str, float]:
    caps = get_tank_capacities(None, fallback_name=nombre_impresora)
    return {
        "Black": caps["black"],
        "Cyan": caps["cyan"],
        "Magenta": caps["magenta"],
        "Yellow": caps["yellow"],
    }


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


def _extraer_porcentajes_foto(imagen: np.ndarray | None) -> dict[str, float]:
    if imagen is None:
        return {}

    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    texto = pytesseract.image_to_string(gris, config="--psm 6")
    valores = [float(v) for v in re.findall(r"(\d{1,3})\s*%", texto)]
    colores = ["Cyan", "Magenta", "Yellow", "Black"]
    salida: dict[str, float] = {}
    for idx, color in enumerate(colores):
        if idx < len(valores):
            salida[color] = max(0.0, min(100.0, valores[idx]))
    return salida


def _mostrar_resultados(resultados: dict[str, float | None], resumen: dict[str, Any]) -> None:
    st.subheader("📊 Resultado del análisis")
    rows = [
        {"Color": color, "Nivel (ml)": round(float(valor or 0.0), 2) if valor is not None else None}
        for color, valor in resultados.items()
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Vida cabezal", f"{float(resumen.get('vida_cabezal_pct', 0.0)):.2f}%")
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
        st.warning("No hay impresoras detectadas por filtro. Selecciona un activo manualmente.")
        activos = listar_activos_disponibles()
        if activos:
            mapa_activos = {
                f"#{row['id']} · {row.get('equipo') or 'Activo'} {('(' + str(row.get('modelo')) + ')') if row.get('modelo') else ''}": row
                for row in activos
            }
            etiqueta_activo = st.selectbox("Activo a vincular", list(mapa_activos.keys()), index=0)
            activo_sel = mapa_activos[etiqueta_activo]
            activo_id_sel = int(activo_sel["id"])
            impresora_sel = str(activo_sel.get("modelo") or activo_sel.get("equipo") or "Otra")
        else:
            st.warning("No hay activos disponibles. Se usará selección manual sin vínculo a Activos.")
            impresora_sel = st.selectbox("Impresora", ["EPSON L805", "EPSON L3250", "Otra"], index=0)
            activo_id_sel = None

    st.subheader("Entrada de diagnóstico")
    archivo_diag = st.file_uploader("📄 Hoja diagnóstico (PDF/imagen)", type=["pdf", "png", "jpg", "jpeg"], key="diag_file")
    archivo_tanque = st.file_uploader("🖼 Foto de tanques", type=["png", "jpg", "jpeg"], key="tank_file")
    texto_manual = st.text_area("Texto OCR (editable)", placeholder="Puedes pegar/corregir el OCR aquí antes de analizar.", height=140)

    capacidad_default = _obtener_capacidad_default(impresora_sel)
    st.subheader("⚙️ Capacidad de tanques (ml)")
    c1, c2, c3, c4 = st.columns(4)
    capacidad = {
        "Cyan": c1.number_input("Cyan (ml)", min_value=0.0, value=float(capacidad_default["Cyan"]), step=1.0),
        "Magenta": c2.number_input("Magenta (ml)", min_value=0.0, value=float(capacidad_default["Magenta"]), step=1.0),
        "Yellow": c3.number_input("Yellow (ml)", min_value=0.0, value=float(capacidad_default["Yellow"]), step=1.0),
        "Black": c4.number_input("Black (ml)", min_value=0.0, value=float(capacidad_default["Black"]), step=1.0),
    }

    if st.button("🔍 Analizar diagnóstico"):
        imagen_diag = _convertir_archivo_a_imagen(archivo_diag) if archivo_diag else None
        texto_ocr = texto_manual.strip()
        if not texto_ocr and imagen_diag is not None:
            texto_ocr = pytesseract.image_to_string(imagen_diag, config="--psm 6")

        imagen_tanque = _convertir_archivo_a_imagen(archivo_tanque) if archivo_tanque else None
        porcentajes_foto = _extraer_porcentajes_foto(imagen_tanque)
        porcentajes_texto = extraer_texto_diagnostico(texto_ocr).get("porcentajes", []) if texto_ocr else []

        analisis = analizar_hoja_diagnostico(
            texto_ocr=texto_ocr,
            capacidad=capacidad,
            porcentajes_foto=porcentajes_foto,
        )
        resultados = analisis["resultados"]
        resumen = DiagnosticsService.summarize(resultados=resultados, vida_cabezal_pct=analisis["vida_cabezal_pct"])
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
    if not datos.get("activo_id"):
        st.warning("Este análisis no está vinculado a un activo; Inventario puede actualizarse, pero Activos no recibirá cambios.")
    st.info("Análisis listo. Usa el botón para enviarlo a Activos e Inventario.")


    st.subheader("🧾 Registro técnico del diagnóstico")
    cc1, cc2, cc3 = st.columns(3)
    total_pages = cc1.number_input("total_pages", min_value=0, value=int(datos.get("contador_impresiones", 0)), step=1)
    color_pages = cc2.number_input("color_pages", min_value=0, value=0, step=1)
    bw_pages = cc3.number_input("bw_pages", min_value=0, value=0, step=1)
    cc4, cc5 = st.columns(2)
    borderless_pages = cc4.number_input("borderless_pages", min_value=0, value=0, step=1)
    scanned_pages = cc5.number_input("scanned_pages", min_value=0, value=0, step=1)

    st.markdown("**Caso especial / estimación**")
    ec1, ec2, ec3 = st.columns(3)
    initial_fill_known = ec1.checkbox("initial_fill_known", value=True)
    estimation_mode = ec2.selectbox("estimation_mode", ["none", "visual", "software", "manual"], index=0)
    confidence_level = ec3.selectbox("confidence_level", ["low", "medium", "high"], index=1)
    notes = st.text_area("notes", value="Registro desde Diagnóstico IA", key="diag_notes")

    st.markdown("**Archivos de soporte**")
    archivos_hoja = st.file_uploader("Hojas diagnóstico / fotos", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="diag_multi_sheet")
    archivos_tanques = st.file_uploader("Fotos de tanques", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="diag_multi_tanks")
    archivos_software = st.file_uploader("Capturas software", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="diag_multi_software")
    archivos_botellas = st.file_uploader("Fotos de botellas de tinta", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="diag_multi_bottles")

    if st.button("📨 Guardar diagnóstico técnico"):
        try:
            if not datos.get("activo_id"):
                raise ValueError("Debes vincular el diagnóstico a un activo")

            activo_id = int(datos.get("activo_id"))
            caps_default = get_tank_capacities(activo_id, impresora_sel)
            save_tank_capacities(activo_id, caps_default)

            tank_levels = {}
            for color, ml in datos["resultados"].items():
                key = color.lower()
                capacity_ml = float(caps_default.get(key, 0.0))
                est_ml = float(ml or 0.0)
                est_pct = (est_ml / capacity_ml * 100.0) if capacity_ml > 0 else 0.0
                tank_levels[key] = {
                    "estimated_percent": max(0.0, min(100.0, est_pct)),
                    "estimated_ml": max(0.0, est_ml),
                    "source_of_measurement": "software" if datos.get("porcentajes_texto") else "photo",
                    "confidence_level": confidence_level,
                    "is_estimated": estimation_mode != "none",
                }

            files_meta = []
            for cat, files in [
                ("diagnostic_sheet", archivos_hoja or []),
                ("tank_photo", archivos_tanques or []),
                ("software_capture", archivos_software or []),
                ("ink_bottle", archivos_botellas or []),
            ]:
                for f in files:
                    meta = save_uploaded_file(f, 0, cat)
                    if meta:
                        files_meta.append(meta)

            rec = create_diagnostic_record(
                usuario=usuario,
                activo_id=activo_id,
                printer_name=impresora_sel,
                counters={
                    "total_pages": int(total_pages),
                    "color_pages": int(color_pages),
                    "bw_pages": int(bw_pages),
                    "borderless_pages": int(borderless_pages),
                    "scanned_pages": int(scanned_pages),
                },
                tank_levels=tank_levels,
                notes=notes,
                files=files_meta,
                estimation_mode=estimation_mode,
                confidence_level=confidence_level,
                initial_fill_known=bool(initial_fill_known),
            )
            st.success(f"✅ Diagnóstico guardado (ID #{rec['diagnostico_id']}).")
            st.caption(
                "Desgaste estimado cabezal: "
                f"{float(rec['head_wear_pct']):.2f}% | Depreciación estimada: ${float(rec['depreciation_amount']):.4f}"
            )
        except Exception as exc:
            st.error(f"No fue posible guardar diagnóstico: {exc}")

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
