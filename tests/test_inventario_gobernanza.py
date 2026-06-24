from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

import database.connection as db_connection
from database.connection import db_transaction
from database.schema import init_schema
from services.facturas_compra_service import registrar_factura_compra
from services.inventory_service import InventoryMovement, InventoryService
from services.inventario_control_contable_service import crear_cierre
from services.inventario_gobernanza_service import (
    anular_factura_compra,
    decidir_ajuste,
    ensure_schema,
    registrar_devolucion_proveedor,
    solicitar_ajuste,
)


class InventarioGobernanzaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="inventario-gobernanza-")
        self.db_path = Path(self.tmp.name) / "gobernanza.db"
        os.environ["IMPERIO_DB_PATH"] = str(self.db_path)
        db_connection.DB_PATH = self.db_path
        init_schema()
        ensure_schema()
        with db_transaction() as conn:
            conn.execute("""
                INSERT INTO inventario(
                    usuario,sku,nombre,categoria,unidad,unidad_base,stock_actual,
                    stock_minimo,costo_unitario_usd,precio_venta_usd
                ) VALUES('qa','PAPEL-QA','Papel QA','Papelería','hoja','hoja',10,1,0.10,0.25)
            """)
            self.item_id = int(conn.execute("SELECT id FROM inventario WHERE sku='PAPEL-QA'").fetchone()["id"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _stock(self) -> float:
        with db_transaction() as conn:
            return float(conn.execute("SELECT stock_actual FROM inventario WHERE id=?", (self.item_id,)).fetchone()["stock_actual"])

    def test_ajuste_requiere_aprobador_distinto(self) -> None:
        solicitud_id = solicitar_ajuste(
            inventario_id=self.item_id,
            tipo="AJUSTE_ENTRADA",
            cantidad=5,
            motivo="Conteo QA",
            usuario="operador",
        )
        self.assertEqual(self._stock(), 10)
        with self.assertRaises(ValueError):
            decidir_ajuste(solicitud_id, aprobar=True, usuario="operador")
        decidir_ajuste(solicitud_id, aprobar=True, usuario="administrador")
        self.assertEqual(self._stock(), 15)

    def test_devolucion_parcial_descuenta_stock_y_factura(self) -> None:
        resultado = registrar_factura_compra(
            usuario="qa",
            proveedor="Proveedor QA",
            numero_factura="DEV-001",
            fecha_factura=date.today().isoformat(),
            lineas=[{
                "tipo_linea": "Materia prima",
                "inventario_id": self.item_id,
                "descripcion": "Papel QA",
                "cantidad": 10,
                "unidad": "hoja",
                "subtotal_usd": 2,
            }],
            tipo_pago="credito",
            monto_pagado_inicial_usd=0,
        )
        linea_id = int(resultado["lineas"][0]["linea_id"])
        stock_antes = self._stock()
        devolucion_id = registrar_devolucion_proveedor(
            factura_linea_id=linea_id,
            cantidad=3,
            motivo="Material defectuoso",
            nota_credito="NC-001",
            usuario="qa",
        )
        self.assertGreater(devolucion_id, 0)
        self.assertEqual(self._stock(), stock_antes - 3)
        with db_transaction() as conn:
            factura = conn.execute("SELECT total_usd FROM facturas_compra WHERE id=?", (resultado["factura_id"],)).fetchone()
            self.assertAlmostEqual(float(factura["total_usd"]), 1.4, places=4)

    def test_anulacion_sin_pago_revierte_stock(self) -> None:
        stock_inicial = self._stock()
        resultado = registrar_factura_compra(
            usuario="qa",
            proveedor="Proveedor QA",
            numero_factura="ANU-001",
            fecha_factura=date.today().isoformat(),
            lineas=[{
                "tipo_linea": "Materia prima",
                "inventario_id": self.item_id,
                "descripcion": "Papel QA",
                "cantidad": 4,
                "unidad": "hoja",
                "subtotal_usd": 1,
            }],
            tipo_pago="credito",
            monto_pagado_inicial_usd=0,
        )
        self.assertEqual(self._stock(), stock_inicial + 4)
        anular_factura_compra(resultado["factura_id"], usuario="admin", motivo="Factura duplicada")
        self.assertEqual(self._stock(), stock_inicial)
        with db_transaction() as conn:
            estado = conn.execute("SELECT estado FROM facturas_compra WHERE id=?", (resultado["factura_id"],)).fetchone()["estado"]
            self.assertEqual(estado, "anulada")

    def test_cierre_bloquea_movimientos_actuales(self) -> None:
        periodo = date.today().strftime("%Y-%m")
        crear_cierre(periodo, "admin", "Cierre QA")
        with db_transaction() as conn:
            ok, mensaje = InventoryService().procesar_movimiento(conn, InventoryMovement(
                item_id=self.item_id,
                tipo="ENTRADA",
                cantidad=1,
                costo_unitario=0.10,
                motivo="Movimiento posterior al cierre",
                usuario="qa",
            ))
        self.assertFalse(ok)
        self.assertIn("cerrado", mensaje.lower())


if __name__ == "__main__":
    unittest.main()
