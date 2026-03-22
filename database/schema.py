from __future__ import annotations

from database.connection import db_transaction


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
);

CREATE TABLE IF NOT EXISTS inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    sku TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL,
    unidad TEXT NOT NULL,
    stock_actual REAL NOT NULL DEFAULT 0,
    stock_minimo REAL NOT NULL DEFAULT 0,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    precio_venta_usd REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    inventario_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada','salida','ajuste')),
    cantidad REAL NOT NULL,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    referencia TEXT
);

CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'registrada',
    cliente_id INTEGER,
    moneda TEXT NOT NULL,
    tasa_cambio REAL NOT NULL DEFAULT 1,
    metodo_pago TEXT NOT NULL,
    subtotal_usd REAL NOT NULL,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    total_usd REAL NOT NULL,
    total_bs REAL NOT NULL DEFAULT 0,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS ventas_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    venta_id INTEGER NOT NULL,
    inventario_id INTEGER,
    descripcion TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio_unitario_usd REAL NOT NULL,
    costo_unitario_usd REAL NOT NULL,
    subtotal_usd REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    descripcion TEXT NOT NULL,
    categoria TEXT NOT NULL,
    metodo_pago TEXT NOT NULL,
    moneda TEXT NOT NULL,
    tasa_cambio REAL NOT NULL,
    monto_usd REAL NOT NULL,
    monto_bs REAL NOT NULL,
    periodicidad TEXT NOT NULL DEFAULT 'Único',
    dias_periodicidad INTEGER,
    factor_mensual REAL NOT NULL DEFAULT 1,
    monto_mensual_usd REAL NOT NULL DEFAULT 0,
    monto_mensual_bs REAL NOT NULL DEFAULT 0,
    cancelado_motivo TEXT
);

CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    saldo_usd REAL NOT NULL,
    fecha_vencimiento TEXT,
    notas TEXT
);

CREATE TABLE IF NOT EXISTS cierres_caja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'cerrado',
    cash_start REAL NOT NULL,
    sales_cash REAL NOT NULL,
    sales_transfer REAL NOT NULL,
    sales_zelle REAL NOT NULL,
    sales_binance REAL NOT NULL,
@@ -171,28 +176,64 @@ CREATE TABLE IF NOT EXISTS ordenes_produccion_detalle (
    FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id)
);

CREATE TABLE IF NOT EXISTS produccion_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    modulo TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT
);

CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_fecha ON ordenes_produccion(fecha);
CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_detalle_orden ON ordenes_produccion_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_produccion_auditoria_fecha ON produccion_auditoria(fecha);



CREATE TABLE IF NOT EXISTS configuracion (
    parametro TEXT PRIMARY KEY,
    valor TEXT
);
"""


def _ensure_gastos_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(gastos)").fetchall()}

    if "periodicidad" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN periodicidad TEXT NOT NULL DEFAULT 'Único'")
    if "dias_periodicidad" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN dias_periodicidad INTEGER")
    if "factor_mensual" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN factor_mensual REAL NOT NULL DEFAULT 1")
    if "monto_mensual_usd" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN monto_mensual_usd REAL NOT NULL DEFAULT 0")
    if "monto_mensual_bs" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN monto_mensual_bs REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        UPDATE gastos
        SET periodicidad = COALESCE(NULLIF(periodicidad, ''), 'Único'),
            factor_mensual = CASE
                WHEN factor_mensual IS NULL OR factor_mensual <= 0 THEN 1
                ELSE factor_mensual
            END,
            monto_mensual_usd = CASE
                WHEN monto_mensual_usd IS NULL OR monto_mensual_usd <= 0 THEN ROUND(monto_usd * COALESCE(NULLIF(factor_mensual, 0), 1), 4)
                ELSE monto_mensual_usd
            END,
            monto_mensual_bs = CASE
                WHEN monto_mensual_bs IS NULL OR monto_mensual_bs <= 0 THEN ROUND(monto_bs * COALESCE(NULLIF(factor_mensual, 0), 1), 2)
                ELSE monto_mensual_bs
            END
        WHERE 1=1
        """
    )


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_gastos_migration(conn)

