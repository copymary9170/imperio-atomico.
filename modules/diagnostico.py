from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.diagnostics_service import DiagnosticsService, extraer_contador_impresiones
from ui.state import SessionStateService


def _load_vision_stack() -> tuple[Any, Any, Any, Any, Any]:
    import cv2
    import numpy as np
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image

    return cv2, np, pytesseract, convert_from_bytes, Image


def _convertir_imagen(uploaded_file) -> Any:
    if uploaded_file is None:
        return None

    cv2, np, _, convert_from_bytes, Image = _load_vision_stack()
    file_bytes = uploaded_file.read()

    if uploaded_file.type == "application/pdf":
        pages = convert_from_bytes(file_bytes)
        if not pages:
            return None
        return cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR)

    pil_img = Image.open(uploaded_file)
    return cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _detectar_por_texto(img: Any) -> tuple[list[float], str, int]:
    if img is None:
        return [], "", 0

    _, _, pytesseract, _, _ = _load_vision_stack()
    texto = pytesseract.image_to_string(img)
    porcentajes = [float(v) for v in re.findall(r"(\d{1,3})\s*%", texto)]
    contador_impresiones = int(extraer_contador_impresiones(texto).get("contador_impresiones", 0) or 0)
    return porcentajes, texto, contador_impresiones


def _detectar_vida_cabezal(img: Any) -> float | None:
    if img is None:
        return None

    _, _, pytesseract, _, _ = _load_vision_stack()
    texto = pytesseract.image_to_string(img)
    m = re.search(r"(?:head|cabezal)[^\d]{0,15}(\d{1,3})\s*%", texto, flags=re.IGNORECASE)
    if not m:
        return None

    return max(0.0, min(100.0, float(m.group(1))))


def _detectar_por_foto(img: Any) -> dict[str, float]:
    if img is None:
        return {}

    cv2, np, _, _, _ = _load_vision_stack()

    if len(img.shape) < 3:
        return {}

    h, w, _ = img.shape
    _ = h

    zonas = {
        "Black": img[:, 0:int(w * 0.25)],
        "Cyan": img[:, int(w * 0.25):int(w * 0.50)],
        "Magenta": img[:, int(w * 0.50):int(w * 0.75)],
        "Yellow": img[:, int(w * 0.75):w],
    }

    niveles: dict[str, float] = {}
    for color, zona in zonas.items():
        gray = cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        cobertura = float(np.sum(thresh > 0) / max(1, thresh.size))
        niveles[color] = max(0.0, min(100.0, cobertura * 100.0))

    return niveles


def _obtener_capacidad_default(nombre_impresora: str) -> dict[str, float]:
    nombre = str(nombre_impresora or "").lower()
    if "122" in nombre:
        return {"Black": 12.4, "Cyan": 14.0, "Magenta": 14.0, "Yellow": 14.0}
    return {"Black": 70.0, "Cyan": 70.0, "Magenta": 70.0, "Yellow": 70.0}


def _actualizar_desgaste_activo(conn, activo_id: int, uso: float) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()}

    if "uso_actual" in cols:
        conn.execute(
            "UPDATE activos SET uso_actual = COALESCE(uso_actual,0) + ? WHERE id=?",
            (float(uso), int(activo_id)),
        )


def _guardar_diagnostico(
    impresora_sel: str,
    archivo_diag,
    archivo_tanque,
    resultados: dict[str, float | None],
    vida_cabezal_pct: float,
    contador_impresiones: int,
    capacidad: dict[str, float],
) -> tuple[bool, str]:
    try:
        with db_transaction() as conn:
            row_imp = conn.execute(
                "SELECT id FROM activos WHERE equipo=? AND COALESCE(activo,1)=1 LIMIT 1",
                (impresora_sel,),
            ).fetchone()

            if not row_imp:
                return False, "La impresora seleccionada no está activa"

            activo_id = int(row_imp[0])
            usuario_diag = SessionStateService.get_current_user("Sistema")
            total_consumido_ml = 0.0

            for color, ml_detectado in resultados.items():
                if ml_detectado is None:
                    continue

                nombre_item = f"Tinta {color} {impresora_sel}"
                inv_row = conn.execute(
                    """
                    SELECT id, COALESCE(cantidad,0), COALESCE(costo_promedio, COALESCE(precio_usd,0),0)
                    FROM inventario
                    WHERE item=? AND COALESCE(activo,1)=1
                    LIMIT 1
                    """,
                    (nombre_item,),
                ).fetchone()

                if not inv_row:
                    continue

                item_id = int(inv_row[0])
                costo_ref = float(inv_row[2] or 0.0)
                capacidad_color = float(capacidad.get(color, 0.0) or 0.0)
                consumo = max(0.0, capacidad_color - float(ml_detectado or 0.0))

                if consumo <= 0:
                    continue

                conn.execute(
                    "UPDATE inventario SET cantidad = MAX(0, COALESCE(cantidad,0) - ?) WHERE id=?",
                    (float(consumo), item_id),
                )

                conn.execute(
                    """
                    INSERT INTO inventario_movs
                    (item_id, tipo, cantidad, saldo_antes, saldo_despues, costo_unitario, costo_total, motivo, usuario)
                    VALUES (
                        ?, 'SALIDA', ?,
                        COALESCE((SELECT cantidad + ? FROM inventario WHERE id=?), 0),
                        COALESCE((SELECT cantidad FROM inventario WHERE id=?), 0),
                        ?, ?,
                        'Consumo detectado por diagnóstico de impresora', ?
                    )
                    """,
                    (
                        item_id,
                        float(consumo),
                        float(consumo),
                        item_id,
                        item_id,
                        float(costo_ref),
                        float(consumo * costo_ref),
                        usuario_diag,
                    ),
                )
                total_consumido_ml += float(consumo)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnosticos_impresora (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                    activo_id INTEGER,
                    archivo_nombre TEXT,
                    archivo_blob BLOB,
                    vida_cabezal_pct REAL,
                    usuario TEXT,
                    tinta_restante_ml REAL,
                    nivel_c REAL,
                    nivel_m REAL,
                    nivel_y REAL,
                    nivel_k REAL
                )
                """
            )

            resumen = DiagnosticsService.summarize(resultados=resultados, vida_cabezal_pct=vida_cabezal_pct)

            conn.execute(
                """
                INSERT INTO diagnosticos_impresora (
                    activo_id, archivo_nombre, archivo_blob, vida_cabezal_pct, usuario,
                    tinta_restante_ml, nivel_c, nivel_m, nivel_y, nivel_k
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activo_id,
                    (archivo_diag.name if archivo_diag is not None else (archivo_tanque.name if archivo_tanque is not None else "diagnostico_sin_archivo")),
                    None,
                    float(vida_cabezal_pct),
                    usuario_diag,
                    float(resumen.get("min_ml", 0.0)),
                    float(resultados.get("Cyan") or 0.0),
                    float(resultados.get("Magenta") or 0.0),
                    float(resultados.get("Yellow") or 0.0),
                    float(resultados.get("Black") or 0.0),
                ),
            )

            _actualizar_desgaste_activo(conn, activo_id, max(1.0, total_consumido_ml))

            cols_activos = {r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()}
            if "vida_restante" in cols_activos and "vida_total" in cols_activos:
                conn.execute(
                    """
                    UPDATE activos
                    SET vida_restante = CASE
                        WHEN vida_total IS NULL OR vida_total <= 0 THEN vida_restante
                        ELSE MAX(0, MIN(COALESCE(vida_restante, vida_total), vida_total * (? / 100.0)))
                    END
                    WHERE id = ?
                    """,
                    (float(vida_cabezal_pct), activo_id),
                )

            if contador_impresiones > 0:
                if "contador_impresiones" not in cols_activos:
                    conn.execute("ALTER TABLE activos ADD COLUMN contador_impresiones INTEGER DEFAULT 0")
                conn.execute(
                    "UPDATE activos SET contador_impresiones=? WHERE id=?",
                    (int(contador_impresiones), int(activo_id)),
                )

        return True, "Diagnóstico guardado correctamente"
    except Exception as e:
        return False, f"No se pudo guardar diagnóstico: {e}"


def render_diagnostico(usuario: str):
    st.title("🧠 Diagnóstico Inteligente Industrial")

    try:
        with db_transaction() as conn:
            df_imp = pd.read_sql_query(
                "SELECT id, equipo FROM activos WHERE COALESCE(activo,1)=1 ORDER BY equipo",
                conn,
            )
    except Exception as e:
        st.error(f"No fue posible cargar impresoras: {e}")
        return

    if df_imp.empty:
        st.warning("No hay impresoras registradas en activos.")
        return

    impresora_sel = st.selectbox("Seleccionar impresora", df_imp["equipo"])
    archivo_diag = st.file_uploader("📄 Hoja diagnóstico", type=["pdf", "png", "jpg", "jpeg"])
    archivo_tanque = st.file_uploader("🖼 Foto de tanques", type=["png", "jpg", "jpeg"])

    st.subheader("⚙️ Configuración de capacidad de tanques (ml)")
    defaults = _obtener_capacidad_default(impresora_sel)
    c1, c2, c3, c4 = st.columns(4)
    capacidad = {
        "Cyan": c1.number_input("Cyan (ml)", min_value=0.0, value=float(defaults["Cyan"]), step=1.0),
        "Magenta": c2.number_input("Magenta (ml)", min_value=0.0, value=float(defaults["Magenta"]), step=1.0),
        "Yellow": c3.number_input("Yellow (ml)", min_value=0.0, value=float(defaults["Yellow"]), step=1.0),
        "Black": c4.number_input("Black (ml)", min_value=0.0, value=float(defaults["Black"]), step=1.0),
    }

    texto_manual = st.text_area("Texto OCR manual (opcional, mejora precisión)")

    if st.button("🚀 ANALIZAR", use_container_width=True):
        if archivo_diag is None and archivo_tanque is None and not texto_manual.strip():
            st.error("Sube al menos un archivo o pega texto OCR.")
            return

        try:
            img_diag = _convertir_imagen(archivo_diag) if archivo_diag is not None else None
            img_tanque = _convertir_imagen(archivo_tanque) if archivo_tanque is not None else None
        except Exception as e:
            st.error(f"No se pudo procesar la imagen/PDF: {e}")
            return

        porcentajes, texto_ocr_diag, contador_imp = _detectar_por_texto(img_diag)
        if texto_manual.strip():
            porcentajes_txt = [float(v) for v in re.findall(r"(\d{1,3})\s*%", texto_manual)]
            if porcentajes_txt:
                porcentajes = porcentajes_txt
                texto_ocr_diag = texto_manual
            contador_imp = max(contador_imp, int(extraer_contador_impresiones(texto_manual).get("contador_impresiones", 0) or 0))

        porcentaje_foto = _detectar_por_foto(img_tanque)

        resultados = DiagnosticsService.merge_levels(
            capacidad=capacidad,
            porcentajes_texto=porcentajes,
            porcentajes_foto=porcentaje_foto,
        )

        vida_cabezal_pct = DiagnosticsService.resolve_head_life(
            detected_value=_detectar_vida_cabezal(img_diag),
            porcentajes_foto=porcentaje_foto,
        )

        resumen_diag = DiagnosticsService.summarize(resultados=resultados, vida_cabezal_pct=vida_cabezal_pct)

        st.subheader("Resultado final")
        st.dataframe(
            pd.DataFrame(
                [{"Color": c, "Nivel (ml)": v if v is not None else "No detectado"} for c, v in resultados.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Vida cabezal", f"{vida_cabezal_pct:.2f}%")
        m2.metric("Estado tintas", str(resumen_diag.get("estado_tintas", "N/D")))
        m3.metric("Estado cabezal", str(resumen_diag.get("estado_cabezal", "N/D")))

        if contador_imp > 0:
            st.info(f"📌 Total Prints detectado: {contador_imp}")

        with st.expander("Texto OCR detectado"):
            st.text(texto_ocr_diag or "(sin texto detectado)")

        ok, msg = _guardar_diagnostico(
            impresora_sel=impresora_sel,
            archivo_diag=archivo_diag,
            archivo_tanque=archivo_tanque,
            resultados=resultados,
            vida_cabezal_pct=vida_cabezal_pct,
            contador_impresiones=contador_imp,
            capacidad=capacidad,
        )

        if ok:
            st.success(msg)
        else:
            st.error(msg)
