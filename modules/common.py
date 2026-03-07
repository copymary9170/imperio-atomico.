from __future__ import annotations

from typing import Any


def clean_text(value: Any) -> str:
    """Normalize user-entered text by trimming whitespace and collapsing gaps."""
    return " ".join(str(value or "").strip().split())


def require_text(value: Any, field_name: str) -> str:
    text = clean_text(value)
    if not text:
        raise ValueError(f"{field_name} es obligatorio")
    return text


def as_positive(value: Any, field_name: str, *, allow_zero: bool = True) -> float:
    number = float(value or 0.0)
    if allow_zero and number < 0:
        raise ValueError(f"{field_name} no puede ser negativo")
    if not allow_zero and number <= 0:
        raise ValueError(f"{field_name} debe ser mayor a cero")
    return number


def money(value: Any) -> float:
    return round(float(value or 0.0), 2)
