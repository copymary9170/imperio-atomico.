rom __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.diagnostics_service import DiagnosticsService, extraer_contador_impresiones
from ui.state import SessionStateService


def _resolver_columnas_inventario(conn) -> tuple[str, str, str, str]:
    cols_inv = {r[1] for r in conn.execute("PRAGMA table_info(inventario)").fetchall()}

    nombre_col = "item" if "item" in cols_inv else "nombre"
    stock_col = "cantidad" if "cantidad" in cols_inv else "stock_actual"
    costo_col = "costo_promedio" if "costo_promedio" in cols_inv else "costo_unitario_usd"
    activo_col = "activo" if "activo" in cols_inv else "estado"

    return nombre_col, stock_col, costo_col, activo_col


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
@@ -97,116 +108,121 @@ def _obtener_capacidad_default(nombre_impresora: str) -> dict[str, float]:
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
            nombre_col, stock_col, costo_col, activo_col = _resolver_columnas_inventario(conn)

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
                    f"""
                    SELECT id, COALESCE({stock_col},0), COALESCE({costo_col},0)
                    FROM inventario
                    WHERE {nombre_col}=?
                      AND COALESCE({activo_col}, {'1' if activo_col == 'activo' else "'activo'"})={'1' if activo_col == 'activo' else "'activo'"}
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
                    f"UPDATE inventario SET {stock_col} = MAX(0, COALESCE({stock_col},0) - ?) WHERE id=?",
                    (float(consumo), item_id),
                )

                tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                if "inventario_movs" in tablas:
                    conn.execute(
                        f"""
                        INSERT INTO inventario_movs
                        (item_id, tipo, cantidad, saldo_antes, saldo_despues, costo_unitario, costo_total, motivo, usuario)
                        VALUES (
                            ?, 'SALIDA', ?,
                            COALESCE((SELECT {stock_col} + ? FROM inventario WHERE id=?), 0),
                            COALESCE((SELECT {stock_col} FROM inventario WHERE id=?), 0),
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
@@ -319,44 +335,44 @@ def render_diagnostico(usuario: str):
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
            st.info(f"📌 Total de páginas impresas detectado: {contador_imp}")

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
