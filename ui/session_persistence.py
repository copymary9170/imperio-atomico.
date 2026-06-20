from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT_DIR / "data" / "session_snapshot.json"
RESTORE_FLAG = "__session_restored__"
CODE_SIGNATURE_KEY = "__code_signature__"
NON_PERSISTENT_KEYS = {
    RESTORE_FLAG,
    CODE_SIGNATURE_KEY,
}
NON_PERSISTENT_PREFIXES = (
    "FormSubmitter",
)
NON_PERSISTENT_EXACT = {
    "kdx_guardar_ajuste",
}
NON_PERSISTENT_CONTAINS = (
    "guardar_",
    "btn_",
    "button_",
)


def _is_non_persistent_key(key: Any) -> bool:
    key_text = str(key)
    if key_text in NON_PERSISTENT_KEYS or key_text in NON_PERSISTENT_EXACT:
        return True
    if key_text.startswith(NON_PERSISTENT_PREFIXES):
        return True
    return any(fragment in key_text for fragment in NON_PERSISTENT_CONTAINS)


def _project_code_signature() -> str:
    """
    Firma liviana del estado del código.

    Si cambia cualquier archivo .py del proyecto, la firma cambia y el
    snapshot de sesión previo se invalida automáticamente.
    """
    files = sorted(p for p in ROOT_DIR.rglob("*.py") if p.is_file())
    digest = hashlib.sha256()
    for file in files:
        rel = file.relative_to(ROOT_DIR).as_posix()
        stat = file.stat()
        digest.update(rel.encode("utf-8"))
        digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
    return digest.hexdigest()


def _is_json_serializable(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


def clear_session_snapshot() -> None:
    """Elimina la sesión persistida en disco."""
    try:
        SNAPSHOT_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def restore_session_snapshot() -> None:
    """Restaura el estado persistido, sólo una vez por sesión Streamlit."""
    if st.session_state.get(RESTORE_FLAG):
        return

    st.session_state[RESTORE_FLAG] = True
    current_signature = _project_code_signature()

    if not SNAPSHOT_PATH.exists():
        st.session_state[CODE_SIGNATURE_KEY] = current_signature
        return

    try:
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        saved_signature = str(raw.get(CODE_SIGNATURE_KEY, ""))
        if saved_signature != current_signature:
            # El código cambió: se ignora el snapshot para evitar inconsistencias.
            SNAPSHOT_PATH.unlink(missing_ok=True)
            st.session_state[CODE_SIGNATURE_KEY] = current_signature
            return

        payload = raw.get("data", {})
        if isinstance(payload, dict):
            for key, value in payload.items():
                if _is_non_persistent_key(key):
                    continue
                st.session_state.setdefault(key, value)

        st.session_state[CODE_SIGNATURE_KEY] = current_signature
    except Exception:
        # Si el archivo está corrupto o incompleto, se reinicia silenciosamente.
        SNAPSHOT_PATH.unlink(missing_ok=True)
        st.session_state[CODE_SIGNATURE_KEY] = current_signature


def save_session_snapshot() -> None:
    """Guarda el estado serializable para recuperarlo en próximas sesiones."""
    current_signature = st.session_state.get(CODE_SIGNATURE_KEY) or _project_code_signature()

    data: dict[str, Any] = {}
    for key, value in st.session_state.items():
        if _is_non_persistent_key(key):
            continue
        if _is_json_serializable(value):
            data[str(key)] = value

    payload = {
        CODE_SIGNATURE_KEY: current_signature,
        "data": data,
    }

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
