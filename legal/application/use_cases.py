from __future__ import annotations

from dataclasses import asdict

from legal.application.commands import ChangeMatterStatusCommand, CreateLegalMatterCommand
from legal.audit.events import AuditEvent
from legal.domain.entities import LegalMatter
from legal.repositories.contracts import UnitOfWork
from legal.security.rbac import LegalPermission, SecurityContext, require_permission


class CreateLegalMatterUseCase:
    """Create a legal matter through authorization, validation and audit."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def execute(self, command: CreateLegalMatterCommand, context: SecurityContext) -> int:
        require_permission(context, LegalPermission.CREATE)
        matter = LegalMatter(**asdict(command))
        matter.validate()
        with self.uow as uow:
            matter_id = uow.matters.add(matter)
            event = AuditEvent(
                actor=context.user,
                action="LEGAL_MATTER_CREATED",
                entity_type="legal_matter",
                entity_id=matter_id,
                before={},
                after=asdict(matter),
                context={"session_id": context.session_id, "correlation_id": context.correlation_id},
                previous_hash=uow.audit.last_hash(),
            ).seal()
            uow.audit.add(event)
            uow.commit()
            return matter_id


class ChangeMatterStatusUseCase:
    """Change legal matter status through domain policy and audit."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def execute(self, command: ChangeMatterStatusCommand, context: SecurityContext) -> None:
        require_permission(context, LegalPermission.UPDATE)
        with self.uow as uow:
            matter = uow.matters.get(command.matter_id)
            if matter is None:
                raise ValueError("Expediente juridico no encontrado.")
            before = asdict(matter)
            matter.transition_to(command.target_status, comment=command.comment)
            uow.matters.update(command.matter_id, matter)
            event = AuditEvent(
                actor=context.user,
                action="LEGAL_MATTER_STATUS_CHANGED",
                entity_type="legal_matter",
                entity_id=command.matter_id,
                before=before,
                after=asdict(matter),
                context={"comment": command.comment, "session_id": context.session_id, "correlation_id": context.correlation_id},
                previous_hash=uow.audit.last_hash(),
            ).seal()
            uow.audit.add(event)
            uow.commit()
