from __future__ import annotations

from datetime import date
from typing import Any

from models.operacion_industrial import (
    EstadoMantenimiento,
    MaintenanceOrderInput,
    TipoMantenimiento,
    TraceabilityEvent,
)
from repositories.operacion_industrial_repository import OperacionIndustrialRepository
from services.priorizacion_service import PriorizacionService


class OperacionIndustrialService:
    def __init__(
        self,
        repository: OperacionIndustrialRepository | None = None,
        priorizacion_service: PriorizacionService | None = None,
    ) -> None:
        self.repository = repository or OperacionIndustrialRepository()
        self.priorizacion_service = priorizacion_service or PriorizacionService()
        self.bootstrap()

    def bootstrap(self) -> None:
        """Inicializa esquema del módulo de operación industrial de forma explícita."""
        self.repository.ensure_schema()

    def get_executive_overview(self) -> dict[str, Any]:
        metrics = self.repository.get_overview_metrics()
        assets = self.repository.list_assets_catalog()
        history = self.repository.list_unified_history(limit=500)

        scored_assets = []
        for asset in assets:
            score = self.priorizacion_service.score_for_asset(asset, history)
            scored_assets.append(
                {
                    "activo_id": score.activo_id,
                    "activo_label": score.activo_label,
                    "prioridad": score.prioridad,
                    "score": score.score,
                    "razones": "; ".join(score.razones),
                }
            )

        scored_assets.sort(key=lambda x: x["score"], reverse=True)
        metrics["activos_criticos"] = scored_assets[:10]
        metrics["proximos_vencimientos"] = sorted(
            [
                a
                for a in assets
                if a.get("vida_restante_pct") is not None
                and float(a.get("vida_restante_pct") or 0.0) <= 30.0
            ],
            key=lambda x: float(x.get("vida_restante_pct") or 100.0),
        )[:10]
        return metrics

    def list_assets(self) -> list[dict[str, Any]]:
        return self.repository.list_assets_catalog()

    def list_recent_diagnostics(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_recent_diagnostics(limit=limit)

    def list_maintenance_backlog(self) -> list[dict[str, Any]]:
        items = self.repository.list_open_maintenance_orders()
        history = self.repository.list_unified_history(limit=500)
        by_asset = {a["id"]: a for a in self.repository.list_assets_catalog()}

        enriched: list[dict[str, Any]] = []
        for item in items:
            asset = dict(by_asset.get(int(item.get("activo_id") or 0), {}))
            asset.update(
                {
                    "id": item.get("activo_id"),
                    "equipo": item.get("equipo") or asset.get("equipo"),
                }
            )
            score = self.priorizacion_service.score_for_asset(asset, history)
            merged = dict(item)
            merged["criticidad_score"] = score.score
            merged["prioridad"] = score.prioridad
            merged["razones"] = "; ".join(score.razones)
            enriched.append(merged)

        enriched.sort(key=lambda row: (float(row.get("criticidad_score") or 0.0), row.get("fecha_programada") or ""), reverse=True)
        return enriched

    def create_maintenance_order(
        self,
        *,
        activo_id: int,
        tipo: str,
        estado: str,
        fecha_programada: date,
        tecnico_responsable: str,
        descripcion: str,
        usuario: str,
        costo_estimado: float = 0.0,
        notas: str = "",
        evidencia_url: str = "",
    ) -> int:
        if fecha_programada < date(2000, 1, 1):
            raise ValueError("La fecha programada debe ser posterior al 2000-01-01.")

        payload = MaintenanceOrderInput(
            activo_id=int(activo_id),
            tipo=TipoMantenimiento(str(tipo).lower()),
            estado=EstadoMantenimiento(str(estado).lower()),
            fecha_programada=fecha_programada,
            tecnico_responsable=str(tecnico_responsable).strip(),
            descripcion=str(descripcion).strip(),
            costo_estimado=max(0.0, float(costo_estimado or 0.0)),
            notas=str(notas or "").strip(),
            evidencia_url=str(evidencia_url or "").strip(),
        )

        if not payload.tecnico_responsable:
            raise ValueError("Debes indicar el técnico/responsable.")
        if not payload.descripcion:
            raise ValueError("La orden de mantenimiento requiere descripción.")

        order_id = self.repository.create_maintenance_order(payload, usuario=usuario)
        self.repository.log_traceability(
            TraceabilityEvent(
                activo_id=payload.activo_id,
                accion="crear_mantenimiento",
                detalle=f"Orden #{order_id}: {payload.tipo.value}/{payload.estado.value} - {payload.descripcion}",
                usuario=usuario,
                costo=payload.costo_estimado,
                evidencia_ref=payload.evidencia_url,
                metadata={"payload": payload.__dict__},
            )
        )
        return order_id

    def list_unified_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.list_unified_history(limit=limit)
