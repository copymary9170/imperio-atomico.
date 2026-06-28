from __future__ import annotations

from legal.domain.enums import MatterStatus
from legal.domain.errors import InvalidTransitionError

TRANSITIONS: dict[MatterStatus, set[MatterStatus]] = {
    MatterStatus.DRAFT: {MatterStatus.IN_REVIEW, MatterStatus.ARCHIVED},
    MatterStatus.IN_REVIEW: {MatterStatus.CHANGES_REQUESTED, MatterStatus.APPROVED},
    MatterStatus.CHANGES_REQUESTED: {MatterStatus.DRAFT, MatterStatus.IN_REVIEW},
    MatterStatus.APPROVED: {MatterStatus.PENDING_SIGNATURE, MatterStatus.ACTIVE, MatterStatus.ARCHIVED},
    MatterStatus.PENDING_SIGNATURE: {MatterStatus.ACTIVE, MatterStatus.CHANGES_REQUESTED},
    MatterStatus.ACTIVE: {MatterStatus.SUSPENDED, MatterStatus.CLOSED, MatterStatus.ARCHIVED},
    MatterStatus.SUSPENDED: {MatterStatus.ACTIVE, MatterStatus.CLOSED},
    MatterStatus.CLOSED: {MatterStatus.ARCHIVED},
    MatterStatus.ARCHIVED: set(),
}

FINAL_STATUSES = {MatterStatus.CLOSED, MatterStatus.ARCHIVED}
APPROVAL_STATUSES = {MatterStatus.APPROVED, MatterStatus.PENDING_SIGNATURE, MatterStatus.ACTIVE}


def allowed_targets(current_status: MatterStatus) -> set[MatterStatus]:
    return set(TRANSITIONS.get(current_status, set()))


def validate_transition(current_status: MatterStatus, target_status: MatterStatus, *, approver: str = "", comment: str = "") -> None:
    if target_status not in allowed_targets(current_status):
        raise InvalidTransitionError("Transicion juridica no permitida.")
    if target_status in APPROVAL_STATUSES and not approver.strip():
        raise InvalidTransitionError("La transicion requiere aprobador.")
    if target_status in FINAL_STATUSES and not comment.strip():
        raise InvalidTransitionError("La transicion final requiere comentario.")
