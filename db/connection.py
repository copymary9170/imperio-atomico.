""Adaptador de compatibilidad para conexiones SQLite.

Uso legado:
    from db.connection import connect as db_connect

Internamente delega a `database.connection.get_connection`.
"""

from __future__ import annotations

import sqlite3

from database.connection import get_connection


def connect() -> sqlite3.Connection:
    """Devuelve una conexión SQLite configurada para el ERP."""
    return get_connection()
