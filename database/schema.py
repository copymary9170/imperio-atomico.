from __future__ import annotations

from database.connection import db_transaction

SECURITY_PERMISSION_CATALOG = (
    ("*", "Acceso total del sistema (superusuario)."),
    ("dashboard.view", "Acceso al panel de control y utilidades generales."),
    ("inventario.view", "Consultar módulo de inventario."),
    ("inventario.create", "Crear productos en inventario."),
    ("inventario.edit", "Editar productos en inventario."),
    ("inventario.move", "Registrar movimientos de inventario."),
    ("inventario.adjust", "Ajustar existencias de inventario."),
    ("kardex.view", "Consultar módulo de kardex."),
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
        "inventario.create",
        "inventario.edit",
        "inventario.move",
        "inventario.adjust",
        "kardex.view",
        "activos.view",
        "clientes.view",
        "crm.view",
        "ventas.view",
        "ventas.create",
        "ventas.edit",
        "ventas.cancel",
        "ventas.approve_discount",
        "cotizaciones.view",
        "produccion.view",
        "produccion.execute",
        "produccion.plan",
        "produccion.route",
        "produccion.quality",
        "produccion.scrap",
        "gastos.view",
        "gastos.create",
        "gastos.edit",
        "caja.view",
        "caja.payment_in",
        "caja.payment_out",
        "caja.close",
        "tesoreria.view",
        "tesoreria.edit",
        "cxp.view",
        "contabilidad.view",
        "contabilidad.entry",
        "contabilidad.approve",
        "contabilidad.close",
        "conciliacion.view",
        "impuestos.view",
        "costeo.view",
        "costeo_industrial.view",
        "auditoria.view",
        "rrhh.view",
        "config.view",
        "config.edit",
        "security.view",
        "security.edit",
        "mantenimiento.view",
    ),
    "Operator": (
        "dashboard.view",
        "inventario.view",
        "inventario.create",
        "inventario.edit",
        "inventario.move",
        "inventario.adjust",
        "kardex.view",
        "clientes.view",
        "ventas.view",
        "ventas.create",
        "cotizaciones.view",
        "produccion.execute",
        "produccion.plan",
        "produccion.route",
        "produccion.quality",
        "produccion.scrap",
        "gastos.view",
        "caja.view",
        "tesoreria.view",
        "costeo.view",
    ),
}

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

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
    saldo_a_cobrar_usd REAL NOT NULL DEFAULT 0,
    notas TEXT
);

CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    nombre TEXT NOT NULL UNIQUE,
    telefono TEXT,
    email TEXT,
    rif TEXT,
    contacto TEXT,
    direccion TEXT,
    ciudad TEXT,
    pais TEXT,
    observaciones TEXT,
    especialidades TEXT,
    condicion_pago_default TEXT NOT NULL DEFAULT 'contado',
    dias_credito_default INTEGER NOT NULL DEFAULT 0,
    moneda_default TEXT NOT NULL DEFAULT 'USD',
    metodo_pago_default TEXT NOT NULL DEFAULT 'transferencia',
    banco TEXT,
    datos_bancarios TEXT,
    tipo_proveedor TEXT NOT NULL DEFAULT 'general',
    estatus_comercial TEXT NOT NULL DEFAULT 'aprobado',
    lead_time_dias INTEGER NOT NULL DEFAULT 0,
    pedido_minimo_usd REAL NOT NULL DEFAULT 0,
    ultima_compra TEXT,
    activo INTEGER NOT NULL DEFAULT 1
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
    creado_por TEXT,
    creado_en TEXT,
    actualizado_por TEXT,
    actualizado_en TEXT
);

CREATE TABLE IF NOT EXISTS inventario_variantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventario_id INTEGER NOT NULL,
    color TEXT NOT NULL,
    sku_variante TEXT,
    stock_actual REAL NOT NULL DEFAULT 0,
    stock_minimo REAL NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
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
    referencia TEXT,
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS historial_compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    inventario_id INTEGER,
    proveedor_id INTEGER,
    item TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT NOT NULL DEFAULT 'unidad',
    costo_total_usd REAL NOT NULL DEFAULT 0,
    costo_unit_usd REAL NOT NULL DEFAULT 0,
    impuestos REAL NOT NULL DEFAULT 0,
    delivery REAL NOT NULL DEFAULT 0,
    moneda_pago TEXT NOT NULL DEFAULT 'USD',
    tipo_pago TEXT NOT NULL DEFAULT 'contado',
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    monto_pagado_inicial_usd REAL NOT NULL DEFAULT 0,
    saldo_pendiente_usd REAL NOT NULL DEFAULT 0,
    fecha_vencimiento TEXT,
    FOREIGN KEY (inventario_id) REFERENCES inventario(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS proveedor_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER NOT NULL,
    inventario_id INTEGER NOT NULL,
    sku_proveedor TEXT,
    nombre_proveedor_item TEXT,
    unidad_compra TEXT NOT NULL DEFAULT 'unidad',
    equivalencia_unidad REAL NOT NULL DEFAULT 1,
    precio_referencia_usd REAL NOT NULL DEFAULT 0,
    moneda_referencia TEXT NOT NULL DEFAULT 'USD',
    pedido_minimo REAL NOT NULL DEFAULT 0,
    lead_time_dias INTEGER NOT NULL DEFAULT 0,
    proveedor_principal INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (proveedor_id, inventario_id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS ordenes_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    proveedor_id INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'emitida',
    moneda TEXT NOT NULL DEFAULT 'USD',
    tasa_cambio REAL NOT NULL DEFAULT 1,
    subtotal_usd REAL NOT NULL DEFAULT 0,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    delivery_usd REAL NOT NULL DEFAULT 0,
    total_usd REAL NOT NULL DEFAULT 0,
    condicion_pago TEXT NOT NULL DEFAULT 'contado',
    fecha_entrega_estimada TEXT,
    observaciones TEXT,
    fecha_cierre TEXT,
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS ordenes_compra_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_compra_id INTEGER NOT NULL,
    inventario_id INTEGER NOT NULL,
    descripcion TEXT,
    cantidad REAL NOT NULL DEFAULT 0,
    cantidad_recibida REAL NOT NULL DEFAULT 0,
    unidad TEXT NOT NULL DEFAULT 'unidad',
    costo_unit_usd REAL NOT NULL DEFAULT 0,
    impuesto_pct REAL NOT NULL DEFAULT 0,
    subtotal_usd REAL NOT NULL DEFAULT 0,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    total_usd REAL NOT NULL DEFAULT 0,
    estado_linea TEXT NOT NULL DEFAULT 'pendiente',
    FOREIGN KEY (orden_compra_id) REFERENCES ordenes_compra(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS recepciones_orden_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_compra_id INTEGER NOT NULL,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'recibida',
    observaciones TEXT,
    FOREIGN KEY (orden_compra_id) REFERENCES ordenes_compra(id)
);

CREATE TABLE IF NOT EXISTS recepciones_orden_compra_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recepcion_id INTEGER NOT NULL,
    orden_detalle_id INTEGER NOT NULL,
    inventario_id INTEGER NOT NULL,
    cantidad_recibida REAL NOT NULL DEFAULT 0,
    costo_unit_usd REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (recepcion_id) REFERENCES recepciones_orden_compra(id),
    FOREIGN KEY (orden_detalle_id) REFERENCES ordenes_compra_detalle(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS evaluaciones_proveedor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    proveedor_id INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    calidad INTEGER NOT NULL DEFAULT 0,
    entrega INTEGER NOT NULL DEFAULT 0,
    precio INTEGER NOT NULL DEFAULT 0,
    soporte INTEGER NOT NULL DEFAULT 0,
    incidencia TEXT,
    comentario TEXT,
    calificacion_general REAL NOT NULL DEFAULT 0,
    decision TEXT NOT NULL DEFAULT 'aprobado',
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS proveedor_documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER,
    tipo_referencia TEXT NOT NULL DEFAULT 'general',
    referencia_id INTEGER,
    titulo TEXT,
    tipo_documento TEXT,
    nombre_archivo TEXT,
    ruta_archivo TEXT,
    url_externa TEXT,
    fecha_documento TEXT,
    fecha_vencimiento TEXT,
    observaciones TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'registrado',
    cliente_id INTEGER,
    moneda TEXT NOT NULL DEFAULT 'USD',
    tasa_cambio REAL NOT NULL DEFAULT 1,
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    subtotal_usd REAL NOT NULL DEFAULT 0,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    total_usd REAL NOT NULL DEFAULT 0,
    total_bs REAL NOT NULL DEFAULT 0,
    observaciones TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS ventas_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    venta_id INTEGER NOT NULL,
    inventario_id INTEGER,
    descripcion TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 0,
    precio_unitario_usd REAL NOT NULL DEFAULT 0,
    costo_unitario_usd REAL NOT NULL DEFAULT 0,
    subtotal_usd REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (venta_id) REFERENCES ventas(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo',
    descripcion TEXT NOT NULL,
    categoria TEXT NOT NULL,
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    moneda TEXT NOT NULL DEFAULT 'USD',
    tasa_cambio REAL NOT NULL DEFAULT 1,
    subtotal_usd REAL NOT NULL DEFAULT 0,
    impuesto_pct REAL NOT NULL DEFAULT 0,
    impuesto_usd REAL NOT NULL DEFAULT 0,
    monto_usd REAL NOT NULL DEFAULT 0,
    monto_bs REAL NOT NULL DEFAULT 0,
    periodicidad TEXT NOT NULL DEFAULT 'Unico',
    dias_periodicidad INTEGER,
    factor_mensual REAL NOT NULL DEFAULT 1,
    monto_mensual_usd REAL NOT NULL DEFAULT 0,
    monto_mensual_bs REAL NOT NULL DEFAULT 0,
    motivo_cancelacion TEXT
);

CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    tipo_documento TEXT NOT NULL DEFAULT 'venta',
    monto_original_usd REAL NOT NULL DEFAULT 0,
    monto_cobrado_usd REAL NOT NULL DEFAULT 0,
    saldo_usd REAL NOT NULL DEFAULT 0,
    fecha_vencimiento TEXT,
    dias_vencimiento INTEGER NOT NULL DEFAULT 30,
    notas TEXT,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (venta_id) REFERENCES ventas(id)
);

CREATE TABLE IF NOT EXISTS pagos_clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    monto_usd REAL NOT NULL DEFAULT 0,
    moneda_pago TEXT NOT NULL DEFAULT 'USD',
    monto_moneda_pago REAL NOT NULL DEFAULT 0,
    tasa_cambio REAL NOT NULL DEFAULT 1,
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    referencia TEXT,
    observaciones TEXT,
    promesa_pago_fecha TEXT,
    proxima_gestion_fecha TEXT,
    FOREIGN KEY (cuenta_por_cobrar_id) REFERENCES cuentas_por_cobrar(id),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (venta_id) REFERENCES ventas(id)
);

CREATE TABLE IF NOT EXISTS gestiones_cobranza (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    observaciones TEXT,
    promesa_pago_fecha TEXT,
    proxima_gestion_fecha TEXT,
    FOREIGN KEY (cuenta_por_cobrar_id) REFERENCES cuentas_por_cobrar(id)
);

CREATE TABLE IF NOT EXISTS cuentas_por_pagar_proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','parcial','pagada','vencida')),
    proveedor_id INTEGER,
    compra_id INTEGER NOT NULL,
    tipo_documento TEXT NOT NULL DEFAULT 'compra',
    monto_original_usd REAL NOT NULL DEFAULT 0,
    monto_pagado_usd REAL NOT NULL DEFAULT 0,
    saldo_usd REAL NOT NULL DEFAULT 0,
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
    monto_usd REAL NOT NULL DEFAULT 0,
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
            'compra_inicial_pagada',
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
    estado TEXT NOT NULL DEFAULT 'confirmado' CHECK (estado IN ('confirmado','cancelado')),
    metadata TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cierres_caja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'cerrado',
    inicio_efectivo REAL NOT NULL DEFAULT 0,
    ventas_efectivo REAL NOT NULL DEFAULT 0,
    ventas_transferencia REAL NOT NULL DEFAULT 0,
    ventas_pago_movil REAL NOT NULL DEFAULT 0,
    ventas_binance REAL NOT NULL DEFAULT 0,
    gastos_efectivo REAL NOT NULL DEFAULT 0,
    gastos_transferencia REAL NOT NULL DEFAULT 0,
    fin_efectivo REAL NOT NULL DEFAULT 0,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS movimientos_bancarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    monto REAL NOT NULL CHECK (monto > 0),
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    cuenta_bancaria TEXT NOT NULL,
    referencia_banco TEXT,
    origen TEXT NOT NULL DEFAULT 'manual',
    moneda TEXT NOT NULL DEFAULT 'USD',
    saldo_reportado REAL,
    usuario TEXT NOT NULL,
    estado_conciliacion TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado_conciliacion IN ('pendiente','conciliado','con_diferencia')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conciliaciones_bancarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    banco_movimiento_id INTEGER NOT NULL UNIQUE,
    tesoreria_movimiento_id INTEGER NOT NULL UNIQUE,
    estado_resultado TEXT NOT NULL CHECK (estado_resultado IN ('conciliado','con_diferencia')),
    diferencia_usd REAL NOT NULL DEFAULT 0,
    notas TEXT,
    conciliado_por TEXT NOT NULL,
    conciliado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (banco_movimiento_id) REFERENCES movimientos_bancarios(id),
    FOREIGN KEY (tesoreria_movimiento_id) REFERENCES movimientos_tesoreria(id)
);

CREATE TABLE IF NOT EXISTS cierres_periodo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo TEXT NOT NULL,
    tipo_cierre TEXT NOT NULL CHECK (tipo_cierre IN ('diario','mensual')),
    fecha_desde TEXT NOT NULL,
    fecha_hasta TEXT NOT NULL,
    total_ingresos_usd REAL NOT NULL DEFAULT 0,
    total_egresos_usd REAL NOT NULL DEFAULT 0,
    saldo_neto_usd REAL NOT NULL DEFAULT 0,
    no_conciliados_banco INTEGER NOT NULL DEFAULT 0,
    no_conciliados_tesoreria INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'cerrado' CHECK (estado IN ('abierto','cerrado')),
    cerrado_por TEXT NOT NULL,
    cerrado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
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
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT,
    cliente_id INTEGER,
    descripcion TEXT,
    costo_estimado_usd REAL NOT NULL DEFAULT 0,
    margen_pct REAL NOT NULL DEFAULT 0,
    precio_final_usd REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'cotizacion',
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
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
    estado TEXT NOT NULL DEFAULT 'activo',
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
    estado TEXT NOT NULL DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS ordenes_produccion_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL,
    inventario_id INTEGER NOT NULL,
    cantidad REAL NOT NULL,
    costo_unitario REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id)
);

CREATE TABLE IF NOT EXISTS produccion_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    modulo TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT
);

CREATE TABLE IF NOT EXISTS configuracion (
    parametro TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS catalogo_cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('activo','pasivo','patrimonio','ingreso','gasto')),
    naturaleza TEXT NOT NULL CHECK (naturaleza IN ('deudora','acreedora')),
    permite_movimiento INTEGER NOT NULL DEFAULT 1 CHECK (permite_movimiento IN (0,1)),
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asientos_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    evento_tipo TEXT NOT NULL,
    referencia_tabla TEXT NOT NULL,
    referencia_id INTEGER NOT NULL,
    descripcion TEXT NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'USD',
    total_debe_usd REAL NOT NULL DEFAULT 0,
    total_haber_usd REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'contabilizado' CHECK (estado IN ('contabilizado','cancelado')),
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (evento_tipo, referencia_tabla, referencia_id)
);

CREATE TABLE IF NOT EXISTS asientos_contables_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_id INTEGER NOT NULL,
    cuenta_codigo TEXT NOT NULL,
    descripcion TEXT,
    tercero_tipo TEXT,
    tercero_id INTEGER,
    debe_usd REAL NOT NULL DEFAULT 0,
    haber_usd REAL NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asiento_id) REFERENCES asientos_contables(id),
    FOREIGN KEY (cuenta_codigo) REFERENCES catalogo_cuentas(codigo)
);

/* ==========================================================
   PLANIFICACION DE PRODUCCION
   ========================================================== */

CREATE TABLE IF NOT EXISTS plan_produccion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    fecha_inicio TEXT,
    fecha_fin TEXT,
    estado TEXT NOT NULL DEFAULT 'borrador' CHECK (
        estado IN ('borrador','planificado','en_proceso','completado','cancelado')
    ),
    prioridad TEXT NOT NULL DEFAULT 'media' CHECK (
        prioridad IN ('baja','media','alta','urgente')
    ),
    origen TEXT NOT NULL DEFAULT 'manual' CHECK (
        origen IN ('manual','venta','cotizacion','reposicion')
    ),
    referencia_tipo TEXT,
    referencia_id INTEGER,
    observaciones TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_produccion_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    inventario_id INTEGER,
    venta_id INTEGER,
    cotizacion_id INTEGER,
    orden_produccion_id INTEGER,
    producto_nombre TEXT NOT NULL,
    sku TEXT,
    cantidad_planificada REAL NOT NULL DEFAULT 0,
    cantidad_producida REAL NOT NULL DEFAULT 0,
    unidad TEXT NOT NULL DEFAULT 'unidad',
    prioridad TEXT NOT NULL DEFAULT 'media' CHECK (
        prioridad IN ('baja','media','alta','urgente')
    ),
    fecha_requerida TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (
        estado IN ('pendiente','en_proceso','parcial','completado','cancelado')
    ),
    notas TEXT,
    FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
    FOREIGN KEY (inventario_id) REFERENCES inventario(id),
    FOREIGN KEY (venta_id) REFERENCES ventas(id),
    FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
    FOREIGN KEY (orden_produccion_id) REFERENCES ordenes_produccion(id)
);

CREATE TABLE IF NOT EXISTS plan_produccion_recursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    detalle_id INTEGER,
    tipo_recurso TEXT NOT NULL CHECK (
        tipo_recurso IN ('maquina','persona','material','turno','otro')
    ),
    recurso_nombre TEXT NOT NULL,
    referencia_id INTEGER,
    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT,
    disponibilidad TEXT NOT NULL DEFAULT 'pendiente' CHECK (
        disponibilidad IN ('pendiente','reservado','asignado','consumido','liberado')
    ),
    notas TEXT,
    FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
    FOREIGN KEY (detalle_id) REFERENCES plan_produccion_detalle(id)
);

CREATE TABLE IF NOT EXISTS plan_produccion_seguimiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    detalle_id INTEGER,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT,
    comentario TEXT,
    avance_pct REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
    FOREIGN KEY (detalle_id) REFERENCES plan_produccion_detalle(id)
);

/* ==========================================================
   RUTAS DE PRODUCCION
   ========================================================== */

CREATE TABLE IF NOT EXISTS rutas_produccion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    producto_tipo TEXT,
    descripcion TEXT,
    estado TEXT NOT NULL DEFAULT 'activa',
    tiempo_total_min REAL NOT NULL DEFAULT 0,
    costo_base_usd REAL NOT NULL DEFAULT 0,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS rutas_produccion_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruta_id INTEGER NOT NULL,
    secuencia INTEGER NOT NULL DEFAULT 1,
    proceso TEXT NOT NULL,
    centro_trabajo TEXT,
    maquina TEXT,
    operario TEXT,
    insumo_principal TEXT,
    tiempo_estimado_min REAL NOT NULL DEFAULT 0,
    costo_estimado_usd REAL NOT NULL DEFAULT 0,
    punto_control INTEGER NOT NULL DEFAULT 0,
    requiere_mantenimiento INTEGER NOT NULL DEFAULT 0,
    observaciones TEXT,
    FOREIGN KEY (ruta_id) REFERENCES rutas_produccion(id)
);

/* ==========================================================
   CORTE INDUSTRIAL
   ========================================================== */

CREATE TABLE IF NOT EXISTS ordenes_corte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    archivo_nombre TEXT,
    referencia TEXT,
    material_id INTEGER,
    material_nombre TEXT,
    material_unidad TEXT DEFAULT 'unidad',
    equipo_id INTEGER,
    equipo_nombre TEXT,
    ruta_id INTEGER,
    ruta_codigo TEXT,
    ruta_nombre TEXT,
    orden_produccion_id INTEGER,
    profundidad REAL NOT NULL DEFAULT 0,
    velocidad REAL NOT NULL DEFAULT 0,
    presion REAL NOT NULL DEFAULT 0,
    area_cm2_estimada REAL NOT NULL DEFAULT 0,
    cm_corte_estimado REAL NOT NULL DEFAULT 0,
    tiempo_estimado_min REAL NOT NULL DEFAULT 0,
    costo_material_estimado_usd REAL NOT NULL DEFAULT 0,
    costo_mano_obra_estimado_usd REAL NOT NULL DEFAULT 0,
    costo_desgaste_estimado_usd REAL NOT NULL DEFAULT 0,
    costo_total_estimado_usd REAL NOT NULL DEFAULT 0,
    cantidad_material_estimada REAL NOT NULL DEFAULT 0,
    desgaste_por_cm REAL NOT NULL DEFAULT 0,
    lote TEXT,
    prioridad TEXT NOT NULL DEFAULT 'normal',
    estado TEXT NOT NULL DEFAULT 'analizado',
    observaciones TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ejecuciones_corte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_corte_id INTEGER NOT NULL,
    fecha_inicio TEXT,
    fecha_fin TEXT,
    usuario TEXT NOT NULL,
    cm_corte_real REAL NOT NULL DEFAULT 0,
    tiempo_real_min REAL NOT NULL DEFAULT 0,
    material_real_usado REAL NOT NULL DEFAULT 0,
    merma REAL NOT NULL DEFAULT 0,
    retazo_reutilizable REAL NOT NULL DEFAULT 0,
    costo_material_real_usd REAL NOT NULL DEFAULT 0,
    costo_mano_obra_real_usd REAL NOT NULL DEFAULT 0,
    costo_desgaste_real_usd REAL NOT NULL DEFAULT 0,
    costo_real_usd REAL NOT NULL DEFAULT 0,
    desgaste_registrado REAL NOT NULL DEFAULT 0,
    incidencias TEXT,
    estado_final TEXT NOT NULL DEFAULT 'terminado',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
);

CREATE TABLE IF NOT EXISTS movimientos_corte_material (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_corte_id INTEGER NOT NULL,
    inventario_id INTEGER,
    material_nombre TEXT,
    tipo TEXT NOT NULL DEFAULT 'salida',
    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT,
    referencia TEXT,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
);

CREATE TABLE IF NOT EXISTS retazos_corte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_corte_id INTEGER NOT NULL,
    inventario_id_origen INTEGER,
    material_nombre TEXT,
    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT,
    reutilizable INTEGER NOT NULL DEFAULT 1,
    observaciones TEXT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
);

CREATE TABLE IF NOT EXISTS corte_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_corte_id INTEGER NOT NULL,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT,
    FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
);

/* ==========================================================
   SUBLIMACION
   ========================================================== */

CREATE TABLE IF NOT EXISTS sublimacion_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT,
    origen TEXT,
    referencia_origen TEXT,
    cliente TEXT,
    producto TEXT NOT NULL,
    tipo_producto TEXT DEFAULT 'Otro',
    diseno TEXT,
    ruta_id INTEGER,
    ruta_codigo TEXT,
    ruta_nombre TEXT,
    orden_produccion_id INTEGER,
    maquina TEXT,
    capacidad_instalada_hora REAL NOT NULL DEFAULT 0,
    temperatura_c REAL DEFAULT 0,
    tiempo_seg REAL DEFAULT 0,
    presion TEXT,
    papel_tipo TEXT,
    tinta_tipo TEXT,
    tinta_ml_estimado REAL NOT NULL DEFAULT 0,
    tinta_ml_real REAL NOT NULL DEFAULT 0,
    material_base_estimado REAL NOT NULL DEFAULT 0,
    material_base_real REAL NOT NULL DEFAULT 0,
    cantidad_programada REAL NOT NULL DEFAULT 0,
    cantidad_producida REAL NOT NULL DEFAULT 0,
    cantidad_aprobada REAL NOT NULL DEFAULT 0,
    cantidad_reproceso REAL NOT NULL DEFAULT 0,
    cantidad_merma REAL NOT NULL DEFAULT 0,
    cantidad_rechazada REAL NOT NULL DEFAULT 0,
    reproceso_pct REAL NOT NULL DEFAULT 0,
    merma_pct REAL NOT NULL DEFAULT 0,
    calidad_promedio REAL NOT NULL DEFAULT 0,
    observaciones TEXT,
    costo_transfer_total REAL DEFAULT 0,
    costo_transfer_unit REAL DEFAULT 0,
    costo_tinta_unit REAL DEFAULT 0,
    costo_material_unit REAL DEFAULT 0,
    costo_energia_unit REAL DEFAULT 0,
    costo_mano_obra_unit REAL DEFAULT 0,
    costo_depreciacion_unit REAL DEFAULT 0,
    costo_indirecto_unit REAL DEFAULT 0,
    costo_unitario_final REAL DEFAULT 0,
    costo_total_final REAL DEFAULT 0,
    estado TEXT DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS sublimacion_control_calidad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lote_id INTEGER NOT NULL,
    usuario TEXT,
    color_correcto INTEGER DEFAULT 1,
    transferencia_completa INTEGER DEFAULT 1,
    sin_manchas INTEGER DEFAULT 1,
    sin_ghosting INTEGER DEFAULT 1,
    sin_quemado INTEGER DEFAULT 1,
    acabado_correcto INTEGER DEFAULT 1,
    observaciones TEXT,
    resultado TEXT DEFAULT 'aprobado',
    puntaje REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
);

CREATE TABLE IF NOT EXISTS sublimacion_mermas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lote_id INTEGER NOT NULL,
    usuario TEXT,
    tipo_falla TEXT,
    cantidad REAL NOT NULL DEFAULT 0,
    costo_estimado_usd REAL DEFAULT 0,
    observaciones TEXT,
    FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
);

CREATE TABLE IF NOT EXISTS sublimacion_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lote_id INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT,
    FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
);

/* ==========================================================
   CONTROL DE CALIDAD GENERAL
   ========================================================== */

CREATE TABLE IF NOT EXISTS control_calidad_registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    modulo_origen TEXT NOT NULL,
    referencia_id INTEGER,
    referencia_codigo TEXT,
    producto TEXT,
    criterio TEXT,
    resultado TEXT NOT NULL DEFAULT 'aprobado',
    puntaje REAL NOT NULL DEFAULT 0,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS control_calidad_hallazgos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_id INTEGER NOT NULL,
    tipo_hallazgo TEXT,
    severidad TEXT DEFAULT 'media',
    descripcion TEXT,
    accion_correctiva TEXT,
    FOREIGN KEY (control_id) REFERENCES control_calidad_registros(id)
);

/* ==========================================================
   MERMAS Y DESPERDICIO GENERAL
   ========================================================== */

CREATE TABLE IF NOT EXISTS mermas_desperdicio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    modulo_origen TEXT NOT NULL,
    referencia_id INTEGER,
    producto TEXT,
    tipo_merma TEXT,
    cantidad REAL NOT NULL DEFAULT 0,
    unidad TEXT DEFAULT 'unidad',
    costo_estimado_usd REAL NOT NULL DEFAULT 0,
    causa TEXT,
    observaciones TEXT
);

CREATE INDEX IF NOT EXISTS idx_inventario_sku ON inventario(sku);
CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_fecha ON movimientos_inventario(fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_item ON movimientos_inventario(inventario_id, fecha);
CREATE INDEX IF NOT EXISTS idx_historial_compras_fecha ON historial_compras(fecha);
CREATE INDEX IF NOT EXISTS idx_proveedor_items_proveedor ON proveedor_items(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_fecha ON ordenes_compra(fecha);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_estado ON ordenes_compra(estado);
CREATE INDEX IF NOT EXISTS idx_ordenes_compra_detalle_orden ON ordenes_compra_detalle(orden_compra_id);
CREATE INDEX IF NOT EXISTS idx_recepciones_oc_fecha ON recepciones_orden_compra(fecha);
CREATE INDEX IF NOT EXISTS idx_evaluaciones_proveedor_fecha ON evaluaciones_proveedor(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_detalle_venta ON ventas_detalle(venta_id);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado);
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id);
CREATE INDEX IF NOT EXISTS idx_cxc_estado ON cuentas_por_cobrar(estado);
CREATE INDEX IF NOT EXISTS idx_cxc_cliente_estado ON cuentas_por_cobrar(cliente_id, estado);
CREATE INDEX IF NOT EXISTS idx_cxc_vencimiento ON cuentas_por_cobrar(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_clientes_cxc ON pagos_clientes(cuenta_por_cobrar_id);
CREATE INDEX IF NOT EXISTS idx_pagos_clientes_cliente ON pagos_clientes(cliente_id, fecha);
CREATE INDEX IF NOT EXISTS idx_gestiones_cobranza_cxc ON gestiones_cobranza(cuenta_por_cobrar_id, fecha);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tesoreria_origen_referencia_tipo
ON movimientos_tesoreria(origen, referencia_id, tipo)
WHERE referencia_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tesoreria_fecha ON movimientos_tesoreria(fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_tipo_fecha ON movimientos_tesoreria(tipo, fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_origen_fecha ON movimientos_tesoreria(origen, fecha);
CREATE INDEX IF NOT EXISTS idx_tesoreria_metodo_pago ON movimientos_tesoreria(metodo_pago);
CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_fecha ON movimientos_bancarios(fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_estado ON movimientos_bancarios(estado_conciliacion);
CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_cuenta_fecha ON movimientos_bancarios(cuenta_bancaria, fecha);
CREATE INDEX IF NOT EXISTS idx_conciliaciones_tesoreria ON conciliaciones_bancarias(tesoreria_movimiento_id);
CREATE INDEX IF NOT EXISTS idx_cierres_periodo_rango ON cierres_periodo(tipo_cierre, fecha_desde, fecha_hasta, estado);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cierres_periodo_unique ON cierres_periodo(periodo, tipo_cierre, estado);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_fecha ON costeo_ordenes(fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_tipo_fecha ON costeo_ordenes(tipo_proceso, fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_estado ON costeo_ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_cotizacion ON costeo_ordenes(cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_venta ON costeo_ordenes(venta_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_produccion ON costeo_ordenes(orden_produccion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden ON costeo_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden_tipo ON costeo_detalle(orden_id, tipo_registro);
CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_fecha ON ordenes_produccion(fecha);
CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_detalle_orden ON ordenes_produccion_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_produccion_auditoria_fecha ON produccion_auditoria(fecha);
CREATE INDEX IF NOT EXISTS idx_catalogo_cuentas_tipo ON catalogo_cuentas(tipo);
CREATE INDEX IF NOT EXISTS idx_asientos_fecha ON asientos_contables(fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_evento_ref ON asientos_contables(evento_tipo, referencia_tabla, referencia_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_asiento ON asientos_contables_detalle(asiento_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_cuenta ON asientos_contables_detalle(cuenta_codigo);

CREATE INDEX IF NOT EXISTS idx_plan_produccion_fecha ON plan_produccion(fecha);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_estado ON plan_produccion(estado);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_prioridad ON plan_produccion(prioridad);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_fechas ON plan_produccion(fecha_inicio, fecha_fin);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_detalle_plan ON plan_produccion_detalle(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_detalle_estado ON plan_produccion_detalle(estado);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_detalle_fecha_req ON plan_produccion_detalle(fecha_requerida);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_recursos_plan ON plan_produccion_recursos(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_recursos_detalle ON plan_produccion_recursos(detalle_id);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_seguimiento_plan ON plan_produccion_seguimiento(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_seguimiento_detalle ON plan_produccion_seguimiento(detalle_id);
CREATE INDEX IF NOT EXISTS idx_plan_produccion_seguimiento_fecha ON plan_produccion_seguimiento(fecha);

CREATE INDEX IF NOT EXISTS idx_rutas_produccion_codigo ON rutas_produccion(codigo);
CREATE INDEX IF NOT EXISTS idx_rutas_produccion_estado ON rutas_produccion(estado);
CREATE INDEX IF NOT EXISTS idx_rutas_produccion_detalle_ruta ON rutas_produccion_detalle(ruta_id, secuencia);

CREATE INDEX IF NOT EXISTS idx_ordenes_corte_estado ON ordenes_corte(estado);
CREATE INDEX IF NOT EXISTS idx_ordenes_corte_material ON ordenes_corte(material_id);
CREATE INDEX IF NOT EXISTS idx_ordenes_corte_ruta ON ordenes_corte(ruta_id);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_corte_orden ON ejecuciones_corte(orden_corte_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_corte_orden ON movimientos_corte_material(orden_corte_id);
CREATE INDEX IF NOT EXISTS idx_retazos_corte_orden ON retazos_corte(orden_corte_id);
CREATE INDEX IF NOT EXISTS idx_corte_historial_orden ON corte_historial(orden_corte_id, fecha);

CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_fecha ON sublimacion_lotes(fecha);
CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_estado ON sublimacion_lotes(estado);
CREATE INDEX IF NOT EXISTS idx_sublimacion_lotes_ruta ON sublimacion_lotes(ruta_id);
CREATE INDEX IF NOT EXISTS idx_sublimacion_qc_lote ON sublimacion_control_calidad(lote_id);
CREATE INDEX IF NOT EXISTS idx_sublimacion_mermas_lote ON sublimacion_mermas(lote_id);
CREATE INDEX IF NOT EXISTS idx_sublimacion_historial_lote ON sublimacion_historial(lote_id, fecha);

CREATE INDEX IF NOT EXISTS idx_control_calidad_modulo_ref ON control_calidad_registros(modulo_origen, referencia_id);
CREATE INDEX IF NOT EXISTS idx_mermas_modulo_ref ON mermas_desperdicio(modulo_origen, referencia_id);
"""

DEFAULT_CONFIG_VALUES = (
    ("tasa_bcv", "36.5"),
    ("tasa_binance", "38.0"),
    ("inv_alerta_dias", "14"),
    ("inv_impuesto_default", "16.0"),
    ("inv_delivery_default", "0.0"),
)


def _ensure_config_defaults(conn) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO configuracion (parametro, valor)
        VALUES (?, ?)
        """,
        DEFAULT_CONFIG_VALUES,
    )


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (str(table_name),),
    ).fetchone()
    return row is not None


def _get_table_columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_column(conn, table_name: str, column_name: str, ddl: str) -> None:
    cols = _get_table_columns(conn, table_name)
    if column_name not in cols:
        conn.execute(ddl)


def _ensure_gastos_migration(conn) -> None:
    columns = _get_table_columns(conn, "gastos")
    if not columns:
        return

    if "periodicidad" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN periodicidad TEXT NOT NULL DEFAULT 'Unico'")
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
    if "motivo_cancelacion" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN motivo_cancelacion TEXT")

    conn.execute(
        """
        UPDATE gastos
        SET periodicidad = COALESCE(NULLIF(periodicidad, ''), 'Unico'),
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
        """
    )


def _ensure_cxc_migration(conn) -> None:
    columns = _get_table_columns(conn, "cuentas_por_cobrar")
    if not columns:
        return

    if "tipo_documento" not in columns:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN tipo_documento TEXT NOT NULL DEFAULT 'venta'")
    if "monto_original_usd" not in columns:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN monto_original_usd REAL NOT NULL DEFAULT 0")
    if "monto_cobrado_usd" not in columns:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN monto_cobrado_usd REAL NOT NULL DEFAULT 0")
    if "dias_vencimiento" not in columns:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN dias_vencimiento INTEGER NOT NULL DEFAULT 30")

    conn.execute(
        """
        UPDATE cuentas_por_cobrar
        SET tipo_documento = COALESCE(NULLIF(tipo_documento, ''), 'venta'),
            monto_original_usd = CASE
                WHEN COALESCE(monto_original_usd, 0) <= 0 THEN COALESCE(saldo_usd, 0) + COALESCE(monto_cobrado_usd, 0)
                ELSE monto_original_usd
            END,
            monto_cobrado_usd = CASE
                WHEN COALESCE(monto_cobrado_usd, 0) < 0 THEN 0
                ELSE COALESCE(monto_cobrado_usd, 0)
            END,
            saldo_usd = CASE
                WHEN COALESCE(saldo_usd, 0) < 0 THEN 0
                ELSE COALESCE(saldo_usd, 0)
            END,
            dias_vencimiento = CASE
                WHEN COALESCE(dias_vencimiento, 0) <= 0 THEN 30
                ELSE dias_vencimiento
            END,
            estado = CASE
                WHEN LOWER(COALESCE(estado, '')) IN ('pendiente','parcial','pagada','vencida','incobrable') THEN LOWER(estado)
                WHEN COALESCE(saldo_usd, 0) <= 0 THEN 'pagada'
                ELSE 'pendiente'
            END
        """
    )


def _ensure_tesoreria_migration(conn) -> None:
    columns = _get_table_columns(conn, "movimientos_tesoreria")
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
    params_columns = _get_table_columns(conn, "parametros_costeo")
    if params_columns and "estado" not in params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo'")
    if params_columns and "actualizado_en" not in params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN actualizado_en TEXT")
        conn.execute("UPDATE parametros_costeo SET actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)")

    conn.executemany(
        """
        INSERT INTO parametros_costeo (clave, valor_num, descripcion)
        VALUES (?, ?, ?)
        ON CONFLICT (clave) DO NOTHING
        """,
        [
            ("factor_imprevistos_pct", 5.0, "Porcentaje extra para variaciones no planificadas."),
            ("factor_indirecto_pct", 10.0, "Porcentaje indirecto estándar aplicado al subtotal."),
            ("margen_objetivo_pct", 35.0, "Margen sugerido inicial para cotizaciones."),
        ],
    )

    ordenes_columns = _get_table_columns(conn, "costeo_ordenes")
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
                WHEN LOWER(COALESCE(estado, '')) IN ('calculado','cotizacion') THEN 'borrador'
                ELSE 'borrador'
            END
            """
        )

    detalle_columns = _get_table_columns(conn, "costeo_detalle")
    if detalle_columns and "tipo_registro" not in detalle_columns:
        conn.execute("ALTER TABLE costeo_detalle ADD COLUMN tipo_registro TEXT NOT NULL DEFAULT 'estimado'")


def _ensure_contabilidad_migration(conn) -> None:
    catalogo = conn.execute("PRAGMA table_info(catalogo_cuentas)").fetchall()
    if not catalogo:
        return

    cuentas_base = [
        ("110101", "Caja general", "activo", "deudora"),
        ("110201", "Bancos", "activo", "deudora"),
        ("120101", "Cuentas por cobrar clientes", "activo", "deudora"),
        ("130101", "Inventario de mercaderia", "activo", "deudora"),
        ("210301", "IVA debito fiscal", "pasivo", "acreedora"),
        ("210302", "IVA credito fiscal", "activo", "deudora"),
        ("220101", "Cuentas por pagar proveedores", "pasivo", "acreedora"),
        ("410101", "Ingresos por ventas", "ingreso", "acreedora"),
        ("420101", "Otros ingresos operativos", "ingreso", "acreedora"),
        ("510101", "Gastos operativos", "gasto", "deudora"),
        ("590101", "Ajustes y diferencias", "gasto", "deudora"),
    ]
    conn.executemany(
        """
        INSERT INTO catalogo_cuentas (codigo, nombre, tipo, naturaleza)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            nombre = excluded.nombre,
            tipo = excluded.tipo,
            naturaleza = excluded.naturaleza
        """,
        cuentas_base,
    )


def _ensure_conciliacion_migration(conn) -> None:
    movimientos_banco_cols = _get_table_columns(conn, "movimientos_bancarios")
    if not movimientos_banco_cols:
        return

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


def _ensure_planificacion_produccion_migration(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_produccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            codigo TEXT NOT NULL UNIQUE,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            estado TEXT NOT NULL DEFAULT 'borrador' CHECK (
                estado IN ('borrador','planificado','en_proceso','completado','cancelado')
            ),
            prioridad TEXT NOT NULL DEFAULT 'media' CHECK (
                prioridad IN ('baja','media','alta','urgente')
            ),
            origen TEXT NOT NULL DEFAULT 'manual' CHECK (
                origen IN ('manual','venta','cotizacion','reposicion')
            ),
            referencia_tipo TEXT,
            referencia_id INTEGER,
            observaciones TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_produccion_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            inventario_id INTEGER,
            venta_id INTEGER,
            cotizacion_id INTEGER,
            orden_produccion_id INTEGER,
            producto_nombre TEXT NOT NULL,
            sku TEXT,
            cantidad_planificada REAL NOT NULL DEFAULT 0,
            cantidad_producida REAL NOT NULL DEFAULT 0,
            unidad TEXT NOT NULL DEFAULT 'unidad',
            prioridad TEXT NOT NULL DEFAULT 'media' CHECK (
                prioridad IN ('baja','media','alta','urgente')
            ),
            fecha_requerida TEXT,
            estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (
                estado IN ('pendiente','en_proceso','parcial','completado','cancelado')
            ),
            notas TEXT,
            FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
            FOREIGN KEY (inventario_id) REFERENCES inventario(id),
            FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id),
            FOREIGN KEY (orden_produccion_id) REFERENCES ordenes_produccion(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_produccion_recursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            detalle_id INTEGER,
            tipo_recurso TEXT NOT NULL CHECK (
                tipo_recurso IN ('maquina','persona','material','turno','otro')
            ),
            recurso_nombre TEXT NOT NULL,
            referencia_id INTEGER,
            cantidad REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            disponibilidad TEXT NOT NULL DEFAULT 'pendiente' CHECK (
                disponibilidad IN ('pendiente','reservado','asignado','consumido','liberado')
            ),
            notas TEXT,
            FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
            FOREIGN KEY (detalle_id) REFERENCES plan_produccion_detalle(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_produccion_seguimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            detalle_id INTEGER,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            estado_anterior TEXT,
            estado_nuevo TEXT,
            comentario TEXT,
            avance_pct REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (plan_id) REFERENCES plan_produccion(id),
            FOREIGN KEY (detalle_id) REFERENCES plan_produccion_detalle(id)
        )
        """
    )


def _ensure_rutas_produccion_migration(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rutas_produccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            codigo TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            producto_tipo TEXT,
            descripcion TEXT,
            estado TEXT NOT NULL DEFAULT 'activa',
            tiempo_total_min REAL NOT NULL DEFAULT 0,
            costo_base_usd REAL NOT NULL DEFAULT 0,
            observaciones TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rutas_produccion_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ruta_id INTEGER NOT NULL,
            secuencia INTEGER NOT NULL DEFAULT 1,
            proceso TEXT NOT NULL,
            centro_trabajo TEXT,
            maquina TEXT,
            operario TEXT,
            insumo_principal TEXT,
            tiempo_estimado_min REAL NOT NULL DEFAULT 0,
            costo_estimado_usd REAL NOT NULL DEFAULT 0,
            punto_control INTEGER NOT NULL DEFAULT 0,
            requiere_mantenimiento INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY (ruta_id) REFERENCES rutas_produccion(id)
        )
        """
    )


def _ensure_corte_migration(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ordenes_corte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            archivo_nombre TEXT,
            referencia TEXT,
            material_id INTEGER,
            material_nombre TEXT,
            material_unidad TEXT DEFAULT 'unidad',
            equipo_id INTEGER,
            equipo_nombre TEXT,
            ruta_id INTEGER,
            ruta_codigo TEXT,
            ruta_nombre TEXT,
            orden_produccion_id INTEGER,
            profundidad REAL NOT NULL DEFAULT 0,
            velocidad REAL NOT NULL DEFAULT 0,
            presion REAL NOT NULL DEFAULT 0,
            area_cm2_estimada REAL NOT NULL DEFAULT 0,
            cm_corte_estimado REAL NOT NULL DEFAULT 0,
            tiempo_estimado_min REAL NOT NULL DEFAULT 0,
            costo_material_estimado_usd REAL NOT NULL DEFAULT 0,
            costo_mano_obra_estimado_usd REAL NOT NULL DEFAULT 0,
            costo_desgaste_estimado_usd REAL NOT NULL DEFAULT 0,
            costo_total_estimado_usd REAL NOT NULL DEFAULT 0,
            cantidad_material_estimada REAL NOT NULL DEFAULT 0,
            desgaste_por_cm REAL NOT NULL DEFAULT 0,
            lote TEXT,
            prioridad TEXT NOT NULL DEFAULT 'normal',
            estado TEXT NOT NULL DEFAULT 'analizado',
            observaciones TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    _ensure_column(conn, "ordenes_corte", "material_unidad", "ALTER TABLE ordenes_corte ADD COLUMN material_unidad TEXT DEFAULT 'unidad'")
    _ensure_column(conn, "ordenes_corte", "ruta_id", "ALTER TABLE ordenes_corte ADD COLUMN ruta_id INTEGER")
    _ensure_column(conn, "ordenes_corte", "ruta_codigo", "ALTER TABLE ordenes_corte ADD COLUMN ruta_codigo TEXT")
    _ensure_column(conn, "ordenes_corte", "ruta_nombre", "ALTER TABLE ordenes_corte ADD COLUMN ruta_nombre TEXT")
    _ensure_column(conn, "ordenes_corte", "orden_produccion_id", "ALTER TABLE ordenes_corte ADD COLUMN orden_produccion_id INTEGER")
    _ensure_column(conn, "ordenes_corte", "costo_material_estimado_usd", "ALTER TABLE ordenes_corte ADD COLUMN costo_material_estimado_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ordenes_corte", "costo_mano_obra_estimado_usd", "ALTER TABLE ordenes_corte ADD COLUMN costo_mano_obra_estimado_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ordenes_corte", "costo_desgaste_estimado_usd", "ALTER TABLE ordenes_corte ADD COLUMN costo_desgaste_estimado_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ordenes_corte", "costo_total_estimado_usd", "ALTER TABLE ordenes_corte ADD COLUMN costo_total_estimado_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ordenes_corte", "lote", "ALTER TABLE ordenes_corte ADD COLUMN lote TEXT")
    _ensure_column(conn, "ordenes_corte", "updated_at", "ALTER TABLE ordenes_corte ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ejecuciones_corte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_corte_id INTEGER NOT NULL,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            usuario TEXT NOT NULL,
            cm_corte_real REAL NOT NULL DEFAULT 0,
            tiempo_real_min REAL NOT NULL DEFAULT 0,
            material_real_usado REAL NOT NULL DEFAULT 0,
            merma REAL NOT NULL DEFAULT 0,
            retazo_reutilizable REAL NOT NULL DEFAULT 0,
            costo_material_real_usd REAL NOT NULL DEFAULT 0,
            costo_mano_obra_real_usd REAL NOT NULL DEFAULT 0,
            costo_desgaste_real_usd REAL NOT NULL DEFAULT 0,
            costo_real_usd REAL NOT NULL DEFAULT 0,
            desgaste_registrado REAL NOT NULL DEFAULT 0,
            incidencias TEXT,
            estado_final TEXT NOT NULL DEFAULT 'terminado',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
        )
        """
    )

    _ensure_column(conn, "ejecuciones_corte", "costo_material_real_usd", "ALTER TABLE ejecuciones_corte ADD COLUMN costo_material_real_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ejecuciones_corte", "costo_mano_obra_real_usd", "ALTER TABLE ejecuciones_corte ADD COLUMN costo_mano_obra_real_usd REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "ejecuciones_corte", "costo_desgaste_real_usd", "ALTER TABLE ejecuciones_corte ADD COLUMN costo_desgaste_real_usd REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movimientos_corte_material (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_corte_id INTEGER NOT NULL,
            inventario_id INTEGER,
            material_nombre TEXT,
            tipo TEXT NOT NULL DEFAULT 'salida',
            cantidad REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            referencia TEXT,
            usuario TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS retazos_corte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_corte_id INTEGER NOT NULL,
            inventario_id_origen INTEGER,
            material_nombre TEXT,
            cantidad REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            reutilizable INTEGER NOT NULL DEFAULT 1,
            observaciones TEXT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS corte_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_corte_id INTEGER NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT,
            FOREIGN KEY (orden_corte_id) REFERENCES ordenes_corte(id)
        )
        """
    )


def _ensure_sublimacion_migration(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sublimacion_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            origen TEXT,
            referencia_origen TEXT,
            cliente TEXT,
            producto TEXT NOT NULL,
            tipo_producto TEXT DEFAULT 'Otro',
            diseno TEXT,
            ruta_id INTEGER,
            ruta_codigo TEXT,
            ruta_nombre TEXT,
            orden_produccion_id INTEGER,
            maquina TEXT,
            capacidad_instalada_hora REAL NOT NULL DEFAULT 0,
            temperatura_c REAL DEFAULT 0,
            tiempo_seg REAL DEFAULT 0,
            presion TEXT,
            papel_tipo TEXT,
            tinta_tipo TEXT,
            tinta_ml_estimado REAL NOT NULL DEFAULT 0,
            tinta_ml_real REAL NOT NULL DEFAULT 0,
            material_base_estimado REAL NOT NULL DEFAULT 0,
            material_base_real REAL NOT NULL DEFAULT 0,
            cantidad_programada REAL NOT NULL DEFAULT 0,
            cantidad_producida REAL NOT NULL DEFAULT 0,
            cantidad_aprobada REAL NOT NULL DEFAULT 0,
            cantidad_reproceso REAL NOT NULL DEFAULT 0,
            cantidad_merma REAL NOT NULL DEFAULT 0,
            cantidad_rechazada REAL NOT NULL DEFAULT 0,
            reproceso_pct REAL NOT NULL DEFAULT 0,
            merma_pct REAL NOT NULL DEFAULT 0,
            calidad_promedio REAL NOT NULL DEFAULT 0,
            observaciones TEXT,
            costo_transfer_total REAL DEFAULT 0,
            costo_transfer_unit REAL DEFAULT 0,
            costo_tinta_unit REAL DEFAULT 0,
            costo_material_unit REAL DEFAULT 0,
            costo_energia_unit REAL DEFAULT 0,
            costo_mano_obra_unit REAL DEFAULT 0,
            costo_depreciacion_unit REAL DEFAULT 0,
            costo_indirecto_unit REAL DEFAULT 0,
            costo_unitario_final REAL DEFAULT 0,
            costo_total_final REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente'
        )
        """
    )

    _ensure_column(conn, "sublimacion_lotes", "ruta_id", "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_id INTEGER")
    _ensure_column(conn, "sublimacion_lotes", "ruta_codigo", "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_codigo TEXT")
    _ensure_column(conn, "sublimacion_lotes", "ruta_nombre", "ALTER TABLE sublimacion_lotes ADD COLUMN ruta_nombre TEXT")
    _ensure_column(conn, "sublimacion_lotes", "orden_produccion_id", "ALTER TABLE sublimacion_lotes ADD COLUMN orden_produccion_id INTEGER")
    _ensure_column(conn, "sublimacion_lotes", "capacidad_instalada_hora", "ALTER TABLE sublimacion_lotes ADD COLUMN capacidad_instalada_hora REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "tinta_ml_estimado", "ALTER TABLE sublimacion_lotes ADD COLUMN tinta_ml_estimado REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "tinta_ml_real", "ALTER TABLE sublimacion_lotes ADD COLUMN tinta_ml_real REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "material_base_estimado", "ALTER TABLE sublimacion_lotes ADD COLUMN material_base_estimado REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "material_base_real", "ALTER TABLE sublimacion_lotes ADD COLUMN material_base_real REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "reproceso_pct", "ALTER TABLE sublimacion_lotes ADD COLUMN reproceso_pct REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "calidad_promedio", "ALTER TABLE sublimacion_lotes ADD COLUMN calidad_promedio REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "costo_tinta_unit", "ALTER TABLE sublimacion_lotes ADD COLUMN costo_tinta_unit REAL DEFAULT 0")
    _ensure_column(conn, "sublimacion_lotes", "costo_material_unit", "ALTER TABLE sublimacion_lotes ADD COLUMN costo_material_unit REAL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sublimacion_control_calidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            lote_id INTEGER NOT NULL,
            usuario TEXT,
            color_correcto INTEGER DEFAULT 1,
            transferencia_completa INTEGER DEFAULT 1,
            sin_manchas INTEGER DEFAULT 1,
            sin_ghosting INTEGER DEFAULT 1,
            sin_quemado INTEGER DEFAULT 1,
            acabado_correcto INTEGER DEFAULT 1,
            observaciones TEXT,
            resultado TEXT DEFAULT 'aprobado',
            puntaje REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
        )
        """
    )

    _ensure_column(conn, "sublimacion_control_calidad", "acabado_correcto", "ALTER TABLE sublimacion_control_calidad ADD COLUMN acabado_correcto INTEGER DEFAULT 1")
    _ensure_column(conn, "sublimacion_control_calidad", "puntaje", "ALTER TABLE sublimacion_control_calidad ADD COLUMN puntaje REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sublimacion_mermas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            lote_id INTEGER NOT NULL,
            usuario TEXT,
            tipo_falla TEXT,
            cantidad REAL NOT NULL DEFAULT 0,
            costo_estimado_usd REAL DEFAULT 0,
            observaciones TEXT,
            FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sublimacion_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            lote_id INTEGER NOT NULL,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            detalle TEXT,
            FOREIGN KEY (lote_id) REFERENCES sublimacion_lotes(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS control_calidad_registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            modulo_origen TEXT NOT NULL,
            referencia_id INTEGER,
            referencia_codigo TEXT,
            producto TEXT,
            criterio TEXT,
            resultado TEXT NOT NULL DEFAULT 'aprobado',
            puntaje REAL NOT NULL DEFAULT 0,
            observaciones TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS control_calidad_hallazgos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_id INTEGER NOT NULL,
            tipo_hallazgo TEXT,
            severidad TEXT DEFAULT 'media',
            descripcion TEXT,
            accion_correctiva TEXT,
            FOREIGN KEY (control_id) REFERENCES control_calidad_registros(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mermas_desperdicio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            modulo_origen TEXT NOT NULL,
            referencia_id INTEGER,
            producto TEXT,
            tipo_merma TEXT,
            cantidad REAL NOT NULL DEFAULT 0,
            unidad TEXT DEFAULT 'unidad',
            costo_estimado_usd REAL NOT NULL DEFAULT 0,
            causa TEXT,
            observaciones TEXT
        )
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

    conn.execute(
        """
        INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
        VALUES ('Operator', 'produccion.plan')
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
        VALUES ('Operator', 'produccion.route')
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
        VALUES ('Operator', 'produccion.execute')
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
        VALUES ('Operator', 'produccion.quality')
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
        VALUES ('Operator', 'produccion.scrap')
        """
    )


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_config_defaults(conn)
        _ensure_gastos_migration(conn)
        _ensure_cxc_migration(conn)
        _ensure_tesoreria_migration(conn)
        _ensure_costeo_migration(conn)
        _ensure_contabilidad_migration(conn)
        _ensure_conciliacion_migration(conn)
        _ensure_planificacion_produccion_migration(conn)
        _ensure_rutas_produccion_migration(conn)
        _ensure_corte_migration(conn)
        _ensure_sublimacion_migration(conn)
        _ensure_security_migration(conn)
