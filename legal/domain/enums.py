from __future__ import annotations

from enum import Enum


class _TextEnum(str, Enum):
    """String enum compatible with Python versions before StrEnum."""

    def __str__(self) -> str:
        return self.value


class MatterStatus(_TextEnum):
    """Controlled lifecycle states for any legal record."""

    DRAFT = "Borrador"
    IN_REVIEW = "En revision"
    CHANGES_REQUESTED = "Cambios solicitados"
    APPROVED = "Aprobado"
    PENDING_SIGNATURE = "Pendiente de firma"
    ACTIVE = "Vigente"
    SUSPENDED = "Suspendido"
    CLOSED = "Cerrado"
    ARCHIVED = "Archivado"


class RiskLevel(_TextEnum):
    """Enterprise legal risk scale."""

    LOW = "Bajo"
    MEDIUM = "Medio"
    HIGH = "Alto"
    CRITICAL = "Critico"


class Confidentiality(_TextEnum):
    """Document and matter confidentiality classes."""

    PUBLIC = "Publico"
    INTERNAL = "Interno"
    CONFIDENTIAL = "Confidencial"
    RESTRICTED = "Restringido"


class LegalArea(_TextEnum):
    """Functional areas covered by the Legal Department."""

    PUBLIC_LEGAL = "Documentos publicos"
    CONTRACTS = "Contratos"
    PRIVACY = "Privacidad"
    INTELLECTUAL_PROPERTY = "Propiedad intelectual"
    CLAIMS = "Reclamos y garantias"
    LITIGATION = "Litigios"
    COMPLIANCE = "Cumplimiento"
    RISKS = "Riesgos"
    LICENSES = "Licencias y permisos"
    GOVERNANCE = "Gobierno corporativo"
