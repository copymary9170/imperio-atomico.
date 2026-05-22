from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from database.connection import db_transaction

CALCULATOR_DEFAULTS = {
    "monto_usd": 100.0,
    "tasa_manual": 36.50,
}

CONFIG_FALLBACKS = {
    "tasa_bcv": 36.50,
    "tasa_binance": 38.00,
    "kontigo_perc": 5.0,
    "kontigo_perc_entrada": 5.0,
    "kontigo_perc_salida": 5.0,
    "kontigo_saldo": 0.0,
}


def _load_config() -> dict[str, float]:
    config = CONFIG_FALLBACKS.copy()
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


def _tasa_select(config: dict[str, float], key_prefix: str) -> tuple[str, float]:
    fuente = st.selectbox(
        "Tasa de cambio",
        options=("BCV", "Binance", "Manual"),
        index=0,
        key=f"{key_prefix}_fuente_tasa",
    )
    sugerida = {
        "BCV": config["tasa_bcv"],
        "Binance": config["tasa_binance"],
        "Manual": CALCULATOR_DEFAULTS["tasa_manual"],
    }[fuente]
    tasa = st.number_input(
        "Bs/USD",
        min_value=0.0,
        value=float(sugerida),
        step=0.01,
        format="%.2f",
        key=f"{key_prefix}_tasa",
    )
    if tasa <= 0:
        st.warning("La tasa está en 0. El resultado en Bs será 0.")
    return fuente, float(tasa)


def _add_history(tipo: str, datos: dict) -> None:
    item = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tipo": tipo,
        **datos,
    }
    st.session_state.setdefault("calculadora_historial", [])
    st.session_state["calculadora_historial"].insert(0, item)
    st.session_state["calculadora_historial"] = st.session_state["calculadora_historial"][:50]


def _show_result_table(rows: list[dict]) -> None:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _calcular_resumen_comision(monto_usd: float, tasa_cambio: float, comision_pct: float) -> dict[str, float]:
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


def _render_conversion(config: dict[str, float]) -> None:
    st.subheader("💱 Conversión USD / Bs")
    c1, c2, c3 = st.columns(3)
    modo = c1.radio("Convertir", ["USD a Bs", "Bs a USD"], horizontal=True, key="calc_conv_modo")
    with c2:
        _, tasa = _tasa_select(config, "calc_conv")
    monto = c3.number_input("Monto", min_value=0.0, value=100.0, step=1.0, format="%.2f", key="calc_conv_monto")

    if modo == "USD a Bs":
        resultado = monto * tasa
        st.metric("Resultado", f"Bs {resultado:,.2f}")
        datos = {"monto": round(monto, 2), "tasa": round(tasa, 2), "resultado": round(resultado, 2), "modo": modo}
    else:
        resultado = monto / tasa if tasa else 0.0
        st.metric("Resultado", f"$ {resultado:,.2f}")
        datos = {"monto": round(monto, 2), "tasa": round(tasa, 2), "resultado": round(resultado, 2), "modo": modo}
    if st.button("Guardar en historial", key="calc_conv_save", use_container_width=True):
        _add_history("Conversión", datos)
        st.success("Cálculo guardado.")


def _render_comisiones(config: dict[str, float]) -> None:
    st.subheader("💸 Comisiones entrada / salida")
    st.caption("Calculadora original de Kontigo/comisiones. Lee tasas y porcentajes desde Configuración.")
    tipo_operacion = st.radio("Tipo de operación", options=("Entrada", "Salida"), horizontal=True, key="calc_com_tipo")
    c1, c2, c3, c4 = st.columns(4)
    monto_usd = c1.number_input("Monto USD", min_value=0.0, value=CALCULATOR_DEFAULTS["monto_usd"], step=1.0, format="%.2f", key="calc_com_monto")
    with c2:
        _, tasa_cambio = _tasa_select(config, "calc_com")
    comision_default = config["kontigo_perc_entrada"] if tipo_operacion == "Entrada" else config["kontigo_perc_salida"]
    comision_pct = c3.number_input("Comisión (%)", min_value=0.0, value=float(comision_default), step=0.1, format="%.3f", key="calc_com_pct")
    saldo_disponible = c4.number_input("Saldo referencia USD", min_value=0.0, value=float(config["kontigo_saldo"]), step=1.0, format="%.2f", key="calc_com_saldo")

    resumen = _calcular_resumen_comision(monto_usd, tasa_cambio, comision_pct)
    saldo_proyectado = saldo_disponible + resumen["neto_usd"] if tipo_operacion == "Entrada" else saldo_disponible - monto_usd
    if comision_pct > 30:
        st.warning("Comisión mayor a 30%. Revisa si es correcto.")
    if saldo_proyectado < 0:
        st.error("Saldo proyectado negativo.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Comisión", f"$ {resumen['comision_usd']:.2f}", f"{resumen['comision_pct']:.3f}%")
    m2.metric("Neto recibido", f"$ {resumen['neto_usd']:.2f}")
    m3.metric("Neto Bs", f"Bs {resumen['neto_bs']:.2f}")
    m4.metric("Saldo proyectado", f"$ {saldo_proyectado:.2f}")

    rows = [
        {"Concepto": "Monto base USD", "Valor": round(resumen["monto_usd"], 2)},
        {"Concepto": "Tasa Bs/USD", "Valor": round(resumen["tasa_cambio"], 2)},
        {"Concepto": "Comisión %", "Valor": round(resumen["comision_pct"], 3)},
        {"Concepto": "Comisión USD", "Valor": round(resumen["comision_usd"], 2)},
        {"Concepto": "Neto USD", "Valor": round(resumen["neto_usd"], 2)},
        {"Concepto": "Neto Bs", "Valor": round(resumen["neto_bs"], 2)},
        {"Concepto": "Saldo proyectado USD", "Valor": round(saldo_proyectado, 2)},
    ]
    _show_result_table(rows)
    if st.button("Guardar comisión en historial", key="calc_com_save", use_container_width=True):
        _add_history("Comisión", {"operación": tipo_operacion, "monto_usd": round(monto_usd, 2), "comisión_pct": round(comision_pct, 3), "neto_usd": round(resumen["neto_usd"], 2), "saldo_proyectado": round(saldo_proyectado, 2)})
        st.success("Cálculo guardado.")


def _render_margen_precio() -> None:
    st.subheader("📈 Margen y precio rápido")
    c1, c2, c3 = st.columns(3)
    costo = c1.number_input("Costo", min_value=0.0, value=10.0, step=1.0, format="%.2f", key="calc_marg_costo")
    margen_pct = c2.number_input("Margen deseado (%)", min_value=-100.0, value=50.0, step=1.0, format="%.2f", key="calc_marg_pct")
    redondeo = c3.number_input("Redondeo", min_value=0.0, value=0.05, step=0.05, format="%.2f", key="calc_marg_redondeo")
    precio = costo * (1 + margen_pct / 100)
    if redondeo > 0:
        precio = round(precio / redondeo) * redondeo
    utilidad = precio - costo
    margen_real = (utilidad / precio * 100) if precio else 0.0
    if precio < costo:
        st.error("Precio final menor al costo.")
    if margen_real < 0:
        st.error("Margen negativo.")
    m1, m2, m3 = st.columns(3)
    m1.metric("Precio sugerido", f"$ {precio:,.2f}")
    m2.metric("Utilidad", f"$ {utilidad:,.2f}")
    m3.metric("Margen sobre venta", f"{margen_real:,.2f}%")
    _show_result_table([
        {"Concepto": "Costo", "Valor": round(costo, 2)},
        {"Concepto": "Margen deseado %", "Valor": round(margen_pct, 2)},
        {"Concepto": "Precio sugerido", "Valor": round(precio, 2)},
        {"Concepto": "Utilidad", "Valor": round(utilidad, 2)},
        {"Concepto": "Margen sobre venta %", "Valor": round(margen_real, 2)},
    ])
    if st.button("Guardar margen en historial", key="calc_marg_save", use_container_width=True):
        _add_history("Margen/precio", {"costo": round(costo, 2), "precio": round(precio, 2), "utilidad": round(utilidad, 2), "margen_venta_pct": round(margen_real, 2)})
        st.success("Cálculo guardado.")


def _render_impuestos_descuentos() -> None:
    st.subheader("🧾 IVA / impuesto / descuento")
    c1, c2, c3 = st.columns(3)
    subtotal = c1.number_input("Subtotal", min_value=0.0, value=100.0, step=1.0, format="%.2f", key="calc_imp_subtotal")
    descuento_pct = c2.number_input("Descuento (%)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="calc_imp_desc")
    impuesto_pct = c3.number_input("Impuesto (%)", min_value=0.0, value=16.0, step=1.0, format="%.2f", key="calc_imp_pct")
    descuento = subtotal * descuento_pct / 100
    base = subtotal - descuento
    impuesto = base * impuesto_pct / 100
    total = base + impuesto
    m1, m2, m3 = st.columns(3)
    m1.metric("Descuento", f"$ {descuento:,.2f}")
    m2.metric("Impuesto", f"$ {impuesto:,.2f}")
    m3.metric("Total", f"$ {total:,.2f}")
    _show_result_table([
        {"Concepto": "Subtotal", "Valor": round(subtotal, 2)},
        {"Concepto": "Descuento", "Valor": round(descuento, 2)},
        {"Concepto": "Base imponible", "Valor": round(base, 2)},
        {"Concepto": "Impuesto", "Valor": round(impuesto, 2)},
        {"Concepto": "Total", "Valor": round(total, 2)},
    ])
    if st.button("Guardar impuesto/descuento en historial", key="calc_imp_save", use_container_width=True):
        _add_history("IVA/descuento", {"subtotal": round(subtotal, 2), "descuento": round(descuento, 2), "impuesto": round(impuesto, 2), "total": round(total, 2)})
        st.success("Cálculo guardado.")


def _render_cantidad_precio() -> None:
    st.subheader("📦 Cantidad × precio unitario")
    c1, c2, c3 = st.columns(3)
    cantidad = c1.number_input("Cantidad", min_value=0.0, value=10.0, step=1.0, format="%.2f", key="calc_qty_cantidad")
    precio_unitario = c2.number_input("Precio unitario", min_value=0.0, value=5.0, step=1.0, format="%.2f", key="calc_qty_precio")
    descuento_pct = c3.number_input("Descuento (%)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="calc_qty_desc")
    bruto = cantidad * precio_unitario
    descuento = bruto * descuento_pct / 100
    total = bruto - descuento
    st.metric("Total", f"$ {total:,.2f}")
    _show_result_table([
        {"Concepto": "Cantidad", "Valor": round(cantidad, 2)},
        {"Concepto": "Precio unitario", "Valor": round(precio_unitario, 2)},
        {"Concepto": "Bruto", "Valor": round(bruto, 2)},
        {"Concepto": "Descuento", "Valor": round(descuento, 2)},
        {"Concepto": "Total", "Valor": round(total, 2)},
    ])
    if st.button("Guardar cantidad/precio en historial", key="calc_qty_save", use_container_width=True):
        _add_history("Cantidad x precio", {"cantidad": round(cantidad, 2), "precio_unitario": round(precio_unitario, 2), "total": round(total, 2)})
        st.success("Cálculo guardado.")


def _render_impresion_rapida() -> None:
    st.subheader("🖨️ Costo rápido de impresión")
    st.caption("Estimación manual rápida. Para análisis real de tinta por archivo usa Producción → Impresiones / CMYK.")
    c1, c2, c3, c4 = st.columns(4)
    paginas = c1.number_input("Páginas", min_value=0, value=10, step=1, key="calc_print_paginas")
    costo_tinta = c2.number_input("Tinta por página", min_value=0.0, value=0.05, step=0.01, format="%.4f", key="calc_print_tinta")
    costo_papel = c3.number_input("Papel por página", min_value=0.0, value=0.03, step=0.01, format="%.4f", key="calc_print_papel")
    desgaste = c4.number_input("Desgaste por página", min_value=0.0, value=0.02, step=0.01, format="%.4f", key="calc_print_desgaste")
    margen_pct = st.slider("Margen sugerido (%)", 0, 300, 60, 1, key="calc_print_margen")
    costo_unitario = costo_tinta + costo_papel + desgaste
    costo_total = costo_unitario * paginas
    precio = costo_total * (1 + margen_pct / 100)
    utilidad = precio - costo_total
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Costo unitario", f"$ {costo_unitario:.4f}")
    m2.metric("Costo total", f"$ {costo_total:.2f}")
    m3.metric("Precio sugerido", f"$ {precio:.2f}")
    m4.metric("Utilidad", f"$ {utilidad:.2f}")
    if st.button("Guardar impresión rápida en historial", key="calc_print_save", use_container_width=True):
        _add_history("Impresión rápida", {"páginas": paginas, "costo_total": round(costo_total, 2), "precio": round(precio, 2), "utilidad": round(utilidad, 2)})
        st.success("Cálculo guardado.")


def _render_historial() -> None:
    st.subheader("📋 Historial de cálculos")
    hist = st.session_state.get("calculadora_historial", [])
    if not hist:
        st.info("No hay cálculos guardados en esta sesión.")
        return
    df = pd.DataFrame(hist)
    st.dataframe(df, use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Descargar historial CSV", data=df.to_csv(index=False).encode("utf-8-sig"), file_name="historial_calculadora.csv", mime="text/csv", use_container_width=True)
    if c2.button("Limpiar historial", use_container_width=True, key="calc_hist_clear"):
        st.session_state["calculadora_historial"] = []
        st.success("Historial limpiado.")
        st.rerun()


def _render_parametros(config: dict[str, float]) -> None:
    with st.expander("⚙️ Parámetros cargados desde Configuración", expanded=False):
        st.dataframe([
            {"Parámetro": "Tasa BCV", "Valor": round(config["tasa_bcv"], 2)},
            {"Parámetro": "Tasa Binance", "Valor": round(config["tasa_binance"], 2)},
            {"Parámetro": "Comisión Kontigo general", "Valor": round(config["kontigo_perc"], 3)},
            {"Parámetro": "Comisión entrada", "Valor": round(config["kontigo_perc_entrada"], 3)},
            {"Parámetro": "Comisión salida", "Valor": round(config["kontigo_perc_salida"], 3)},
            {"Parámetro": "Saldo registrado", "Valor": round(config["kontigo_saldo"], 2)},
        ], use_container_width=True, hide_index=True)


def render_calculadora(usuario: str):
    del usuario
    config = _load_config()
    st.title("🧮 Calculadora")
    st.caption("Utilidades rápidas para tasas, comisiones, márgenes, impuestos, cantidades e impresión. No reemplaza Costeo, Finanzas ni CMYK.")

    secciones = {
        "💱 Conversión USD/Bs": lambda: _render_conversion(config),
        "💸 Comisiones": lambda: _render_comisiones(config),
        "📈 Margen / precio": _render_margen_precio,
        "🧾 IVA / descuento": _render_impuestos_descuentos,
        "📦 Cantidad × precio": _render_cantidad_precio,
        "🖨️ Impresión rápida": _render_impresion_rapida,
        "📋 Historial": _render_historial,
    }
    seccion = st.radio("Herramienta", list(secciones.keys()), horizontal=True, key="calc_seccion_activa")
    st.divider()
    secciones[seccion]()
    _render_parametros(config)
