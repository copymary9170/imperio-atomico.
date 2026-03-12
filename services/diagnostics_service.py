from __future__ import annotations

import re
from typing import Any


# Orden de colores estándar
_COLOR_ORDER = ("Cyan", "Magenta", "Yellow", "Black")


# Niveles de alerta configurables
CRITICAL_LEVEL = 10
LOW_LEVEL = 25


# Regex compilados
PERCENT_REGEX = re.compile(r"(\d{1,3})\s*%")
COUNTER_PATTERNS = [
    re.compile(r"(?:total\s*(?:(?:de|do)\s*)?(?:pages|paginas|p[aá]ginas)\s*impresas?)\D{0,30}(\d{1,9})", re.I),
    re.compile(r"(?:pages\s*printed|printed\s*pages)\D{0,15}(\d{1,9})", re.I),
    re.compile(r"(?:total\s*(?:prints|impresiones)|print\s*count|contador)\D{0,10}(\d{1,9})", re.I),
    re.compile(r"(?:pages|paginas|p[aá]ginas)\D{0,30}(\d{1,9})", re.I),
]

IGNORE_COUNTER_CONTEXT = [
    re.compile(r"\bpin\b", re.I),
    re.compile(r"serial", re.I),
    re.compile(r"imei", re.I),
]


class DiagnosticsService:
    """Herramientas de diagnóstico para impresoras."""


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

@@ -117,56 +125,75 @@ class DiagnosticsService:
        return {
            "estado_tintas": estado_tintas,
            "estado_cabezal": estado_cabezal,
            "vida_cabezal_pct": vida if vida is not None else 100.0,
            "min_ml": round(min_ml, 2),
            "max_ml": round(max_ml, 2),
        }


def extraer_texto_diagnostico(texto_ocr: str | None) -> dict[str, Any]:

    texto = str(texto_ocr or "")

    porcentajes = [float(v) for v in PERCENT_REGEX.findall(texto)]

    return {
        "porcentajes": [_clamp_percentage(v) for v in porcentajes],
        "contadores": extraer_contador_impresiones(texto),
    }


def extraer_contador_impresiones(texto_ocr: str | None) -> dict[str, int]:

    texto = str(texto_ocr or "")

    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]

    for linea in lineas:
        if any(p.search(linea) for p in IGNORE_COUNTER_CONTEXT):
            continue
        for patron in COUNTER_PATTERNS:
            m = patron.search(linea)
            if not m:
                continue
            valor = int(m.group(1))
            if valor <= 0:
                continue
            return {"contador_impresiones": valor}

    for patron in COUNTER_PATTERNS:
        m = patron.search(texto)
        if m:
            valor = int(m.group(1))
            if valor > 0:
                return {"contador_impresiones": valor}

    texto_filtrado = "\n".join(
        ln for ln in lineas if not any(p.search(ln) for p in IGNORE_COUNTER_CONTEXT)
    )
    numeros = [int(v) for v in re.findall(r"\b\d{3,9}\b", texto_filtrado)]

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
