from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class ClaseActivo(str, Enum):
    EQUIPO_PRINCIPAL = "equipo_principal"
    COMPONENTE = "componente"
    HERRAMIENTA = "herramienta"


class EstadoMantenimiento(str, Enum):
    PENDIENTE = "pendiente"
    PROGRAMADO = "programado"
    EN_EJECUCION = "en_ejecucion"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"


class TipoMantenimiento(str, Enum):
    PREVENTIVO = "preventivo"
    CORRECTIVO = "correctivo"


@dataclass(slots=True)
class MaintenanceOrderInput:
    activo_id: int
    tipo: TipoMantenimiento
    estado: EstadoMantenimiento
    fecha_programada: date
    tecnico_responsable: str
    descripcion: str
    costo_estimado: float = 0.0
    notas: str = ""
    evidencia_url: str = ""


@dataclass(slots=True)
class CriticalityScore:
    activo_id: int
    activo_label: str
    prioridad: str
    score: float
    razones: list[str]


@dataclass(slots=True)
class TraceabilityEvent:
    activo_id: int | None
    accion: str
    detalle: str
    usuario: str
    costo: float
    evidencia_ref: str
    metadata: dict[str, Any]
    created_at: datetime | None = None
