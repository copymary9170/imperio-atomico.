-- Operación industrial unificada: mantenimiento + trazabilidad.
CREATE TABLE IF NOT EXISTS industrial_maintenance_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activo_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('preventivo', 'correctivo')),
    estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'programado', 'en_ejecucion', 'completado', 'cancelado')),
    fecha_programada TEXT NOT NULL,
    tecnico_responsable TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    costo_estimado REAL NOT NULL DEFAULT 0,
    costo_real REAL,
    notas TEXT,
    evidencia_url TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activo_id) REFERENCES activos(id)
);

CREATE TABLE IF NOT EXISTS industrial_traceability_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activo_id INTEGER,
    accion TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,
    costo REAL NOT NULL DEFAULT 0,
    evidencia_ref TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activo_id) REFERENCES activos(id)
);
