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
    subtotal_usd REAL NOT NULL DEFAULT 0,
    impuesto_pct REAL NOT NULL DEFAULT 0,
    impuesto_usd REAL NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS cuentas_por_pagar_proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','parcial','pagada','vencida')),
    proveedor_id INTEGER,
    compra_id INTEGER NOT NULL,
    tipo_documento TEXT NOT NULL DEFAULT 'compra',
    monto_original_usd REAL NOT NULL,
    monto_pagado_usd REAL NOT NULL DEFAULT 0,
    saldo_usd REAL NOT NULL,
    fecha_vencimiento TEXT,
    notas TEXT,
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
    FOREIGN KEY (compra_id) REFERENCES historial_compras(id)
);

CREATE TABLE IF NOT EXISTS pagos_proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    cuenta_por_pagar_id INTEGER NOT NULL,
    proveedor_id INTEGER,
    monto_usd REAL NOT NULL,
    moneda_pago TEXT NOT NULL DEFAULT 'USD',
    monto_moneda_pago REAL NOT NULL DEFAULT 0,
    tasa_cambio REAL NOT NULL DEFAULT 1,
    referencia TEXT,
    observaciones TEXT,
    FOREIGN KEY (cuenta_por_pagar_id) REFERENCES cuentas_por_pagar_proveedores(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS movimientos_tesoreria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    origen TEXT NOT NULL CHECK (
        origen IN (
            'venta',
            'cobro_cliente',
            'gasto',
            'pago_proveedor',
            'compra_pago_inicial',
            'ajuste_manual',
            'cierre_caja'
        )
    ),
    referencia_id INTEGER,
    descripcion TEXT NOT NULL,
    monto_usd REAL NOT NULL CHECK (monto_usd > 0),
    moneda TEXT NOT NULL DEFAULT 'USD',
    monto_moneda REAL NOT NULL DEFAULT 0 CHECK (monto_moneda >= 0),
    tasa_cambio REAL NOT NULL DEFAULT 1 CHECK (tasa_cambio > 0),
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'confirmado' CHECK (estado IN ('confirmado','anulado')),
    metadata TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS parametros_costeo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT NOT NULL UNIQUE,
    valor_num REAL,
    valor_texto TEXT,
    descripcion TEXT,
    estado TEXT NOT NULL DEFAULT 'activo',
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plantillas_costeo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo_proceso TEXT NOT NULL,
    descripcion TEXT,
    margen_objetivo_pct REAL NOT NULL DEFAULT 35,
    estado TEXT NOT NULL DEFAULT 'activa',
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS costeo_ordenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    tipo_proceso TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 1,
    moneda TEXT NOT NULL DEFAULT 'USD',
    costo_materiales_usd REAL NOT NULL DEFAULT 0,
    costo_mano_obra_usd REAL NOT NULL DEFAULT 0,
    costo_indirecto_usd REAL NOT NULL DEFAULT 0,
    costo_total_usd REAL NOT NULL DEFAULT 0,
    margen_pct REAL NOT NULL DEFAULT 0,
    precio_sugerido_usd REAL NOT NULL DEFAULT 0,
    origen TEXT NOT NULL DEFAULT 'manual',
    referencia_id INTEGER,
    cotizacion_id INTEGER,
    venta_id INTEGER,
    orden_produccion_id INTEGER,
    costo_real_usd REAL NOT NULL DEFAULT 0,
    precio_vendido_usd REAL NOT NULL DEFAULT 0,
    margen_real_pct REAL NOT NULL DEFAULT 0,
    diferencia_vs_estimado_usd REAL NOT NULL DEFAULT 0,
    ejecutado_en TEXT,
    cerrado_en TEXT,
    estado TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','cotizado','aprobado','ejecutado','cerrado'))
);

CREATE TABLE IF NOT EXISTS costeo_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    concepto TEXT NOT NULL,
    categoria TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 1,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    subtotal_usd REAL NOT NULL DEFAULT 0,
    metadata TEXT,
    tipo_registro TEXT NOT NULL DEFAULT 'estimado' CHECK (tipo_registro IN ('estimado','real')),
    FOREIGN KEY (orden_id) REFERENCES costeo_ordenes(id)
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
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado);
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tesoreria_origen_referencia_tipo
ON movimientos_tesoreria(origen, referencia_id, tipo)
WHERE referencia_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tesoreria_fecha ON movimientos_tesoreria(fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_tipo_fecha ON movimientos_tesoreria(tipo, fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_origen_fecha ON movimientos_tesoreria(origen, fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_metodo_pago ON movimientos_tesoreria(metodo_pago);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_fecha ON costeo_ordenes(fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_tipo_fecha ON costeo_ordenes(tipo_proceso, fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_estado ON costeo_ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_cotizacion ON costeo_ordenes(cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_venta ON costeo_ordenes(venta_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_produccion ON costeo_ordenes(orden_produccion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden ON costeo_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden_tipo ON costeo_detalle(orden_id, tipo_registro);

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
    if "subtotal_usd" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN subtotal_usd REAL NOT NULL DEFAULT 0")
    if "impuesto_pct" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN impuesto_pct REAL NOT NULL DEFAULT 0")
    if "impuesto_usd" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN impuesto_usd REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        UPDATE gastos
        SET periodicidad = COALESCE(NULLIF(periodicidad, ''), 'Único'),
            subtotal_usd = CASE
                WHEN subtotal_usd IS NULL OR subtotal_usd <= 0 THEN ROUND(monto_usd - COALESCE(impuesto_usd, 0), 4)
                ELSE subtotal_usd
            END,
            impuesto_pct = COALESCE(impuesto_pct, 0),
            impuesto_usd = COALESCE(impuesto_usd, 0),
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


def _ensure_tesoreria_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(movimientos_tesoreria)").fetchall()}
    if not columns:
        return

    if "metadata" not in columns:
        conn.execute("ALTER TABLE movimientos_tesoreria ADD COLUMN metadata TEXT")
    if "fecha_creacion" not in columns:
        conn.execute("ALTER TABLE movimientos_tesoreria ADD COLUMN fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")

    conn.execute(
        """
        UPDATE movimientos_tesoreria
        SET moneda = COALESCE(NULLIF(moneda, ''), 'USD'),
            monto_moneda = CASE
                WHEN COALESCE(monto_moneda, 0) <= 0 THEN COALESCE(monto_usd, 0)
                ELSE monto_moneda
            END,
            tasa_cambio = CASE
                WHEN COALESCE(tasa_cambio, 0) <= 0 THEN 1
                ELSE tasa_cambio
            END,
            metodo_pago = COALESCE(NULLIF(metodo_pago, ''), 'efectivo'),
            estado = COALESCE(NULLIF(estado, ''), 'confirmado'),
            fecha_creacion = COALESCE(fecha_creacion, fecha, CURRENT_TIMESTAMP)
        """
    )


def _ensure_costeo_migration(conn) -> None:
    params_columns = {row[1] for row in conn.execute("PRAGMA table_info(parametros_costeo)").fetchall()}
    if params_columns and "estado" not in params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo'")
    if params_columns and "actualizado_en" not in params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN actualizado_en TEXT")
        conn.execute("UPDATE parametros_costeo SET actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)")

    conn.executemany(
        """
        INSERT INTO parametros_costeo (clave, valor_num, descripcion)
        VALUES (?, ?, ?)
        ON CONFLICT(clave) DO NOTHING
        """,
        [
            ("factor_imprevistos_pct", 5.0, "Porcentaje extra para variaciones no planificadas."),
            ("factor_indirecto_pct", 10.0, "Porcentaje indirecto estándar aplicado al subtotal."),
            ("margen_objetivo_pct", 35.0, "Margen sugerido inicial para cotizaciones."),
        ],
    )

    ordenes_columns = {row[1] for row in conn.execute("PRAGMA table_info(costeo_ordenes)").fetchall()}
    if ordenes_columns:
        if "cotizacion_id" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN cotizacion_id INTEGER")
        if "venta_id" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN venta_id INTEGER")
        if "orden_produccion_id" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN orden_produccion_id INTEGER")
        if "costo_real_usd" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN costo_real_usd REAL NOT NULL DEFAULT 0")
        if "precio_vendido_usd" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN precio_vendido_usd REAL NOT NULL DEFAULT 0")
        if "margen_real_pct" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN margen_real_pct REAL NOT NULL DEFAULT 0")
        if "diferencia_vs_estimado_usd" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN diferencia_vs_estimado_usd REAL NOT NULL DEFAULT 0")
        if "ejecutado_en" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN ejecutado_en TEXT")
        if "cerrado_en" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN cerrado_en TEXT")

        conn.execute(
            """
            UPDATE costeo_ordenes
            SET estado = CASE
                WHEN LOWER(COALESCE(estado, '')) IN ('borrador','cotizado','aprobado','ejecutado','cerrado') THEN LOWER(estado)
                WHEN LOWER(COALESCE(estado, '')) IN ('calculado', 'cotizacion') THEN 'borrador'
                ELSE 'borrador'
            END
            """
        )

    detalle_columns = {row[1] for row in conn.execute("PRAGMA table_info(costeo_detalle)").fetchall()}
    if detalle_columns and "tipo_registro" not in detalle_columns:
        conn.execute("ALTER TABLE costeo_detalle ADD COLUMN tipo_registro TEXT NOT NULL DEFAULT 'estimado'")


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_gastos_migration(conn)
        _ensure_tesoreria_migration(conn)
        _ensure_costeo_migration(conn)
