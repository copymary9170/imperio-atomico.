 __future__ import annotations

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
    saldo_a_cobrar_usd REAL NO NULO PREDETERMINADO 0,
    notas TEXT
);

CREAR TABLA SI NO EXISTE inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    sku TEXTO NO NULO ÚNICO,
    nombre TEXTO NO NULO,
    categoría TEXTO NO NULO,
    unidad TEXTO NO NULO,
    stock_actual REAL NO NULO PREDETERMINADO 0,
    stock_minimo REAL NO NULO PREDETERMINADO 0,
    costo_unitario_usd REAL NO NULO PREDETERMINADO 0,
    precio_venta_usd REAL NO NULO PREDETERMINADO 0
);

CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    inventario_id ENTERO NO NULO,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada','salida','ajuste')),
    cantidad REAL NOT NULL,
    costo_unitario_usd REAL NO NULO PREDETERMINADO 0,
    referencia TEXT
);

CREAR TABLA SI NO EXISTE ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'registrado',
    ID_cliente ENTERO,
    moneda TEXTO NO NULO,
    tasa_cambio REAL NO NULO PREDETERMINADO 1,
    metodo_pago TEXTO NO NULO,
    subtotal_usd REAL NO NULO,
    impuesto_usd REAL NO NULO PREDETERMINADO 0,
    total_usd REAL NO NULO,
    total_bs REAL NO NULO PREDETERMINADO 0,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS ventas_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    venta_id ENTERO NO NULO,
    inventario_id INTEGER,
    Descripción TEXTO NO NULO,
    cantidad REAL NOT NULL,
    precio_unitario_usd REAL NOT NULL,
    costo_unitario_usd REAL NO NULO,
    subtotal_usd REAL NO NULO
);

CREAR TABLA SI NO EXISTE gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    Descripción TEXTO NO NULO,
    categoría TEXTO NO NULO,
    metodo_pago TEXTO NO NULO,
    moneda TEXTO NO NULO,
    tasa_cambio REAL NO NULO,
    subtotal_usd REAL NO NULO PREDETERMINADO 0,
    impuesto_pct REAL NO NULO PREDETERMINADO 0,
    impuesto_usd REAL NO NULO PREDETERMINADO 0,
    monto_usd REAL NO NULO,
    monto_bs REAL NO NULO,
    periodicidad TEXT NOT NULL DEFAULT 'Único',
    dias_periodicidad INTEGER,
    factor_mensual REAL NO NULO PREDETERMINADO 1,
    monto_mensual_usd REAL NO NULO PREDETERMINADO 0,
    monto_mensual_bs REAL NO NULO PREDETERMINADO 0,
    motivo de cancelación TEXTO
);

CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    cliente_id ENTERO NO NULO,
    venta_id INTEGER,
    tipo_documento TEXTO NO NULO PREDETERMINADO 'venta',
    monto_original_usd REAL NO NULO PREDETERMINADO 0,
    cantidad_cobrada_usd REAL NO NULO PREDETERMINADO 0,
    saldo_usd REAL NO NULO,
    fecha_vencimiento TEXT,
    dias_vencimiento INTEGER NOT NULL DEFAULT 30,
    notas TEXT
);

CREAR TABLA SI NO EXISTE pagos_clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    cliente_id ENTERO NO NULO,
    venta_id INTEGER,
    monto_usd REAL NO NULO,
    moneda_pago TEXTO NO NULO VALOR PREDETERMINADO 'USD',
    monto_moneda_pago REAL NO NULO PREDETERMINADO 0,
    tasa_cambio REAL NO NULO PREDETERMINADO 1,
    paid_method TEXTO NO NULO PREDETERMINADO 'efectivo',
    referencia TEXT,
    observaciones TEXT,
    promesa_pago_fecha TEXT,
    proxima_gestion_fecha TEXT,
    FOREIGN KEY (cuenta_por_cobrar_id) REFERENCES cuentas_por_cobrar(id),
    CLAVE FORÁNEA (client_id) REFERENCIAS clientes(id),
    CLAVE FORÁNEA (sales_id) REFERENCIA sales(id)
);

CREATE TABLE IF NOT EXISTS gestiones_cobranza (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    observaciones TEXT,
    promesa_pago_fecha TEXT,
    proxima_gestion_fecha TEXT,
    FOREIGN KEY (cuenta_por_cobrar_id) REFERENCES cuentas_por_cobrar(id)
);

CREATE TABLE IF NOT EXISTS cuentas_por_pagar_proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','parcial','pagada','vencida')),
    proveedor_id INTEGER,
    compra_id ENTERO NO NULO,
    tipo_documento TEXTO NO NULO PREDETERMINADO 'compra',
    monto_original_usd REAL NO NULO,
    cantidad_pagada_usd REAL NO NULO PREDETERMINADO 0,
    saldo_usd REAL NO NULO,
    fecha_vencimiento TEXT,
    notas TEXT,
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id),
    FOREIGN KEY (compra_id) REFERENCES historial_compras(id)
);

CREAR TABLA SI NO EXISTE pagos_proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    cuenta_por_pagar_id INTEGER NOT NULL,
    proveedor_id INTEGER,
    monto_usd REAL NO NULO,
    moneda_pago TEXTO NO NULO VALOR PREDETERMINADO 'USD',
    monto_moneda_pago REAL NO NULO PREDETERMINADO 0,
    tasa_cambio REAL NO NULO PREDETERMINADO 1,
    referencia TEXT,
    observaciones TEXT,
    FOREIGN KEY (cuenta_por_pagar_id) REFERENCES cuentas_por_pagar_proveedores(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

CREATE TABLE IF NOT EXISTS movimientos_tesoreria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    origen COMPROBACIÓN DE TEXTO NO NULO (
        origen EN (
            'venta',
            'cobro_cliente',
            'gastado',
            'pago_proveedor',
            'compra_inicial_pagada',
            'ajuste_manual',
            'cierre_caja'
        )
    ),
    referencia_id INTEGER,
    Descripción TEXTO NO NULO,
    monto_usd REAL NOT NULL CHECK (monto_usd > 0),
    moneda TEXTO NO NULO PREDETERMINADO 'USD',
    monto_moneda REAL NO NULO PREDETERMINADO 0 COMPROBAR (monto_moneda >= 0),
    tasa_cambio REAL NOT NULL DEFAULT 1 CHECK (tasa_cambio > 0),
    paid_method TEXTO NO NULO PREDETERMINADO 'efectivo',
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'confirmado' VERIFICAR (estado EN ('confirmado','cancelado')),
    metadatos TEXTO,
    fecha_creación TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL
);

CREAR TABLA SI NO EXISTE cierres_caja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    estado TEXTO NO NULO PREDETERMINADO 'cerrado',
    inicio_efectivo REAL NO NULO,
    ventas_efectivo REAL NO NULO,
    transferencia_de_ventas REAL NO NULO,
    celda_de_ventas REAL NO NULO,
    sales_binance REAL NO NULO,
    gastos_efectivo REAL NO NULO,
    gastos_transferencia REAL NO NULO,
    fin_de_efectivo REAL NO NULO,
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS movimientos_bancarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO,
    Descripción TEXTO NO NULO,
    monto REAL NOT NULL CHECK (monto > 0),
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    cuenta_bancaria TEXT NOT NULL,
    referencia_banco TEXT,
    origen TEXTO NO NULO PREDETERMINADO 'manual',
    moneda TEXTO NO NULO PREDETERMINADO 'USD',
    saldo_reportado REAL,
    usuario TEXTO NO NULO,
    estado_conciliacion TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado_conciliacion IN ('pendiente','conciliado','con_diferencia')),
    creado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL
);

CREATE TABLE IF NOT EXISTS conciliaciones_bancarias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    banco_movimiento_id INTEGER NOT NULL UNIQUE,
    id_movimiento_tesorería ENTERO NO NULO ÚNICO,
    estado_resultado TEXT NOT NULL CHECK (estado_resultado IN ('conciliado','con_diferencia')),
    diferencia_usd REAL NO NULO PREDETERMINADO 0,
    notas TEXT,
    reconciliado por TEXTO NO NULO,
    conciliado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    FOREIGN KEY (banco_movimiento_id) REFERENCES movimientos_bancarios(id),
    FOREIGN KEY (tesoreria_movimiento_id) REFERENCES movimientos_tesoreria(id)
);

CREAR TABLA SI NO EXISTE cierres_periodo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    período TEXTO NO NULO,
    tipo_cierre TEXT NOT NULL CHECK (tipo_cierre IN ('diario','mensual')),
    fecha_desde TEXT NOT NULL,
    fecha_hasta TEXT NOT NULL,
    total_ingresos_usd REAL NO NULO PREDETERMINADO 0,
    total_egresos_usd REAL NO NULO PREDETERMINADO 0,
    saldo_neto_usd REAL NO NULO PREDETERMINADO 0,
    no_conciliados_banco ENTERO NO NULO PREDETERMINADO 0,
    no_conciliados_tesareria ENTERO NO NULO POR DEFECTO 0,
    estado TEXT NOT NULL DEFAULT 'cerrado' CHECK (estado IN ('abierto','cerrado')),
    cerrado_por TEXTO NO NULO,
    cerrado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    notas TEXT
);

CREAR TABLA SI NO EXISTE auditorios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    TEXTO del usuario,
    accion TEXT,
    valor_anterior TEXTO,
    valor_nuevo TEXT
);

CREATE TABLE IF NOT EXISTS cotizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    TEXTO del usuario,
    ID_cliente ENTERO,
    descripcion TEXT,
    costo_estimado_usd REAL,
    margen_pct REAL,
    precio_final_usd REAL,
    estado TEXT DEFAULT 'Cotización',
    fecha TEXTO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL
);

CREAR TABLA SI NO EXISTE parametros_costeo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXTO NO NULO ÚNICO,
    valor_num REAL,
    valor_texto TEXTO,
    descripcion TEXT,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    actualizado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL
);

CREATE TABLE IF NOT EXISTS plantillas_costeo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    nombre TEXTO NO NULO,
    tipo_proceso TEXTO NO NULO,
    descripcion TEXT,
    margen_objetivo_pct REAL NO NULO PREDETERMINADO 35,
    estado TEXTO NO NULO PREDETERMINADO 'activo',
    metadatos TEXTO
);

CREAR TABLA SI NO EXISTE costeo_ordenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    tipo_proceso TEXTO NO NULO,
    Descripción TEXTO NO NULO,
    cantidad REAL NO NULO PREDETERMINADO 1,
    moneda TEXTO NO NULO PREDETERMINADO 'USD',
    costo_materiales_usd REAL NO NULO PREDETERMINADO 0,
    costo_mano_obra_usd REAL NO NULO PREDETERMINADO 0,
    costo_indirect_usd REAL NO NULO PREDETERMINADO 0,
    costo_total_usd REAL NO NULO PREDETERMINADO 0,
    margen_pct REAL NO NULO PREDETERMINADO 0,
    precio_sugerido_usd REAL NO NULO PREDETERMINADO 0,
    origen TEXTO NO NULO PREDETERMINADO 'manual',
    referencia_id INTEGER,
    cotizacion_id INTEGER,
    venta_id INTEGER,
    orden_produccion_id INTEGER,
    costo_real_usd REAL NO NULO PREDETERMINADO 0,
    precio_vendido_usd REAL NO NULO PREDETERMINADO 0,
    margen_real_pct REAL NO NULO PREDETERMINADO 0,
    diferencia_vs_estimado_usd REAL NOT NULL DEFAULT 0,
    ejecutado_en TEXT,
    cerrado_en TEXT,
    estado TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','cotizado','aprobado','ejecutado','cerrado'))
);

CREAR TABLA SI NO EXISTE costeo_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id ENTERO NO NULO,
    concepto TEXTO NO NULO,
    categoría TEXTO NO NULO,
    cantidad REAL NO NULO PREDETERMINADO 1,
    costo_unitario_usd REAL NO NULO PREDETERMINADO 0,
    subtotal_usd REAL NO NULO PREDETERMINADO 0,
    metadatos TEXTO,
    tipo_registro TEXTO NO NULO PREDETERMINADO 'estimado' VERIFICAR (tipo_registro EN ('estimado','real')),
    CLAVE FORÁNEA (orden_id) REFERENCIAS costeo_ordenes(id)
);

CREAR TABLA SI NO EXISTE órdenes_producción (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    tipo TEXTO NO NULO,
    referencia TEXTO NO NULO,
    costo_estimado REAL NO NULO DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'Pendiente'
);

CREATE TABLE IF NOT EXISTS órdenes_produccion_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id ENTERO NO NULO,
    inventario_id ENTERO NO NULO,
    cantidad REAL NOT NULL,
    costo_unitario REAL NO NULO,
    CLAVE FORÁNEA (order_id) REFERENCIAS production_orders(id)
);

CREATE TABLE IF NOT EXISTS produccion_auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    usuario TEXTO NO NULO,
    módulo TEXTO NO NULO,
    acción TEXTO NO NULO,
    detalle TEXTO
);

CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_fecha ON ordenes_produccion(fecha);
CREATE INDEX IF NOT EXISTS idx_ordenes_produccion_detalle_orden ON ordenes_produccion_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_produccion_auditoria_fecha ON produccion_auditoria(fecha);
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_estado ON cuentas_por_pagar_proveedores(estado);
CREATE INDEX IF NOT EXISTS idx_cxp_proveedor_vencimiento ON cuentas_por_pagar_proveedores(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_proveedores_cxp ON pagos_proveedores(cuenta_por_pagar_id);
CREATE INDEX IF NOT EXISTS idx_cxc_estado ON cuentas_por_cobrar(estado);
CREATE INDEX IF NOT EXISTS idx_cxc_cliente_estado ON cuentas_por_cobrar(cliente_id, estado);
CREATE INDEX IF NOT EXISTS idx_cxc_vencimiento ON cuentas_por_cobrar(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_clientes_cxc ON pagos_clientes(cuenta_por_cobrar_id);
CREAR ÍNDICE SI NO EXISTE idx_pagos_clientes_cliente ON pagos_clientes(cliente_id, fecha);
CREATE INDEX IF NOT EXISTS idx_gestiones_cobranza_cxc ON gestiones_cobranza(cuenta_por_cobrar_id, fecha);
CREAR ÍNDICE ÚNICO SI NO EXISTE idx_tesoreria_origen_referencia_tipo
ON movimientos_tesoreria(origen, referencia_id, tipo)
DONDE referencia_id NO ES NULO;
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

CREATE TABLE IF NOT EXISTS configuración (
    parámetro TEXTO CLAVE PRIMARIA,
    valor TEXTO
);

CREAR TABLA SI NO EXISTE catalogo_cuentas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    código TEXTO NO NULO ÚNICO,
    nombre TEXTO NO NULO,
    tipo TEXT NOT NULL CHECK (tipo IN ('activo','pasivo','patrimonio','ingreso','gasto')),
    naturaleza TEXT NOT NULL CHECK (naturaleza IN ('deudora','acreedora')),
    permite_movimiento INTEGER NOT NULL DEFAULT 1 CHECK (permite_movimiento IN (0,1)),
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    creado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL
);

CREATE TABLE IF NOT EXISTS asientos_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    evento_tipo TEXTO NO NULO,
    tabla_de_referencia TEXTO NO NULO,
    referencia_id ENTERO NO NULO,
    Descripción TEXTO NO NULO,
    moneda TEXTO NO NULO PREDETERMINADO 'USD',
    total_debe_usd REAL NO NULO PREDETERMINADO 0,
    total_haber_usd REAL NO NULO PREDETERMINADO 0,
    estado TEXTO NO NULO PREDETERMINADO 'contabilizado' VERIFICAR (estado EN ('contabilizado','cancelado')),
    TEXTO DEL USUARIO NO NULO VALOR PREDETERMINADO 'Sistema',
    creado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    UNIQUE(evento_tipo, referencia_tabla, referencia_id)
);

CREATE TABLE IF NOT EXISTS asientos_contables_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asiento_id ENTERO NO NULO,
    cuenta_codigo TEXT NOT NULL,
    descripcion TEXT,
    tercero_tipo TEXT,
    tercero_id INTEGER,
    debe_usd REAL NO NULO PREDETERMINADO 0,
    haber_usd REAL NO NULO PREDETERMINADO 0,
    creado_en TEXTO NO NULO PREDETERMINADO MARCA_DE_TIEMPO_ACTUAL,
    FOREIGN KEY (asiento_id) REFERENCES asientos_contables(id),
    FOREIGN KEY (cuenta_codigo) REFERENCES catalogo_cuentas(codigo)
);

CREATE INDEX IF NOT EXISTS idx_catalogo_cuentas_tipo ON catalogo_cuentas(tipo);
CREATE INDEX IF NOT EXISTS idx_asientos_fecha ON asientos_contables(fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_evento_ref ON asientos_contables(evento_tipo, referencia_tabla, referencia_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_asiento ON asientos_contables_detalle(asiento_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_cuenta ON asientos_contables_detalle(cuenta_codigo);
"""


def _ensure_gastos_migration(conn) -> None:
    columnas = {fila[1] para fila en conn.execute("PRAGMA table_info(gastos)").fetchall()}

    Si "periodicidad" no está en columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN periodicidad TEXT NOT NULL DEFAULT 'Único'")
    if "dias_periodicidad" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN dias_periodicidad INTEGER")
    Si "factor_mensual" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN factor_mensual REAL NOT NULL DEFAULT 1")
    Si "monto_mensual_usd" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN monto_mensual_usd REAL NOT NULL DEFAULT 0")
    Si "monto_mensual_bs" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN monto_mensual_bs REAL NOT NULL DEFAULT 0")
    Si "subtotal_usd" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN subtotal_usd REAL NOT NULL DEFAULT 0")
    Si "impuesto_pct" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN impuesto_pct REAL NOT NULL DEFAULT 0")
    Si "impuesto_usd" no está en las columnas:
        conn.execute("ALTER TABLE gastos ADD COLUMN impuesto_usd REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        UPDATE gastos
        SET periodicidad = COALESCE(NULLIF(periodicidad, ''), 'Único'),
            subtotal_usd = CASO
                CUANDO subtotal_usd ES NULO O subtotal_usd <= 0 ENTONCES REDONDEAR(monto_usd - COALESCE(impuesto_usd, 0), 4)
                DE LO CONTRARIO subtotal_usd
            FIN,
            impuesto_pct = COALESCE(impuesto_pct, 0),
            impuesto_usd = COALESCE(impuesto_usd, 0),
            factor_mensual = CASE
                CUANDO factor_mensual ES NULO O factor_mensual <= 0 ENTONCES 1
                ELSE factor_mensual
            FIN,
            monto_mensual_usd = CASE
                CUANDO monto_mensual_usd ES NULO O monto_mensual_usd <= 0 ENTONCES REDONDEAR(monto_usd * COALESCE(NULLIF(factor_mensual, 0), 1), 4)
                ELSE monto_mensual_usd
            FIN,
            monto_mensual_bs = CASE
                CUANDO monto_mensual_bs ES NULO O monto_mensual_bs <= 0 ENTONCES REDONDEAR(monto_bs * COALESCE(NULLIF(factor_mensual, 0), 1), 2)
                ELSE monto_mensual_bs
            FIN
        DONDE 1=1
        """
    )


def _ensure_cxc_migration(conn) -> None:
    columnas = {fila[1] para fila en conn.execute("PRAGMA table_info(cuentas_por_cobrar)").fetchall()}
    si no hay columnas:
        devolver

    Si "tipo_documento" no está en las columnas:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN tipo_documento TEXT NOT NULL DEFAULT 'venta'")
    Si "monto_original_usd" no está en las columnas:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN monto_original_usd REAL NOT NULL DEFAULT 0")
    Si "monto_cobrado_usd" no está en las columnas:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN monto_cobrado_usd REAL NOT NULL DEFAULT 0")
    if "dias_vencimiento" not in columns:
        conn.execute("ALTER TABLE cuentas_por_cobrar ADD COLUMN dias_vencimiento INTEGER NOT NULL DEFAULT 30")

    conn.execute(
        """
        UPDATE cuentas_por_cobrar
        SET tipo_documento = COALESCE(NULLIF(tipo_documento, ''), 'venta'),
            monto_original_usd = CASO
                CUANDO COALESCE(monto_original_usd, 0) <= 0 ENTONCES COALESCE(saldo_usd, 0) + COALESCE(monto_cobrado_usd, 0)
                ELSE monto_original_usd
            FIN,
            monto_cobrado_usd = CASE
                WHEN COALESCE(monto_cobrado_usd, 0) < 0 THEN 0
                DE LO CONTRARIO, COALESCE(cantidad_cobrada_en_USD, 0)
            FIN,
            saldo_usd = CASO
                CUANDO COALESCE(saldo_usd, 0) < 0 ENTONCES 0
                ELSE COALESCE(saldo_usd, 0)
            FIN,
            dias_vencimiento = CASE
                WHEN COALESCE(dias_vencimiento, 0) <= 0 THEN 30
                ELSE dias_vencimiento
            FIN,
            estado = CASE
                WHEN LOWER(COALESCE(estado, '')) IN ('pendiente','parcial','pagada','vencida','incobrable') THEN LOWER(estado)
                CUANDO COALESCE(saldo_usd, 0) <= 0 ENTONCES 'pagada'
                ELSE 'pendiente'
            FIN
        """
    )


def _ensure_tesoreria_migration(conn) -> None:
    columnas = {fila[1] para fila en conn.execute("PRAGMA table_info(movimientos_tesoreria)").fetchall()}
    si no hay columnas:
        devolver

    Si "metadatos" no está en las columnas:
        conn.execute("ALTER TABLE movimientos_tesoreria ADD COLUMN metadata TEXT")
    Si "fecha_creación" no está en las columnas:
        conn.execute("ALTER TABLE movimientos_tesoreria ADD COLUMN fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")

    conn.execute(
        """
        UPDATE movimientos_tesoreria
        ESTABLECER moneda = COALESCE(NULLIF(moneda, ''), 'USD'),
            monto_moneda = CASE
                CUANDO COALESCE(monto_moneda, 0) <= 0 ENTONCES COALESCE(monto_usd, 0)
                ELSE monto_moneda
            FIN,
            tasa_cambio = CASE
                WHEN COALESCE(tasa_cambio, 0) <= 0 THEN 1
                ELSE tasa_cambio
            FIN,
            metodo_pago = COALESCE(NULLIF(metodo_pago, ''), 'efectivo'),
            estado = COALESCE(NULLIF(estado, ''), 'confirmado'),
            fecha_creacion = COALESCE(fecha_creacion, fecha, CURRENT_TIMESTAMP)
        """
    )


def _ensure_costeo_migration(conn) -> None:
    params_columns = {row[1] for row in conn.execute("PRAGMA table_info(parametros_costeo)").fetchall()}
    Si params_columns y "estado" no están en params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    Si params_columns y "actualizado_en" no están en params_columns:
        conn.execute("ALTER TABLE parametros_costeo ADD COLUMN actualizado_en TEXT")
        conn.execute("UPDATE parametros_costeo SET actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP)")

    conn.executemany(
        """
        INSERT INTO parametros_costeo (clave, valor_num, descripcion)
        VALORES (?, ?, ?)
        EN CASO DE CONFLICTO (clave) NO HAGAS NADA
        """,
        [
            ("factor_imprevistos_pct", 5.0, "Porcentaje extra para variaciones no planificadas."),
            ("factor_indirecto_pct", 10.0, "Porcentaje indirecto estándar aplicado al subtotal."),
            ("margen_objetivo_pct", 35.0, "Margen sugerido inicial para cotizaciones."),
        ],
    )

    columnas_ordenes = {fila[1] para fila en conn.execute("PRAGMA table_info(costeo_ordenes)").fetchall()}
    si columnas_de_ordenes:
        Si "quote_id" no está en órdenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN cotizacion_id INTEGER")
        Si "venta_id" no está en órdenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN venta_id INTEGER")
        Si "orden_produccion_id" no está en órdenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN orden_produccion_id INTEGER")
        Si "costo_real_usd" no está en órdenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN costo_real_usd REAL NOT NULL DEFAULT 0")
        if "precio_vendido_usd" not in ordenes_columns:
            conn.execute("ALTER TABLE costeo_ordenes ADD COLUMN precio_vendido_usd REAL NOT NULL DEFAULT 0")
        Si "margen_real_pct" no está en ordenes_columns:
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
            ESTABLECER estado = CASO
                WHEN LOWER(COALESCE(estado, '')) IN ('borrador','cotizado','aprobado','ejecutado','cerrado') THEN LOWER(estado)
                WHEN LOWER(COALESCE(estado, '')) IN ('calculado', 'cotizacion') THEN 'borrador'
                DE LO CONTRARIO 'borroso'
            FIN
            """
        )

    detalle_columns = {row[1] for row in conn.execute("PRAGMA table_info(costeo_detalle)").fetchall()}
    if detalle_columns and "tipo_registro" not in detalle_columns:
        conn.execute("ALTER TABLE costeo_detalle ADD COLUMN tipo_registro TEXT NOT NULL DEFAULT 'estimado'")


def _ensure_contabilidad_migration(conn) -> None:
    catálogo = conn.execute("PRAGMA table_info(catalogo_cuentas)").fetchall()
    si no catálogo:
        devolver

    cuentas_base = [
        ("110101", "Caja general", "activo", "deudora"),
        ("110201", "Bancos", "activo", "deudora"),
        ("120101", "Cuentas por cobrar clientes", "activo", "deudora"),
        ("130101", "Inventario de mercadería", "activo", "deudora"),
        ("210301", "IVA débito fiscal", "pasivo", "acreedora"),
        ("210302", "IVA crédito fiscal", "activo", "deudora"),
        ("220101", "Cuentas por pagar proveedores", "pasivo", "acreedora"),
        ("410101", "Ingresos por ventas", "ingreso", "acreedora"),
        ("420101", "Otros ingresos operativos", "ingreso", "acreedora"),
        ("510101", "Gastos operativos", "gasto", "deudora"),
        ("590101", "Ajustes y diferencias", "gasto", "deudora"),
    ]
    conn.executemany(
        """
        INSERT INTO catalogo_cuentas (codigo, nombre, tipo, naturaleza)
        VALORES (?, ?, ?, ?)
        EN CONFLICTO(código) HACER ACTUALIZAR CONJUNTO
            nombre=excluded.nombre,
            tipo=excluded.tipo,
            naturaleza=excluded.naturaleza
        """,
        cuentas_base,
    )


def _asegurar_conciliación_migración(conn) -> Ninguno:
    movimientos_banco_cols = {row[1] for row in conn.execute("PRAGMA table_info(movimientos_bancarios)").fetchall()}
    if movimientos_banco_cols:
        if "estado_conciliacion" not in movimientos_banco_cols:
            conn.execute(
                "ALTER TABLE movimientos_bancarios ADD COLUMN estado_conciliacion TEXT NOT NULL DEFAULT 'pendiente'"
            )
        si "created_at" no está en movimientos_banco_cols:
            conn.execute("ALTER TABLE movimientos_bancarios ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        conn.execute(
            """
            UPDATE movimientos_bancarios
            SET estado_conciliacion = CASE
                WHEN LOWER(COALESCE(estado_conciliacion, '')) IN ('pendiente','conciliado','con_diferencia') THEN LOWER(estado_conciliacion)
                ELSE 'pendiente'
            FIN
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
