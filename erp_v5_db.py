"""ERP Imperio v5.0 - Parte 1
Estructura de Base de Datos (soft deletes, logs y relaciones) + conexión.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Iterator, Optional

# Precisión base para operaciones intermedias; salida monetaria a 2 decimales.
getcontext().prec = 28
MONEY_QUANT = Decimal("0.01")


def D(value: object, default: str = "0") -> Decimal:
    """Convierte valor a Decimal de forma segura."""
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def money(value: object) -> Decimal:
    """Redondeo financiero estricto a 2 decimales."""
    return D(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DBConfig:
    path: str = "database.db"
    timeout: int = 30


@contextmanager
def db_connect(config: DBConfig = DBConfig()) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.path, timeout=config.timeout, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA cache_size = -10000;")
        yield conn
    finally:
        conn.close()


# Tablas núcleo v5.0 (todas con activo=1 por política de cero borrado)
BASE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        nombre TEXT,
        rol TEXT,
        password_hash TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        whatsapp TEXT,
        categoria TEXT DEFAULT 'General',
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT,
        rif TEXT,
        contacto TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipo TEXT NOT NULL,
        modelo TEXT,
        tipo TEXT,
        categoria TEXT,
        costo_hora REAL DEFAULT 0,
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT NOT NULL,
        modelo_referencia TEXT,
        categoria TEXT,
        unidad TEXT DEFAULT 'unidad',
        cantidad REAL DEFAULT 0,
        precio_usd REAL DEFAULT 0,
        minimo REAL DEFAULT 0,
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activos_insumos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activo_id INTEGER NOT NULL,
        inventario_id INTEGER NOT NULL,
        prioridad INTEGER DEFAULT 1,
        observacion TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (activo_id, inventario_id),
        FOREIGN KEY (activo_id) REFERENCES activos(id),
        FOREIGN KEY (inventario_id) REFERENCES inventario(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        detalle TEXT,
        metodo TEXT,
        prioridad_urgencia INTEGER DEFAULT 0,
        monto_total REAL NOT NULL DEFAULT 0,
        usuario TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT,
        categoria TEXT,
        metodo TEXT,
        monto REAL NOT NULL DEFAULT 0,
        usuario TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ordenes_produccion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        trabajo TEXT,
        estado TEXT DEFAULT 'Cotización',
        costo_base REAL DEFAULT 0,
        usuario TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS configuracion (
        parametro TEXT PRIMARY KEY,
        valor TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS logs_actividad (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        usuario TEXT,
        accion TEXT NOT NULL,
        tabla_afectada TEXT NOT NULL,
        id_registro INTEGER,
        valor_anterior TEXT,
        valor_nuevo TEXT
    )
    """,
]


def _get_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return [r[0] for r in rows]


def _ensure_column_activo(conn: sqlite3.Connection, table: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "activo" not in cols and table != "configuracion":
        conn.execute(f"ALTER TABLE {table} ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")
    if table != "configuracion":
        conn.execute(f"UPDATE {table} SET activo=1 WHERE activo IS NULL")


def initialize_db(config: DBConfig = DBConfig()) -> None:
    with db_connect(config) as conn:
        conn.execute("BEGIN")
        for ddl in BASE_TABLES_SQL:
            conn.execute(ddl)

        # Política global: todas las tablas de negocio con soft delete.
        for t in _get_tables(conn):
            if t in {"logs_actividad", "configuracion"}:
                continue
            _ensure_column_activo(conn, t)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_logs_tabla_fecha ON logs_actividad(tabla_afectada, timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventario_item_modelo ON inventario(item, modelo_referencia)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activos_equipo_modelo ON activos(equipo, modelo)"
        )

        defaults = [
            ("factor_desperdicio", "1.15"),
            ("costo_limpieza_cabezal", "0.00"),
            ("golpe_de_prensa", "0.00"),
            ("recargo_urgencia_25", "25"),
            ("recargo_urgencia_50", "50"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO configuracion(parametro, valor) VALUES (?, ?)",
            defaults,
        )
        conn.commit()


def log_actividad(
    conn: sqlite3.Connection,
    usuario: str,
    accion: str,
    tabla_afectada: str,
    id_registro: Optional[int] = None,
    valor_anterior: Optional[str] = None,
    valor_nuevo: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO logs_actividad
            (usuario, accion, tabla_afectada, id_registro, valor_anterior, valor_nuevo)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (usuario, accion, tabla_afectada, id_registro, valor_anterior, valor_nuevo),
    )


def soft_delete(conn: sqlite3.Connection, table: str, record_id: int, usuario: str = "Sistema") -> None:
    prev = conn.execute(f"SELECT * FROM {table} WHERE id=?", (int(record_id),)).fetchone()
    conn.execute(f"UPDATE {table} SET activo=0 WHERE id=?", (int(record_id),))
    log_actividad(
        conn=conn,
        usuario=usuario,
        accion="SOFT_DELETE",
        tabla_afectada=table,
        id_registro=int(record_id),
        valor_anterior=str(dict(prev)) if prev else None,
        valor_nuevo="{'activo': 0}",
    )


if __name__ == "__main__":
    initialize_db()
    print("ERP v5.0 Parte 1 inicializada correctamente.")
