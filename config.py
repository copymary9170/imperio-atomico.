import os
import tempfile
from pathlib import Path

# ======================================================
# CONFIGURACIÓN GLOBAL ERP IMPERIO
# ======================================================


def _resolve_database_path() -> str:
    configured_path = os.getenv("IMPERIO_DB_PATH")
    if configured_path:
        return str(Path(configured_path).expanduser())

    repo_default = Path("data/imperio.db")
    try:
        repo_default.parent.mkdir(parents=True, exist_ok=True)
        probe_file = repo_default.parent / ".write_test"
        probe_file.touch(exist_ok=True)
        probe_file.unlink(missing_ok=True)
        return str(repo_default)
    except OSError:
        temp_dir = Path(tempfile.gettempdir()) / "imperio-atomico"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return str(temp_dir / "imperio.db")


DATABASE = _resolve_database_path()

EMPRESA = "IMPERIO ATOMICO"

VERSION = "IMPERIO ERP PRO 3.0"

APP_NAME = f"{EMPRESA} - {VERSION}"

DEFAULT_CURRENCY = "USD"

BCV_API = None  # aquí podrías colocar API futura de tasa BCV
