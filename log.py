from __future__ import annotations

import datetime
import os

LOG_FOLDER = "logs"
LOG_FILE = os.path.join(LOG_FOLDER, "erp.log")


def log(message: str, level: str = "INFO") -> None:
    """Registro simple de eventos del sistema."""

    if not os.path.exists(LOG_FOLDER):
        os.makedirs(LOG_FOLDER)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", encoding="utf8") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")
