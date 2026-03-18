from datetime import datetime
from io import BytesIO
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
    register_diagnostic_files,
    save_tank_capacities,
    save_uploaded_file,
    register_printer_refill,
    list_printer_refills,
    register_printer_maintenance,
    list_printer_maintenance,
    list_printer_diagnostics,
)

COLOR_ORDER = ("black", "cyan", "magenta", "yellow")
COLOR_LABELS = {"black": "Black", "cyan": "Cyan", "magenta": "Magenta", "yellow": "Yellow"}

PRINTER_PROFILES = {
    "hp smart tank 580-590": {
        "match_terms": ["smart tank 580", "smart tank 590", "580", "590"],
        "ink_system_type": "factory_tank",
        "ink_usage_type": "standard",
        "initial_fill_known": True,
        "estimation_mode": "software",
        "head_system_type": "integrated",
    },
    "epson l1250 wifi": {
        "match_terms": ["l1250", "epson l1250"],
        "ink_system_type": "factory_tank",
        "ink_usage_type": "sublimation",
        "initial_fill_known": False,
        "estimation_mode": "visual",
        "head_system_type": "integrated",
    },
    "hp deskjet 2000 j210/j210a": {
        "match_terms": ["deskjet 2000", "j210", "j210a"],
        "ink_system_type": "adapted_external_tank",
        "ink_usage_type": "standard",
        "initial_fill_known": False,
        "estimation_mode": "visual",
        "head_system_type": "integrated",
    },
}


def _normalizar_texto_impresora(*valores: Any) -> str:
    return " ".join(str(valor or "").strip().lower() for valor in valores if str(valor or "").strip())


def _formatear_opcion_activo(row: dict[str, Any], default_label: str = "Activo") -> str:
    equipo = str(row.get("equipo") or default_label).strip()
    modelo = str(row.get("modelo") or "").strip()
    tipo_detalle = str(row.get("tipo_detalle") or "").strip()
    partes = [f"#{row['id']} · {equipo}"]
    if modelo:
        partes.append(f"({modelo})")
    if tipo_detalle:
        partes.append(f"· {tipo_detalle}")
    return " ".join(partes).strip()


def _obtener_perfil_impresora(nombre_impresora: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    nombre = _normalizar_texto_impresora(
        nombre_impresora,
        metadata.get("equipo"),
        metadata.get("modelo"),
        metadata.get("tipo_detalle"),
        metadata.get("unidad"),
    )
    for _, profile in PRINTER_PROFILES.items():
        if any(term in nombre for term in profile["match_terms"]):
            return profile
    tipo_detalle = str(metadata.get("tipo_detalle") or "").strip().lower()
    if "sublim" in tipo_detalle:
        return {
            "ink_system_type": "factory_tank",
            "ink_usage_type": "sublimation",
            "initial_fill_known": False,
            "estimation_mode": "visual",
            "head_system_type": "integrated",
        }
    if "cartucho" in tipo_detalle:
        return {
            "ink_system_type": "cartridge",
            "ink_usage_type": "standard",
            "initial_fill_known": False,
            "estimation_mode": "manual",
            "head_system_type": "integrated",
        }
    return {
        "ink_system_type": "factory_tank",
        "ink_usage_type": "standard",
        "initial_fill_known": True,
        "estimation_mode": "none",
        "head_system_type": "integrated",
    }

def _obtener_capacidades_canonicas(activo_id: int | None, nombre_impresora: str) -> dict[str, float]:
    caps = get_tank_capacities(activo_id, fallback_name=nombre_impresora)
    return {c: float(caps.get(c, 0.0)) for c in COLOR_ORDER}


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


class _StoredUpload(BytesIO):
    def __init__(self, content: bytes, name: str, mime_type: str) -> None:
        super().__init__(content)
        self.name = name
        self.type = mime_type

    def getvalue(self) -> bytes:  # type: ignore[override]
        return super().getvalue()


def _snapshot_upload(file_obj, category: str) -> dict[str, Any] | None:
    if file_obj is None:
        return None
    content = file_obj.getvalue()
    if not content:
        return None
    return {
        "name": str(file_obj.name or "archivo"),
        "type": str(getattr(file_obj, "type", "application/octet-stream")),
        "content": content,
        "category": category,
    }


def _restore_upload(payload: dict[str, Any]) -> _StoredUpload:
    return _StoredUpload(
        content=bytes(payload.get("content") or b""),
        name=str(payload.get("name") or "archivo"),
        mime_type=str(payload.get("type") or "application/octet-stream"),
    )


def _extraer_porcentajes_por_ocr(imagen: np.ndarray | None) -> dict[str, float]:
    if imagen is None:
        return {}
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    texto = pytesseract.image_to_string(gris, config="--psm 6")
    lectura = extraer_texto_diagnostico(texto)
    porcentajes = lectura.get("porcentajes", [])
    resultado: dict[str, float] = {}
    for idx, color in enumerate(("cyan", "magenta", "yellow", "black")):
        if idx < len(porcentajes):
            resultado[color] = max(0.0, min(100.0, float(porcentajes[idx])))
    return resultado


def _analizar_tanque_visual(imagen: np.ndarray | None) -> dict[str, float]:
    if imagen is None:
        return {}

    h, w = imagen.shape[:2]
    if h < 40 or w < 40:
        return {}

    h, w = imagen.shape[:2]
    if h < 40 or w < 40:
        return {}

    segmentos = np.array_split(imagen, 4, axis=1)
    orden_segmentos = ["cyan", "magenta", "yellow", "black"]
    salida: dict[str, float] = {}

    for color, seg in zip(orden_segmentos, segmentos):
        hsv = cv2.cvtColor(seg, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1].astype(np.float32)
        value = hsv[:, :, 2].astype(np.float32)

        if color == "black":
            tinta_mask = value < 90
        else:
            tinta_mask = (saturation > 40) & (value > 30)

        filas = tinta_mask.mean(axis=1)
        candidatas = np.where(filas > 0.15)[0]
        if len(candidatas) == 0:
            continue

        top = int(candidatas.min())
        bottom = int(candidatas.max())
        fill_ratio = max(0.0, min(1.0, (bottom - top + 1) / max(1, seg.shape[0])))
        salida[color] = round(fill_ratio * 100.0, 2)

    return salida


def _fusionar_porcentajes(
    report_pct: list[float] | None,
    software_pct: dict[str, float],
    visual_pct: dict[str, float],
    ink_system_type: str,
) -> dict[str, float]:
    salida: dict[str, float] = {}
    report_map: dict[str, float] = {}
    for idx, color in enumerate(("cyan", "magenta", "yellow", "black")):
        if report_pct and idx < len(report_pct):
            report_map[color] = float(report_pct[idx])

    for color in COLOR_ORDER:
        candidates = []
        if color in software_pct:
            candidates.append((software_pct[color], 0.6))
        if color in report_map:
            candidates.append((report_map[color], 0.5))
        if color in visual_pct:
            candidates.append((visual_pct[color], 0.7 if ink_system_type == "adapted_external_tank" else 0.4))

        if not candidates:
            continue

        weighted = sum(v * w for v, w in candidates) / sum(w for _, w in candidates)
        salida[color] = round(max(0.0, min(100.0, weighted)), 2)
    return salida


def _calcular_ml_desde_porcentaje(pct_by_color: dict[str, float], capacidad: dict[str, float]) -> dict[str, float | None]:
    resultados = {COLOR_LABELS[c]: None for c in COLOR_ORDER}
    for c in COLOR_ORDER:
        pct = pct_by_color.get(c)
        if pct is None:
            continue
        resultados[COLOR_LABELS[c]] = round((float(capacidad.get(c, 0.0)) * float(pct)) / 100.0, 2)
    return resultados


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


def _seleccionar_impresora() -> tuple[str, int | None]:
    impresoras_activas = listar_impresoras_activas()
    if impresoras_activas:
        mapa_impresoras = {
            _formatear_opcion_activo(row, default_label="Impresora"): row
            for row in impresoras_activas
        }
        etiqueta_sel = st.selectbox("Impresora (desde activos)", list(mapa_impresoras.keys()), index=0)
        impresora_data = mapa_impresoras[etiqueta_sel]
        impresora_sel = str(impresora_data.get("modelo") or impresora_data.get("equipo") or "Otra")
        activo_id_sel = int(impresora_data["id"])
        return impresora_sel, activo_id_sel

    st.warning("No hay impresoras detectadas por filtro. Selecciona un activo manualmente.")
    activos = listar_activos_disponibles()
    if activos:
        mapa_activos = {
            _formatear_opcion_activo(row): row
            for row in activos
        }
        etiqueta_activo = st.selectbox("Activo a vincular", list(mapa_activos.keys()), index=0)
        activo_sel = mapa_activos[etiqueta_activo]
        return str(activo_sel.get("modelo") or activo_sel.get("equipo") or "Otra"), int(activo_sel["id"])

    st.warning("No hay activos disponibles. Se usará selección manual sin vínculo a Activos.")
    impresora_sel = st.selectbox("Impresora", ["EPSON L805", "EPSON L3250", "Otra"], index=0)
    return impresora_sel, None


def _capturar_entradas() -> tuple[Any, Any, Any, str]:
    st.subheader("Entrada de diagnóstico")
    archivo_diag = st.file_uploader("📄 Hoja diagnóstico (PDF/imagen)", type=["pdf", "png", "jpg", "jpeg"], key="diag_file")
    archivo_tanque = st.file_uploader("🖼 Foto de tanques", type=["png", "jpg", "jpeg"], key="tank_file")
    archivo_software = st.file_uploader("💻 Captura de software", type=["png", "jpg", "jpeg"], key="software_file")
    texto_manual = st.text_area("Texto OCR (editable)", placeholder="Puedes pegar/corregir el OCR aquí antes de analizar.", height=140)
    return archivo_diag, archivo_tanque, archivo_software, texto_manual


def _render_guardado_tecnico(usuario: str, impresora_sel: str, datos: dict[str, Any], capacidad: dict[str, float]) -> None:
    st.markdown("---")
    st.subheader("4) Registro técnico del diagnóstico")
    st.caption("Completa estos campos para guardar el diagnóstico técnico.")

    cc1, cc2, cc3 = st.columns(3)
    total_pages = cc1.number_input("total_pages", min_value=0, value=int(datos.get("contador_impresiones", 0)), step=1)
    color_pages = cc2.number_input("color_pages", min_value=0, value=0, step=1)
    bw_pages = cc3.number_input("bw_pages", min_value=0, value=0, step=1)
    cc4, cc5 = st.columns(2)
    borderless_pages = cc4.number_input("borderless_pages", min_value=0, value=0, step=1)
    scanned_pages = cc5.number_input("scanned_pages", min_value=0, value=0, step=1)

    st.markdown("**Caso especial / estimación**")
    ec1, ec2, ec3 = st.columns(3)
    initial_fill_known = ec1.checkbox("initial_fill_known", value=bool(datos["profile"].get("initial_fill_known", True)))
    estimation_mode_options = ["none", "visual", "software", "manual"]
    em_default = datos["profile"].get("estimation_mode", "none")
    em_index = estimation_mode_options.index(em_default) if em_default in estimation_mode_options else 0
    estimation_mode = ec2.selectbox("estimation_mode", estimation_mode_options, index=em_index)
    confidence_level = ec3.selectbox("confidence_level", ["low", "medium", "high"], index=1)

    pc1, pc2, pc3 = st.columns(3)
    ink_system_opts = ["factory_tank", "cartridge", "adapted_external_tank"]
    usage_opts = ["standard", "sublimation"]
    ink_default = datos["profile"].get("ink_system_type", "factory_tank")
    usage_default = datos["profile"].get("ink_usage_type", "standard")
    ink_system_type = pc1.selectbox("ink_system_type", ink_system_opts, index=ink_system_opts.index(ink_default) if ink_default in ink_system_opts else 0)
    ink_usage_type = pc2.selectbox("ink_usage_type", usage_opts, index=usage_opts.index(usage_default) if usage_default in usage_opts else 0)
    head_system_type = pc3.text_input("head_system_type", value=str(datos["profile"].get("head_system_type", "integrated")))
    vc1, vc2 = st.columns(2)
    purchase_value = vc1.number_input("purchase_value", min_value=0.0, value=0.0, step=10.0)
    current_value = vc2.number_input("current_value", min_value=0.0, value=0.0, step=10.0)

    notes = st.text_area("notes", value="Registro desde Diagnóstico IA", key="diag_notes")

    st.markdown("**Lectura por color**")
    source_options = ["photo", "software", "report", "manual"]
    per_color_source: dict[str, str] = {}
    per_color_conf: dict[str, str] = {}
    cols = st.columns(4)
    for idx, color in enumerate(COLOR_ORDER):
        source_default = "software" if color in datos.get("porcentajes_software", {}) else "photo"
        per_color_source[color] = cols[idx].selectbox(f"{color}_source", source_options, index=source_options.index(source_default), key=f"src_{color}")
        per_color_conf[color] = cols[idx].selectbox(f"{color}_confidence", ["low", "medium", "high"], index=1, key=f"conf_{color}")

    st.markdown("**Evidencia extra**")
    st.caption(
        "Se guardarán automáticamente los mismos archivos usados para el análisis (hoja, tanques y software)."
    )
    archivos_extra = st.file_uploader(
        "Evidencia extra opcional (fotos adicionales, botellas, otros soportes)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="diag_extra_files",
    )

    st.subheader("5) Guardado del diagnóstico")
    if st.button("📨 Guardar diagnóstico técnico"):
        try:
            if not datos.get("activo_id"):
                raise ValueError("Debes vincular el diagnóstico a un activo")

            activo_id = int(datos.get("activo_id"))
            save_tank_capacities(activo_id, capacidad)

            tank_levels = {}
            for color in COLOR_ORDER:
                est_pct = float(datos.get("fusion_pct", {}).get(color, 0.0))
                capacity_ml = float(capacidad.get(color, 0.0))
                est_ml = round((est_pct * capacity_ml) / 100.0, 2)
                tank_levels[color] = {
                    "estimated_percent": est_pct,
                    "estimated_ml": max(0.0, est_ml),
                    "source_of_measurement": per_color_source.get(color, "manual"),
                    "confidence_level": per_color_conf.get(color, confidence_level),
                    "is_estimated": estimation_mode != "none",
                }

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
                files=[],
                estimation_mode=estimation_mode,
                confidence_level=confidence_level,
                initial_fill_known=bool(initial_fill_known),
                ink_system_type=ink_system_type,
                ink_usage_type=ink_usage_type,
                head_system_type=head_system_type,
                purchase_value=float(purchase_value),
                current_value=float(current_value),
            )

            files_meta = []
            legacy_id = int(rec.get("legacy_diagnostico_id") or rec["diagnostico_id"])

            archivos_principales = list(datos.get("archivos_principales") or [])
            for payload in archivos_principales:
                stored_file = _restore_upload(payload)
                meta = save_uploaded_file(stored_file, legacy_id, str(payload.get("category") or "evidencia"))
                if meta:
                    files_meta.append(meta)

            for extra_file in archivos_extra or []:
                meta = save_uploaded_file(extra_file, legacy_id, "evidencia_extra")
                if meta:
                    files_meta.append(meta)

            if files_meta:
                register_diagnostic_files(int(rec["diagnostico_id"]), legacy_id, files_meta)

            st.success(f"✅ Diagnóstico guardado (ID #{rec['diagnostico_id']}).")
            st.caption(
                "Desgaste estimado cabezal: "
                f"{float(rec['head_wear_pct']):.2f}% | Depreciación estimada: ${float(rec['depreciation_amount']):.4f}"
            )
        except Exception as exc:
            st.error(f"No fue posible guardar diagnóstico: {exc}")


def _render_historial(usuario: str, datos: dict[str, Any]) -> None:
    st.markdown("---")
    st.subheader("6) Recargas, mantenimiento e historiales")
    if not datos.get("activo_id"):
        return

    st.subheader("💧 Registro de recargas")
    rr1, rr2, rr3, rr4 = st.columns(4)
    refill_color = rr1.selectbox("color", list(COLOR_ORDER), key="refill_color")
    refill_ml = rr2.number_input("added_ml", min_value=0.0, value=0.0, step=1.0, key="refill_ml")
    refill_unit_cost = rr3.number_input("unit_cost", min_value=0.0, value=0.0, step=0.1, key="refill_uc")
    refill_date = rr4.text_input("refill_date", value="", key="refill_date")
    refill_bottle = st.text_input("bottle_reference", key="refill_bottle")
    refill_notes = st.text_area("refill_notes", key="refill_notes")
    if st.button("Guardar recarga"):
        try:
            _ = register_printer_refill(
                usuario=usuario,
                activo_id=int(datos.get("activo_id")),
                color=refill_color,
                added_ml=float(refill_ml),
                refill_date=refill_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                bottle_reference=refill_bottle,
                unit_cost=float(refill_unit_cost),
                notes=refill_notes,
            )
            st.success("Recarga registrada")
        except Exception as exc:
            st.error(f"No fue posible registrar recarga: {exc}")

    df_refills = pd.DataFrame(list_printer_refills(int(datos.get("activo_id")), limit=50))
    st.dataframe(df_refills, use_container_width=True, hide_index=True)

    st.subheader("🛠️ Historial de mantenimiento")
    mm1, mm2, mm3 = st.columns(3)
    maintenance_date = mm1.text_input("maintenance_date", value="", key="mnt_date")
    maintenance_type = mm2.text_input("maintenance_type", value="limpieza", key="mnt_type")
    maintenance_cost = mm3.number_input("maintenance_cost", min_value=0.0, value=0.0, step=0.1, key="mnt_cost")
    maintenance_notes = st.text_area("maintenance_notes", key="mnt_notes")
    if st.button("Guardar mantenimiento"):
        try:
            _ = register_printer_maintenance(
                usuario=usuario,
                activo_id=int(datos.get("activo_id")),
                maintenance_date=maintenance_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                maintenance_type=maintenance_type,
                cost=float(maintenance_cost),
                notes=maintenance_notes,
            )
            st.success("Mantenimiento registrado")
        except Exception as exc:
            st.error(f"No fue posible registrar mantenimiento: {exc}")

    df_maint = pd.DataFrame(list_printer_maintenance(int(datos.get("activo_id")), limit=50))
    st.dataframe(df_maint, use_container_width=True, hide_index=True)

    st.subheader("📜 Historial de diagnósticos")
    df_hist = pd.DataFrame(list_printer_diagnostics(int(datos.get("activo_id")), limit=50))
    st.dataframe(df_hist, use_container_width=True, hide_index=True)


def render_diagnostico(usuario: str) -> None:
    st.caption(f"Usuario activo: {usuario}")
    show_save_form_key = "diag_show_save_form"
    selected_printer_key = "diag_selected_printer"

    if show_save_form_key not in st.session_state:
        st.session_state[show_save_form_key] = False

    impresora_sel, activo_id_sel = _seleccionar_impresora()
    activos_lookup = {
        int(row["id"]): row
        for row in (listar_impresoras_activas() + listar_activos_disponibles())
        if row.get("id") is not None
    }
    activo_metadata = activos_lookup.get(int(activo_id_sel)) if activo_id_sel else None

    profile = _obtener_perfil_impresora(impresora_sel, activo_metadata)

    previous_printer = st.session_state.get(selected_printer_key)
    if previous_printer != impresora_sel:
        st.session_state[show_save_form_key] = False
    st.session_state[selected_printer_key] = impresora_sel

    archivo_diag, archivo_tanque, archivo_software, texto_manual = _capturar_entradas()

    capacidad_default = _obtener_capacidades_canonicas(activo_id_sel, impresora_sel)
    st.subheader("⚙️ Capacidad de tanques (ml)")
    c1, c2, c3, c4 = st.columns(4)
    capacidad = {
        "cyan": c1.number_input("Cyan (ml)", min_value=0.0, value=float(capacidad_default["cyan"]), step=1.0),
        "magenta": c2.number_input("Magenta (ml)", min_value=0.0, value=float(capacidad_default["magenta"]), step=1.0),
        "yellow": c3.number_input("Yellow (ml)", min_value=0.0, value=float(capacidad_default["yellow"]), step=1.0),
        "black": c4.number_input("Black (ml)", min_value=0.0, value=float(capacidad_default["black"]), step=1.0),
    }
    

    if st.button("🔍 Analizar diagnóstico"):
        texto_ocr = texto_manual.strip()
        imagen_diag = _convertir_archivo_a_imagen(archivo_diag) if archivo_diag else None
        if not texto_ocr and imagen_diag is not None:
            texto_ocr = pytesseract.image_to_string(imagen_diag, config="--psm 6")

        analisis_hoja = analizar_hoja_diagnostico(texto_ocr, {COLOR_LABELS[k]: v for k, v in capacidad.items()}, porcentajes_foto={})
        porcentajes_hoja = extraer_texto_diagnostico(texto_ocr).get("porcentajes", []) if texto_ocr else []

        imagen_software = _convertir_archivo_a_imagen(archivo_software) if archivo_software else None
        porcentajes_software = _extraer_porcentajes_por_ocr(imagen_software)

        imagen_tanque = _convertir_archivo_a_imagen(archivo_tanque) if archivo_tanque else None
        porcentajes_visual = _analizar_tanque_visual(imagen_tanque)

        fusion_pct = _fusionar_porcentajes(
            report_pct=porcentajes_hoja,
            software_pct=porcentajes_software,
            visual_pct=porcentajes_visual,
            ink_system_type=profile["ink_system_type"],
        )

        resultados = _calcular_ml_desde_porcentaje(fusion_pct, capacidad)
        vida = float(analisis_hoja.get("vida_cabezal_pct", 100.0))
        resumen = DiagnosticsService.summarize(resultados, vida)

        st.session_state["diag_last_analysis"] = {
            "impresora": impresora_sel,
            "activo_id": activo_id_sel,
            "resultados": resultados,
            "resumen": resumen,
            "contador_impresiones": int(analisis_hoja.get("contador_impresiones", 0)),
            "vida_cabezal_pct": vida,
            "desgaste_componentes": dict(analisis_hoja.get("desgaste_componentes", {})),
            "texto_ocr": texto_ocr,
            "porcentajes_hoja": porcentajes_hoja,
            "porcentajes_software": porcentajes_software,
            "porcentajes_visual": porcentajes_visual,
            "fusion_pct": fusion_pct,
            "capacidad": capacidad,
            "profile": profile,
            "archivos_principales": [
                payload
                for payload in (
                    _snapshot_upload(archivo_diag, "diagnostic_sheet"),
                    _snapshot_upload(archivo_tanque, "tank_photo"),
                    _snapshot_upload(archivo_software, "software_capture"),
                )
                if payload
            ],
        }
        st.session_state[show_save_form_key] = False
    datos = st.session_state.get("diag_last_analysis")
    if not datos or datos.get("impresora") != impresora_sel:
        st.session_state[show_save_form_key] = False
        return

    show_save_form = bool(st.session_state.get(show_save_form_key, False))
    st.caption(f"🐞 DEBUG show_save_form={show_save_form}")
    
    st.markdown("---")
    st.subheader("3) Resultado del análisis")
    _mostrar_resultados(datos["resultados"], datos["resumen"])
    r1, r2 = st.columns(2)
    r1.metric("Contador de páginas", int(datos.get("contador_impresiones", 0)))
    r2.metric("Vida del cabezal", f"{float(datos.get('vida_cabezal_pct', 0.0)):.2f}%")

    st.markdown("#### Resumen")
    st.write(
        {
            "Estado tintas": datos["resumen"].get("estado_tintas", "N/D"),
            "Estado cabezal": datos["resumen"].get("estado_cabezal", "N/D"),
            "Mín tinta (ml)": round(float(datos["resumen"].get("min_ml", 0.0)), 2),
        }
    )

    st.markdown("#### Señales detectadas")
    s1, s2, s3 = st.columns(3)
    s1.markdown("**Porcentajes hoja:**")
    s1.write([round(float(v), 2) for v in datos.get("porcentajes_hoja", [])])
    s2.markdown("**Porcentajes software:**")
    s2.write({k: round(float(v), 2) for k, v in datos.get("porcentajes_software", {}).items()})
    s3.markdown("**Porcentajes visuales:**")
    s3.write({k: round(float(v), 2) for k, v in datos.get("porcentajes_visual", {}).items()})

    if not datos.get("activo_id"):
        st.warning("Este análisis no está vinculado a un activo; Inventario puede actualizarse, pero Activos no recibirá cambios.")
    st.info("Análisis listo. Revisa los resultados y luego continúa a la fase de guardado.")

    if not show_save_form:
        if st.button("➡️ Continuar para guardar diagnóstico"):
            st.session_state[show_save_form_key] = True
            st.rerun()

    if show_save_form:
        _render_guardado_tecnico(usuario, impresora_sel, datos, capacidad)

    _render_historial(usuario, datos)

    contador_imp = int(datos.get("contador_impresiones", 0))
    if contador_imp > 0:
        st.info(f"📌 Total de páginas impresas detectado: {contador_imp}")
    if datos.get("texto_ocr"):
        with st.expander("Ver texto OCR usado"):
            st.code(str(datos["texto_ocr"]))

    if not datos.get("texto_ocr") and not datos.get("fusion_pct"):
        st.warning("No se detectaron datos automáticos. Ingresa texto OCR o una foto más clara para mejores resultados.")
