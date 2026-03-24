from __future__ import annotations

import argparse
import os
import py_compile
import sqlite3
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _all_python_files() -> list[Path]:
    return sorted(p for p in REPO_ROOT.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts)


def check_compile() -> list[str]:
    errors: list[str] = []
    for file in _all_python_files():
        try:
            py_compile.compile(str(file), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{file.relative_to(REPO_ROOT)} :: {exc.msg}")
    return errors


def check_legacy_filenames() -> list[str]:
    issues: list[str] = []
    for entry in REPO_ROOT.iterdir():
        if entry.is_file() and any(ch in entry.name for ch in ["\n", "\t"]):
            issues.append(f"Nombre inválido detectado: {entry.name!r}")
        if entry.is_file() and entry.suffix not in {".py", ".md", ".txt", ".db", ".bat", ".yml", ".yaml", ".toml", ".json", ".lock"}:
            if " " in entry.name and "streamlit" in entry.name.lower():
                issues.append(f"Archivo legacy sospechoso: {entry.name}")
    return issues


def check_migrations_and_integrity() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="imperio-stability-") as tmp:
        db_path = Path(tmp) / "stability.db"
        os.environ["IMPERIO_DB_PATH"] = str(db_path)

        import database.connection as db_connection
        from database.connection import db_transaction
        from database.schema import init_schema
        from modules.inventario import _ensure_inventory_support_tables

        db_connection.DB_PATH = db_path
        init_schema()
        _ensure_inventory_support_tables()

        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO clientes (usuario, nombre, limite_credito_usd, saldo_por_cobrar_usd)
                VALUES ('check', 'Cliente Check', 1000, 0)
                """
            )
            conn.execute(
                """
                INSERT INTO inventario (usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd)
                VALUES ('check', 'SKU-CHECK', 'Producto Check', 'General', 'unidad', 20, 1, 4, 7)
                """
            )

            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                errors.append(f"foreign_key_check encontró {len(fk)} inconsistencias")

            checks = {
                "saldos_cxc_negativos": "SELECT COUNT(*) AS c FROM cuentas_por_cobrar WHERE saldo_usd < 0",
                "saldos_cxp_negativos": "SELECT COUNT(*) AS c FROM cuentas_por_pagar_proveedores WHERE saldo_usd < 0",
                "mov_tesoreria_no_positivos": "SELECT COUNT(*) AS c FROM movimientos_tesoreria WHERE monto_usd <= 0",
                "asientos_descuadrados": "SELECT COUNT(*) AS c FROM asientos_contables WHERE ABS(total_debe_usd-total_haber_usd) > 0.01",
                "stock_negativo": "SELECT COUNT(*) AS c FROM inventario WHERE stock_actual < 0",
            }
            for name, query in checks.items():
                count = int(conn.execute(query).fetchone()["c"])
                if count > 0:
                    errors.append(f"{name}: {count}")

    return errors


def run() -> int:
    parser = argparse.ArgumentParser(description="Checklist de estabilización técnica ERP")
    parser.add_argument("--strict", action="store_true", help="Falla si encuentra cualquier issue")
    args = parser.parse_args()

    all_issues: list[str] = []

    compile_errors = check_compile()
    if compile_errors:
        all_issues.extend([f"[compile] {x}" for x in compile_errors])

    legacy_issues = check_legacy_filenames()
    if legacy_issues:
        all_issues.extend([f"[legacy] {x}" for x in legacy_issues])

    mig_issues = check_migrations_and_integrity()
    if mig_issues:
        all_issues.extend([f"[integrity] {x}" for x in mig_issues])

    if not all_issues:
        print("OK: compilación, migraciones e integridad básica sin hallazgos.")
        return 0

    print("HALLAZGOS:")
    for issue in all_issues:
        print(f" - {issue}")

    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(run())
