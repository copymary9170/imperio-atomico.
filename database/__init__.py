"""Compatibilidad con código legado que importaba `db.connection`.

Este paquete reexpone la conexión central actual (`database.connection`) para
permitir migraciones graduales sin romper imports históricos.
"""

from db.connection import connect

__all__ = ["connect"]
