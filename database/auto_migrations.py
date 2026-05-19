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
}


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _table_columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_columns(conn, table_name: str, column_specs: Iterable[tuple[str, str]]) -> None:
    columns = _table_columns(conn, table_name)
    if not columns:
        return
    for column_name, ddl in column_specs:
        if column_name not in columns:
            conn.execute(ddl)
            columns.add(column_name)


def _backfill_timestamps(conn) -> None:
    for table_name, column_name in (
        ("movimientos_tesoreria", "fecha"),
        ("cierres_caja", "fecha"),
    ):
        if _table_exists(conn, table_name) and column_name in _table_columns(conn, table_name):
            conn.execute(f"UPDATE {table_name} SET {column_name}=CURRENT_TIMESTAMP WHERE {column_name} IS NULL OR {column_name}='' ")


def _backfill_fiscal_values(conn) -> None:
    if _table_exists(conn, "ventas"):
        columns = _table_columns(conn, "ventas")
        if {"fiscal_tipo", "fiscal_iva_debito_usd"}.issubset(columns):
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
    if _table_exists(conn, "gastos"):
        columns = _table_columns(conn, "gastos")
        if {"fiscal_tipo", "fiscal_iva_credito_usd", "fiscal_credito_iva_deducible"}.issubset(columns):
            impuesto_expr = "COALESCE(impuesto_usd, 0)" if "impuesto_usd" in columns else "0"
            conn.execute(
                f"""
                UPDATE gastos
                SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                    fiscal_credito_iva_deducible = COALESCE(fiscal_credito_iva_deducible, 1),
                    fiscal_iva_credito_usd = CASE
                        WHEN COALESCE(fiscal_iva_credito_usd, 0) <= 0 THEN {impuesto_expr}
                        ELSE fiscal_iva_credito_usd
                    END
                """
            )
    if _table_exists(conn, "historial_compras"):
        columns = _table_columns(conn, "historial_compras")
        if {"fiscal_tipo", "fiscal_iva_credito_usd", "fiscal_credito_iva_deducible"}.issubset(columns):
            impuesto_expr = "COALESCE(impuestos, 0)" if "impuestos" in columns else "0"
            conn.execute(
                f"""
                UPDATE historial_compras
                SET fiscal_tipo = COALESCE(NULLIF(fiscal_tipo, ''), 'gravada'),
                    fiscal_credito_iva_deducible = COALESCE(fiscal_credito_iva_deducible, 1),
                    fiscal_iva_credito_usd = CASE
                        WHEN COALESCE(fiscal_iva_credito_usd, 0) <= 0 THEN {impuesto_expr}
                        ELSE fiscal_iva_credito_usd
                    END
                """
            )


def run_auto_migrations() -> None:
    """Ejecuta migraciones idempotentes y seguras para bases SQLite existentes."""
    with db_transaction() as conn:
        for table_name, column_specs in COLUMN_MIGRATIONS.items():
            _ensure_columns(conn, table_name, column_specs)
        _backfill_timestamps(conn)
        _backfill_fiscal_values(conn)
