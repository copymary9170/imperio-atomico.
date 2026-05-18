from __future__ import annotations

from database.connection import db_transaction

NEW_PERMISSION_CATALOG = (
    ("pos.view", "Consultar POS rápido."),
    ("pos.create", "Registrar ventas rápidas desde POS."),
    ("pos.ticket", "Emitir tickets y comprobantes POS."),
    ("cola_impresion.view", "Consultar cola de impresión."),
    ("cola_impresion.edit", "Gestionar archivos y estados en cola de impresión."),
    ("contadores.view", "Consultar contadores y clics de impresión."),
    ("contadores.create", "Registrar lecturas de contadores y clics."),
    ("despacho.view", "Consultar despacho, envíos y entregas."),
    ("despacho.edit", "Gestionar estatus y datos de despacho."),
    ("compras.view", "Consultar compras y órdenes de suministro."),
    ("compras.create", "Crear órdenes de compra y recepciones."),
    ("proveedores.view", "Consultar base de datos de proveedores."),
    ("proveedores.edit", "Crear y editar proveedores."),
    ("bom.view", "Consultar fichas técnicas y BOM."),
    ("bom.edit", "Crear y editar fichas técnicas, recetas y componentes."),
    ("disenos.view", "Consultar diseños y aprobaciones."),
    ("disenos.edit", "Crear, actualizar y aprobar diseños."),
    ("unidades_fraccionadas.view", "Consultar conversiones de unidades fraccionadas."),
    ("unidades_fraccionadas.edit", "Crear y editar conversiones de unidades fraccionadas."),
    ("caja.turno_close", "Registrar cierre de caja por turno."),
    ("reportes.export", "Exportar reportes operativos y financieros."),
)

ADMINISTRATION_NEW_PERMISSIONS = tuple(code for code, _ in NEW_PERMISSION_CATALOG)

OPERATOR_NEW_PERMISSIONS = (
    "pos.view",
    "pos.create",
    "pos.ticket",
    "cola_impresion.view",
    "cola_impresion.edit",
    "contadores.view",
    "contadores.create",
    "despacho.view",
    "despacho.edit",
    "compras.view",
    "proveedores.view",
    "bom.view",
    "disenos.view",
    "disenos.edit",
    "unidades_fraccionadas.view",
    "caja.turno_close",
)


def ensure_extended_permissions() -> None:
    """Agrega permisos de módulos nuevos sin depender de recrear el esquema principal."""
    with db_transaction() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO permisos (codigo, descripcion) VALUES (?, ?)",
            NEW_PERMISSION_CATALOG,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Administration', ?)",
            [(code,) for code in ADMINISTRATION_NEW_PERMISSIONS],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo) VALUES ('Operator', ?)",
            [(code,) for code in OPERATOR_NEW_PERMISSIONS],
        )
