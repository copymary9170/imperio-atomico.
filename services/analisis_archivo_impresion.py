from __future__ import annotations

import io
from dataclasses import dataclass, asdict
from typing import Any

import fitz
import numpy as np
from PIL import Image


@dataclass
class PageAnalysis:
    page_number: int
    width_cm: float
    height_cm: float
    width_px: int
    height_px: int
    color_mode: str
    coverage_c_pct: float
    coverage_m_pct: float
    coverage_y_pct: float
    coverage_k_pct: float
    coverage_total_pct: float
    inked_area_cm2: float


@dataclass
class FileAnalysis:
    filename: str
    file_type: str
    pages: int
    total_area_cm2: float
    total_inked_area_cm2: float
    avg_c_pct: float
    avg_m_pct: float
    avg_y_pct: float
    avg_k_pct: float
    avg_total_pct: float
    has_color: bool
    page_details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rgb_to_cmyk_coverage(rgb: np.ndarray) -> tuple[float, float, float, float, float]:
    arr = rgb.astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    k = 1.0 - np.maximum(np.maximum(r, g), b)
    denom = np.maximum(1.0 - k, 1e-6)
    c = (1.0 - r - k) / denom
    m = (1.0 - g - k) / denom
    y = (1.0 - b - k) / denom
    c = np.where(k >= 0.999, 0.0, np.clip(c, 0.0, 1.0))
    m = np.where(k >= 0.999, 0.0, np.clip(m, 0.0, 1.0))
    y = np.where(k >= 0.999, 0.0, np.clip(y, 0.0, 1.0))
    k = np.clip(k, 0.0, 1.0)

    # El fondo casi blanco no se considera tinta. Evita cobrar ruido JPEG o escaneo.
    neutral_white = (r > 0.985) & (g > 0.985) & (b > 0.985)
    c = np.where(neutral_white, 0.0, c)
    m = np.where(neutral_white, 0.0, m)
    y = np.where(neutral_white, 0.0, y)
    k = np.where(neutral_white, 0.0, k)

    c_pct = float(c.mean() * 100.0)
    m_pct = float(m.mean() * 100.0)
    y_pct = float(y.mean() * 100.0)
    k_pct = float(k.mean() * 100.0)
    total_pct = c_pct + m_pct + y_pct + k_pct
    return c_pct, m_pct, y_pct, k_pct, total_pct


def _analyze_image(image: Image.Image, page_number: int, width_cm: float | None = None, height_cm: float | None = None) -> PageAnalysis:
    rgb_img = image.convert("RGB")
    rgb = np.asarray(rgb_img)
    width_px, height_px = rgb_img.size

    dpi = image.info.get("dpi", (300, 300))
    dpi_x = float(dpi[0] or 300)
    dpi_y = float(dpi[1] or 300)
    if width_cm is None:
        width_cm = width_px / dpi_x * 2.54
    if height_cm is None:
        height_cm = height_px / dpi_y * 2.54

    c, m, y, k, total = _rgb_to_cmyk_coverage(rgb)
    page_area = max(float(width_cm) * float(height_cm), 0.0)
    coverage_fraction = min(max(total / 400.0, 0.0), 1.0)
    inked_area = page_area * coverage_fraction
    color_mode = "Color" if max(c, m, y) >= 0.15 else "Escala de grises / negro"
    return PageAnalysis(
        page_number=page_number,
        width_cm=round(float(width_cm), 3),
        height_cm=round(float(height_cm), 3),
        width_px=int(width_px),
        height_px=int(height_px),
        color_mode=color_mode,
        coverage_c_pct=round(c, 4),
        coverage_m_pct=round(m, 4),
        coverage_y_pct=round(y, 4),
        coverage_k_pct=round(k, 4),
        coverage_total_pct=round(total, 4),
        inked_area_cm2=round(inked_area, 4),
    )


def analyze_uploaded_file(file_obj, render_dpi: int = 144) -> FileAnalysis:
    if file_obj is None:
        raise ValueError("Debes subir un archivo PDF, PNG, JPG o JPEG.")
    filename = str(getattr(file_obj, "name", "archivo"))
    mime = str(getattr(file_obj, "type", "")).lower()
    data = file_obj.getvalue()
    pages: list[PageAnalysis] = []

    if filename.lower().endswith(".pdf") or "pdf" in mime:
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            zoom = max(float(render_dpi), 72.0) / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            for idx, page in enumerate(doc):
                rect = page.rect
                width_cm = rect.width / 72.0 * 2.54
                height_cm = rect.height / 72.0 * 2.54
                pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pages.append(_analyze_image(image, idx + 1, width_cm, height_cm))
        finally:
            doc.close()
        file_type = "PDF"
    else:
        image = Image.open(io.BytesIO(data))
        pages.append(_analyze_image(image, 1))
        file_type = image.format or "Imagen"

    if not pages:
        raise ValueError("El archivo no contiene páginas analizables.")

    total_area = sum(p.width_cm * p.height_cm for p in pages)
    total_inked = sum(p.inked_area_cm2 for p in pages)
    count = len(pages)
    avg_c = sum(p.coverage_c_pct for p in pages) / count
    avg_m = sum(p.coverage_m_pct for p in pages) / count
    avg_y = sum(p.coverage_y_pct for p in pages) / count
    avg_k = sum(p.coverage_k_pct for p in pages) / count
    avg_total = sum(p.coverage_total_pct for p in pages) / count
    has_color = any(p.color_mode == "Color" for p in pages)

    return FileAnalysis(
        filename=filename,
        file_type=file_type,
        pages=count,
        total_area_cm2=round(total_area, 4),
        total_inked_area_cm2=round(total_inked, 4),
        avg_c_pct=round(avg_c, 4),
        avg_m_pct=round(avg_m, 4),
        avg_y_pct=round(avg_y, 4),
        avg_k_pct=round(avg_k, 4),
        avg_total_pct=round(avg_total, 4),
        has_color=has_color,
        page_details=[asdict(p) for p in pages],
    )


def estimate_ink_ml(analysis: FileAnalysis, full_coverage_ml: dict[str, float], copies: float = 1.0) -> dict[str, float]:
    copies = max(float(copies or 1), 0.0)
    channels = {
        "C": analysis.avg_c_pct,
        "M": analysis.avg_m_pct,
        "Y": analysis.avg_y_pct,
        "K": analysis.avg_k_pct,
    }
    result: dict[str, float] = {}
    for channel, coverage_pct in channels.items():
        ml_100 = max(float(full_coverage_ml.get(channel, 0.0) or 0.0), 0.0)
        result[channel] = round(ml_100 * (coverage_pct / 100.0) * analysis.pages * copies, 8)
    result["TOTAL"] = round(sum(result.values()), 8)
    return result
