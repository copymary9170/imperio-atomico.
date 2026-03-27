from __future__ import annotations

import unittest
from datetime import date

from services.operacion_industrial_service import OperacionIndustrialService


class OperacionIndustrialServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OperacionIndustrialService()
        self.service.bootstrap()

    def test_rechaza_fecha_ambigua_o_invalida(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_maintenance_order(
                activo_id=1,
                tipo="preventivo",
                estado="pendiente",
                fecha_programada=date(1999, 1, 1),
                tecnico_responsable="Tecnico",
                descripcion="Prueba",
                usuario="qa",
            )

    def test_overview_devuelve_estructura_esperada(self) -> None:
        overview = self.service.get_executive_overview()
        for key in (
            "total_activos",
            "inversion_instalada",
            "backlog_abierto",
            "activos_criticos",
            "proximos_vencimientos",
        ):
            self.assertIn(key, overview)


if __name__ == "__main__":
    unittest.main()
