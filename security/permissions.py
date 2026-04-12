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
    if SUPERUSER_PERMISSION in permisos:
        return True

    if any(code in permisos for code in permission_codes):
        return True

    st.error(
        message
        or "🚫 No tienes permisos suficientes para esta acción. "
        f"Requerido uno de: {', '.join(permission_codes)}"
    )
    return False


def get_users_roles_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                usuario,
                nombre_completo,
                estado,
                rol,
                ultimo_login
            FROM usuarios
            ORDER BY usuario
            """,
            conn,
        )


def get_permissions_catalog_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                codigo,
                descripcion
            FROM permisos
            ORDER BY codigo
            """,
            conn,
        )


def get_role_permissions_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                rol,
                permiso_codigo
            FROM roles_permisos
            ORDER BY rol, permiso_codigo
            """,
            conn,
        )


def get_auditoria_seguridad_df(limit: int = 200) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                fecha,
                usuario,
                accion,
                detalle
            FROM auditoria_seguridad
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )


def _insert_auditoria_seguridad(*, usuario: str, accion: str, detalle: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, ?, ?)
            """,
            (usuario, accion, detalle),
        )


def set_role_permissions(rol: str, permission_codes: List[str], usuario: str | None = None) -> None:
    actor = usuario or get_current_user()

    with db_transaction() as conn:
        conn.execute("DELETE FROM roles_permisos WHERE rol = ?", (rol,))
        conn.executemany(
            """
            INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
            VALUES (?, ?)
            """,
            [(rol, code) for code in permission_codes],
        )

    _insert_auditoria_seguridad(
        usuario=actor,
        accion="set_role_permissions",
        detalle=f"Rol '{rol}' actualizado con {len(permission_codes)} permisos.",
    )


def assign_role_to_user(target_usuario: str, new_role: str, actor_usuario: str | None = None) -> None:
    actor = actor_usuario or get_current_user()

    with db_transaction() as conn:
        current_row = conn.execute(
            """
            SELECT rol
            FROM usuarios
            WHERE usuario = ?
            LIMIT 1
            """,
            (target_usuario,),
        ).fetchone()
        old_role = current_row["rol"] if current_row else None

        conn.execute(
            """
            UPDATE usuarios
            SET rol = ?
            WHERE usuario = ?
            """,
            (new_role, target_usuario),
        )

    _insert_auditoria_seguridad(
        usuario=actor,
        accion="assign_role_to_user",
        detalle=f"Usuario '{target_usuario}': rol '{old_role}' -> '{new_role}'.",
    )
