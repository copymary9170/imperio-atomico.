from __future__ import annotations

from typing import Dict, Any

from modules.configuracion import _to_float, DEFAULT_CONFIG


def get_rates(config: Dict[str, Any]) -> Dict[str, float]:
    """Devuelve tasas centralizadas del sistema ERP."""

    def f(key: str) -> float:
        return _to_float(config, key, float(DEFAULT_CONFIG.get(key, 0)))

    return {
        "bcv": f("tasa_bcv"),
        "binance": f("tasa_binance"),
        "kontigo_entrada": f("kontigo_entrada"),
        "kontigo_salida": f("kontigo_salida"),
    }


def get_rates_display(config: Dict[str, Any]) -> Dict[str, str]:
    r = get_rates(config)
    return {
        "bcv": f"{r['bcv']:,.2f} Bs/USD",
        "binance": f"{r['binance']:,.2f} Bs/USD",
        "kontigo_entrada": f"{r['kontigo_entrada']:,.2f} Bs/USD",
        "kontigo_salida": f"{r['kontigo_salida']:,.2f} Bs/USD",
    }
