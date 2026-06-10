from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

CARACAS_TZ = ZoneInfo("America/Caracas")


def now_caracas() -> datetime:
    """Devuelve la fecha y hora actual en zona horaria de Caracas."""
    return datetime.now(CARACAS_TZ)


def caracas_timestamp() -> str:
    """Formato estándar para guardar fecha/hora local en base de datos."""
    return now_caracas().strftime("%Y-%m-%d %H:%M:%S")


def caracas_iso() -> str:
    """Fecha/hora ISO local de Caracas, útil para mostrar en información técnica."""
    return now_caracas().isoformat(timespec="seconds")
