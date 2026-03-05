from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import fitz
import numpy as np
import pandas as pd


@dataclass
class PrinterDiagnosisResult:
    niveles_ml: Dict[str, Optional[float]]
    vida_cabezal_pct: float
    tinta_restante_ml: float


@dataclass
class PredictiveSummary:
    consumo_promedio_ml_pag: float
    paginas_hasta_mantenimiento: Optional[float]
    degradacion_vida_pct_por_1000_pag: float
    limpiezas_por_1000_pag: float
    riesgo_falla: str
    alertas: List[str]


COLOR_KEYWORDS = {
    "C": ["cyan", "cian", "c"],
    "M": ["magenta", "m"],
    "Y": ["yellow", "amarillo", "y"],
    "K": ["black", "negro", "bk", "k"],
}


# -----------------------------
# OCR + parsing helpers
# -----------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _extract_first_number(text: str, pattern: str, multiplier: float = 1.0) -> Optional[float]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return _safe_float(match.group(1)) * multiplier


def _normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _read_image_for_ocr(image: np.ndarray) -> str:
    try:
        import cv2
        import pytesseract
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenCV/Tesseract no disponibles para OCR") from exc

    if image is None or image.size == 0:
        raise ValueError("Imagen de diagnóstico vacía o inválida")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return _normalize_ocr_text(pytesseract.image_to_string(thr, config="--oem 3 --psm 6"))


def _load_first_page_as_bgr(path: str | Path) -> np.ndarray:
    try:
        import cv2
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenCV no disponible") from exc

    path = str(path)
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        doc = fitz.open(path)
        if doc.page_count == 0:
            raise ValueError("PDF sin páginas")
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return bgr

    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo abrir la imagen de diagnóstico")
    return img


def _extract_percent_by_label(text: str, labels: Iterable[str]) -> Optional[float]:
    for label in labels:
        pattern = rf"{re.escape(label)}[^\d%]{{0,20}}(\d{{1,3}}(?:[\.,]\d+)?)\s*%"
        val = _extract_first_number(text, pattern)
        if val is not None:
            return max(0.0, min(100.0, val))
    return None


def extraer_texto_diagnostico(path_archivo: str | Path) -> str:
    """Extrae texto OCR desde hoja de diagnóstico (PDF o imagen)."""
    image = _load_first_page_as_bgr(path_archivo)
    return _read_image_for_ocr(image)


def _extract_int_by_patterns(text: str, patterns: Iterable[str]) -> int:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            token = re.sub(r"[^\d]", "", str(match.group(1)))
            if token:
                return int(token)
    return 0


def extraer_contador_impresiones(texto_ocr: str) -> Dict[str, int]:
    """Extrae contadores clave desde texto OCR de diagnóstico."""
    text = _normalize_ocr_text(texto_ocr)
    metrics = {
        "contador_impresiones": _extract_int_by_patterns(
            text,
            [
                r"total\s*prints?\s*[:=\-]?\s*([\d\.,]+)",
                r"print\s*counter\s*[:=\-]?\s*([\d\.,]+)",
                r"contador\s*impresiones\s*[:=\-]?\s*([\d\.,]+)",
            ],
        ),
        "total_pages": _extract_int_by_patterns(
            text,
            [
                r"total\s*pages\s*printed\s*[:=\-]?\s*([\d\.,]+)",
                r"total\s*pages\s*[:=\-]?\s*([\d\.,]+)",
                r"pages\s*printed\s*[:=\-]?\s*([\d\.,]+)",
            ],
        ),
        "pages_printed": _extract_int_by_patterns(
            text,
            [r"pages\s*printed\s*[:=\-]?\s*([\d\.,]+)"],
        ),
        "print_counter": _extract_int_by_patterns(
            text,
            [r"print\s*counter\s*[:=\-]?\s*([\d\.,]+)"],
        ),
        "cleaning_count": _extract_int_by_patterns(
            text,
            [
                r"head\s*cleaning\s*count\s*[:=\-]?\s*([\d\.,]+)",
                r"cleaning\s*count\s*[:=\-]?\s*([\d\.,]+)",
                r"cleaning\s*cycles?\s*[:=\-]?\s*([\d\.,]+)",
            ],
        ),
    }

    if metrics["contador_impresiones"] <= 0:
        metrics["contador_impresiones"] = max(metrics["print_counter"], metrics["total_pages"], metrics["pages_printed"])

    return metrics


def actualizar_activo_impresora(conn: sqlite3.Connection, impresora: str, contador_impresiones: int) -> bool:
    """Actualiza activos.contador_impresiones y vida_restante = vida_total - contador_impresiones."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()]
    if "contador_impresiones" not in cols:
        conn.execute("ALTER TABLE activos ADD COLUMN contador_impresiones INTEGER DEFAULT 0")

    row = conn.execute(
        """
        SELECT id, COALESCE(vida_total, 0)
        FROM activos
        WHERE equipo=? AND COALESCE(activo,1)=1
        LIMIT 1
        """,
        (impresora,),
    ).fetchone()
    if not row:
        return False

    activo_id = int(row[0])
    vida_total = _safe_float(row[1], 0.0)
    contador = max(0, int(contador_impresiones or 0))
    vida_restante = max(0.0, vida_total - float(contador))

    conn.execute(
        """
        UPDATE activos
        SET contador_impresiones=?, vida_restante=?
        WHERE id=?
        """,
        (contador, float(vida_restante), activo_id),
    )
    return True


def analizar_hoja_diagnostico(path_archivo: str | Path) -> Dict[str, Any]:
    """Lee hoja de diagnóstico (PDF/imagen) y extrae métricas por OCR."""
    text = extraer_texto_diagnostico(path_archivo)
    contadores = extraer_contador_impresiones(text)

    niveles_pct = {
        "C": _extract_percent_by_label(text, COLOR_KEYWORDS["C"]),
        "M": _extract_percent_by_label(text, COLOR_KEYWORDS["M"]),
        "Y": _extract_percent_by_label(text, COLOR_KEYWORDS["Y"]),
        "K": _extract_percent_by_label(text, COLOR_KEYWORDS["K"]),
    }

    paginas = _extract_first_number(text, r"(?:contador|pages?|paginas?)\D{0,15}(\d{1,9})")
    vida_cabezal = _extract_first_number(text, r"(?:vida\s*cabezal|head\s*life)\D{0,15}(\d{1,3}(?:[\.,]\d+)?)\s*%")
    ciclos_limpieza = _extract_first_number(text, r"(?:limpiezas?|cleaning\s*cycles?)\D{0,15}(\d{1,7})")
    fecha_str = None
    fecha_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", text)
    if fecha_match:
        fecha_str = fecha_match.group(1)

    errores = re.findall(r"(?:error|codigo|code)\s*[:#-]?\s*([A-Z0-9]{2,10})", text, flags=re.IGNORECASE)

    return {
        "ocr_text": text,
        "niveles_pct": niveles_pct,
        "paginas_impresas": int(contadores["total_pages"] or contadores["pages_printed"] or paginas or 0),
        "contador_impresiones": int(contadores["contador_impresiones"]),
        "print_counter": int(contadores["print_counter"]),
        "cleaning_count": int(contadores["cleaning_count"]),
        "vida_cabezal_pct": max(0.0, min(100.0, _safe_float(vida_cabezal, 0.0))),
        "ciclos_limpieza": int(contadores["cleaning_count"] or ciclos_limpieza or 0),
        "errores": sorted(set(errores)),
        "fecha_reporte": fecha_str,
    }


# -----------------------------
# OpenCV tank analysis
# -----------------------------

def leer_hoja_diagnostico(path_archivo: str | Path) -> Dict[str, Any]:
    """Alias público para análisis OCR completo de hoja de diagnóstico."""
    return analizar_hoja_diagnostico(path_archivo)


def calcular_consumo_tinta(capacidad: float, nivel_actual: float) -> float:
    """Calcula consumo real en ml con piso en cero."""
    return max(0.0, _safe_float(capacidad, 0.0) - _safe_float(nivel_actual, 0.0))


def actualizar_activos_impresora(conn: sqlite3.Connection, impresora: str, texto_ocr: str) -> bool:
    """Extrae contadores del OCR y actualiza `activos` para la impresora."""
    contadores = extraer_contador_impresiones(texto_ocr)
    return actualizar_activo_impresora(
        conn=conn,
        impresora=impresora,
        contador_impresiones=int(contadores.get("contador_impresiones", 0)),
    )


def actualizar_inventario_tintas(
    conn: sqlite3.Connection,
    impresora: str,
    capacidad_tanques_ml: Dict[str, float],
    niveles_ml_detectados: Dict[str, float],
    usuario: str,
    procesar_movimiento_inventario_fn: Callable[..., Tuple[bool, str]],
) -> Dict[str, float]:
    """Descarga inventario por consumo detectado: consumo = capacidad - nivel actual."""
    consumos: Dict[str, float] = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}

    for color in ["C", "M", "Y", "K"]:
        row = _find_inventory_row(conn, impresora, color)
        if not row:
            continue

        item_id, _stock_actual, costo = row
        capacidad_ml = _safe_float(capacidad_tanques_ml.get(color, 0.0), 0.0)
        nivel_detectado_ml = _safe_float(niveles_ml_detectados.get(color, 0.0), 0.0)
        consumo = calcular_consumo_tinta(capacidad=capacidad_ml, nivel_actual=nivel_detectado_ml)

        if consumo <= 0:
            continue

        ok, msg = procesar_movimiento_inventario_fn(
            item_id=item_id,
            tipo="SALIDA",
            cantidad=float(consumo),
            costo_unitario=float(costo),
            motivo="Consumo detectado por diagnóstico de impresora",
            usuario=str(usuario or "Sistema"),
            conn=conn,
        )
        if not ok:
            raise RuntimeError(f"Error ajustando inventario {color}: {msg}")

        consumos[color] = float(consumo)

    return consumos

def analizar_imagen_tanques(path_imagen: str | Path) -> Dict[str, float]:
    """Detecta niveles (%) C/M/Y/K en foto de tanques usando segmentación HSV."""
    try:
        import cv2
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("OpenCV no disponible") from exc

    img = _load_first_page_as_bgr(path_imagen)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    masks = {
        "C": cv2.inRange(hsv, np.array([75, 40, 40]), np.array([105, 255, 255])),
        "M": cv2.inRange(hsv, np.array([125, 40, 40]), np.array([170, 255, 255])),
        "Y": cv2.inRange(hsv, np.array([15, 70, 70]), np.array([40, 255, 255])),
        "K": cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 60])),
    }

    kernel = np.ones((3, 3), np.uint8)
    levels: Dict[str, float] = {}

    for color, mask in masks.items():
        clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel)
        coords = cv2.findNonZero(clean)
        if coords is None:
            levels[color] = 0.0
            continue

        x, y, w, h = cv2.boundingRect(coords)
        tank_roi = clean[y : y + h, x : x + w]
        col_sum = np.sum(tank_roi > 0, axis=1)
        active_rows = np.where(col_sum > max(3, int(w * 0.05)))[0]
        if active_rows.size == 0:
            levels[color] = 0.0
            continue

        filled_height = int(active_rows.max() - active_rows.min() + 1)
        levels[color] = max(0.0, min(100.0, (filled_height / max(1, h)) * 100.0))

    return levels


def calcular_ml_restantes(niveles_pct: Dict[str, float], capacidad_tanques_ml: Dict[str, float]) -> Dict[str, float]:
    return {
        color: max(0.0, _safe_float(capacidad_tanques_ml.get(color, 0.0)) * (_safe_float(niveles_pct.get(color, 0.0)) / 100.0))
        for color in ["C", "M", "Y", "K"]
    }


# -----------------------------
# DB integration + predictive intelligence
# -----------------------------
def _ensure_diagnosticos_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnosticos_impresora (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            impresora TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            nivel_c REAL,
            nivel_m REAL,
            nivel_y REAL,
            nivel_k REAL,
            vida_cabezal REAL,
            paginas_impresas INTEGER,
            ciclos_limpieza INTEGER DEFAULT 0,
            riesgo_falla TEXT,
            consumo_ml_estimado REAL DEFAULT 0
        )
        """
    )


def _find_inventory_row(conn: sqlite3.Connection, printer_name: str, color: str) -> Optional[Tuple[int, float, float]]:
    names = [
        f"Tinta {color} {printer_name}",
        f"Tinta {color}",
        f"Ink {color} {printer_name}",
        f"Ink {color}",
    ]
    for name in names:
        row = conn.execute(
            """
            SELECT id, COALESCE(cantidad,0), COALESCE(costo_promedio, COALESCE(precio_usd,0), 0)
            FROM inventario
            WHERE item=? AND COALESCE(activo,1)=1
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        if row:
            return int(row[0]), _safe_float(row[1]), _safe_float(row[2])
    return None


def actualizar_inventario_diagnostico(
    conn: sqlite3.Connection,
    impresora: str,
    niveles_ml_detectados: Dict[str, float],
    usuario: str,
    procesar_movimiento_inventario_fn: Callable[..., Tuple[bool, str]],
) -> Dict[str, float]:
    """Ajusta inventario con movimiento SALIDA por diagnóstico."""
    consumos: Dict[str, float] = {"C": 0.0, "M": 0.0, "Y": 0.0, "K": 0.0}
    for color in ["C", "M", "Y", "K"]:
        row = _find_inventory_row(conn, impresora, color)
        if not row:
            continue

        item_id, stock_actual, costo = row
        nivel_detectado = max(0.0, _safe_float(niveles_ml_detectados.get(color, 0.0)))
        consumo = max(0.0, stock_actual - nivel_detectado)
        if consumo <= 0:
            continue

        ok, msg = procesar_movimiento_inventario_fn(
            item_id=item_id,
            tipo="SALIDA",
            cantidad=float(consumo),
            costo_unitario=float(costo),
            motivo="Ajuste automático por diagnóstico de impresora",
            usuario=str(usuario or "Sistema"),
            conn=conn,
        )
        if not ok:
            raise RuntimeError(f"Error ajustando inventario {color}: {msg}")
        consumos[color] = float(consumo)

    return consumos


def _risk_label(vida_cabezal: float, min_tanque_pct: float, limpiezas_por_1000: float) -> str:
    score = 0
    if vida_cabezal < 20:
        score += 2
    elif vida_cabezal < 35:
        score += 1

    if min_tanque_pct < 15:
        score += 2
    elif min_tanque_pct < 25:
        score += 1

    if limpiezas_por_1000 > 25:
        score += 2
    elif limpiezas_por_1000 > 12:
        score += 1

    if score >= 4:
        return "ALTO"
    if score >= 2:
        return "MEDIO"
    return "BAJO"


def _build_predictive_summary(actual: Dict[str, Any], historico: pd.DataFrame) -> PredictiveSummary:
    alertas: List[str] = []

    vida_cabezal = _safe_float(actual.get("vida_cabezal_pct", 0.0))
    niveles_pct = actual.get("niveles_pct", {})
    min_tanque_pct = min((_safe_float(v, 100.0) for v in niveles_pct.values()), default=100.0)

    consumo_prom_ml_pag = 0.0
    degradacion_vida = 0.0
    limpiezas_por_1000 = 0.0
    paginas_hasta_mant: Optional[float] = None

    if not historico.empty and len(historico) >= 2:
        hist = historico.sort_values("paginas_impresas")
        d_pag = max(1.0, _safe_float(hist["paginas_impresas"].iloc[-1] - hist["paginas_impresas"].iloc[0], 1.0))
        d_cons = max(0.0, _safe_float(hist["consumo_ml_estimado"].iloc[-1] - hist["consumo_ml_estimado"].iloc[0], 0.0))
        consumo_prom_ml_pag = d_cons / d_pag

        d_vida = max(0.0, _safe_float(hist["vida_cabezal"].iloc[0] - hist["vida_cabezal"].iloc[-1], 0.0))
        degradacion_vida = (d_vida / d_pag) * 1000.0

        d_clean = max(0.0, _safe_float(hist["ciclos_limpieza"].iloc[-1] - hist["ciclos_limpieza"].iloc[0], 0.0))
        limpiezas_por_1000 = (d_clean / d_pag) * 1000.0

        vida_drop_per_page = d_vida / d_pag if d_pag > 0 else 0.0
        if vida_drop_per_page > 0:
            paginas_hasta_mant = max(0.0, (vida_cabezal - 20.0) / vida_drop_per_page)

    riesgo = _risk_label(vida_cabezal, min_tanque_pct, limpiezas_por_1000)

    if vida_cabezal < 20:
        alertas.append("Cabezal por debajo de 20% de vida")
    if min_tanque_pct < 15:
        alertas.append("Tanque de tinta por debajo de 15%")
    if limpiezas_por_1000 > 20:
        alertas.append("Limpiezas excesivas detectadas")

    return PredictiveSummary(
        consumo_promedio_ml_pag=float(consumo_prom_ml_pag),
        paginas_hasta_mantenimiento=paginas_hasta_mant,
        degradacion_vida_pct_por_1000_pag=float(degradacion_vida),
        limpiezas_por_1000_pag=float(limpiezas_por_1000),
        riesgo_falla=riesgo,
        alertas=alertas,
    )


def actualizar_estado_activo_impresora(
    conn: sqlite3.Connection,
    impresora: str,
    vida_cabezal_pct: float,
    paginas_impresas: int,
    riesgo_falla: str,
) -> None:
    row = conn.execute(
        "SELECT id, vida_total FROM activos WHERE equipo=? AND COALESCE(activo,1)=1 LIMIT 1",
        (impresora,),
    ).fetchone()
    if not row:
        return

    activo_id = int(row[0])
    vida_total = _safe_float(row[1], 100.0)
    vida_restante = max(0.0, min(vida_total, vida_total * (_safe_float(vida_cabezal_pct, 0.0) / 100.0)))
    estado = "Operativo" if riesgo_falla == "BAJO" else "Mantenimiento Preventivo" if riesgo_falla == "MEDIO" else "Riesgo Alto"

    conn.execute(
        """
        UPDATE activos
        SET vida_restante=?, desgaste=?, observaciones=TRIM(COALESCE(observaciones,'') || ' | Diagnóstico: riesgo=' || ? || ', páginas=' || ?)
        WHERE id=?
        """,
        (float(vida_restante), float(100.0 - _safe_float(vida_cabezal_pct, 0.0)), str(riesgo_falla), int(paginas_impresas), activo_id),
    )

    # Si existe columna estado en esta instalación, actualizarla.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(activos)").fetchall()]
    if "estado" in cols:
        conn.execute("UPDATE activos SET estado=? WHERE id=?", (estado, activo_id))


def procesar_diagnostico_impresora(
    conn: sqlite3.Connection,
    impresora: str,
    archivo_diagnostico: str | Path,
    foto_tanques: str | Path,
    capacidad_tanques_ml: Dict[str, float],
    usuario: str,
    procesar_movimiento_inventario_fn: Callable[..., Tuple[bool, str]],
) -> Dict[str, Any]:
    """Pipeline completo de diagnóstico + ajuste + predicción + reporte."""
    _ensure_diagnosticos_schema(conn)

    data_ocr = analizar_hoja_diagnostico(archivo_diagnostico)
    data_img = analizar_imagen_tanques(foto_tanques)

    niveles_pct = {
        c: float(np.mean([v for v in [data_ocr["niveles_pct"].get(c), data_img.get(c)] if v is not None]))
        if any(v is not None for v in [data_ocr["niveles_pct"].get(c), data_img.get(c)])
        else 0.0
        for c in ["C", "M", "Y", "K"]
    }

    niveles_ml = calcular_ml_restantes(niveles_pct=niveles_pct, capacidad_tanques_ml=capacidad_tanques_ml)
    consumos = actualizar_inventario_tintas(
        conn=conn,
        impresora=impresora,
        capacidad_tanques_ml=capacidad_tanques_ml,
        niveles_ml_detectados=niveles_ml,
        usuario=usuario,
        procesar_movimiento_inventario_fn=procesar_movimiento_inventario_fn,
    )

    consumo_estimado_total = float(sum(consumos.values()))

    historico = pd.read_sql_query(
        """
        SELECT fecha, nivel_c, nivel_m, nivel_y, nivel_k, vida_cabezal, paginas_impresas,
               ciclos_limpieza, COALESCE(consumo_ml_estimado,0) AS consumo_ml_estimado
        FROM diagnosticos_impresora
        WHERE impresora=?
        ORDER BY datetime(fecha) ASC
        """,
        conn,
        params=(impresora,),
    )

    actual_payload = {
        "vida_cabezal_pct": data_ocr["vida_cabezal_pct"],
        "niveles_pct": niveles_pct,
    }
    pred = _build_predictive_summary(actual_payload, historico)

    conn.execute(
        """
        INSERT INTO diagnosticos_impresora (
            impresora, fecha, nivel_c, nivel_m, nivel_y, nivel_k,
            vida_cabezal, paginas_impresas, ciclos_limpieza, riesgo_falla, consumo_ml_estimado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            impresora,
            datetime.now().isoformat(timespec="seconds"),
            float(niveles_pct["C"]),
            float(niveles_pct["M"]),
            float(niveles_pct["Y"]),
            float(niveles_pct["K"]),
            float(data_ocr["vida_cabezal_pct"]),
            int(data_ocr["paginas_impresas"]),
            int(data_ocr["ciclos_limpieza"]),
            pred.riesgo_falla,
            float(consumo_estimado_total),
        ),
    )

    actualizar_estado_activo_impresora(
        conn=conn,
        impresora=impresora,
        vida_cabezal_pct=data_ocr["vida_cabezal_pct"],
        paginas_impresas=data_ocr["paginas_impresas"],
        riesgo_falla=pred.riesgo_falla,
    )
    actualizar_activos_impresora(
        conn=conn,
        impresora=impresora,
        texto_ocr=str(data_ocr.get("ocr_text", "")),
    )
    conn.commit()

    return {
        "impresora": impresora,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "niveles_tinta_pct": niveles_pct,
        "niveles_tinta_ml": niveles_ml,
        "consumo_estimado_ml": consumo_estimado_total,
        "estado_cabezal": data_ocr["vida_cabezal_pct"],
        "riesgo_falla": pred.riesgo_falla,
        "paginas_impresas": data_ocr["paginas_impresas"],
        "alertas_mantenimiento": pred.alertas,
        "prediccion": {
            "consumo_promedio_ml_por_pagina": pred.consumo_promedio_ml_pag,
            "paginas_hasta_mantenimiento": pred.paginas_hasta_mantenimiento,
            "degradacion_vida_pct_por_1000_pag": pred.degradacion_vida_pct_por_1000_pag,
            "limpiezas_por_1000_pag": pred.limpiezas_por_1000_pag,
        },
        "errores_detectados": data_ocr["errores"],
        "fecha_reporte_ocr": data_ocr["fecha_reporte"],
    }


class DiagnosticsService:
    @staticmethod
    def merge_levels(capacidad: Dict[str, float], porcentajes_texto: Iterable[float], porcentajes_foto: Dict[str, float]) -> Dict[str, Optional[float]]:
        arr_texto = list(porcentajes_texto or [])
        resultados: Dict[str, Optional[float]] = {}
        for i, color in enumerate(capacidad.keys()):
            p_texto = arr_texto[i] if i < len(arr_texto) else None
            p_foto = porcentajes_foto.get(color)
            if p_texto is not None and p_foto is not None:
                porcentaje = (float(p_texto) + float(p_foto)) / 2.0
            elif p_texto is not None:
                porcentaje = float(p_texto)
            elif p_foto is not None:
                porcentaje = float(p_foto)
            else:
                porcentaje = None
            resultados[color] = (float(capacidad[color]) * porcentaje / 100.0) if porcentaje is not None else None
        return resultados

    @staticmethod
    def resolve_head_life(detected_value: Optional[float], porcentajes_foto: Dict[str, float]) -> float:
        if detected_value is not None:
            return max(0.0, min(100.0, float(detected_value)))
        cobertura_ref = np.mean([v for v in porcentajes_foto.values()]) if porcentajes_foto else 75.0
        return max(5.0, min(100.0, 100.0 - (100.0 - float(cobertura_ref)) * 0.6))


    @staticmethod
    def summarize(resultados: Dict[str, Optional[float]], vida_cabezal_pct: float) -> PrinterDiagnosisResult:
        alias_colores = {
            "C": ["C", "Cyan"],
            "M": ["M", "Magenta"],
            "Y": ["Y", "Yellow"],
            "K": ["K", "Black", "BK"],
        }

        niveles_ml: Dict[str, Optional[float]] = {}
        for color, aliases in alias_colores.items():
            valor = None
            for key in aliases:
                if key in resultados and resultados.get(key) is not None:
                    valor = float(resultados[key])
                    break
            niveles_ml[color] = valor

        tinta_restante_ml = float(sum(v for v in niveles_ml.values() if v is not None))
        return PrinterDiagnosisResult(
            niveles_ml=niveles_ml,
            vida_cabezal_pct=max(0.0, min(100.0, float(vida_cabezal_pct))),
            tinta_restante_ml=tinta_restante_ml,
        )
