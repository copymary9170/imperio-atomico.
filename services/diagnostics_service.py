from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import numpy as np


@dataclass
class PrinterDiagnosisResult:
    niveles_ml: Dict[str, Optional[float]]
    vida_cabezal_pct: float
    tinta_restante_ml: float


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
        return PrinterDiagnosisResult(
            niveles_ml=resultados,
            vida_cabezal_pct=max(0.0, min(100.0, float(vida_cabezal_pct))),
            tinta_restante_ml=float(sum(v for v in resultados.values() if v is not None)),
        )
