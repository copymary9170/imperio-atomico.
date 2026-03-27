from __future__ import annotations

import unittest

import pandas as pd

from modules.activos import _construir_backlog_mantenimiento, _prioridad_mantenimiento


class ActivosMaintenancePriorityTest(unittest.TestCase):
    def test_prioridad_inmediata_para_componente_critico(self) -> None:
        prioridad, score, accion = _prioridad_mantenimiento(
            {
                "clase_registro": "componente",
                "estado_componente": "Crítico",
                "vida_restante_pct": 12,
                "riesgo": "🟢 Bajo",
            }
        )
        self.assertEqual(prioridad, "🔴 Prioridad inmediata")
        self.assertGreaterEqual(score, 95)
        self.assertIn("Reemplazar", accion)

    def test_backlog_ordenado_por_score_prioridad(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "id": 1,
                    "equipo": "Plotter A",
                    "unidad": "Corte",
                    "clase_registro": "equipo_principal",
                    "clase_registro_label": "Equipo principal",
                    "estado_componente": "Operativo",
                    "vida_restante_pct": 90,
                    "desgaste": 0.2,
                    "riesgo": "🟠 Medio",
                },
                {
                    "id": 2,
                    "equipo": "Cuchilla B",
                    "unidad": "Corte",
                    "clase_registro": "componente",
                    "clase_registro_label": "Componente / Repuesto",
                    "estado_componente": "Crítico",
                    "vida_restante_pct": 8,
                    "desgaste": 0.1,
                    "riesgo": "🟢 Bajo",
                },
            ]
        )

        backlog = _construir_backlog_mantenimiento(df, limite=5)

        self.assertEqual(backlog.iloc[0]["equipo"], "Cuchilla B")
        self.assertIn("prioridad_mantenimiento", backlog.columns)
        self.assertIn("accion_sugerida", backlog.columns)


if __name__ == "__main__":
    unittest.main()
