from __future__ import annotations

from enum import StrEnum


class MatterStatus(StrEnum):
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


class RiskLevel(StrEnum):
    """Enterprise legal risk scale."""

    LOW = "Bajo"
    MEDIUM = "Medio"
    HIGH = "Alto"
    CRITICAL = "Critico"


class Confidentiality(StrEnum):
    """Document and matter confidentiality classes."""

    PUBLIC = "Publico"
    INTERNAL = "Interno"
    CONFIDENTIAL = "Confidencial"
    RESTRICTED = "Restringido"


class LegalArea(StrEnum):
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
