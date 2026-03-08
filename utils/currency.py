from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_CURRENCIES = ("USD", "BS", "USDT", "KONTIGO")


def _safe(value: float | int | None) -> float:
    """
    Convierte el valor a float y evita valores inválidos.
    """
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass(frozen=True)
class CurrencyAmount:
    """
    Representa un monto en una moneda específica.
    """
    currency: str
    amount: float
    fx_rate: float


def validate_currency(currency: str) -> str:
    """
    Normaliza y valida la moneda.
    """
    normalized = str(currency or "").upper().strip()

    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Moneda no soportada: {currency}")

    return normalized


def convert_to_usd(amount: float, currency: str, fx_rate: float) -> float:
    """
    Convierte un monto a USD.
    """

    currency = validate_currency(currency)
    amount = _safe(amount)

    if amount < 0:
        raise ValueError("Monto inválido")

    if currency in {"USD", "USDT", "KONTIGO"}:
        return round(amount, 4)

    fx_rate = _safe(fx_rate)

    if fx_rate <= 0:
        raise ValueError("La tasa BCV debe ser mayor a cero")

    return round(amount / fx_rate, 4)


def convert_to_bs(amount_usd: float, fx_rate: float) -> float:
    """
    Convierte USD a bolívares usando la tasa BCV.
    """

    amount_usd = _safe(amount_usd)
    fx_rate = _safe(fx_rate)

    if amount_usd < 0:
        raise ValueError("Monto inválido")

    if fx_rate <= 0:
        raise ValueError("La tasa BCV debe ser mayor a cero")

    return round(amount_usd * fx_rate, 2)
