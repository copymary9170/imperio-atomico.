from __future__ import annotations

from typing import Any

from models.operacion_industrial import CriticalityScore


class PriorizacionService:
    """Motor de criticidad para priorizar backlog de mantenimiento."""

    def __init__(
        self,
        pesos: dict[str, float] | None = None,
    ) -> None:
        self.pesos = pesos or {
            "vida_restante": 0.35,
            "componente_critico": 0.2,
            "diagnostico": 0.25,
            "frecuencia_fallas": 0.2,
        }

    def score_for_asset(self, asset: dict[str, Any], history: list[dict[str, Any]] | None = None) -> CriticalityScore:
        history = history or []
        razones: list[str] = []

        vida_restante = float(asset.get("vida_restante_pct") or 100.0)
        score_vida = max(0.0, min(100.0, 100.0 - vida_restante))
        if vida_restante <= 25:
            razones.append("Vida restante crítica")

        clase = str(asset.get("clase_registro") or "")
        component_score = 100.0 if clase == "componente" else 30.0
        if component_score >= 100:
            razones.append("Componente/repuesto impacta continuidad")

        confidence = str(asset.get("confidence_level") or "medium").lower()
        estimation = str(asset.get("estimation_mode") or "none").lower()
        diagnostico_score = {"high": 35.0, "medium": 60.0, "low": 85.0}.get(confidence, 60.0)
        if estimation in {"visual", "manual"}:
            diagnostico_score += 10
            razones.append("Diagnóstico heurístico requiere validación")

        fallas = sum(1 for row in history if str(row.get("origen")) in {"diagnostico_mantenimiento", "mantenimiento_industrial"})
        fail_score = min(100.0, fallas * 25.0)
        if fail_score >= 50:
            razones.append("Alta recurrencia de fallas/mantenimientos")

        score = (
            score_vida * self.pesos["vida_restante"]
            + component_score * self.pesos["componente_critico"]
            + diagnostico_score * self.pesos["diagnostico"]
            + fail_score * self.pesos["frecuencia_fallas"]
        )

        if score >= 80:
            prioridad = "P1 - Inmediata"
        elif score >= 60:
            prioridad = "P2 - Alta"
        elif score >= 40:
            prioridad = "P3 - Media"
        else:
            prioridad = "P4 - Preventiva"

        if not razones:
            razones.append("Operación estable con monitoreo preventivo")

        return CriticalityScore(
            activo_id=int(asset.get("id") or asset.get("activo_id") or 0),
            activo_label=f"#{asset.get('id') or asset.get('activo_id')} · {asset.get('equipo') or 'Activo'}",
            prioridad=prioridad,
            score=round(score, 2),
            razones=razones,
        )
