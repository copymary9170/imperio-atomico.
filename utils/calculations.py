from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PrintingCostBreakdown:
    paper_cost: float
    ink_cost: float
    machine_depreciation: float
    electricity_cost: float

    @property
    def total(self) -> float:
        return round(
           self.paper_cost + self.ink_cost + self.machine_depreciation + self.electricity_cost,
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
    return PrintingCostBreakdown(
        paper_cost=round(paper_units * paper_unit_cost, 4),
        ink_cost=round(ink_ml * ink_cost_per_ml, 4),
        machine_depreciation=round(machine_hourly_depreciation * hours_used, 4),
        electricity_cost=round(electricity_kwh * electricity_cost_per_kwh, 4),
    )


def calculate_daily_profit(sales_usd: float, expenses_usd: float, production_costs_usd: float) -> float:
    return round(sales_usd - expenses_usd - production_costs_usd, 2)
