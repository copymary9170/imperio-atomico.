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
    notas TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario)
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
    precio_venta_usd REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario)
);

CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    inventario_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'salida', 'ajuste')),
    cantidad REAL NOT NULL,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    referencia TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario),
    FOREIGN KEY(inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'registrada',
    cliente_id INTEGER,
    moneda TEXT NOT NULL CHECK (moneda IN ('USD', 'BS', 'USDT', 'KONTIGO')),
    tasa_cambio REAL NOT NULL DEFAULT 1,
    metodo_pago TEXT NOT NULL,
    subtotal_usd REAL NOT NULL,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    total_usd REAL NOT NULL,
    total_bs REAL NOT NULL DEFAULT 0,
    observaciones TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id)
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
    subtotal_usd REAL NOT NULL,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario),
    FOREIGN KEY(venta_id) REFERENCES ventas(id),
    FOREIGN KEY(inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    descripcion TEXT NOT NULL,
    categoria TEXT NOT NULL,
    metodo_pago TEXT NOT NULL,
    moneda TEXT NOT NULL CHECK (moneda IN ('USD', 'BS', 'USDT', 'KONTIGO')),
    tasa_cambio REAL NOT NULL,
    monto_usd REAL NOT NULL,
    monto_bs REAL NOT NULL,
    cancelado_motivo TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario)
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
    notas TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario),
    FOREIGN KEY(cliente_id) REFERENCES clientes(id),
    FOREIGN KEY(venta_id) REFERENCES ventas(id)
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
    observaciones TEXT,
    FOREIGN KEY(usuario) REFERENCES usuarios(usuario)
);

CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_item ON movimientos_inventario(inventario_id);
CREATE INDEX IF NOT EXISTS idx_cxc_cliente_estado ON cuentas_por_cobrar(cliente_id, estado);
"""


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
