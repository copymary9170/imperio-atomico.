"""Domain layer for the enterprise legal department."""

from legal.domain.enums import Confidentiality, MatterStatus, RiskLevel
from legal.domain.entities import LegalMatter, LegalParty
from legal.domain.errors import DomainError, InvalidTransitionError, SegregationOfDutiesError

__all__ = [
    "Confidentiality",
    "DomainError",
    "InvalidTransitionError",
    "LegalMatter",
    "LegalParty",
    "MatterStatus",
    "RiskLevel",
    "SegregationOfDutiesError",
]
