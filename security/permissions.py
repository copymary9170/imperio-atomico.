from __future__ import annotations

import sqlite3
from typing import List, Set

import pandas as pd
import streamlit as st

from database.connection import db_transaction


SUPERUSER_PERMISSION = "*"


def get_current_user() -> str:
    return st.session_state.get("usuario", "Sistema")


def get_current_role() -> str:
    return st.session_state.get("rol", "Operator")


def set_session_role_from_db() -> str:
    """
    Sincroniza el rol en session_state usando la tabla usuarios.
    Si no encuentra el usuario, conserva el rol actual o usa Operator.
    """
    usuario = get_current_user()

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT rol
            FROM usuarios
            WHERE usuario = ?
            LIMIT 1
            """,
            (usuario,),
        ).fetchone()

    if row and row["rol"]:
        st.session_state["rol"] = row["rol"]
        return str(row["rol"])

    if "rol" not in st.session_state:
        st.session_state["rol"] = "Operator"

    return str(st.session_state["rol"])


def get_permissions_for_role(rol: str) -> Set[str]:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT permiso_codigo
                FROM roles_permisos
                WHERE rol = ?
                """,
                (rol,),
            ).fetchall()
    except sqlite3.OperationalError:
        # En despliegues con DB vacía o desfasada (p.ej. Streamlit Cloud),
        # intentamos autocurar el esquema de seguridad antes de reintentar.
        from database.schema import init_schema

        init_schema()
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT permiso_codigo
                FROM roles_permisos
                WHERE rol = ?
                """,
                (rol,),
            ).fetchall()

    return {str(r["permiso_codigo"]) for r in rows}


def get_current_permissions() -> Set[str]:
    rol = get_current_role()
    return get_permissions_for_role(rol)


def has_permission(permission_code: str) -> bool:
    permisos = get_current_permissions()
    return SUPERUSER_PERMISSION in permisos or permission_code in permisos


def require_permission(permission_code: str, message: str | None = None) -> bool:
    if has_permission(permission_code):
        return True

    st.error(message or f"🚫 No tienes permiso para acceder a esta acción: {permission_code}")
    return False


def require_any_permission(permission_codes: List[str], message: str | None = None) -> bool:
    permisos = get_current_permissions()

