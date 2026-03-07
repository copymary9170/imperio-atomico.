from __future__ import annotations

import re
from typing import Any

_COLOR_ORDER = ("Cyan", "Magenta", "Yellow", "Black")

class DiagnosticsService:
    """Utilidades de normalización para diagnóstico de tanques y cabezal."""

    @staticmethod
    def merge_levels(
        capacidad: dict[str, float],
        porcentajes_texto: list[float] | None = None,
        porcentajes_foto: dict[str, float] | None = None,
    ) -> dict[str, float | None]:
        porcentajes_texto = list(porcentajes_texto or [])
        porcentajes_foto = dict(porcentajes_foto or {})

        merged: dict[str, float | None] = {}
        for idx, color in enumerate(_COLOR_ORDER):
            pct_text = None
            if idx < len(porcentajes_texto):
                pct_text = _clamp_percentage(porcentajes_texto[idx])

            pct_photo = _clamp_percentage(porcentajes_foto.get(color))
            if pct_photo is None:
                # Compatibilidad por si llegan claves minúsculas.
                pct_photo = _clamp_percentage(porcentajes_foto.get(color.lower()))

            final_pct = _prefer_non_zero(pct_text, pct_photo)
            capacidad_color = _safe_float(capacidad.get(color), default=0.0)
            if capacidad_color <= 0 or final_pct is None:
                merged[color] = None
            else:
                merged[color] = round(capacidad_color * (final_pct / 100.0), 2)

        return merged

    @staticmethod
    def resolve_head_life(
        detected_value: float | None,
        porcentajes_foto: dict[str, float] | None = None,
    ) -> float:
        detected = _clamp_percentage(detected_value)
        if detected is not None:
            return detected

        porcentajes_foto = dict(porcentajes_foto or {})
        valores = [
            _clamp_percentage(porcentajes_foto.get(color))
            for color in _COLOR_ORDER
        ]
        validos = [v for v in valores if v is not None]
        if not validos:
            return 100.0

        return round(sum(validos) / len(validos), 2)

    @staticmethod
    def summarize(resultados: dict[str, float | None], vida_cabezal_pct: float | None = None) -> dict[str, Any]:
        niveles = [float(v) for v in resultados.values() if v is not None]
        min_ml = min(niveles) if niveles else 0.0
        max_ml = max(niveles) if niveles else 0.0

        estado_tintas = "Sin datos"
        if niveles:
            if min_ml < 10:
                estado_tintas = "Crítico"
            elif min_ml < 25:
                estado_tintas = "Bajo"
            else:
                estado_tintas = "Óptimo"

        vida = _clamp_percentage(vida_cabezal_pct)
        if vida is None:
            estado_cabezal = "Desconocido"
        elif vida < 30:
            estado_cabezal = "Reemplazo recomendado"
        elif vida < 60:
            estado_cabezal = "Mantenimiento preventivo"
        else:
            estado_cabezal = "Operativo"

        return {
            "estado_tintas": estado_tintas,
            "estado_cabezal": estado_cabezal,
            "vida_cabezal_pct": vida if vida is not None else 100.0,
            "min_ml": round(min_ml, 2),
            "max_ml": round(max_ml, 2),
        }


def extraer_texto_diagnostico(texto_ocr: str | None) -> dict[str, Any]:
    texto = str(texto_ocr or "")
    porcentajes = [float(v) for v in re.findall(r"(\d{1,3})\s*%", texto)]
    return {
        "porcentajes": [_clamp_percentage(v) for v in porcentajes],
        "contadores": extraer_contador_impresiones(texto),
    }


def extraer_contador_impresiones(texto_ocr: str | None) -> dict[str, int]:
    texto = str(texto_ocr or "")
    patrones = [
        r"(?:total\s*(?:prints|impresiones)|print\s*count|contador)\D{0,10}(\d{1,9})",
        r"(?:pages|paginas|p[aá]ginas)\D{0,10}(\d{1,9})",
    ]
    for patron in patrones:
        m = re.search(patron, texto, flags=re.IGNORECASE)
        if m:
            return {"contador_impresiones": int(m.group(1))}

    # Fallback: tomar el número entero más grande del texto cuando no hay etiqueta explícita.
    numeros = [int(v) for v in re.findall(r"\b\d{3,9}\b", texto)]
    return {"contador_impresiones": max(numeros) if numeros else 0}


def analizar_hoja_diagnostico(
    texto_ocr: str | None,
    capacidad: dict[str, float],
    porcentajes_foto: dict[str, float] | None = None,
    vida_cabezal_detectada: float | None = None,
) -> dict[str, Any]:
    extraido = extraer_texto_diagnostico(texto_ocr)
    porcentajes_texto = extraido.get("porcentajes", [])
    resultados = DiagnosticsService.merge_levels(
        capacidad=capacidad,
        porcentajes_texto=porcentajes_texto,
        porcentajes_foto=porcentajes_foto,
    )
    vida_cabezal = DiagnosticsService.resolve_head_life(
        detected_value=vida_cabezal_detectada,
        porcentajes_foto=porcentajes_foto,
    )
    resumen = DiagnosticsService.summarize(resultados=resultados, vida_cabezal_pct=vida_cabezal)
    return {
        "resultados": resultados,
        "vida_cabezal_pct": vida_cabezal,
        "resumen": resumen,
        "contadores": extraido.get("contadores", {"contador_impresiones": 0}),
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp_percentage(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0:
        return 0.0
    if num > 100:
        return 100.0
    return num


def _prefer_non_zero(primary: float | None, secondary: float | None) -> float | None:
    if primary is not None and primary > 0:
        return primary
    if secondary is not None:
        return secondary
    return primary
