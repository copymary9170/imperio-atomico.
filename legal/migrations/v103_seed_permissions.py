from __future__ import annotations

from database.connection import db_transaction

MIGRATION_VERSION = 103
MIGRATION_NAME = "seed_legal_enterprise_permissions"

PERMISSIONS = {
    "legal.view": "Ver Departamento Jurídico Enterprise",
    "legal.create": "Crear registros jurídicos Enterprise",
    "legal.update": "Actualizar registros jurídicos Enterprise",
    "legal.review": "Revisar expedientes jurídicos Enterprise",
    "legal.approve": "Aprobar expedientes jurídicos Enterprise",
    "legal.sign": "Gestionar firma jurídica Enterprise",
    "legal.publish": "Publicar documentos legales Enterprise",
    "legal.export": "Exportar información jurídica Enterprise",
    "legal.audit.view": "Ver auditoría jurídica Enterprise",
    "legal.admin": "Administrar configuración jurídica Enterprise",
}

ADMIN_ROLES = ("Admin", "Administrador", "Administradora")


def apply() -> None:
    """Seed Legal Enterprise permissions without failing on older databases."""

    with db_transaction() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "permisos" in tables:
            for code, description in PERMISSIONS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO permisos(codigo, descripcion) VALUES(?, ?)",
                    (code, description),
                )
        if "roles_permisos" in tables:
            for role in ADMIN_ROLES:
                for code in PERMISSIONS:
                    conn.execute(
                        "INSERT OR IGNORE INTO roles_permisos(rol, permiso_codigo) VALUES(?, ?)",
                        (role, code),
                    )
        conn.execute(
            "INSERT OR IGNORE INTO legal_enterprise_schema_migrations(version, name) VALUES(?, ?)",
            (MIGRATION_VERSION, MIGRATION_NAME),
        )
