from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class _TextEnum(str, Enum):
    """String enum compatible with Python versions before StrEnum."""

    def __str__(self) -> str:
        return self.value


class LegalPermission(_TextEnum):
    VIEW = "legal.view"
    CREATE = "legal.create"
    UPDATE = "legal.update"
    REVIEW = "legal.review"
    APPROVE = "legal.approve"
    SIGN = "legal.sign"
    PUBLISH = "legal.publish"
    EXPORT = "legal.export"
    AUDIT_VIEW = "legal.audit.view"
    ADMIN = "legal.admin"


@dataclass(slots=True)
class SecurityContext:
    user: str
    roles: tuple[str, ...] = ()
    permissions: frozenset[str] = field(default_factory=frozenset)
    session_id: str = ""
    correlation_id: str = ""

    def has(self, permission: LegalPermission | str) -> bool:
        value = permission.value if isinstance(permission, LegalPermission) else permission
        return LegalPermission.ADMIN.value in self.permissions or value in self.permissions


def require_permission(context: SecurityContext, permission: LegalPermission | str) -> None:
    if not context.has(permission):
        value = permission.value if isinstance(permission, LegalPermission) else permission
        raise PermissionError(f"Permiso juridico requerido: {value}")
