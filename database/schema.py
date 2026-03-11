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
    expenses_cash REAL NOT NULL,
    expenses_transfer REAL NOT NULL,
    cash_end REAL NOT NULL,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT,
    accion TEXT,
    valor_anterior TEXT,
    valor_nuevo TEXT
);

CREATE TABLE IF NOT EXISTS cotizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT,
    cliente_id INTEGER,
    descripcion TEXT,
    costo_estimado_usd REAL,
    margen_pct REAL,
    precio_final_usd REAL,
    estado TEXT DEFAULT 'Cotización',
    fecha TEXT DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE IF NOT EXISTS ordenes_produccion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    tipo TEXT NOT NULL,
    referencia TEXT NOT NULL,
    costo_estimado REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'Pendiente'
);

CREATE TABLE IF NOT EXISTS ordenes_produccion_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    inventario_id INTEGER NOT NULL,
    cantidad REAL NOT NULL,
    costo_unitario REAL NOT NULL,
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


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
