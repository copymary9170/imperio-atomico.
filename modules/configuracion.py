from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


ALLOWED_CONFIG_ROLES = {"Admin", "Administration", "Administracion"}


DEFAULT_CONFIG = {
    "tasa_bcv": 36.5,
    "tasa_binance": 38.0,
    "costo_tinta_ml": 0.10,
    "costo_tinta_auto": 1.0,
    "iva_perc": 16.0,
    "igtf_perc": 3.0,
    "banco_perc": 0.5,
    "kontigo_perc": 5.0,
    "kontigo_perc_entrada": 5.0,
    "kontigo_perc_salida": 5.0,
    "kontigo_saldo": 0.0,
    "factor_desperdicio_cmyk": 1.15,
    "desgaste_cabezal_ml": 0.005,
    "costo_bajada_plancha": 0.03,
    "recargo_urgente_pct": 0.0,
    "costo_limpieza_cabezal": 0.02,
    "margen_impresion": 30.0,
    "costo_kwh": 0.10,
}


def _to_float(config: dict[str, object], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except Exception:
        return default


def _detectar_costo_tinta() -> float | None:
    try:
        with db_transaction() as conn:
            df_tintas = pd.read_sql_query(
                """
                SELECT costo_unitario_usd
                FROM inventario
                WHERE estado='activo'
                  AND lower(nombre) LIKE '%tinta%'
                  AND lower(trim(unidad))='ml'
                  AND costo_unitario_usd > 0
                """,
                conn,
            )

        if df_tintas.empty:
            return None

        return float(df_tintas["costo_unitario_usd"].mean())
    except Exception:
        return None


def render_configuracion(usuario: str):
    role = st.session_state.get("rol", "Admin")
    if role not in ALLOWED_CONFIG_ROLES:
        st.error("🚫 Acceso denegado. Solo Admin/Administración puede modificar configuración.")
        return

    st.subheader("⚙️ Configuración del Sistema")
    st.info("Estos parámetros afectan cotizaciones, costos operativos y análisis financieros.")

    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT parametro, valor
                FROM configuracion
                """
            ).fetchall()

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS historial_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parametro TEXT NOT NULL,
                    valor_anterior REAL,
                    valor_nuevo REAL,
                    usuario TEXT,
                    fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        config = {r["parametro"]: r["valor"] for r in rows}
    except Exception as e:
        st.error("Error cargando configuración")
        st.exception(e)
        return

    costo_tinta_detectado = _detectar_costo_tinta()

    with st.form("config_general"):
        st.subheader("💵 Tasas")
        c1, c2 = st.columns(2)

        tasa_bcv = c1.number_input(
            "Tasa BCV (Bs/$)",
            value=_to_float(config, "tasa_bcv", DEFAULT_CONFIG["tasa_bcv"]),
            format="%.2f",
        )

        tasa_binance = c2.number_input(
            "Tasa Binance (Bs/$)",
            value=_to_float(config, "tasa_binance", DEFAULT_CONFIG["tasa_binance"]),
            format="%.2f",
        )

        st.divider()
        st.subheader("🎨 Costos")

        costo_tinta_auto = st.checkbox(
            "Calcular costo tinta desde inventario",
            value=bool(_to_float(config, "costo_tinta_auto", DEFAULT_CONFIG["costo_tinta_auto"])),
        )

        if costo_tinta_auto:
            if costo_tinta_detectado is not None:
                costo_tinta_ml = float(costo_tinta_detectado)
                st.success(f"Costo de tinta detectado: $ {costo_tinta_ml:.4f} / ml")
            else:
                costo_tinta_ml = _to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"])
                st.warning("No hay tintas válidas en inventario, se mantiene el último valor guardado.")
        else:
            costo_tinta_ml = st.number_input(
                "Costo de tinta por ml ($)",
                value=_to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"]),
                step=0.0001,
                format="%.4f",
            )

        c3, c4, c5 = st.columns(3)
        margen = c3.number_input(
            "Margen de ganancia (%)",
            value=_to_float(config, "margen_impresion", DEFAULT_CONFIG["margen_impresion"]),
            format="%.2f",
        )
        costo_kwh = c4.number_input(
            "Costo electricidad kWh ($)",
            value=_to_float(config, "costo_kwh", DEFAULT_CONFIG["costo_kwh"]),
            format="%.4f",
        )
        factor_desperdicio = c5.number_input(
            "Factor desperdicio CMYK",
            value=_to_float(config, "factor_desperdicio_cmyk", DEFAULT_CONFIG["factor_desperdicio_cmyk"]),
            format="%.3f",
        )

        c6, c7, c8 = st.columns(3)
        desgaste_cabezal = c6.number_input(
            "Desgaste cabezal por ml ($)",
            value=_to_float(config, "desgaste_cabezal_ml", DEFAULT_CONFIG["desgaste_cabezal_ml"]),
            format="%.4f",
        )
        costo_bajada = c7.number_input(
            "Bajada de plancha ($/u)",
            value=_to_float(config, "costo_bajada_plancha", DEFAULT_CONFIG["costo_bajada_plancha"]),
            format="%.3f",
        )
        costo_limpieza = c8.number_input(
            "Limpieza cabezal por trabajo ($)",
            value=_to_float(config, "costo_limpieza_cabezal", DEFAULT_CONFIG["costo_limpieza_cabezal"]),
            format="%.3f",
        )

        st.divider()
        st.subheader("🛡️ Impuestos y Comisiones")

        p1, p2, p3, p4, p5 = st.columns(5)
        iva_perc = p1.number_input("IVA (%)", value=_to_float(config, "iva_perc", DEFAULT_CONFIG["iva_perc"]), format="%.2f")
        igtf_perc = p2.number_input("IGTF (%)", value=_to_float(config, "igtf_perc", DEFAULT_CONFIG["igtf_perc"]), format="%.2f")
        banco_perc = p3.number_input("Comisión bancaria (%)", value=_to_float(config, "banco_perc", DEFAULT_CONFIG["banco_perc"]), format="%.3f")
        kontigo_perc = p4.number_input("Comisión Kontigo (%)", value=_to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"]), format="%.3f")
        recargo_urgente = p5.selectbox(
            "Recargo urgencia global (%)",
            [0.0, 25.0, 50.0],
            index=[0.0, 25.0, 50.0].index(_to_float(config, "recargo_urgente_pct", DEFAULT_CONFIG["recargo_urgente_pct"]))
            if _to_float(config, "recargo_urgente_pct", DEFAULT_CONFIG["recargo_urgente_pct"]) in [0.0, 25.0, 50.0]
            else 0,
        )

        p6, p7, p8 = st.columns(3)
        kontigo_entrada = p6.number_input(
            "Kontigo entrada (%)",
            value=_to_float(config, "kontigo_perc_entrada", _to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"])),
            format="%.3f",
        )
        kontigo_salida = p7.number_input(
            "Kontigo salida (%)",
            value=_to_float(config, "kontigo_perc_salida", _to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"])),
            format="%.3f",
        )
        kontigo_saldo = p8.number_input(
            "Saldo cuenta Kontigo ($)",
            value=_to_float(config, "kontigo_saldo", DEFAULT_CONFIG["kontigo_saldo"]),
            format="%.2f",
        )

        guardar = st.form_submit_button("💾 Guardar cambios")

    if guardar:
        actualizaciones = {
            "tasa_bcv": tasa_bcv,
            "tasa_binance": tasa_binance,
            "costo_tinta_ml": costo_tinta_ml,
            "costo_tinta_auto": 1.0 if costo_tinta_auto else 0.0,
            "margen_impresion": margen,
            "costo_kwh": costo_kwh,
            "iva_perc": iva_perc,
            "igtf_perc": igtf_perc,
            "banco_perc": banco_perc,
            "kontigo_perc": kontigo_perc,
            "kontigo_perc_entrada": kontigo_entrada,
            "kontigo_perc_salida": kontigo_salida,
            "kontigo_saldo": kontigo_saldo,
            "factor_desperdicio_cmyk": factor_desperdicio,
            "desgaste_cabezal_ml": desgaste_cabezal,
            "costo_bajada_plancha": costo_bajada,
            "recargo_urgente_pct": recargo_urgente,
            "costo_limpieza_cabezal": costo_limpieza,
        }

        try:
            with db_transaction() as conn:
                for param, nuevo_valor in actualizaciones.items():
                    old_row = conn.execute(
                        "SELECT valor FROM configuracion WHERE parametro=?",
                        (param,),
                    ).fetchone()
                    valor_anterior = float(old_row["valor"]) if old_row and old_row["valor"] is not None else None

                    conn.execute(
                        "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES (?, ?)",
                        (param, str(nuevo_valor)),
                    )

                    if valor_anterior != float(nuevo_valor):
                        conn.execute(
                            """
                            INSERT INTO historial_config (parametro, valor_anterior, valor_nuevo, usuario)
                            VALUES (?, ?, ?, ?)
                            """,
                            (param, valor_anterior, float(nuevo_valor), usuario),
                        )

            for key, value in actualizaciones.items():
                st.session_state[key] = value

            st.success("✅ Configuración actualizada y registrada en historial")
            st.rerun()

        except Exception as e:
            st.error("Error guardando configuración")
            st.exception(e)

    st.divider()
    st.subheader("📋 Tabla de control")

    tabla_cfg = pd.DataFrame(
        [
            {"Concepto": "Tasa BCV (Bs/$)", "Valor": _to_float(config, "tasa_bcv", DEFAULT_CONFIG["tasa_bcv"])},
            {"Concepto": "Tasa Binance (Bs/$)", "Valor": _to_float(config, "tasa_binance", DEFAULT_CONFIG["tasa_binance"])},
            {"Concepto": "IVA (%)", "Valor": _to_float(config, "iva_perc", DEFAULT_CONFIG["iva_perc"])},
            {"Concepto": "IGTF (%)", "Valor": _to_float(config, "igtf_perc", DEFAULT_CONFIG["igtf_perc"])},
            {"Concepto": "Comisión Bancaria (%)", "Valor": _to_float(config, "banco_perc", DEFAULT_CONFIG["banco_perc"])},
            {"Concepto": "Comisión Kontigo (%)", "Valor": _to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"])},
            {"Concepto": "Kontigo Entrada (%)", "Valor": _to_float(config, "kontigo_perc_entrada", DEFAULT_CONFIG["kontigo_perc_entrada"])},
            {"Concepto": "Kontigo Salida (%)", "Valor": _to_float(config, "kontigo_perc_salida", DEFAULT_CONFIG["kontigo_perc_salida"])},
            {"Concepto": "Saldo Cuenta Kontigo ($)", "Valor": _to_float(config, "kontigo_saldo", DEFAULT_CONFIG["kontigo_saldo"])},
            {"Concepto": "Costo Tinta por ml ($)", "Valor": _to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"])},
        ]
    )
    st.dataframe(tabla_cfg, use_container_width=True, hide_index=True)

    with st.expander("📜 Ver historial de cambios"):
        try:
            with db_transaction() as conn:
                historial = pd.read_sql_query(
                    """
                    SELECT fecha, parametro, valor_anterior, valor_nuevo, usuario
                    FROM historial_config
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    conn,
                )

            if historial.empty:
                st.info("Aún no hay cambios registrados.")
            else:
                st.dataframe(historial, use_container_width=True, hide_index=True)
        except Exception:
            st.info("Historial aún no disponible.")
