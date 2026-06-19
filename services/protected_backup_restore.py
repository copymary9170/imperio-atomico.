from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from services.backup_service import DATA_DIR, create_backup, get_database_path


def _secret(name: str, default: str = "") -> str:
    try:
        if st is not None and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return default


def _xor_unprotect(data: bytes, password: str) -> bytes:
    if not password:
        return data
    key = hashlib.sha256(password.encode("utf-8")).digest()
    return bytes(byte ^ key[i % len(key)] for i, byte in enumerate(data))


def restore_protected_backup(uploaded_file) -> tuple[bool, str]:
    password = _secret("BACKUP_PASSWORD")
    if not password:
        return False, "Falta BACKUP_PASSWORD en los Secrets de Streamlit."

    try:
        envelope = json.loads(uploaded_file.getvalue().decode("utf-8"))
    except Exception:
        return False, "El archivo no es un respaldo protegido válido."

    if envelope.get("format") != "copy-mary-backup-v1":
        return False, "Formato de respaldo protegido no reconocido."

    try:
        encrypted = base64.b64decode(envelope.get("payload_base64", ""))
        raw = _xor_unprotect(encrypted, password)
    except Exception:
        return False, "No se pudo descifrar el respaldo."

    expected_signature = str(envelope.get("signature_sha256_hmac", ""))
    actual_signature = hmac.new(password.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not expected_signature or not hmac.compare_digest(expected_signature, actual_signature):
        return False, "La contraseña no coincide o el respaldo está dañado."

    if not raw.startswith(b"SQLite format 3"):
        return False, "El contenido restaurado no parece una base SQLite válida."

    db_path = get_database_path()
    if db_path is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DATA_DIR / "imperio_atomico.db"

    create_backup("antes_restaurar_protegido", upload_external=True)
    try:
        Path(db_path).write_bytes(raw)
        return True, f"Respaldo restaurado correctamente en {db_path.name}."
    except Exception as exc:
        return False, f"No se pudo escribir la base restaurada: {exc}"
