from __future__ import annotations

from typing import Iterable

from database.connection import db_transaction


COLUMN_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "ventas": [
        ("fiscal_tipo", "ALTER TABLE ventas ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'"),
        ("fiscal_iva_debito_usd", "ALTER TABLE ventas ADD COLUMN fiscal_iva_debito_usd REAL NOT NULL DEFAULT 0"),
        ("subtotal_usd", "ALTER TABLE ventas ADD COLUMN subtotal_usd REAL NOT NULL DEFAULT 0"),
        ("impuesto_usd", "ALTER TABLE ventas ADD COLUMN impuesto_usd REAL NOT NULL DEFAULT 0"),
        ("estado", "ALTER TABLE ventas ADD COLUMN estado TEXT NOT NULL DEFAULT 'activa'"),
    ],
    "gastos": [
        ("fiscal_tipo", "ALTER TABLE gastos ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'"),
        ("fiscal_iva_credito_usd", "ALTER TABLE gastos ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0"),
        ("fiscal_credito_iva_deducible", "ALTER TABLE gastos ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1"),
        ("subtotal_usd", "ALTER TABLE gastos ADD COLUMN subtotal_usd REAL NOT NULL DEFAULT 0"),
        ("impuesto_usd", "ALTER TABLE gastos ADD COLUMN impuesto_usd REAL NOT NULL DEFAULT 0"),
        ("estado", "ALTER TABLE gastos ADD COLUMN estado TEXT NOT NULL DEFAULT 'confirmado'"),
    ],
    "historial_compras": [
        ("fiscal_tipo", "ALTER TABLE historial_compras ADD COLUMN fiscal_tipo TEXT NOT NULL DEFAULT 'gravada'"),
        ("fiscal_iva_credito_usd", "ALTER TABLE historial_compras ADD COLUMN fiscal_iva_credito_usd REAL NOT NULL DEFAULT 0"),
        ("fiscal_credito_iva_deducible", "ALTER TABLE historial_compras ADD COLUMN fiscal_credito_iva_deducible INTEGER NOT NULL DEFAULT 1"),
        ("activo", "ALTER TABLE historial_compras ADD COLUMN activo INTEGER NOT NULL DEFAULT 1"),
        ("comision_pago_usd", "ALTER TABLE historial_compras ADD COLUMN comision_pago_usd REAL NOT NULL DEFAULT 0"),
    ],
    "movimientos_tesoreria": [
        ("fecha", "ALTER TABLE movimientos_tesoreria ADD COLUMN fecha TEXT"),
        ("tipo", "ALTER TABLE movimientos_tesoreria ADD COLUMN tipo TEXT NOT NULL DEFAULT 'ingreso'"),
        ("origen", "ALTER TABLE movimientos_tesoreria ADD COLUMN origen TEXT"),
        ("referencia_id", "ALTER TABLE movimientos_tesoreria ADD COLUMN referencia_id INTEGER"),
        ("descripcion", "ALTER TABLE movimientos_tesoreria ADD COLUMN descripcion TEXT"),
        ("monto_usd", "ALTER TABLE movimientos_tesoreria ADD COLUMN monto_usd REAL NOT NULL DEFAULT 0"),
        ("moneda", "ALTER TABLE movimientos_tesoreria ADD COLUMN moneda TEXT NOT NULL DEFAULT 'USD'"),
        ("monto_moneda", "ALTER TABLE movimientos_tesoreria ADD COLUMN monto_moneda REAL NOT NULL DEFAULT 0"),
        ("tasa_cambio", "ALTER TABLE movimientos_tesoreria ADD COLUMN tasa_cambio REAL NOT NULL DEFAULT 1"),
        ("metodo_pago", "ALTER TABLE movimientos_tesoreria ADD COLUMN metodo_pago TEXT NOT NULL DEFAULT 'efectivo'"),
        ("usuario", "ALTER TABLE movimientos_tesoreria ADD COLUMN usuario TEXT NOT NULL DEFAULT 'Sistema'"),
        ("estado", "ALTER TABLE movimientos_tesoreria ADD COLUMN estado TEXT NOT NULL DEFAULT 'confirmado'"),
        ("metadata", "ALTER TABLE movimientos_tesoreria ADD COLUMN metadata TEXT"),
    ],
    "cierres_caja": [
        ("fecha", "ALTER TABLE cierres_caja ADD COLUMN fecha TEXT"),
        ("usuario", "ALTER TABLE cierres_caja ADD COLUMN usuario TEXT NOT NULL DEFAULT 'Sistema'"),
        ("estado", "ALTER TABLE cierres_caja ADD COLUMN estado TEXT NOT NULL DEFAULT 'cerrado'"),
        ("cash_start", "ALTER TABLE cierres_caja ADD COLUMN cash_start REAL NOT NULL DEFAULT 0"),
        ("cash_end", "ALTER TABLE cierres_caja ADD COLUMN cash_end REAL NOT NULL DEFAULT 0"),
        ("observaciones", "ALTER TABLE cierres_caja ADD COLUMN observaciones TEXT"),
    ],
    "despachos_entregas": [
        ("telefono", "ALTER TABLE despachos_entregas ADD COLUMN telefono TEXT"),
        ("venta_id", "ALTER TABLE despachos_entregas ADD COLUMN venta_id INTEGER"),
        ("orden_produccion_id", "ALTER TABLE despachos_entregas ADD COLUMN orden_produccion_id INTEGER"),
        ("referencia", "ALTER TABLE despachos_entregas ADD COLUMN referencia TEXT"),
        ("numero_guia", "ALTER TABLE despachos_entregas ADD COLUMN numero_guia TEXT"),
        ("motorizado", "ALTER TABLE despachos_entregas ADD COLUMN motorizado TEXT"),
        ("costo_envio_usd", "ALTER TABLE despachos_entregas ADD COLUMN costo_envio_usd REAL NOT NULL DEFAULT 0"),
        ("cobrado_cliente_usd", "ALTER TABLE despachos_entregas ADD COLUMN cobrado_cliente_usd REAL NOT NULL DEFAULT 0"),
        ("estado", "ALTER TABLE despachos_entregas ADD COLUMN estado TEXT NOT NULL DEFAULT 'Por empaquetar'"),
    ],
    "fichas_tecnicas_bom": [
        ("codigo", "ALTER TABLE fichas_tecnicas_bom ADD COLUMN codigo TEXT NOT NULL DEFAULT ''"),
        ("producto", "ALTER TABLE fichas_tecnicas_bom ADD COLUMN producto TEXT NOT NULL DEFAULT ''"),
        ("costo_total_usd", "ALTER TABLE fichas_tecnicas_bom ADD COLUMN costo_total_usd REAL NOT NULL DEFAULT 0"),
        ("precio_sugerido_usd", "ALTER TABLE fichas_tecnicas_bom ADD COLUMN precio_sugerido_usd REAL NOT NULL DEFAULT 0"),
        ("estado", "ALTER TABLE fichas_tecnicas_bom ADD COLUMN estado TEXT NOT NULL DEFAULT 'Borrador'"),
    ],
    "disenos_aprobaciones": [
        ("cliente", "ALTER TABLE disenos_aprobaciones ADD COLUMN cliente TEXT NOT NULL DEFAULT ''"),
        ("nombre_diseno", "ALTER TABLE disenos_aprobaciones ADD COLUMN nombre_diseno TEXT NOT NULL DEFAULT ''"),
        ("estado", "ALTER TABLE disenos_aprobaciones ADD COLUMN estado TEXT NOT NULL DEFAULT 'En diseño'"),
        ("bloqueo_produccion", "ALTER TABLE disenos_aprobaciones ADD COLUMN bloqueo_produccion INTEGER NOT NULL DEFAULT 1"),
    ],
    "unidades_fraccionadas": [
        ("material", "ALTER TABLE unidades_fraccionadas ADD COLUMN material TEXT NOT NULL DEFAULT ''"),
        ("unidad_compra", "ALTER TABLE unidades_fraccionadas ADD COLUMN unidad_compra TEXT NOT NULL DEFAULT 'unidad'"),
        ("unidad_consumo", "ALTER TABLE unidades_fraccionadas ADD COLUMN unidad_consumo TEXT NOT NULL DEFAULT 'unidad'"),
        ("factor_conversion", "ALTER TABLE unidades_fraccionadas ADD COLUMN factor_conversion REAL NOT NULL DEFAULT 1"),
    ],
    "impresora_consumibles": [
        ("capacidad_maquina_ml", "ALTER TABLE impresora_consumibles ADD COLUMN capacidad_maquina_ml REAL NOT NULL DEFAULT 0"),
        ("cantidad_en_maquina_ml", "ALTER TABLE impresora_consumibles ADD COLUMN cantidad_en_maquina_ml REAL NOT NULL DEFAULT 0"),
        ("unidad_carga", "ALTER TABLE impresora_consumibles ADD COLUMN unidad_carga TEXT NOT NULL DEFAULT 'ml'"),
        ("descontar_de_inventario", "ALTER TABLE impresora_consumibles ADD COLUMN descontar_de_inventario INTEGER NOT NULL DEFAULT 1"),
    ],
}


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _table_columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_migration_log_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            area TEXT NOT NULL,
            tabla TEXT,
            columna TEXT,
            operacion TEXT,
            error TEXT NOT NULL
        )
        """
    )


def _log_migration_error(conn, *, area: str, tabla: str | None, columna: str | None, operacion: str, error: Exception | str) -> None:
    _ensure_migration_log_table(conn)
    conn.execute(
        """
        INSERT INTO migration_errors(area, tabla, columna, operacion, error)
        VALUES (?, ?, ?, ?, ?)
        """,
        (area, tabla, columna, operacion, str(error)[:1000]),
    )


def _ensure_columns(conn, table_name: str, column_specs: Iterable[tuple[str, str]]) -> None:
    columns = _table_columns(conn, table_name)
    if not columns:
        return
    for column_name, ddl in column_specs:
        if column_name in columns:
            continue
        try:
            conn.execute(ddl)
            columns.add(column_name)
        except Exception as exc:
            _log_migration_error(
                conn,
                area="column_migration",
                tabla=table_name,
                columna=column_name,
                operacion=ddl,
                error=exc,
            )


def _ensure_printer_consumables_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS impresora_consumibles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            activo_id INTEGER NOT NULL,
            inventario_id INTEGER NOT NULL,
            tipo_consumible TEXT NOT NULL DEFAULT 'tinta',
            color TEXT NOT NULL DEFAULT 'No aplica',
            rendimiento_paginas REAL NOT NULL DEFAULT 0,
            cobertura_referencia TEXT,
            costo_estimado_hoja_usd REAL NOT NULL DEFAULT 0,
            capacidad_maquina_ml REAL NOT NULL DEFAULT 0,
            cantidad_en_maquina_ml REAL NOT NULL DEFAULT 0,
            unidad_carga TEXT NOT NULL DEFAULT 'ml',
            descontar_de_inventario INTEGER NOT NULL DEFAULT 1,
            notas TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            UNIQUE (activo_id, inventario_id, color),
            FOREIGN KEY (activo_id) REFERENCES activos(id),
            FOREIGN KEY (inventario_id) REFERENCES inventario(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_impresora_consumibles_activo ON impresora_consumibles(activo_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_impresora_consumibles_inventario ON impresora_consumibles(inventario_id)")


def _backfill_timestamps(conn) -> None:
    for table_name, column_name in (("movimientos_tesoreria", "fecha"), ("cierres_caja", "fecha")):
        try:
            if _table_exists(conn, table_name) and column_name in _table_columns(conn, table_name):
                conn.execute(f"UPDATE {table_name} SET {column_name}=CURRENT_TIMESTAMP WHERE {column_name} IS NULL OR {column_name}='' ")
        except Exception as exc:
            _log_migration_error(conn, area="timestamp_backfill", tabla=table_name, columna=column_name, operacion="backfill timestamp", error=exc)


def _backfill_fiscal_values(conn) -> None:
    fiscal_tables = ("ventas", "gastos", "historial_compras")
    for table_name in fiscal_tables:
        if not _table_exists(conn, table_name):
            continue
        try:
            columns = _table_columns(conn, table_name)
            if table_name == "ventas" and {"fiscal_tipo", "fiscal_iva_debito_usd"}.issubset(columns):
                impuesto_expr = "COALESCE(impuesto_usd, 0)" if "impuesto_usd" in columns else "0"
                conn.execute(
                    f"""
                    UPDATE ventas
                    SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                        fiscal_iva_debito_usd = CASE
                            WHEN COALESCE(fiscal_iva_debito_usd, 0) <= 0 THEN {impuesto_expr}
                            ELSE fiscal_iva_debito_usd
                        END
                    """
                )
            elif table_name in {"gastos", "historial_compras"} and {"fiscal_tipo", "fiscal_iva_credito_usd", "fiscal_credito_iva_deducible"}.issubset(columns):
                impuesto_col = "impuesto_usd" if table_name == "gastos" else "impuestos"
                impuesto_expr = f"COALESCE({impuesto_col}, 0)" if impuesto_col in columns else "0"
                conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                        fiscal_credito_iva_deducible = COALESCE(fiscal_credito_iva_deducible, 1),
                        fiscal_iva_credito_usd = CASE
                            WHEN COALESCE(fiscal_iva_credito_usd, 0) <= 0 THEN {impuesto_expr}
                            ELSE fiscal_iva_credito_usd
                        END
                    """
                )
        except Exception as exc:
            _log_migration_error(conn, area="fiscal_backfill", tabla=table_name, columna=None, operacion="backfill fiscal", error=exc)


def run_auto_migrations() -> None:
    """Ejecuta migraciones idempotentes y seguras para bases SQLite existentes."""
    with db_transaction() as conn:
        _ensure_migration_log_table(conn)
        try:
            _ensure_printer_consumables_table(conn)
        except Exception as exc:
            _log_migration_error(conn, area="table_creation", tabla="impresora_consumibles", columna=None, operacion="create table", error=exc)
        for table_name, column_specs in COLUMN_MIGRATIONS.items():
            try:
                _ensure_columns(conn, table_name, column_specs)
            except Exception as exc:
                _log_migration_error(conn, area="table_migration", tabla=table_name, columna=None, operacion="ensure columns", error=exc)
        _backfill_timestamps(conn)
        _backfill_fiscal_values(conn)
