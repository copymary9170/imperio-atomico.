import pytest

from legal.audit.events import AuditEvent
from legal.security.rbac import LegalPermission, SecurityContext, require_permission


def test_security_context_denies_by_default():
    context = SecurityContext(user="admin")
    with pytest.raises(PermissionError):
        require_permission(context, LegalPermission.CREATE)


def test_security_context_allows_explicit_permission():
    context = SecurityContext(user="admin", permissions=frozenset({LegalPermission.CREATE.value}))
    require_permission(context, LegalPermission.CREATE)


def test_admin_permission_allows_all_actions():
    context = SecurityContext(user="admin", permissions=frozenset({LegalPermission.ADMIN.value}))
    require_permission(context, LegalPermission.EXPORT)


def test_audit_event_is_sealed_with_hash():
    event = AuditEvent(
        actor="admin",
        action="TEST",
        entity_type="legal_matter",
        entity_id=1,
        before={},
        after={"status": "Borrador"},
        context={"session_id": "s1"},
    ).seal()
    assert len(event.event_hash) == 64
