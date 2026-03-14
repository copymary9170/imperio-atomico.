import hashlib
from typing import Dict, Any


# ==========================================================
# CACHE EN MEMORIA
# ==========================================================

_ANALYSIS_CACHE: Dict[str, Any] = {}


# ==========================================================
# GENERAR HASH DE ARCHIVO
# ==========================================================

def file_hash(file_bytes: bytes) -> str:
    """
    Genera un hash único para un archivo.
    """
    return hashlib.md5(file_bytes).hexdigest()


# ==========================================================
# GENERAR CLAVE DE CACHÉ
# ==========================================================

def build_cache_key(file_bytes: bytes, config: dict) -> str:
    """
    Genera una clave única para el análisis considerando
    archivo + configuración de análisis.
    """

    h = file_hash(file_bytes)

    config_str = "_".join(
        f"{k}:{v}" for k, v in sorted(config.items())
    )

    return f"{h}_{config_str}"


# ==========================================================
# GUARDAR EN CACHE
# ==========================================================

def cache_set(key: str, value: Any) -> None:
    _ANALYSIS_CACHE[key] = value


# ==========================================================
# LEER CACHE
# ==========================================================

def cache_get(key: str):

    return _ANALYSIS_CACHE.get(key)
