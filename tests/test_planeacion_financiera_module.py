import pandas as pd

from modules.planeacion_financiera import _concat_for_export, _records_to_dataframe


def test_records_to_dataframe_normalizes_missing_records_with_columns():
    df = _records_to_dataframe(None, ["nivel", "mensaje"])

    assert list(df.columns) == ["nivel", "mensaje"]
    assert df.empty


def test_records_to_dataframe_normalizes_lists_for_concat_exports():
    flujo = _records_to_dataframe(
        [
            {
                "horizonte_dias": 30,
                "saldo_actual_usd": 100.0,
                "flujo_proyectado_usd": 75.0,
            }
        ],
        [
            "horizonte_dias",
            "saldo_actual_usd",
            "cobros_esperados_usd",
            "pagos_proximos_usd",
            "flujo_proyectado_usd",
        ],
    )
    alertas = _records_to_dataframe([{"nivel": "success", "mensaje": "OK"}], ["nivel", "mensaje"])

    export_df = _concat_for_export(
        [
            {"ingresos_reales_usd": 0.0},
            flujo,
            alertas,
        ]
    )

    assert len(export_df) == 3
    assert export_df.loc[1, "flujo_proyectado_usd"] == 75.0


def test_concat_for_export_normalizes_non_dataframe_fragments():
    export_df = _concat_for_export(
        [
            {"ingresos_reales_usd": 125.0},
            [{"nivel": "warning", "mensaje": "Revisar caja"}],
            pd.Series({"comparativo": "base", "variacion_usd": 5.0}),
            None,
            "nota manual",
        ]
    )

    assert len(export_df) == 4
    assert export_df.loc[0, "ingresos_reales_usd"] == 125.0
    assert export_df.loc[1, "mensaje"] == "Revisar caja"
    assert export_df.loc[2, "variacion_usd"] == 5.0
    assert export_df.loc[3, "valor"] == "nota manual"
