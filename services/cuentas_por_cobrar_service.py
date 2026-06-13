from __future__ import annotations

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text


ESTADOS_CXC = ["pendiente", "parcial", "cobrada", "vencida", "anulada"]

CXC_COLUMNS = {
    "fecha": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "fecha_creacion": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "usuario": "TEXT NOT NULL DEFAULT 'Sistema'",
    "venta_id": "INTEGER",
    "cliente_id": "INTEGER",
    "cliente": "TEXT NOT NULL DEFAULT ''",
    "concepto": "TEXT NOT NULL DEFAULT ''",
    "referencia": "TEXT",
    "tipo_documento": "TEXT NOT NULL DEFAULT 'venta'",
    "fecha_compromiso": "TEXT",
    "monto_original_usd": "REAL NOT NULL DEFAULT 0",
    "monto_cobrado_usd": "REAL NOT NULL DEFAULT 0",
    "total_usd": "REAL NOT NULL DEFAULT 0",
    "pagado_usd": "REAL NOT NULL DEFAULT 0",
    "pendiente_usd": "REAL NOT NULL DEFAULT 0",
    "saldo_usd": "REAL NOT NULL DEFAULT 0",
    "dias_vencimiento": "INTEGER NOT NULL DEFAULT 0",
    "estado": "TEXT NOT NULL DEFAULT 'pendiente'",
    "metodo_pago": "TEXT",
    "notas": "TEXT",
}

ABONOS_CXC_COLUMNS = {
    "fecha": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "usuario": "TEXT NOT NULL DEFAULT 'Sistema'",
    "cuenta_id": "INTEGER NOT NULL DEFAULT 0",
    "monto_usd": "REAL NOT NULL DEFAULT 0",
    "metodo_pago": "TEXT",
    "referencia": "TEXT",
    "notas": "TEXT",
}


def _table_columns(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_cuentas_por_cobrar_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                venta_id INTEGER,
                cliente_id INTEGER,
                cliente TEXT NOT NULL DEFAULT '',
                concepto TEXT NOT NULL DEFAULT '',
                referencia TEXT,
                tipo_documento TEXT NOT NULL DEFAULT 'venta',
                fecha_compromiso TEXT,
                monto_original_usd REAL NOT NULL DEFAULT 0,
                monto_cobrado_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                pagado_usd REAL NOT NULL DEFAULT 0,
                pendiente_usd REAL NOT NULL DEFAULT 0,
                saldo_usd REAL NOT NULL DEFAULT 0,
                dias_vencimiento INTEGER NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                metodo_pago TEXT,
                notas TEXT
            )
            """
        )
        cols = _table_columns(conn, "cuentas_por_cobrar")
        for column, ddl in CXC_COLUMNS.items():
            if column not in cols:
                conn.execute(f"ALTER TABLE cuentas_por_cobrar ADD COLUMN {column} {ddl}")
                cols.add(column)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS abonos_cuentas_por_cobrar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                cuenta_id INTEGER NOT NULL DEFAULT 0,
                monto_usd REAL NOT NULL DEFAULT 0,
                metodo_pago TEXT,
                referencia TEXT,
                notas TEXT,
                FOREIGN KEY(cuenta_id) REFERENCES cuentas_por_cobrar(id)
            )
            """
        )
        cols_abonos = _table_columns(conn, "abonos_cuentas_por_cobrar")
        for column, ddl in ABONOS_CXC_COLUMNS.items():
            if column not in cols_abonos:
                conn.execute(f"ALTER TABLE abonos_cuentas_por_cobrar ADD COLUMN {column} {ddl}")
                cols_abonos.add(column)


def _estado_por_pago(total: float, pagado: float) -> str:
    if pagado <= 0:
        return "pendiente"
    if pagado + 0.0001 >= total:
        return "cobrada"
    return "parcial"


def crear_cuenta_por_cobrar(*, usuario: str, cliente: str, concepto: str, total_usd: float, pagado_usd: float = 0.0, fecha_compromiso: str = "", metodo_pago: str = "", referencia: str = "", notas: str = "", venta_id: int | None = None, cliente_id: int | None = None) -> int:
    ensure_cuentas_por_cobrar_tables()
    cliente_ok = require_text(cliente, "Cliente")
    concepto_ok = require_text(concepto, "Concepto")
    total = float(total_usd or 0.0)
    pagado = max(0.0, float(pagado_usd or 0.0))
    if total <= 0:
        raise ValueError("El total debe ser mayor a cero.")
    pagado = min(pagado, total)
    pendiente = max(0.0, total - pagado)
    estado = _estado_por_pago(total, pagado)
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cuentas_por_cobrar
            (usuario, venta_id, cliente_id, cliente, concepto, referencia, tipo_documento, fecha_compromiso, monto_original_usd, monto_cobrado_usd, total_usd, pagado_usd, pendiente_usd, saldo_usd, estado, metodo_pago, notas)
            VALUES (?, ?, ?, ?, ?, ?, 'venta', NULLIF(?, ''), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(usuario or "Sistema"), int(venta_id) if venta_id else None, int(cliente_id) if cliente_id else None, cliente_ok, concepto_ok, clean_text(referencia), clean_text(fecha_compromiso), round(total, 4), round(pagado, 4), round(total, 4), round(pagado, 4), round(pendiente, 4), round(pendiente, 4), estado, clean_text(metodo_pago), clean_text(notas)),
        )
        cuenta_id = int(cur.lastrowid)
        if pagado > 0:
            conn.execute(
                "INSERT INTO abonos_cuentas_por_cobrar(usuario, cuenta_id, monto_usd, metodo_pago, referencia, notas) VALUES (?, ?, ?, ?, ?, ?)",
                (str(usuario or "Sistema"), cuenta_id, round(pagado, 4), clean_text(metodo_pago), clean_text(referencia), "Pago inicial"),
            )
        return cuenta_id


def registrar_abono_cxc(*, usuario: str, cuenta_id: int, monto_usd: float, metodo_pago: str = "", referencia: str = "", notas: str = "") -> dict:
    ensure_cuentas_por_cobrar_tables()
    monto = float(monto_usd or 0.0)
    if monto <= 0:
        raise ValueError("El abono debe ser mayor a cero.")
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM cuentas_por_cobrar WHERE id=?", (int(cuenta_id),)).fetchone()
        if not row:
            raise ValueError("Cuenta por cobrar no encontrada.")
        total = float(row["total_usd"] or row["monto_original_usd"] or 0.0)
        pagado_actual = float(row["pagado_usd"] or row["monto_cobrado_usd"] or 0.0)
        nuevo_pagado = min(total, pagado_actual + monto)
        pendiente = max(0.0, total - nuevo_pagado)
        estado = _estado_por_pago(total, nuevo_pagado)
        conn.execute("UPDATE cuentas_por_cobrar SET pagado_usd=?, monto_cobrado_usd=?, pendiente_usd=?, saldo_usd=?, estado=?, metodo_pago=COALESCE(NULLIF(?, ''), metodo_pago) WHERE id=?", (round(nuevo_pagado, 4), round(nuevo_pagado, 4), round(pendiente, 4), round(pendiente, 4), estado, clean_text(metodo_pago), int(cuenta_id)))
        cur = conn.execute(
            "INSERT INTO abonos_cuentas_por_cobrar(usuario, cuenta_id, monto_usd, metodo_pago, referencia, notas) VALUES (?, ?, ?, ?, ?, ?)",
            (str(usuario or "Sistema"), int(cuenta_id), round(monto, 4), clean_text(metodo_pago), clean_text(referencia), clean_text(notas)),
        )
        return {"abono_id": int(cur.lastrowid), "pagado_usd": nuevo_pagado, "pendiente_usd": pendiente, "saldo_usd": pendiente, "estado": estado}


def listar_cuentas_por_cobrar(limit: int = 200) -> pd.DataFrame:
    ensure_cuentas_por_cobrar_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, venta_id, cliente_id, cliente, concepto, referencia, fecha_compromiso, total_usd, pagado_usd, pendiente_usd, saldo_usd, estado, metodo_pago, notas
            FROM cuentas_por_cobrar
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )


def listar_abonos_cxc(cuenta_id: int) -> pd.DataFrame:
    ensure_cuentas_por_cobrar_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha, monto_usd, metodo_pago, referencia, notas
            FROM abonos_cuentas_por_cobrar
            WHERE cuenta_id=?
            ORDER BY id DESC
            """,
            conn,
            params=(int(cuenta_id),),
        )
