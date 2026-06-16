from __future__ import annotations

from database.connection import db_transaction


TRANSACTIONAL_CORE_SQL = """
CREATE TABLE IF NOT EXISTS eventos_transaccionales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipo_evento TEXT NOT NULL,
    modulo_origen TEXT NOT NULL,
    referencia_tabla TEXT,
    referencia_id INTEGER,
    usuario TEXT NOT NULL DEFAULT 'Sistema',
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','procesado','fallido','anulado')),
    severidad TEXT NOT NULL DEFAULT 'normal' CHECK (severidad IN ('baja','normal','alta','critica')),
    payload_json TEXT,
    resultado_json TEXT,
    error TEXT,
    procesado_en TEXT
);

CREATE TABLE IF NOT EXISTS reglas_negocio_transaccionales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    modulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1,
    prioridad INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metricas_dashboard_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    periodo TEXT NOT NULL DEFAULT 'diario',
    ventas_usd REAL NOT NULL DEFAULT 0,
    utilidad_estimada_usd REAL NOT NULL DEFAULT 0,
    gastos_usd REAL NOT NULL DEFAULT 0,
    cuentas_por_cobrar_usd REAL NOT NULL DEFAULT 0,
    cuentas_por_pagar_usd REAL NOT NULL DEFAULT 0,
    stock_critico INTEGER NOT NULL DEFAULT 0,
    trabajos_pendientes INTEGER NOT NULL DEFAULT 0,
    alertas_criticas INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_eventos_transaccionales_fecha ON eventos_transaccionales(fecha);
CREATE INDEX IF NOT EXISTS idx_eventos_transaccionales_estado ON eventos_transaccionales(estado);
CREATE INDEX IF NOT EXISTS idx_eventos_transaccionales_tipo ON eventos_transaccionales(tipo_evento);
CREATE INDEX IF NOT EXISTS idx_eventos_transaccionales_ref ON eventos_transaccionales(referencia_tabla, referencia_id);
CREATE INDEX IF NOT EXISTS idx_reglas_negocio_modulo ON reglas_negocio_transaccionales(modulo, activa, prioridad);
CREATE INDEX IF NOT EXISTS idx_metricas_dashboard_periodo_fecha ON metricas_dashboard_snapshot(periodo, fecha);
"""

DEFAULT_BUSINESS_RULES = (
    (
        "VENTA_MUEVE_CAJA",
        "Toda venta pagada debe registrar movimiento de tesoreria/caja.",
        "ventas",
        "Cuando se registra una venta contado, se crea un movimiento de ingreso en movimientos_tesoreria.",
        1,
        10,
    ),
    (
        "VENTA_DESCUENTA_INVENTARIO",
        "Toda venta con items inventariables debe descontar stock.",
        "inventario",
        "Cada linea de venta asociada a inventario genera salida en movimientos_inventario y actualiza stock_actual.",
        1,
        20,
    ),
    (
        "VENTA_CREDITO_GENERA_CXC",
        "Toda venta a credito debe crear cuenta por cobrar.",
        "finanzas",
        "Si la condicion de pago es credito, se crea una cuenta pendiente en cuentas_por_cobrar.",
        1,
        30,
    ),
    (
        "COTIZACION_APROBADA_CONVIERTE_OPERACION",
        "Una cotizacion aprobada debe convertirse en venta u orden de produccion.",
        "cotizaciones",
        "La aprobacion de cotizacion dispara el flujo comercial y operativo correspondiente.",
        1,
        40,
    ),
    (
        "PRODUCCION_REGISTRA_COSTO_MERMA_CALIDAD",
        "Produccion debe cerrar costo real, merma y calidad.",
        "produccion",
        "Al completar una orden se registran consumo, merma, control de calidad y despacho.",
        1,
        50,
    ),
)


def ensure_transactional_core_schema() -> None:
    """Create the cross-module transactional layer used by ERP domain services."""
    with db_transaction() as conn:
        conn.executescript(TRANSACTIONAL_CORE_SQL)
        conn.executemany(
            """
            INSERT INTO reglas_negocio_transaccionales
                (codigo, nombre, modulo, descripcion, activa, prioridad)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(codigo) DO UPDATE SET
                nombre = excluded.nombre,
                modulo = excluded.modulo,
                descripcion = excluded.descripcion,
                activa = excluded.activa,
                prioridad = excluded.prioridad,
                updated_at = CURRENT_TIMESTAMP
            """,
            DEFAULT_BUSINESS_RULES,
        )
