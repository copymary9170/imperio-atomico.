from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Optional

from database.connection import db_transaction
from security.permissions import normalize_role_name

PBKDF2_PREFIX = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    usuario: str = ""
    rol: str = "Operator"
    message: str = ""


def _hash_pbkdf2(password: str, *, salt: str | None = None, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt_value.encode("utf-8"),
        iterations,
    ).hex()
    return f"{PBKDF2_PREFIX}${iterations}${salt_value}${digest}"


def hash_password(password: str) -> str:
    password_clean = str(password or "")
    if len(password_clean) < 8:
        raise ValueError("La contraseña debe tener mínimo 8 caracteres.")
    return _hash_pbkdf2(password_clean)


def _verify_pbkdf2(password: str, stored_hash: str) -> bool:
    try:
        prefix, iterations_raw, salt, expected = stored_hash.split("$", 3)
        if prefix != PBKDF2_PREFIX:
            return False
        iterations = int(iterations_raw)
        candidate = _hash_pbkdf2(password, salt=salt, iterations=iterations).split("$", 3)[3]
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def verify_password(password: str, stored_hash: str) -> bool:
    password_value = str(password or "")
    stored_value = str(stored_hash or "")
    if not stored_value:
        return False
    if stored_value.startswith(f"{PBKDF2_PREFIX}$"):
        return _verify_pbkdf2(password_value, stored_value)

    if hmac.compare_digest(password_value, stored_value):
        return True
    sha256_candidate = hashlib.sha256(password_value.encode("utf-8")).hexdigest()
    return hmac.compare_digest(sha256_candidate, stored_value)


def users_count() -> int:
    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()
        return int(row["total"] if row else 0)


def _audit_login(usuario: str, accion: str, detalle: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, ?, ?)
            """,
            (usuario, accion, detalle),
        )


def create_initial_admin(usuario: str, nombre_completo: str, password: str) -> None:
    usuario_clean = str(usuario or "").strip()
    nombre_clean = str(nombre_completo or "").strip() or usuario_clean
    if not usuario_clean:
        raise ValueError("El usuario administrador es obligatorio.")
    if users_count() > 0:
        raise ValueError("Ya existen usuarios. Crea usuarios desde Configuración > Seguridad.")
    password_hash = hash_password(password)
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO usuarios (usuario, nombre_completo, hash_password, rol, estado, ultimo_login)
            VALUES (?, ?, ?, 'Admin', 'activo', CURRENT_TIMESTAMP)
            """,
            (usuario_clean, nombre_clean, password_hash),
        )
        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, 'bootstrap_admin', 'Administrador inicial creado desde pantalla de primer acceso.')
            """,
            (usuario_clean,),
        )


def authenticate_user(usuario: str, password: str) -> AuthResult:
    usuario_clean = str(usuario or "").strip()
    password_value = str(password or "")
    if not usuario_clean or not password_value:
        return AuthResult(False, message="Usuario y contraseña son obligatorios.")

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT usuario, hash_password, rol, estado
            FROM usuarios
            WHERE LOWER(TRIM(usuario)) = LOWER(TRIM(?))
            LIMIT 1
            """,
            (usuario_clean,),
        ).fetchone()

    if not row:
        _audit_login(usuario_clean, "login_failed", "Usuario no existe.")
        return AuthResult(False, usuario=usuario_clean, message="Credenciales inválidas.")

    stored_usuario = str(row["usuario"] or "").strip()
    estado = str(row["estado"] or "activo").casefold()
    if estado not in {"activo", "active"}:
        _audit_login(stored_usuario or usuario_clean, "login_blocked", f"Usuario con estado '{row['estado']}'.")
        return AuthResult(False, usuario=stored_usuario or usuario_clean, message="Usuario inactivo o bloqueado.")

    if not verify_password(password_value, str(row["hash_password"] or "")):
        _audit_login(stored_usuario or usuario_clean, "login_failed", "Contraseña inválida.")
        return AuthResult(False, usuario=stored_usuario or usuario_clean, message="Credenciales inválidas.")

    rol = normalize_role_name(row["rol"])
    with db_transaction() as conn:
        conn.execute("UPDATE usuarios SET ultimo_login=CURRENT_TIMESTAMP WHERE usuario=?", (stored_usuario,))
        if not str(row["hash_password"] or "").startswith(f"{PBKDF2_PREFIX}$"):
            conn.execute("UPDATE usuarios SET hash_password=? WHERE usuario=?", (hash_password(password_value), stored_usuario))
        conn.execute(
            """
            INSERT INTO auditoria_seguridad (usuario, accion, detalle)
            VALUES (?, 'login_success', ?)
            """,
            (stored_usuario, f"Inicio de sesión exitoso con rol '{rol}'."),
        )
    return AuthResult(True, usuario=stored_usuario, rol=rol, message="OK")


def configured_bootstrap_password() -> Optional[str]:
    return os.getenv("IMPERIO_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD")
