from __future__ import annotations

from typing import Any


# ============================================================
# 🧹 LIMPIEZA DE TEXTO
# ============================================================

def clean_text(value: Any) -> str:
    """
    Limpia texto ingresado por el usuario.

    - elimina espacios extra
    - convierte None a ""
    - normaliza saltos de espacio
    """

    return " ".join(str(value or "").strip().split())


# ============================================================
# 🔒 TEXTO OBLIGATORIO
# ============================================================

def require_text(value: Any, field_name: str) -> str:
    """
    Garantiza que un campo de texto tenga contenido.
    """

    text = clean_text(value)

    if not text:
        raise ValueError(f"{field_name} es obligatorio")

    return text


# ============================================================
# 🔢 VALIDAR NÚMERO POSITIVO
# ============================================================

def as_positive(
    value: Any,
    field_name: str,
    *,
    allow_zero: bool = True
) -> float:
    """
    Convierte un valor a número positivo seguro.

    Parámetros
    ----------
    allow_zero:
        True  → permite 0
        False → requiere > 0
    """

    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} debe ser un número válido")

    if allow_zero:

        if number < 0:
            raise ValueError(f"{field_name} no puede ser negativo")

    else:

        if number <= 0:
            raise ValueError(f"{field_name} debe ser mayor a cero")

    return number


# ============================================================
# 💰 REDONDEO MONETARIO
# ============================================================

def money(value: Any) -> float:
    """
    Normaliza valores monetarios a 2 decimales.
    """

    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0
