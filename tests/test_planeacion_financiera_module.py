import pandas as pd

from modules.planeacion_financiera import _records_to_dataframe


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

    export_df = pd.concat(
        [
            pd.DataFrame([{"ingresos_reales_usd": 0.0}]),
            flujo,
            alertas,
        ],
        ignore_index=True,
        sort=False,
    )

    assert len(export_df) == 3
    assert export_df.loc[1, "flujo_proyectado_usd"] == 75.0
