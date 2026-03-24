from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import database.connection as db_connection
from database.connection import db_transaction
from database.schema import init_schema
from modules.inventario import CompraFinancialInput, _ensure_inventory_support_tables, registrar_compra
from modules.ventas import registrar_venta
from services.conciliacion_service import (
    cerrar_periodo,
    conciliar_movimientos,
    periodo_esta_cerrado,
    registrar_movimiento_bancario,
)
from services.costeo_service import calcular_costo_servicio, calcular_margen_estimado, guardar_costeo
from services.cxc_cobranza_service import CobranzaInput, registrar_abono_cuenta_por_cobrar
from services.cxp_proveedores_service import registrar_pago_cuenta_por_pagar
from services.tesoreria_service import registrar_egreso, registrar_ingreso


class ERPRegressionSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="imperio-smoke-")
        self.db_path = Path(self.tmp.name) / "erp_smoke.db"
        os.environ["IMPERIO_DB_PATH"] = str(self.db_path)
        db_connection.DB_PATH = self.db_path
        init_schema()
        _ensure_inventory_support_tables()

        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO clientes (usuario, nombre, limite_credito_usd, saldo_por_cobrar_usd)
                VALUES ('qa', 'Cliente QA', 5000, 0)
                """
            )
            conn.execute(
                """
                INSERT INTO proveedores (nombre, telefono, contacto, activo)
                VALUES ('Proveedor QA', '000', 'Equipo QA', 1)
                """
            )
            conn.execute(
                """
                INSERT INTO inventario
                (usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd)
                VALUES ('qa', 'SKU-QA-1', 'Producto QA', 'General', 'unidad', 100, 1, 10, 20)
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ids(self) -> tuple[int, int, int]:
        with db_transaction() as conn:
            cliente_id = int(conn.execute("SELECT id FROM clientes LIMIT 1").fetchone()["id"])
            proveedor_id = int(conn.execute("SELECT id FROM proveedores LIMIT 1").fetchone()["id"])
            inventario_id = int(conn.execute("SELECT id FROM inventario LIMIT 1").fetchone()["id"])
        return cliente_id, proveedor_id, inventario_id

    def test_end_to_end_critical_flows(self) -> None:
        cliente_id, proveedor_id, inventario_id = self._ids()

        # 1) venta contado
        venta_contado_id = registrar_venta(
            usuario="qa",
            cliente_id=cliente_id,
            moneda="USD",
            tasa_cambio=1.0,
            metodo_pago="efectivo",
            items=[
                {
                    "inventario_id": inventario_id,
                    "descripcion": "Producto QA",
                    "cantidad": 2,
                    "precio_unitario_usd": 20,
                    "costo_unitario_usd": 10,
                }
            ],
        )
        self.assertGreater(venta_contado_id, 0)

        # 2) venta crédito + abono
        venta_credito_id = registrar_venta(
            usuario="qa",
            cliente_id=cliente_id,
            moneda="USD",
            tasa_cambio=1.0,
            metodo_pago="credito",
            items=[
                {
                    "inventario_id": inventario_id,
                    "descripcion": "Producto QA crédito",
                    "cantidad": 3,
                    "precio_unitario_usd": 20,
                    "costo_unitario_usd": 10,
                }
            ],
        )
        self.assertGreater(venta_credito_id, 0)

        with db_transaction() as conn:
            cxc_id = int(
                conn.execute(
                    "SELECT id FROM cuentas_por_cobrar WHERE venta_id=? ORDER BY id DESC LIMIT 1",
                    (venta_credito_id,),
                ).fetchone()["id"]
            )
            abono = registrar_abono_cuenta_por_cobrar(
                conn,
                usuario="qa",
                payload=CobranzaInput(cuenta_por_cobrar_id=cxc_id, monto_usd=30, metodo_pago="efectivo"),
            )
            self.assertEqual(abono["nuevo_estado"], "parcial")

        # 3) compra contado
        registrar_compra(
            usuario="qa",
            inventario_id=inventario_id,
            cantidad=5,
            costo_total_usd=50,
            proveedor_id=proveedor_id,
            proveedor_nombre="Proveedor QA",
            impuestos_pct=0,
            delivery_usd=0,
            tasa_usada=1,
            moneda_pago="USD",
            financial_input=CompraFinancialInput(tipo_pago="contado", monto_pagado_inicial_usd=50),
        )

        # 4) compra crédito + pago
        registrar_compra(
            usuario="qa",
            inventario_id=inventario_id,
            cantidad=10,
            costo_total_usd=100,
            proveedor_id=proveedor_id,
            proveedor_nombre="Proveedor QA",
            impuestos_pct=0,
            delivery_usd=0,
            tasa_usada=1,
            moneda_pago="USD",
            financial_input=CompraFinancialInput(tipo_pago="credito", fecha_vencimiento="2099-12-31"),
        )

        with db_transaction() as conn:
            cxp_id = int(
                conn.execute(
                    "SELECT id FROM cuentas_por_pagar_proveedores ORDER BY id DESC LIMIT 1"
                ).fetchone()["id"]
            )
            pago_id = registrar_pago_cuenta_por_pagar(conn, usuario="qa", cuenta_por_pagar_id=cxp_id, monto_usd=40)
            self.assertGreater(pago_id, 0)
            asiento_pago = conn.execute(
                "SELECT id FROM asientos_contables WHERE evento_tipo='pago_proveedor' AND referencia_tabla='pagos_proveedores' AND referencia_id=?",
                (pago_id,),
            ).fetchone()
            self.assertIsNotNone(asiento_pago)

            # 5) tesorería manual
            ingreso_id = registrar_ingreso(
                conn,
                origen="ajuste_manual",
                referencia_id=98701,
                descripcion="Ingreso ajuste QA",
                monto_usd=12,
                metodo_pago="efectivo",
                usuario="qa",
            )
            egreso_id = registrar_egreso(
                conn,
                origen="ajuste_manual",
                referencia_id=98702,
                descripcion="Egreso ajuste QA",
                monto_usd=7,
                metodo_pago="efectivo",
                usuario="qa",
            )
            self.assertGreater(ingreso_id, 0)
            self.assertGreater(egreso_id, 0)

            # 6) conciliación
            banco_ingreso_id = registrar_movimiento_bancario(
                conn,
                fecha="2026-03-24",
                descripcion="Ingreso banco QA",
                monto=12,
                tipo="ingreso",
                cuenta_bancaria="BANCO-QA",
                usuario="qa",
            )
            conciliacion_id = conciliar_movimientos(
                conn,
                banco_movimiento_id=banco_ingreso_id,
                tesoreria_movimiento_id=ingreso_id,
                usuario="qa",
            )
            self.assertGreater(conciliacion_id, 0)

            # 7) cierre de período
            cierre_id = cerrar_periodo(
                conn,
                periodo="2026-03",
                tipo_cierre="mensual",
                fecha_desde="2026-03-01",
                fecha_hasta="2026-03-31",
                usuario="qa",
                notas="Smoke test cierre",
            )
            self.assertGreater(cierre_id, 0)
            self.assertTrue(periodo_esta_cerrado(conn, fecha_movimiento="2026-03-24", tipo_cierre="mensual"))

        # 8) costeo/rentabilidad
        costo = calcular_costo_servicio(
            tipo_proceso="impresion",
            cantidad=10,
            costo_materiales_usd=45,
            costo_mano_obra_usd=15,
            costo_indirecto_usd=5,
        )
        margen = calcular_margen_estimado(costo_total_usd=costo["costo_total_usd"], margen_pct=30)
        orden_id = guardar_costeo(
            usuario="qa",
            tipo_proceso="impresion",
            descripcion="Orden costeo QA",
            cantidad=10,
            costo_materiales_usd=45,
            costo_mano_obra_usd=15,
            costo_indirecto_usd=5,
            margen_pct=30,
            precio_sugerido_usd=margen["precio_sugerido_usd"],
            estado="borrador",
        )
        self.assertGreater(orden_id, 0)


if __name__ == "__main__":
    unittest.main()
