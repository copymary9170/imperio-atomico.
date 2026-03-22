from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from modules.configuracion import DEFAULT_CONFIG


CALCULATOR_DEFAULTS = {
    "monto_usd": 100.0,
    "tasa_manual": DEFAULT_CONFIG["tasa_bcv"],
}


def _load_config() -> dict[str, float]:
    config = DEFAULT_CONFIG.copy()

    try:
        with db_transaction() as conn:
            rows = conn.execute("SELECT parametro, valor FROM configuracion").fetchall()

        for row in rows:
            parametro = row["parametro"]
            valor = row["valor"]

            if parametro in config:
                try:
                    config[parametro] = float(valor)
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    return config


def _calcular_resumen(monto_usd: float, tasa_cambio: float, comision_pct: float) -> dict[str, float]:
    comision_usd = monto_usd * (comision_pct / 100)
    neto_usd = monto_usd - comision_usd

    return {
        "monto_usd": monto_usd,
        "comision_pct": comision_pct,
        "comision_usd": comision_usd,
        "neto_usd": neto_usd,
        "monto_bs": monto_usd * tasa_cambio,
        "comision_bs": comision_usd * tasa_cambio,
        "neto_bs": neto_usd * tasa_cambio,
        "tasa_cambio": tasa_cambio,
    }


def render_calculadora(usuario: str):
    del usuario

    config = _load_config()

    st.title("🧮 Calculadora de Comisiones")
    st.caption(
        "Esta vista reemplaza el módulo Kontigo anterior. "
        "Usa los parámetros guardados en Configuración para hacer cálculos rápidos."
    )

    st.info(
        "Configuración y Calculadora no son lo mismo: Configuración guarda tasas y comisiones; "
        "la Calculadora las utiliza para simular montos de entrada y salida."
    )

    tipo_operacion = st.radio(
        "Tipo de operación",
        options=("Entrada", "Salida"),
        horizontal=True,
    )

    tasa_preferida = st.selectbox(
        "Tasa de cambio base",
        options=("BCV", "Binance", "Manual"),
        index=0,
    )

    tasa_sugerida = {
        "BCV": config["tasa_bcv"],
        "Binance": config["tasa_binance"],
        "Manual": CALCULATOR_DEFAULTS["tasa_manual"],
    }[tasa_preferida]

    col1, col2 = st.columns(2)

    monto_usd = col1.number_input(
        "Monto en USD",
        min_value=0.0,
        value=CALCULATOR_DEFAULTS["monto_usd"],
        step=1.0,
        format="%.2f",
    )

    tasa_cambio = col2.number_input(
        "Tasa de cambio (Bs/USD)",
        min_value=0.0,
        value=float(tasa_sugerida),
        step=0.01,
        format="%.2f",
    )

    comision_default = (
        config["kontigo_perc_entrada"] if tipo_operacion == "Entrada" else config["kontigo_perc_salida"]
    )

    col3, col4 = st.columns(2)

    comision_pct = col3.number_input(
        "Comisión aplicada (%)",
        min_value=0.0,
        value=float(comision_default),
        step=0.1,
        format="%.3f",
    )

    saldo_disponible = col4.number_input(
        "Saldo de referencia (USD)",
        min_value=0.0,
        value=float(config["kontigo_saldo"]),
        step=1.0,
        format="%.2f",
    )

    resumen = _calcular_resumen(monto_usd, tasa_cambio, comision_pct)
    saldo_proyectado = saldo_disponible + resumen["neto_usd"] if tipo_operacion == "Entrada" else saldo_disponible - monto_usd

    st.divider()
    met1, met2, met3 = st.columns(3)
    met1.metric("Comisión", f"$ {resumen['comision_usd']:.2f}", f"{resumen['comision_pct']:.3f}%")
    met2.metric("Neto recibido", f"$ {resumen['neto_usd']:.2f}")
    met3.metric("Equivalente neto en Bs", f"Bs {resumen['neto_bs']:.2f}")

    st.subheader("Detalle de cálculo")
    st.dataframe(
        [
            {"Concepto": "Monto base (USD)", "Valor": round(resumen["monto_usd"], 2)},
            {"Concepto": "Tasa usada (Bs/USD)", "Valor": round(resumen["tasa_cambio"], 2)},
            {"Concepto": "Comisión (%)", "Valor": round(resumen["comision_pct"], 3)},
            {"Concepto": "Comisión (USD)", "Valor": round(resumen["comision_usd"], 2)},
            {"Concepto": "Monto neto (USD)", "Valor": round(resumen["neto_usd"], 2)},
            {"Concepto": "Monto base (Bs)", "Valor": round(resumen["monto_bs"], 2)},
            {"Concepto": "Comisión (Bs)", "Valor": round(resumen["comision_bs"], 2)},
            {"Concepto": "Monto neto (Bs)", "Valor": round(resumen["neto_bs"], 2)},
            {"Concepto": "Saldo proyectado luego de la operación (USD)", "Valor": round(saldo_proyectado, 2)},
        ],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Ver parámetros cargados desde Configuración"):
        st.dataframe(
            [
                {"Parámetro": "Tasa BCV", "Valor": round(config["tasa_bcv"], 2)},
                {"Parámetro": "Tasa Binance", "Valor": round(config["tasa_binance"], 2)},
                {"Parámetro": "Comisión Kontigo general", "Valor": round(config["kontigo_perc"], 3)},
                {"Parámetro": "Comisión entrada", "Valor": round(config["kontigo_perc_entrada"], 3)},
                {"Parámetro": "Comisión salida", "Valor": round(config["kontigo_perc_salida"], 3)},
                {"Parámetro": "Saldo registrado", "Valor": round(config["kontigo_saldo"], 2)},
            ],
            use_container_width=True,
            hide_index=True,
        )
