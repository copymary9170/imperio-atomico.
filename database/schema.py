rom __future__ import annotations

from database.connection import db_transaction

SECURITY_PERMISSION_CATALOG = (
    ("*", "Acceso total del sistema (superusuario)."),
    ("dashboard.view", "Acceso al panel de control y utilidades generales."),
    ("inventario.view", "Consultar módulo de inventario."),
    ("inventario.create", "Crear productos en inventario."),
    ("inventario.edit", "Editar productos en inventario."),
    ("inventario.move", "Registrar movimientos de inventario."),
    ("inventario.adjust", "Ajustar existencias de inventario."),
    ("activos.view", "Consultar módulo de activos."),
    ("clientes.view", "Consultar módulo de clientes."),
    ("crm.view", "Consultar CRM y marketing."),
    ("ventas.view", "Consultar módulo de ventas."),
    ("ventas.create", "Crear ventas."),
    ("ventas.edit", "Editar ventas."),
    ("ventas.cancel", "Anular ventas."),
    ("ventas.approve_discount", "Aprobar descuentos en ventas."),
    ("cotizaciones.view", "Consultar cotizaciones."),
    ("produccion.view", "Consultar vistas de producción."),
    ("produccion.execute", "Ejecutar operaciones de producción."),
    ("produccion.plan", "Gestionar planificación de producción."),
    ("produccion.route", "Gestionar rutas de producción."),
    ("produccion.quality", "Registrar control de calidad."),
    ("produccion.scrap", "Registrar mermas y desperdicio."),
    ("gastos.view", "Consultar módulo de gastos."),
    ("gastos.create", "Registrar gastos."),
    ("gastos.edit", "Editar gastos."),
    ("caja.view", "Consultar módulo de caja empresarial."),
    ("caja.payment_in", "Registrar cobros en caja."),
    ("caja.payment_out", "Registrar pagos en caja."),
    ("caja.close", "Ejecutar cierres de caja."),
    ("tesoreria.view", "Consultar módulo de tesorería."),
    ("tesoreria.edit", "Editar operaciones de tesorería."),
    ("cxp.view", "Consultar cuentas por pagar."),
    ("contabilidad.view", "Consultar módulo de contabilidad."),
    ("contabilidad.entry", "Registrar asientos contables."),
    ("contabilidad.approve", "Aprobar ajustes contables."),
    ("contabilidad.close", "Ejecutar cierres contables."),
    ("conciliacion.view", "Consultar conciliación bancaria."),
    ("impuestos.view", "Consultar módulo de impuestos."),
    ("costeo.view", "Consultar rentabilidad y costeo."),
    ("costeo_industrial.view", "Consultar costeo industrial."),
    ("auditoria.view", "Consultar auditoría del sistema."),
    ("rrhh.view", "Consultar módulo de RRHH."),
    ("config.view", "Consultar módulo de configuración."),
    ("config.edit", "Editar configuración del sistema."),
    ("security.view", "Consultar seguridad y roles."),
    ("security.edit", "Editar roles y permisos."),
    ("mantenimiento.view", "Consultar mantenimiento de activos."),
)

DEFAULT_ROLE_PERMISSIONS = {
    "Admin": ("*",),
    "Administration": (
        "dashboard.view",
        "inventario.view",
        "activos.view",
        "clientes.view",
        "crm.view",
        "ventas.view",
        "cotizaciones.view",
        "produccion.view",
        "produccion.execute",
        "produccion.plan",
        "produccion.route",
        "produccion.quality",
        "produccion.scrap",
        "gastos.view",
        "caja.view",
        "tesoreria.view",
        "cxp.view",
        "contabilidad.view",
        "conciliacion.view",
        "impuestos.view",
        "costeo.view",
        "costeo_industrial.view",
        "auditoria.view",
        "rrhh.view",
        "config.view",
        "security.view",
        "mantenimiento.view",
    ),
    "Operator": (
        "dashboard.view",
        "inventario.view",
        "clientes.view",
        "ventas.view",
        "cotizaciones.view",
        "gastos.view",
        "caja.view",
        "tesoreria.view",
        "costeo.view",
    ),
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'activo',
    nombre_completo TEXT NOT NULL,
    hash_password TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('Admin', 'Administration', 'Operator')),
    ultimo_login TEXT
);

CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    nombre TEXT NOT NULL,
    telefono TEXT,
    email TEXT,
    direccion TEXT,
    limite_credito_usd REAL NOT NULL DEFAULT 0,
    saldo_por_cobrar_usd REAL NOT NULL DEFAULT 0,
    notas TEXT
@@ -686,34 +780,90 @@ def _ensure_contabilidad_migration(conn) -> None:
        """,
        cuentas_base,
    )


def _ensure_conciliacion_migration(conn) -> None:
    movimientos_banco_cols = {row[1] for row in conn.execute("PRAGMA table_info(movimientos_bancarios)").fetchall()}
    if movimientos_banco_cols:
        if "estado_conciliacion" not in movimientos_banco_cols:
            conn.execute(
                "ALTER TABLE movimientos_bancarios ADD COLUMN estado_conciliacion TEXT NOT NULL DEFAULT 'pendiente'"
            )
        if "created_at" not in movimientos_banco_cols:
            conn.execute("ALTER TABLE movimientos_bancarios ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        conn.execute(
            """
            UPDATE movimientos_bancarios
            SET estado_conciliacion = CASE
                WHEN LOWER(COALESCE(estado_conciliacion, '')) IN ('pendiente','conciliado','con_diferencia') THEN LOWER(estado_conciliacion)
                ELSE 'pendiente'
            END
            """
        )


def _ensure_security_migration(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS permisos (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roles_permisos (
            rol TEXT NOT NULL,
            permiso_codigo TEXT NOT NULL,
            PRIMARY KEY (rol, permiso_codigo),
            FOREIGN KEY (permiso_codigo) REFERENCES permisos(codigo)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auditoria_seguridad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT NOT NULL
        )
        """
    )

    conn.executemany(
        """
        INSERT OR IGNORE INTO permisos (codigo, descripcion)
        VALUES (?, ?)
        """,
        SECURITY_PERMISSION_CATALOG,
    )

    for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        has_rows = conn.execute(
            "SELECT 1 FROM roles_permisos WHERE rol = ? LIMIT 1",
            (role,),
        ).fetchone()
        if has_rows:
            continue
        conn.executemany(
            """
            INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
            VALUES (?, ?)
            """,
            [(role, permission) for permission in permissions],
        )


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_gastos_migration(conn)
        _ensure_cxc_migration(conn)
        _ensure_tesoreria_migration(conn)
        _ensure_costeo_migration(conn)
        _ensure_contabilidad_migration(conn)
        _ensure_conciliacion_migration(conn)
        _ensure_security_migration(conn)
