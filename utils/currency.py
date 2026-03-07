from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_CURRENCIES = ("USD", "BS", "USDT", "KONTIGO")


@dataclass(frozen=True)
class CurrencyAmount:
    currency: str
    amount: float
    fx_rate: float


def validate_currency(currency: str) -> str:
    normalized = currency.upper().strip()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Moneda no soportada: {currency}")
    return normalized


def convert_to_usd(amount: float, currency: str, fx_rate: float) -> float:
    currency = validate_currency(currency)
    if amount < 0:
        raise ValueError("Monto inválido")
    if currency in {"USD", "USDT", "KONTIGO"}:
        return round(amount, 4)
    if fx_rate <= 0:
        raise ValueError("La tasa BCV debe ser mayor a cero")
    return round(amount / fx_rate, 4)


def convert_to_bs(amount_usd: float, fx_rate: float) -> float:
    if fx_rate <= 0:
        raise ValueError("La tasa BCV debe ser mayor a cero")
    return round(amount_usd * fx_rate, 2)
