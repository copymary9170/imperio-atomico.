from __future__ import annotations

from dataclasses import dataclass


def _safe(value: float | int | None) -> float:
    """
    Garantiza que el valor sea numérico y no negativo.
    """
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


@dataclass
class PrintingCostBreakdown:
    """
    Desglose del costo de impresión.
    """
    paper_cost: float
    ink_cost: float
    machine_depreciation: float
    electricity_cost: float

    @property
    def total(self) -> float:
        """
        Retorna el costo total de impresión.
        """
        return round(
            self.paper_cost
            + self.ink_cost
            + self.machine_depreciation
            + self.electricity_cost,
            4,
        )


def calculate_printing_cost(
    paper_units: float,
    paper_unit_cost: float,
    ink_ml: float,
    ink_cost_per_ml: float,
    machine_hourly_depreciation: float,
    hours_used: float,
    electricity_kwh: float,
    electricity_cost_per_kwh: float,
) -> PrintingCostBreakdown:
    """
    Calcula el costo real de impresión considerando:

    - papel
    - tinta
    - depreciación de máquina
    - electricidad
    """

    paper_units = _safe(paper_units)
    paper_unit_cost = _safe(paper_unit_cost)
    ink_ml = _safe(ink_ml)
    ink_cost_per_ml = _safe(ink_cost_per_ml)
    machine_hourly_depreciation = _safe(machine_hourly_depreciation)
    hours_used = _safe(hours_used)
    electricity_kwh = _safe(electricity_kwh)
    electricity_cost_per_kwh = _safe(electricity_cost_per_kwh)

    return PrintingCostBreakdown(
        paper_cost=round(paper_units * paper_unit_cost, 4),
        ink_cost=round(ink_ml * ink_cost_per_ml, 4),
        machine_depreciation=round(machine_hourly_depreciation * hours_used, 4),
        electricity_cost=round(electricity_kwh * electricity_cost_per_kwh, 4),
    )


def calculate_daily_profit(
    sales_usd: float,
    expenses_usd: float,
    production_costs_usd: float,
) -> float:
    """
    Calcula la ganancia diaria real.

    Fórmula:
        ventas - gastos - costos de producción
    """

    sales = _safe(sales_usd)
    expenses = _safe(expenses_usd)
    production = _safe(production_costs_usd)

    return round(sales - expenses - production, 2)
