from __future__ import annotations

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_schema_module_no_self_import_regression() -> None:
    schema_source = Path("database/schema.py").read_text(encoding="utf-8")
    assert "from database.schema import init_schema" not in schema_source


def test_init_schema_importable() -> None:
    schema_module = importlib.import_module("database.schema")
    assert callable(schema_module.init_schema)
