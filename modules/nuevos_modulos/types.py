from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleBlueprint:
    key: str
    name: str
    icon: str
    category: str
    summary: str
    capabilities: tuple[str, ...]
    integrations: tuple[str, ...]
    business_value: str
    priority: str


@dataclass(frozen=True)
class DataFlow:
    source: str
    target: str
    payload: str
    frequency: str
