from __future__ import annotations


def test_operational_migration_constants_are_versioned():
    from legal.migrations.v101_operational_domains import MIGRATION_NAME, MIGRATION_VERSION

    assert MIGRATION_VERSION == 101
    assert MIGRATION_NAME == "legal_operational_domains"


def test_enterprise_migration_runner_imports():
    from legal.migrations import migrate_all

    assert callable(migrate_all)


def test_security_context_denies_by_default():
    import pytest

    from legal.security.rbac import LegalPermission, SecurityContext, require_permission

    with pytest.raises(PermissionError):
        require_permission(SecurityContext(user="tester"), LegalPermission.CREATE)


def test_security_context_allows_admin():
    from legal.security.rbac import LegalPermission, SecurityContext, require_permission

    context = SecurityContext(user="tester", permissions=frozenset({LegalPermission.ADMIN.value}))
    require_permission(context, LegalPermission.CREATE)
