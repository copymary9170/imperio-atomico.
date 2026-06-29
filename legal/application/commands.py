from __future__ import annotations

from dataclasses import dataclass

from legal.domain.enums import Confidentiality, MatterStatus, RiskLevel


@dataclass(frozen=True, slots=True)
class CreateLegalMatterCommand:
    code: str
    matter_type: str
    title: str
    description: str
    owner: str
    created_by: str
    reviewer: str = ""
    approver: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    counterparty: str = ""
    jurisdiction: str = "Venezuela"
    legal_basis: str = ""
    tags: str = ""
    retention_years: int = 5


@dataclass(frozen=True, slots=True)
class ChangeMatterStatusCommand:
    matter_id: int
    target_status: MatterStatus
    comment: str
