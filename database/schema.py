from __future__ import annotations

from database.connection import db_transaction


SCHEMA_SQL = """
CREAR TABLA SI NO EXISTE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO ÚNICO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    nombre_completo TEXT NOT NULL,
    hash_password TEXTO NO NULO,
    rol TEXTO NO NULO COMPROBAR (rol EN ('Admin', 'Administration', 'Operator')),
    último_inicio_de_sesión TEXTO
);

CREAR TABLA SI NO EXISTE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    nombre TEXTO NO NULO,
    Teléfono de texto,
    TEXTO de correo electrónico,
    direccion TEXT,
    limite_credito_usd REAL NOT NULL DEFAULT 0,
    saldo_a_cobrar_usd REAL NO NULO PREDETERMINADO 0,
    notas TEXT
);
@@ -1177,1104 +1162,25 @@ def _ensure_security_seed(conn) -> None:
            continuar

        for permiso in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALORES (?, ?)
                """,
                (rol, permiso),
            )


def init_schema() -> None:
    con db_transaction() como conexión:
        conn.executescript(SCHEMA_SQL)
        _asegurar_ventas_migración(conn)
        _asegurar_la_migración_de_gastos(conn)
        _asegurar_migración_cxc(conn)
        _ensure_tesoreria_migration(conexión)
        _asegurar_la_migración_costeo(conn)
        _ensure_contabilidad_migration(conn)
        _asegurar_conciliación_migración(conn)
        _ensure_gestion_negocio_migration(conexión)
        _asegurar_manuales_sop_migration(conn)
        _asegurar_seguridad_semilla(conn)
