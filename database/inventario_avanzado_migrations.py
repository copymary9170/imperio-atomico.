from __future__ import annotations

from typing import Iterable


INVENTARIO_COLUMN_SPECS: tuple[tuple[str, str], ...] = (
    ("tipo_item", "ALTER TABLE inventario ADD COLUMN tipo_item TEXT NOT NULL DEFAULT 'producto_venta'"),
    ("unidad_base", "ALTER TABLE inventario ADD COLUMN unidad_base TEXT"),
    ("unidad_compra", "ALTER TABLE inventario ADD COLUMN unidad_compra TEXT"),
    ("factor_conversion_compra", "ALTER TABLE inventario ADD COLUMN factor_conversion_compra REAL NOT NULL DEFAULT 1"),
    ("stock_ideal", "ALTER TABLE inventario ADD COLUMN stock_ideal REAL NOT NULL DEFAULT 0"),
    ("punto_reorden", "ALTER TABLE inventario ADD COLUMN punto_reorden REAL NOT NULL DEFAULT 0"),
    ("lead_time_dias", "ALTER TABLE inventario ADD COLUMN lead_time_dias INTEGER NOT NULL DEFAULT 0"),
    ("margen_objetivo_pct", "ALTER TABLE inventario ADD COLUMN margen_objetivo_pct REAL NOT NULL DEFAULT 0.40"),
    ("merma_estimada_pct", "ALTER TABLE inventario ADD COLUMN merma_estimada_pct REAL NOT NULL DEFAULT 0"),
    ("permite_stock_negativo", "ALTER TABLE inventario ADD COLUMN permite_stock_negativo INTEGER NOT NULL DEFAULT 0"),
    ("control_lote", "ALTER TABLE inventario ADD COLUMN control_lote INTEGER NOT NULL DEFAULT 0"),
    ("ubicacion", "ALTER TABLE inventario ADD COLUMN ubicacion TEXT"),
    ("proveedor_preferido_id", "ALTER TABLE inventario ADD COLUMN proveedor_preferido_id INTEGER"),
)


def table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def log_error(conn, *, area: str, tabla: str | None, columna: str | None, operacion: str, error: Exception | str) -> None:
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
    conn.execute(
        """
        INSERT INTO migration_errors(area, tabla, columna, operacion, error)
        VALUES (?, ?, ?, ?, ?)
        """,
        (area, tabla, columna, operacion, str(error)[:1000]),
    )


def ensure_columns(conn, table_name: str, column_specs: Iterable[tuple[str, str]]) -> None:
    columns = table_columns(conn, table_name)
    if not columns:
        return
    for column_name, ddl in column_specs:
        if column_name in columns:
            continue
        try:
            conn.execute(ddl)
            columns.add(column_name)
        except Exception as exc:
            log_error(
                conn,
                area="inventario_avanzado_columns",
                tabla=table_name,
                columna=column_name,
                operacion=ddl,
                error=exc,
            )


def ensure_recetas_consumo_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recetas_consumo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            insumo_id INTEGER NOT NULL,
            cantidad_insumo REAL NOT NULL DEFAULT 0,
            unidad TEXT,
            merma_pct REAL NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1,
            observaciones TEXT,
            fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (producto_id) REFERENCES inventario(id),
            FOREIGN KEY (insumo_id) REFERENCES inventario(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recetas_consumo_producto ON recetas_consumo(producto_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recetas_consumo_insumo ON recetas_consumo(insumo_id)")


def ensure_conteos_fisicos_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conteos_fisicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'cerrado',
            observaciones TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conteos_fisicos_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conteo_id INTEGER NOT NULL,
            inventario_id INTEGER NOT NULL,
            stock_sistema REAL NOT NULL DEFAULT 0,
            stock_contado REAL NOT NULL DEFAULT 0,
            diferencia REAL NOT NULL DEFAULT 0,
            motivo TEXT,
            FOREIGN KEY (conteo_id) REFERENCES conteos_fisicos(id),
            FOREIGN KEY (inventario_id) REFERENCES inventario(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conteos_fisicos_detalle_conteo ON conteos_fisicos_detalle(conteo_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conteos_fisicos_detalle_inventario ON conteos_fisicos_detalle(inventario_id)")


def run_inventory_advanced_migrations(conn) -> None:
    """Prepara inventario avanzado sin detener la app si algo falla."""
    if not table_exists(conn, "inventario"):
        return

    ensure_columns(conn, "inventario", INVENTARIO_COLUMN_SPECS)

    for table_name, operation in (
        ("recetas_consumo", ensure_recetas_consumo_table),
        ("conteos_fisicos", ensure_conteos_fisicos_tables),
    ):
        try:
            operation(conn)
        except Exception as exc:
            log_error(
                conn,
                area="inventario_avanzado_tables",
                tabla=table_name,
                columna=None,
                operacion="create table/indexes",
                error=exc,
            )
