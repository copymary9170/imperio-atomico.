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
);from __future__ import annotations

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
    fiscal_tipo TEXT NOT NULL DEFAULT 'gravada' CHECK (fiscal_tipo IN ('gravada','exenta','no_sujeta')),
    fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16,
    fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0,
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
    fiscal_tipo TEXT NOT NULL DEFAULT 'gravada' CHECK (fiscal_tipo IN ('gravada','exenta','no_sujeta')),
    fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16,
    fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0,
    fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1 CHECK (fiscal_credito_iva_deducible IN (0,1)),
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
    tipo_documento TEXT NOT NULL DEFAULT 'venta',
    monto_original_usd REAL NOT NULL DEFAULT 0,
    monto_cobrado_usd REAL NOT NULL DEFAULT 0,
    saldo_usd REAL NOT NULL,
    fecha_vencimiento TEXT,
    dias_vencimiento INTEGER NOT NULL DEFAULT 30,
    notas TEXT
);

CREATE TABLE IF NOT EXISTS pagos_clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    monto_usd REAL NOT NULL,
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

CREATE TABLE IF NOT EXISTS presupuesto_operativo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo TEXT NOT NULL,
    categoria TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    monto_presupuestado_usd REAL NOT NULL DEFAULT 0,
    meta_kpi_usd REAL NOT NULL DEFAULT 0,
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    notas TEXT,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(periodo, categoria, tipo)
);

CREATE TABLE IF NOT EXISTS alertas_gerenciales_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    periodo TEXT NOT NULL,
    tipo_alerta TEXT NOT NULL,
    prioridad TEXT NOT NULL CHECK (prioridad IN ('baja','media','alta')),
    mensaje TEXT NOT NULL,
    valor_usd REAL NOT NULL DEFAULT 0,
    metadata TEXT
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

CREATE TABLE IF NOT EXISTS crm_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    cliente_id INTEGER,
    nombre TEXT NOT NULL,
    canal TEXT NOT NULL DEFAULT 'Otro',
    etapa TEXT NOT NULL DEFAULT 'Nuevo' CHECK (etapa IN ('Nuevo','Contactado','Propuesta','Negociación','Ganado','Perdido')),
    valor_estimado_usd REAL NOT NULL DEFAULT 0,
    probabilidad_pct INTEGER NOT NULL DEFAULT 0 CHECK (probabilidad_pct >= 0 AND probabilidad_pct <= 100),
    proximo_contacto TEXT,
    notas TEXT,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS crm_interacciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lead_id INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    tipo TEXT NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'Pendiente',
    detalle TEXT,
    proxima_accion TEXT,
    FOREIGN KEY (lead_id) REFERENCES crm_leads(id)
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
    inventario_id INTEGER NOT NULL,
    cantidad REAL NOT NULL,
    costo_unitario REAL NOT NULL,
    FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id)
);

CREATE TABLE IF NOT EXISTS pedidos_negocio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    sucursal TEXT NOT NULL DEFAULT 'Matriz',
    tipo_negocio TEXT NOT NULL DEFAULT 'General',
    cliente TEXT NOT NULL DEFAULT 'Consumidor final',
    descripcion TEXT NOT NULL,
    fecha_entrega TEXT,
    total_usd REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','en_proceso','entregado','cancelado'))
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    estado TEXT NOT NULL DEFAULT 'contabilizado' CHECK (estado IN ('contabilizado','anulado')),
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(evento_tipo, referencia_tabla, referencia_id)
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asiento_id) REFERENCES asientos_contables(id),
    FOREIGN KEY (cuenta_codigo) REFERENCES catalogo_cuentas(codigo)
);

-- ===========================================
-- Seguridad / Roles
-- ===========================================

CREATE TABLE IF NOT EXISTS permisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    descripcion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles_permisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rol TEXT NOT NULL,
    permiso_codigo TEXT NOT NULL,
    UNIQUE(rol, permiso_codigo)
);

CREATE TABLE IF NOT EXISTS auditoria_seguridad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT
);

-- ===========================================
-- Manuales / SOP
-- ===========================================

CREATE TABLE IF NOT EXISTS manuales_sop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    creado_por TEXT NOT NULL DEFAULT 'Sistema',
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por TEXT NOT NULL DEFAULT 'Sistema',

    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo','borrador')),
    version TEXT NOT NULL DEFAULT '1.0',

    titulo TEXT NOT NULL,
    modulo TEXT NOT NULL,
    proceso TEXT NOT NULL,
    rol_responsable TEXT,
    objetivo TEXT,
    alcance TEXT,

    requisitos_previos TEXT,
    pasos TEXT,
    validaciones_previas TEXT,
    validaciones_posteriores TEXT,
    acciones_correctivas TEXT,
    casos_especiales TEXT,
    evidencia TEXT,
    notas TEXT
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
CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_cuenta_fecha ON movimientos_bancarios(cuenta_bancaria, fecha);
CREATE INDEX IF NOT EXISTS idx_conciliaciones_tesoreria ON conciliaciones_bancarias(tesoreria_movimiento_id);
CREATE INDEX IF NOT EXISTS idx_cierres_periodo_rango ON cierres_periodo(tipo_cierre, fecha_desde, fecha_hasta, estado);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cierres_periodo_unique ON cierres_periodo(periodo, tipo_cierre, estado);
CREATE INDEX IF NOT EXISTS idx_presupuesto_operativo_periodo ON presupuesto_operativo(periodo, tipo);
CREATE INDEX IF NOT EXISTS idx_alertas_gerenciales_fecha ON alertas_gerenciales_log(fecha, prioridad);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_fecha ON costeo_ordenes(fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_tipo_fecha ON costeo_ordenes(tipo_proceso, fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_estado ON costeo_ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_cotizacion ON costeo_ordenes(cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_venta ON costeo_ordenes(venta_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_produccion ON costeo_ordenes(orden_produccion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden ON costeo_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_crm_leads_estado_etapa ON crm_leads(estado, etapa);
CREATE INDEX IF NOT EXISTS idx_crm_leads_proximo_contacto ON crm_leads(proximo_contacto);
CREATE INDEX IF NOT EXISTS idx_crm_interacciones_lead_fecha ON crm_interacciones(lead_id, fecha);
CREATE INDEX IF NOT EXISTS idx_pedidos_negocio_estado_entrega ON pedidos_negocio(estado, fecha_entrega);
CREATE INDEX IF NOT EXISTS idx_catalogo_cuentas_tipo ON catalogo_cuentas(tipo);
CREATE INDEX IF NOT EXISTS idx_asientos_fecha ON asientos_contables(fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_evento_ref ON asientos_contables(evento_tipo, referencia_tabla, referencia_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_asiento ON asientos_contables_detalle(asiento_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_cuenta ON asientos_contables_detalle(cuenta_codigo);

CREATE INDEX IF NOT EXISTS idx_roles_permisos_rol ON roles_permisos(rol);
CREATE INDEX IF NOT EXISTS idx_roles_permisos_permiso ON roles_permisos(permiso_codigo);
CREATE INDEX IF NOT EXISTS idx_auditoria_seguridad_fecha ON auditoria_seguridad(fecha);

CREATE INDEX IF NOT EXISTS idx_manuales_sop_modulo ON manuales_sop(modulo);
CREATE INDEX IF NOT EXISTS idx_manuales_sop_proceso ON manuales_sop(proceso);
CREATE INDEX IF NOT EXISTS idx_manuales_sop_estado ON manuales_sop(estado);
CREATE INDEX IF NOT EXISTS idx_manuales_sop_titulo ON manuales_sop(titulo);
"""
DEFAULT_PERMISSIONS = [
    ("dashboard.view", "Ver panel de control"),

    ("inventario.view", "Ver inventario"),
    ("inventario.create", "Crear inventario"),
    ("inventario.edit", "Editar inventario"),
    ("inventario.move", "Mover inventario"),
    ("inventario.adjust", "Ajustar inventario"),

    ("kardex.view", "Ver kardex"),

    ("clientes.view", "Ver clientes"),
    ("clientes.create", "Crear clientes"),
    ("clientes.edit", "Editar clientes"),

    ("crm.view", "Ver CRM"),
    ("crm.edit", "Editar CRM"),

    ("ventas.view", "Ver ventas"),
    ("ventas.create", "Registrar ventas"),
    ("ventas.edit", "Editar ventas"),
    ("ventas.cancel", "Anular ventas"),
    ("ventas.approve_discount", "Aprobar descuentos"),

    ("cotizaciones.view", "Ver cotizaciones"),
    ("cotizaciones.create", "Crear cotizaciones"),
    ("cotizaciones.edit", "Editar cotizaciones"),
    ("cotizaciones.approve", "Aprobar cotizaciones"),

    ("gastos.view", "Ver gastos"),
    ("gastos.create", "Registrar gastos"),
    ("gastos.edit", "Editar gastos"),

    ("caja.view", "Ver caja"),
    ("caja.payment_in", "Registrar cobros"),
    ("caja.payment_out", "Registrar pagos"),
    ("caja.close", "Cerrar caja"),

    ("tesoreria.view", "Ver tesorería"),
    ("tesoreria.edit", "Editar tesorería"),

    ("cxp.view", "Ver cuentas por pagar"),
    ("cxp.edit", "Editar cuentas por pagar"),

    ("contabilidad.view", "Ver contabilidad"),
    ("contabilidad.entry", "Registrar ajustes contables"),
    ("contabilidad.approve", "Aprobar ajustes contables"),

    ("conciliacion.view", "Ver conciliación bancaria"),
    ("conciliacion.edit", "Editar conciliación bancaria"),

    ("impuestos.view", "Ver impuestos"),
    ("impuestos.edit", "Editar impuestos"),

    ("costeo.view", "Ver costeo"),
    ("costeo.edit", "Modificar costos"),

    ("costeo_industrial.view", "Ver costeo industrial"),
    ("costeo_industrial.edit", "Modificar costeo industrial"),

    ("produccion.view", "Ver producción"),
    ("produccion.plan", "Planificar producción"),
    ("produccion.route", "Gestionar rutas"),
    ("produccion.execute", "Ejecutar producción"),
    ("produccion.quality", "Control de calidad"),
    ("produccion.scrap", "Registrar mermas"),

    ("activos.view", "Ver activos"),
    ("activos.edit", "Editar activos"),

    ("mantenimiento.view", "Ver mantenimiento"),
    ("mantenimiento.edit", "Editar mantenimiento"),

    ("rrhh.view", "Ver RRHH"),
    ("rrhh.edit", "Editar RRHH"),

    ("config.view", "Ver configuración"),
    ("config.edit", "Editar configuración"),

    ("security.view", "Ver seguridad y roles"),
    ("security.edit", "Editar seguridad y roles"),

    ("manuales.view", "Ver manuales y SOP"),
    ("manuales.edit", "Crear y editar manuales y SOP"),

    ("auditoria.view", "Ver auditoría"),
]

DEFAULT_ROLE_PERMISSIONS = {
    "Admin": ["*"],

    "Administration": [
        "dashboard.view",

        "inventario.view", "inventario.create", "inventario.edit", "inventario.move", "inventario.adjust",
        "kardex.view",

        "clientes.view", "clientes.create", "clientes.edit",
        "crm.view", "crm.edit",
        "ventas.view", "ventas.create", "ventas.edit", "ventas.cancel", "ventas.approve_discount",
        "cotizaciones.view", "cotizaciones.create", "cotizaciones.edit", "cotizaciones.approve",

        "gastos.view", "gastos.create", "gastos.edit",
        "caja.view", "caja.payment_in", "caja.payment_out", "caja.close",
        "tesoreria.view", "tesoreria.edit",
        "cxp.view", "cxp.edit",
        "contabilidad.view", "contabilidad.entry", "contabilidad.approve",
        "conciliacion.view", "conciliacion.edit",
        "impuestos.view", "impuestos.edit",

        "costeo.view", "costeo.edit",
        "costeo_industrial.view", "costeo_industrial.edit",

        "produccion.view", "produccion.plan", "produccion.route", "produccion.execute", "produccion.quality", "produccion.scrap",

        "activos.view", "activos.edit",
        "mantenimiento.view", "mantenimiento.edit",
        "rrhh.view", "rrhh.edit",

        "config.view", "config.edit",
        "security.view", "security.edit",
        "manuales.view", "manuales.edit",
        "auditoria.view",
    ],

    "Operator": [
        "dashboard.view",

        "inventario.view",
        "kardex.view",

        "clientes.view",
        "crm.view",
        "ventas.view", "ventas.create",
        "cotizaciones.view", "cotizaciones.create",

        "gastos.view", "gastos.create",
        "caja.view", "caja.payment_in",

        "tesoreria.view",

        "costeo.view",
        "produccion.view", "produccion.execute",

        "activos.view",
        "mantenimiento.view",

        "config.view", "config.edit",
        "manuales.view",
    ],
}


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
    if "fiscal_tipo" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
    if "fiscal_tasa_iva" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16")
    if "fiscal_iva_credito_usd" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0")
    if "fiscal_credito_iva_deducible" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1")

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
            fiscal_tipo = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, '')) IN ('gravada','exenta','no_sujeta') THEN LOWER(fiscal_tipo)
                WHEN COALESCE(impuesto_usd, 0) > 0 THEN 'gravada'
                ELSE 'exenta'
            END,
            fiscal_tasa_iva = CASE
                WHEN COALESCE(fiscal_tasa_iva, 0) <= 0 THEN 0.16
                ELSE fiscal_tasa_iva
            END,
            fiscal_iva_credito_usd = CASE
                WHEN COALESCE(fiscal_credito_iva_deducible, 1) = 1 THEN COALESCE(impuesto_usd, 0)
                ELSE 0
            END,
            fiscal_credito_iva_deducible = CASE
                WHEN COALESCE(fiscal_credito_iva_deducible, 1) IN (0,1) THEN COALESCE(fiscal_credito_iva_deducible, 1)
                ELSE 1
            END,
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


def _ensure_ventas_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ventas)").fetchall()}
    if not columns:
        return

    if "fiscal_tipo" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
    if "fiscal_tasa_iva" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16")
    if "fiscal_iva_debito_usd" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        UPDATE ventas
        SET fiscal_tipo = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, '')) IN ('gravada','exenta','no_sujeta') THEN LOWER(fiscal_tipo)
                WHEN COALESCE(impuesto_usd, 0) > 0 THEN 'gravada'
                ELSE 'exenta'
            END,
            fiscal_tasa_iva = CASE
                WHEN COALESCE(fiscal_tasa_iva, 0) <= 0 THEN 0.16
                ELSE fiscal_tasa_iva
            END,
            fiscal_iva_debito_usd = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, 'gravada')) = 'gravada' THEN COALESCE(impuesto_usd, 0)
                ELSE 0
            END
        """
    )


def _ensure_cxc_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cuentas_por_cobrar)").fetchall()}
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

    if detalle_columns and "tipo_registro" in {row[1] for row in conn.execute("PRAGMA table_info(costeo_detalle)").fetchall()}:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden_tipo ON costeo_detalle(orden_id, tipo_registro)")


def _ensure_contabilidad_migration(conn) -> None:
    catalogo = conn.execute("PRAGMA table_info(catalogo_cuentas)").fetchall()
    if not catalogo:
        return

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
        VALUES (?, ?, ?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            nombre=excluded.nombre,
            tipo=excluded.tipo,
            naturaleza=excluded.naturaleza
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_estado ON movimientos_bancarios(estado_conciliacion)")
        conn.execute(
            """
            UPDATE movimientos_bancarios
            SET estado_conciliacion = CASE
                WHEN LOWER(COALESCE(estado_conciliacion, '')) IN ('pendiente','conciliado','con_diferencia') THEN LOWER(estado_conciliacion)
                ELSE 'pendiente'
            END
            """
        )


def _ensure_gestion_negocio_migration(conn) -> None:
    tablas_con_dimension = [
        "ventas",
        "gastos",
        "cuentas_por_cobrar",
        "cuentas_por_pagar_proveedores",
        "costeo_ordenes",
    ]
    for tabla in tablas_con_dimension:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if not columns:
            continue

        if "sucursal" not in columns:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN sucursal TEXT NOT NULL DEFAULT 'Matriz'")
        if "tipo_negocio" not in columns:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN tipo_negocio TEXT NOT NULL DEFAULT 'General'")

        conn.execute(
            f"""
            UPDATE {tabla}
            SET sucursal = COALESCE(NULLIF(sucursal, ''), 'Matriz'),
                tipo_negocio = COALESCE(NULLIF(tipo_negocio, ''), 'General')
            """
        )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_sucursal_fecha ON ventas(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_tipo_negocio_fecha ON ventas(tipo_negocio, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cxc_sucursal_fecha ON cuentas_por_cobrar(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_sucursal_fecha ON cuentas_por_pagar_proveedores(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_costeo_sucursal_fecha ON costeo_ordenes(sucursal, fecha)")


def _ensure_manuales_sop_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(manuales_sop)").fetchall()}
    if not columns:
        return

    if "creado_por" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN creado_por TEXT NOT NULL DEFAULT 'Sistema'")
    if "actualizado_en" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
    if "actualizado_por" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN actualizado_por TEXT NOT NULL DEFAULT 'Sistema'")
    if "estado" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo'")
    if "version" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN version TEXT NOT NULL DEFAULT '1.0'")
    if "rol_responsable" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN rol_responsable TEXT")
    if "objetivo" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN objetivo TEXT")
    if "alcance" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN alcance TEXT")
    if "requisitos_previos" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN requisitos_previos TEXT")
    if "validaciones_previas" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN validaciones_previas TEXT")
    if "validaciones_posteriores" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN validaciones_posteriores TEXT")
    if "acciones_correctivas" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN acciones_correctivas TEXT")
    if "casos_especiales" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN casos_especiales TEXT")
    if "evidencia" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN evidencia TEXT")
    if "notas" not in columns:
        conn.execute("ALTER TABLE manuales_sop ADD COLUMN notas TEXT")

    conn.execute(
        """
        UPDATE manuales_sop
        SET
            estado = COALESCE(NULLIF(estado, ''), 'activo'),
            version = COALESCE(NULLIF(version, ''), '1.0'),
            actualizado_en = COALESCE(actualizado_en, CURRENT_TIMESTAMP),
            actualizado_por = COALESCE(NULLIF(actualizado_por, ''), 'Sistema'),
            creado_por = COALESCE(NULLIF(creado_por, ''), 'Sistema')
        """
    )


def _ensure_security_seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO permisos (codigo, descripcion)
        VALUES (?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            descripcion = excluded.descripcion
        """,
        DEFAULT_PERMISSIONS,
    )

    for rol, permisos in DEFAULT_ROLE_PERMISSIONS.items():
        if "*" in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALUES (?, ?)
                """,
                (rol, "*"),
            )
            continue

        for permiso in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALUES (?, ?)
                """,
                (rol, permiso),
            )


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_ventas_migration(conn)
        _ensure_gastos_migration(conn)
        _ensure_cxc_migration(conn)
        _ensure_tesoreria_migration(conn)
        _ensure_costeo_migration(conn)
        _ensure_contabilidad_migration(conn)
        _ensure_conciliacion_migration(conn)
        _ensure_gestion_negocio_migration(conn)
        _ensure_manuales_sop_migration(conn)
        _ensure_security_seed(conn)

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
    fiscal_tipo TEXT NOT NULL DEFAULT 'gravada' CHECK (fiscal_tipo IN ('gravada','exenta','no_sujeta')),
    fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16,
    fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0,
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
    fiscal_tipo TEXT NOT NULL DEFAULT 'gravada' CHECK (fiscal_tipo IN ('gravada','exenta','no_sujeta')),
    fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16,
    fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0,
    fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1 CHECK (fiscal_credito_iva_deducible IN (0,1)),
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
    tipo_documento TEXT NOT NULL DEFAULT 'venta',
    monto_original_usd REAL NOT NULL DEFAULT 0,
    monto_cobrado_usd REAL NOT NULL DEFAULT 0,
    saldo_usd REAL NOT NULL,
    fecha_vencimiento TEXT,
    dias_vencimiento INTEGER NOT NULL DEFAULT 30,
    notas TEXT
);

CREATE TABLE IF NOT EXISTS pagos_clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    cuenta_por_cobrar_id INTEGER NOT NULL,
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    monto_usd REAL NOT NULL,
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

CREATE TABLE IF NOT EXISTS presupuesto_operativo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    periodo TEXT NOT NULL,
    categoria TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    monto_presupuestado_usd REAL NOT NULL DEFAULT 0,
    meta_kpi_usd REAL NOT NULL DEFAULT 0,
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    notas TEXT,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(periodo, categoria, tipo)
);

CREATE TABLE IF NOT EXISTS alertas_gerenciales_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    periodo TEXT NOT NULL,
    tipo_alerta TEXT NOT NULL,
    prioridad TEXT NOT NULL CHECK (prioridad IN ('baja','media','alta')),
    mensaje TEXT NOT NULL,
    valor_usd REAL NOT NULL DEFAULT 0,
    metadata TEXT
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

CREATE TABLE IF NOT EXISTS crm_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    cliente_id INTEGER,
    nombre TEXT NOT NULL,
    canal TEXT NOT NULL DEFAULT 'Otro',
    etapa TEXT NOT NULL DEFAULT 'Nuevo' CHECK (etapa IN ('Nuevo','Contactado','Propuesta','Negociación','Ganado','Perdido')),
    valor_estimado_usd REAL NOT NULL DEFAULT 0,
    probabilidad_pct INTEGER NOT NULL DEFAULT 0 CHECK (probabilidad_pct >= 0 AND probabilidad_pct <= 100),
    proximo_contacto TEXT,
    notas TEXT,
    actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS crm_interacciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lead_id INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    tipo TEXT NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'Pendiente',
    detalle TEXT,
    proxima_accion TEXT,
    FOREIGN KEY (lead_id) REFERENCES crm_leads(id)
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
    inventario_id INTEGER NOT NULL,
    cantidad REAL NOT NULL,
    costo_unitario REAL NOT NULL,
    FOREIGN KEY (orden_id) REFERENCES ordenes_produccion(id)
);

CREATE TABLE IF NOT EXISTS pedidos_negocio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    sucursal TEXT NOT NULL DEFAULT 'Matriz',
    tipo_negocio TEXT NOT NULL DEFAULT 'General',
    cliente TEXT NOT NULL DEFAULT 'Consumidor final',
    descripcion TEXT NOT NULL,
    fecha_entrega TEXT,
    total_usd REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','en_proceso','entregado','cancelado'))
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    estado TEXT NOT NULL DEFAULT 'contabilizado' CHECK (estado IN ('contabilizado','anulado')),
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(evento_tipo, referencia_tabla, referencia_id)
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (asiento_id) REFERENCES asientos_contables(id),
    FOREIGN KEY (cuenta_codigo) REFERENCES catalogo_cuentas(codigo)
);

-- ===========================================
-- Seguridad / Roles
-- ===========================================

CREATE TABLE IF NOT EXISTS permisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    descripcion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles_permisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rol TEXT NOT NULL,
    permiso_codigo TEXT NOT NULL,
    UNIQUE(rol, permiso_codigo)
);

CREATE TABLE IF NOT EXISTS auditoria_seguridad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT
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
CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_cuenta_fecha ON movimientos_bancarios(cuenta_bancaria, fecha);
CREATE INDEX IF NOT EXISTS idx_conciliaciones_tesoreria ON conciliaciones_bancarias(tesoreria_movimiento_id);
CREATE INDEX IF NOT EXISTS idx_cierres_periodo_rango ON cierres_periodo(tipo_cierre, fecha_desde, fecha_hasta, estado);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cierres_periodo_unique ON cierres_periodo(periodo, tipo_cierre, estado);
CREATE INDEX IF NOT EXISTS idx_presupuesto_operativo_periodo ON presupuesto_operativo(periodo, tipo);
CREATE INDEX IF NOT EXISTS idx_alertas_gerenciales_fecha ON alertas_gerenciales_log(fecha, prioridad);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_fecha ON costeo_ordenes(fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_tipo_fecha ON costeo_ordenes(tipo_proceso, fecha);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_estado ON costeo_ordenes(estado);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_cotizacion ON costeo_ordenes(cotizacion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_venta ON costeo_ordenes(venta_id);
CREATE INDEX IF NOT EXISTS idx_costeo_ordenes_produccion ON costeo_ordenes(orden_produccion_id);
CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden ON costeo_detalle(orden_id);
CREATE INDEX IF NOT EXISTS idx_crm_leads_estado_etapa ON crm_leads(estado, etapa);
CREATE INDEX IF NOT EXISTS idx_crm_leads_proximo_contacto ON crm_leads(proximo_contacto);
CREATE INDEX IF NOT EXISTS idx_crm_interacciones_lead_fecha ON crm_interacciones(lead_id, fecha);
CREATE INDEX IF NOT EXISTS idx_pedidos_negocio_estado_entrega ON pedidos_negocio(estado, fecha_entrega);
CREATE INDEX IF NOT EXISTS idx_catalogo_cuentas_tipo ON catalogo_cuentas(tipo);
CREATE INDEX IF NOT EXISTS idx_asientos_fecha ON asientos_contables(fecha);
CREATE INDEX IF NOT EXISTS idx_asientos_evento_ref ON asientos_contables(evento_tipo, referencia_tabla, referencia_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_asiento ON asientos_contables_detalle(asiento_id);
CREATE INDEX IF NOT EXISTS idx_asientos_detalle_cuenta ON asientos_contables_detalle(cuenta_codigo);

CREATE INDEX IF NOT EXISTS idx_roles_permisos_rol ON roles_permisos(rol);
CREATE INDEX IF NOT EXISTS idx_roles_permisos_permiso ON roles_permisos(permiso_codigo);
CREATE INDEX IF NOT EXISTS idx_auditoria_seguridad_fecha ON auditoria_seguridad(fecha);
"""
DEFAULT_PERMISSIONS = [
    ("dashboard.view", "Ver panel de control"),

    ("inventario.view", "Ver inventario"),
    ("inventario.create", "Crear inventario"),
    ("inventario.edit", "Editar inventario"),
    ("inventario.move", "Mover inventario"),
    ("inventario.adjust", "Ajustar inventario"),

    ("kardex.view", "Ver kardex"),

    ("clientes.view", "Ver clientes"),
    ("clientes.create", "Crear clientes"),
    ("clientes.edit", "Editar clientes"),

    ("crm.view", "Ver CRM"),
    ("crm.edit", "Editar CRM"),

    ("ventas.view", "Ver ventas"),
    ("ventas.create", "Registrar ventas"),
    ("ventas.edit", "Editar ventas"),
    ("ventas.cancel", "Anular ventas"),
    ("ventas.approve_discount", "Aprobar descuentos"),

    ("cotizaciones.view", "Ver cotizaciones"),
    ("cotizaciones.create", "Crear cotizaciones"),
    ("cotizaciones.edit", "Editar cotizaciones"),
    ("cotizaciones.approve", "Aprobar cotizaciones"),

    ("gastos.view", "Ver gastos"),
    ("gastos.create", "Registrar gastos"),
    ("gastos.edit", "Editar gastos"),

    ("caja.view", "Ver caja"),
    ("caja.payment_in", "Registrar cobros"),
    ("caja.payment_out", "Registrar pagos"),
    ("caja.close", "Cerrar caja"),

    ("tesoreria.view", "Ver tesorería"),
    ("tesoreria.edit", "Editar tesorería"),

    ("cxp.view", "Ver cuentas por pagar"),
    ("cxp.edit", "Editar cuentas por pagar"),

    ("contabilidad.view", "Ver contabilidad"),
    ("contabilidad.entry", "Registrar ajustes contables"),
    ("contabilidad.approve", "Aprobar ajustes contables"),

    ("conciliacion.view", "Ver conciliación bancaria"),
    ("conciliacion.edit", "Editar conciliación bancaria"),

    ("impuestos.view", "Ver impuestos"),
    ("impuestos.edit", "Editar impuestos"),

    ("costeo.view", "Ver costeo"),
    ("costeo.edit", "Modificar costos"),

    ("costeo_industrial.view", "Ver costeo industrial"),
    ("costeo_industrial.edit", "Modificar costeo industrial"),

    ("produccion.view", "Ver producción"),
    ("produccion.plan", "Planificar producción"),
    ("produccion.route", "Gestionar rutas"),
    ("produccion.execute", "Ejecutar producción"),
    ("produccion.quality", "Control de calidad"),
    ("produccion.scrap", "Registrar mermas"),

    ("activos.view", "Ver activos"),
    ("activos.edit", "Editar activos"),

    ("mantenimiento.view", "Ver mantenimiento"),
    ("mantenimiento.edit", "Editar mantenimiento"),

    ("rrhh.view", "Ver RRHH"),
    ("rrhh.edit", "Editar RRHH"),

    ("config.view", "Ver configuración"),
    ("config.edit", "Editar configuración"),

    ("security.view", "Ver seguridad y roles"),
    ("security.edit", "Editar seguridad y roles"),

    ("auditoria.view", "Ver auditoría"),
]

DEFAULT_ROLE_PERMISSIONS = {
    "Admin": ["*"],

    "Administration": [
        "dashboard.view",

        "inventario.view", "inventario.create", "inventario.edit", "inventario.move", "inventario.adjust",
        "kardex.view",

        "clientes.view", "clientes.create", "clientes.edit",
        "crm.view", "crm.edit",
        "ventas.view", "ventas.create", "ventas.edit", "ventas.cancel", "ventas.approve_discount",
        "cotizaciones.view", "cotizaciones.create", "cotizaciones.edit", "cotizaciones.approve",

        "gastos.view", "gastos.create", "gastos.edit",
        "caja.view", "caja.payment_in", "caja.payment_out", "caja.close",
        "tesoreria.view", "tesoreria.edit",
        "cxp.view", "cxp.edit",
        "contabilidad.view", "contabilidad.entry", "contabilidad.approve",
        "conciliacion.view", "conciliacion.edit",
        "impuestos.view", "impuestos.edit",

        "costeo.view", "costeo.edit",
        "costeo_industrial.view", "costeo_industrial.edit",

        "produccion.view", "produccion.plan", "produccion.route", "produccion.execute", "produccion.quality", "produccion.scrap",

        "activos.view", "activos.edit",
        "mantenimiento.view", "mantenimiento.edit",
        "rrhh.view", "rrhh.edit",

        "config.view", "config.edit",
        "security.view",
        "auditoria.view",
    ],

    "Operator": [
        "dashboard.view",

        "inventario.view",
        "kardex.view",

        "clientes.view",
        "crm.view",
        "ventas.view", "ventas.create",
        "cotizaciones.view", "cotizaciones.create",

        "gastos.view", "gastos.create",
        "caja.view", "caja.payment_in",

        "tesoreria.view",

        "costeo.view",
        "produccion.view", "produccion.execute",

        "activos.view",
        "mantenimiento.view",

        "config.view", "config.edit",
    ],
}


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
    if "fiscal_tipo" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
    if "fiscal_tasa_iva" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16")
    if "fiscal_iva_credito_usd" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0")
    if "fiscal_credito_iva_deducible" not in columns:
        conn.execute("ALTER TABLE gastos ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1")

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
            fiscal_tipo = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, '')) IN ('gravada','exenta','no_sujeta') THEN LOWER(fiscal_tipo)
                WHEN COALESCE(impuesto_usd, 0) > 0 THEN 'gravada'
                ELSE 'exenta'
            END,
            fiscal_tasa_iva = CASE
                WHEN COALESCE(fiscal_tasa_iva, 0) <= 0 THEN 0.16
                ELSE fiscal_tasa_iva
            END,
            fiscal_iva_credito_usd = CASE
                WHEN COALESCE(fiscal_credito_iva_deducible, 1) = 1 THEN COALESCE(impuesto_usd, 0)
                ELSE 0
            END,
            fiscal_credito_iva_deducible = CASE
                WHEN COALESCE(fiscal_credito_iva_deducible, 1) IN (0,1) THEN COALESCE(fiscal_credito_iva_deducible, 1)
                ELSE 1
            END,
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


def _ensure_ventas_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ventas)").fetchall()}
    if not columns:
        return

    if "fiscal_tipo" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'")
    if "fiscal_tasa_iva" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_tasa_iva REAL NOT NULL DEFAULT 0.16")
    if "fiscal_iva_debito_usd" not in columns:
        conn.execute("ALTER TABLE ventas ADD COLUMN fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
        UPDATE ventas
        SET fiscal_tipo = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, '')) IN ('gravada','exenta','no_sujeta') THEN LOWER(fiscal_tipo)
                WHEN COALESCE(impuesto_usd, 0) > 0 THEN 'gravada'
                ELSE 'exenta'
            END,
            fiscal_tasa_iva = CASE
                WHEN COALESCE(fiscal_tasa_iva, 0) <= 0 THEN 0.16
                ELSE fiscal_tasa_iva
            END,
            fiscal_iva_debito_usd = CASE
                WHEN LOWER(COALESCE(fiscal_tipo, 'gravada')) = 'gravada' THEN COALESCE(impuesto_usd, 0)
                ELSE 0
            END
        """
    )


def _ensure_cxc_migration(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cuentas_por_cobrar)").fetchall()}
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

    if detalle_columns and "tipo_registro" in {row[1] for row in conn.execute("PRAGMA table_info(costeo_detalle)").fetchall()}:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_costeo_detalle_orden_tipo ON costeo_detalle(orden_id, tipo_registro)")


def _ensure_contabilidad_migration(conn) -> None:
    catalogo = conn.execute("PRAGMA table_info(catalogo_cuentas)").fetchall()
    if not catalogo:
        return

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
        VALUES (?, ?, ?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            nombre=excluded.nombre,
            tipo=excluded.tipo,
            naturaleza=excluded.naturaleza
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_bancarios_estado ON movimientos_bancarios(estado_conciliacion)")
        conn.execute(
            """
            UPDATE movimientos_bancarios
            SET estado_conciliacion = CASE
                WHEN LOWER(COALESCE(estado_conciliacion, '')) IN ('pendiente','conciliado','con_diferencia') THEN LOWER(estado_conciliacion)
                ELSE 'pendiente'
            END
            """
        )


def _ensure_gestion_negocio_migration(conn) -> None:
    tablas_con_dimension = [
        "ventas",
        "gastos",
        "cuentas_por_cobrar",
        "cuentas_por_pagar_proveedores",
        "costeo_ordenes",
    ]
    for tabla in tablas_con_dimension:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        if not columns:
            continue

        if "sucursal" not in columns:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN sucursal TEXT NOT NULL DEFAULT 'Matriz'")
        if "tipo_negocio" not in columns:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN tipo_negocio TEXT NOT NULL DEFAULT 'General'")

        conn.execute(
            f"""
            UPDATE {tabla}
            SET sucursal = COALESCE(NULLIF(sucursal, ''), 'Matriz'),
                tipo_negocio = COALESCE(NULLIF(tipo_negocio, ''), 'General')
            """
        )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_sucursal_fecha ON ventas(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_tipo_negocio_fecha ON ventas(tipo_negocio, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cxc_sucursal_fecha ON cuentas_por_cobrar(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cxp_sucursal_fecha ON cuentas_por_pagar_proveedores(sucursal, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_costeo_sucursal_fecha ON costeo_ordenes(sucursal, fecha)")


def _ensure_security_seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO permisos (codigo, descripcion)
        VALUES (?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            descripcion = excluded.descripcion
        """,
        DEFAULT_PERMISSIONS,
    )

    for rol, permisos in DEFAULT_ROLE_PERMISSIONS.items():
        if "*" in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALUES (?, ?)
                """,
                (rol, "*"),
            )
            continue

        for permiso in permisos:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALUES (?, ?)
                """,
                (rol, permiso),
            )


def init_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_ventas_migration(conn)
        _ensure_gastos_migration(conn)
        _ensure_cxc_migration(conn)
        _ensure_tesoreria_migration(conn)
        _ensure_costeo_migration(conn)
        _ensure_contabilidad_migration(conn)
        _ensure_conciliacion_migration(conn)
        _ensure_gestion_negocio_migration(conn)
        _ensure_security_seed(conn)
