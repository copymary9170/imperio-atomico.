from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import database.connection as db_connection
from database.connection import db_transaction
from database.schema import init_schema
from services.fiscal_service import obtener_resumen_fiscal_periodo


class FiscalServiceSchemaFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="imperio-fiscal-")
        self.db_path = Path(self.tmp.name) / "erp_fiscal.db"
        os.environ["IMPERIO_DB_PATH"] = str(self.db_path)
        db_connection.DB_PATH = self.db_path
        init_schema()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_resumen_fiscal_sin_tabla_historial_compras(self) -> None:
        with db_transaction() as conn:
            resumen = obtener_resumen_fiscal_periodo(conn, periodo="2026-03")
        self.assertEqual(int(resumen["compras_documentos"]), 0)
        self.assertEqual(float(resumen["compras_base_usd"]), 0.0)
        self.assertEqual(float(resumen["iva_credito_compras_usd"]), 0.0)
