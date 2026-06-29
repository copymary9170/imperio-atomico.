from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateContractCommand:
    matter_id: int
    contract_type: str
    effective_date: str = ""
    end_date: str = ""
    renewal_type: str = "No renovable"
    notice_days: int = 30
    amount: float | None = None
    currency: str = "USD"
    governing_law: str = ""


@dataclass(frozen=True, slots=True)
class CreateRiskCommand:
    title: str
    category: str
    likelihood: int
    impact: int
    owner: str
    matter_id: int | None = None
    controls: str = ""
    residual_score: int | None = None
    review_date: str = ""


@dataclass(frozen=True, slots=True)
class CreateComplianceObligationCommand:
    regulation: str
    obligation: str
    owner: str
    matter_id: int | None = None
    authority: str = ""
    frequency: str = "Unica"
    due_date: str = ""
    control_reference: str = ""
    evidence_reference: str = ""


@dataclass(frozen=True, slots=True)
class CreateLitigationCaseCommand:
    matter_id: int
    proceeding_type: str
    authority: str = ""
    case_number: str = ""
    external_counsel: str = ""
    claim_amount: float | None = None
    currency: str = "USD"
    probability: str = "Posible"
    provision_amount: float | None = None
    next_hearing_at: str = ""
    strategy: str = ""


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    title: str
    assigned_to: str
    created_by: str
    matter_id: int | None = None
    due_date: str = ""
    priority: str = "Media"
