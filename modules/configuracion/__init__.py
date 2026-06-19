from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_legacy_path = Path(__file__).resolve().parent.parent / "configuracion.py"
_spec = importlib.util.spec_from_file_location("modules._configuracion_legacy", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"No se pudo cargar {_legacy_path}")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

_original_to_float = _legacy._to_float


def _to_float(config_or_value: Any, key_or_default: Any, default: float | None = None) -> float:
    """Compatibilidad con llamadas antiguas y nuevas.

    Formas admitidas:
    - _to_float(config, key, default)
    - _to_float(value, default)
    """
    if default is None:
        value = config_or_value
        fallback = key_or_default
        try:
            if value in (None, ""):
                return float(fallback)
            return float(value)
        except Exception:
            return float(fallback)
    return _original_to_float(config_or_value, str(key_or_default), float(default))
