from __future__ import annotations

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

    texto = ", ".join(permission_codes)
    st.error(message or f"🚫 No tienes permisos suficientes. Se requiere uno de: {texto}")
    return False


def get_all_permission_codes() -> List[str]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT codigo
            FROM permisos
            ORDER BY codigo
            """
        ).fetchall()

    return [str(r["codigo"]) for r in rows]


def get_permissions_catalog_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT codigo, descripcion
            FROM permisos
            ORDER BY codigo
            """,
            conn,
        )


def get_role_permissions_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT rol, permiso_codigo
            FROM roles_permisos
            ORDER BY rol, permiso_codigo
            """,
            conn,
        )


def get_users_roles_df() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT usuario, nombre_completo, rol, estado, ultimo_login
            FROM usuarios
            ORDER BY usuario
            """,
            conn,
        )


def get_auditoria_seguridad_df(limit: int = 200) -> pd.DataFrame:
    limit = max(1, int(limit))

    with db_transaction() as conn:
        return pd.read_sql_query(
            f"""
            SELECT fecha, usuario, accion, detalle
            FROM auditoria_seguridad
            ORDER BY id DESC
            LIMIT {limit}
            """,
            conn,
        )


def get_permissions_for_role_list(rol: str) -> List[str]:
    return sorted(get_permissions_for_role(rol))


def set_role_permissions(rol: str, permisos: List[str], actor: str) -> None:
    permisos_limpios = sorted({str(p).strip() for p in permisos if str(p).strip()})

    with db_transaction() as conn:
        conn.execute("DELETE FROM roles_permisos WHERE rol = ?", (rol,))

        for permiso in permisos_limpios:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles_permisos (rol, permiso_codigo)
                VALUES (?, ?)
                """,
                (rol, permiso),
            )

        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, ?, ?)
            """,
            (
                actor,
                "editar_permisos_rol",
                f"Rol={rol}; permisos={len(permisos_limpios)}",
            ),
        )


def assign_role_to_user(usuario_objetivo: str, nuevo_rol: str, actor: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE usuarios
            SET rol = ?
            WHERE usuario = ?
            """,
            (nuevo_rol, usuario_objetivo),
        )

        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, ?, ?)
            """,
            (
                actor,
                "asignar_rol_usuario",
                f"Usuario={usuario_objetivo}; nuevo_rol={nuevo_rol}",
            ),
        )

    if usuario_objetivo == get_current_user():
        st.session_state["rol"] = nuevo_rol


def log_security_event(usuario: str, accion: str, detalle: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, ?, ?)
            """,
            (usuario, accion, detalle),
        )
