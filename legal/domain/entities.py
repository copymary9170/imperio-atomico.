from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import uuid4

from legal.domain.enums import Confidentiality, MatterStatus, RiskLevel
from legal.domain.errors import SegregationOfDutiesError
from legal.domain.workflow import validate_transition


@dataclass(slots=True)
class LegalParty:
    """Person or organization involved in a legal matter."""

    name: str
    party_type: str
    tax_id: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    uuid: str = field(default_factory=lambda: str(uuid4()))

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("La parte juridica requiere nombre.")
        if not self.party_type.strip():
            raise ValueError("La parte juridica requiere tipo.")


@dataclass(slots=True)
class LegalMatter:
    """Aggregate root for enterprise legal work."""

    code: str
    matter_type: str
    title: str
    description: str
    owner: str
    created_by: str
    reviewer: str = ""
    approver: str = ""
    status: MatterStatus = MatterStatus.DRAFT
    risk_level: RiskLevel = RiskLevel.MEDIUM
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    counterparty: str = ""
    jurisdiction: str = "Venezuela"
    due_date: date | None = None
    expiration_date: date | None = None
    legal_basis: str = ""
    tags: str = ""
    legal_hold: bool = False
    retention_years: int = 5
    uuid: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    def validate(self) -> None:
        if not self.code.strip():
            raise ValueError("El expediente requiere codigo.")
        if not self.matter_type.strip():
            raise ValueError("El expediente requiere tipo.")
        if not self.title.strip():
            raise ValueError("El expediente requiere titulo.")
        if not self.owner.strip():
            raise ValueError("El expediente requiere responsable.")
        if not self.created_by.strip():
            raise ValueError("El expediente requiere creador.")
        if self.retention_years < 1 or self.retention_years > 100:
            raise ValueError("La retencion debe estar entre 1 y 100 anios.")
        self._validate_segregation()

    def transition_to(self, target_status: MatterStatus, *, comment: str = "") -> None:
        validate_transition(self.status, target_status, approver=self.approver, comment=comment)
        self.status = target_status
        self.updated_at = datetime.utcnow()

    def _validate_segregation(self) -> None:
        people = [p.strip().casefold() for p in (self.owner, self.reviewer, self.approver) if p and p.strip()]
        if len(people) != len(set(people)):
            raise SegregationOfDutiesError("Responsable, revisor y aprobador deben ser diferentes.")
