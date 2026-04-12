om __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission


# =========================================================
# Configuración base
# =========================================================

DEFAULT_CONFIG: Dict[str, Any] = {
    # Tasas
    "tasa_bcv": 36.50,
    "tasa_binance": 38.00,

    # Costos / impresión
    "costo_tinta_ml": 0.10,
    "costo_tinta_auto": 1.0,
    "factor_desperdicio_cmyk": 1.15,
    "desgaste_cabezal_ml": 0.005,
    "costo_bajada_plancha": 0.03,
    "costo_limpieza_cabezal": 0.02,
    "margen_impresion": 30.0,
    "costo_kwh": 0.10,
    "recargo_urgente_pct": 0.0,

    # Impuestos y comisiones
    "iva_perc": 16.0,
    "igtf_perc": 3.0,
    "banco_perc": 0.5,
    "kontigo_perc": 5.0,
    "kontigo_perc_entrada": 5.0,
    "kontigo_perc_salida": 5.0,
    "kontigo_saldo": 0.0,

    # Empresa / ERP general
    "empresa_nombre": "Mi Empresa",
    "empresa_rif": "",
    "empresa_direccion": "",
    "empresa_telefono": "",
    "empresa_email": "",
    "moneda_base": "USD",
    "zona_horaria": "America/Caracas",

    # Inventario
    "inventario_permitir_stock_negativo": 0.0,
    "inventario_stock_minimo_default": 0.0,
    "inventario_metodo_costeo": "PROMEDIO",

    # Ventas / cotizaciones
    "cotizacion_vigencia_dias": 7.0,
    "ventas_descuento_max_perc": 20.0,
    "ventas_aprobar_descuento_mayor": 1.0,

    # Producción
    "produccion_merma_tolerancia_perc": 5.0,
    "produccion_reproceso_permitido": 1.0,

    # Finanzas
    "finanzas_redondeo_monto": 2.0,
}


CONFIG_SECTIONS: Dict[str, List[str]] = {
    "empresa": [
        "empresa_nombre",
        "empresa_rif",
        "empresa_direccion",
        "empresa_telefono",
        "empresa_email",
        "moneda_base",
        "zona_horaria",
    ],
    "tasas": [
        "tasa_bcv",
        "tasa_binance",
    ],
    "costos": [
        "costo_tinta_ml",
        "costo_tinta_auto",
        "factor_desperdicio_cmyk",
        "desgaste_cabezal_ml",
        "costo_bajada_plancha",
        "costo_limpieza_cabezal",
        "margen_impresion",
        "costo_kwh",
        "recargo_urgente_pct",
    ],
    "impuestos": [
        "iva_perc",
        "igtf_perc",
        "banco_perc",
        "kontigo_perc",
        "kontigo_perc_entrada",
        "kontigo_perc_salida",
        "kontigo_saldo",
    ],
    "inventario": [
        "inventario_permitir_stock_negativo",
        "inventario_stock_minimo_default",
        "inventario_metodo_costeo",
    ],
    "ventas": [
        "cotizacion_vigencia_dias",
        "ventas_descuento_max_perc",
        "ventas_aprobar_descuento_mayor",
    ],
    "produccion": [
        "produccion_merma_tolerancia_perc",
        "produccion_reproceso_permitido",
    ],
    "finanzas": [
        "finanzas_redondeo_monto",
    ],
}


READONLY_RATE_FIELDS: List[Tuple[str, str, str, str]] = [
    ("tasa_bcv", "Tasa BCV", "Bs/$", "%.2f"),
    ("tasa_binance", "Tasa Binance", "Bs/$", "%.2f"),
    ("iva_perc", "IVA", "%", "%.2f"),
    ("igtf_perc", "IGTF", "%", "%.2f"),
    ("banco_perc", "Comisión bancaria", "%", "%.3f"),
    ("kontigo_perc", "Comisión Kontigo", "%", "%.3f"),
    ("kontigo_perc_entrada", "Kontigo entrada", "%", "%.3f"),
    ("kontigo_perc_salida", "Kontigo salida", "%", "%.3f"),
    ("kontigo_saldo", "Saldo Kontigo", "$", "%.2f"),
]


# =========================================================
# Inicialización / compatibilidad DB
# =========================================================

def ensure_config_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracion (
                parametro TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parametro TEXT NOT NULL,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario TEXT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        for param, default_value in DEFAULT_CONFIG.items():
            exists = conn.execute(
                "SELECT 1 FROM configuracion WHERE parametro = ?",
                (param,),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO configuracion (parametro, valor) VALUES (?, ?)",
                    (param, str(default_value)),
                )


# =========================================================
# Helpers de conversión
# =========================================================

def _to_float(config: Dict[str, object], key: str, default: float) -> float:
    try:
        value = config.get(key, default)
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_int(config: Dict[str, object], key: str, default: int) -> int:
    try:
        value = config.get(key, default)
        if value in (None, ""):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _to_bool(config: Dict[str, object], key: str, default: bool) -> bool:
    raw_default = 1 if default else 0
    return bool(_to_int(config, key, raw_default))


def _to_str(config: Dict[str, object], key: str, default: str) -> str:
    try:
        value = config.get(key, default)
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


# =========================================================
# Lectura / escritura configuración
# =========================================================

def get_current_config() -> Dict[str, object]:
    ensure_config_tables()

    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT parametro, valor
            FROM configuracion
            """
        ).fetchall()

    config = {r["parametro"]: r["valor"] for r in rows}

    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)

    return config


def set_config_values(values: Dict[str, Any], usuario: str) -> None:
    ensure_config_tables()

    with db_transaction() as conn:
        for param, nuevo_valor in values.items():
            old_row = conn.execute(
                "SELECT valor FROM configuracion WHERE parametro = ?",
                (param,),
            ).fetchone()

            valor_anterior = old_row["valor"] if old_row and old_row["valor"] is not None else None
            valor_nuevo_str = str(nuevo_valor)

            conn.execute(
                """
                INSERT OR REPLACE INTO configuracion (parametro, valor)
                VALUES (?, ?)
                """,
                (param, valor_nuevo_str),
            )

            if valor_anterior != valor_nuevo_str:
                conn.execute(
                    """
                    INSERT INTO historial_config (parametro, valor_anterior, valor_nuevo, usuario)
                    VALUES (?, ?, ?, ?)
                    """,
                    (param, valor_anterior, valor_nuevo_str, usuario),
                )


# =========================================================
# Resumen / tablas
# =========================================================

def build_rates_dataframe(config: Dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Concepto": label,
                "Valor": _to_float(config, key, float(DEFAULT_CONFIG[key]))
                if isinstance(DEFAULT_CONFIG[key], (int, float))
                else config.get(key, DEFAULT_CONFIG[key]),
                "Unidad": unit,
            }
            for key, label, unit, _fmt in READONLY_RATE_FIELDS
        ]
    )


def build_full_config_dataframe(config: Dict[str, object]) -> pd.DataFrame:
    rows = []

    for section, keys in CONFIG_SECTIONS.items():
        for key in keys:
            default = DEFAULT_CONFIG.get(key, "")
            if isinstance(default, float):
                value = _to_float(config, key, default)
            elif isinstance(default, int):
                value = _to_int(config, key, default)
            else:
                value = config.get(key, default)

            rows.append(
                {
                    "Sección": section,
                    "Parámetro": key,
                    "Valor": value,
                }
            )

    return pd.DataFrame(rows)


def render_rates_overview(config: Dict[str, object]) -> None:
    st.caption("Vista rápida de las tasas, impuestos y comisiones activas del sistema.")

    for start in range(0, len(READONLY_RATE_FIELDS), 3):
        columns = st.columns(3)
        for column, (key, label, unit, fmt) in zip(columns, READONLY_RATE_FIELDS[start : start + 3]):
            value = _to_float(config, key, float(DEFAULT_CONFIG[key]))
            prefix = "$ " if unit == "$" else ""
            suffix = "" if unit == "$" else f" {unit}"
            column.metric(label, f"{prefix}{fmt % value}{suffix}")

    st.dataframe(build_rates_dataframe(config), use_container_width=True, hide_index=True)


def render_sidebar_config_snapshot() -> None:
    try:
        config = get_current_config()
    except Exception:
        st.sidebar.warning("No se pudo cargar el resumen de configuración.")
        return

    with st.sidebar.expander("👀 Configuración activa", expanded=False):
        st.caption("Resumen rápido de tasas y comisiones definidas en Configuración.")

        snapshot_fields = [
            ("tasa_bcv", "BCV", "Bs/$", "%.2f"),
            ("tasa_binance", "Binance", "Bs/$", "%.2f"),
            ("iva_perc", "IVA", "%", "%.2f"),
            ("igtf_perc", "IGTF", "%", "%.2f"),
            ("banco_perc", "Banco", "%", "%.3f"),
            ("kontigo_perc", "Kontigo", "%", "%.3f"),
        ]

        for key, label, unit, fmt in snapshot_fields:
            value = _to_float(config, key, float(DEFAULT_CONFIG[key]))
            st.sidebar.metric(label, f"{fmt % value} {unit}")


# =========================================================
# Integración inventario
# =========================================================

def _detectar_costo_tinta() -> Optional[float]:
    try:
        with db_transaction() as conn:
            df_tintas = pd.read_sql_query(
                """
                SELECT costo_unitario_usd
                FROM inventario
                WHERE estado = 'activo'
                  AND lower(nombre) LIKE '%tinta%'
                  AND lower(trim(unidad)) = 'ml'
                  AND costo_unitario_usd > 0
                """,
                conn,
            )

        if df_tintas.empty:
            return None

        return float(df_tintas["costo_unitario_usd"].mean())
    except Exception:
        return None


# =========================================================
# Validaciones
# =========================================================

def _validar_config(values: Dict[str, Any]) -> List[str]:
    errores: List[str] = []

    def rango(nombre: str, minimo: float | None = None, maximo: float | None = None) -> None:
        valor = values.get(nombre)
        try:
            v = float(valor)
        except Exception:
            errores.append(f"El parámetro '{nombre}' no tiene un valor válido.")
            return

        if minimo is not None and v < minimo:
            errores.append(f"'{nombre}' no puede ser menor que {minimo}.")
        if maximo is not None and v > maximo:
            errores.append(f"'{nombre}' no puede ser mayor que {maximo}.")

    rango("tasa_bcv", 0.0001, None)
    rango("tasa_binance", 0.0001, None)
    rango("costo_tinta_ml", 0.0, None)
    rango("margen_impresion", 0.0, 1000.0)
    rango("costo_kwh", 0.0, None)
    rango("factor_desperdicio_cmyk", 1.0, 10.0)
    rango("desgaste_cabezal_ml", 0.0, None)
    rango("costo_bajada_plancha", 0.0, None)
    rango("costo_limpieza_cabezal", 0.0, None)
    rango("iva_perc", 0.0, 100.0)
    rango("igtf_perc", 0.0, 100.0)
    rango("banco_perc", 0.0, 100.0)
    rango("kontigo_perc", 0.0, 100.0)
    rango("kontigo_perc_entrada", 0.0, 100.0)
    rango("kontigo_perc_salida", 0.0, 100.0)
    rango("kontigo_saldo", 0.0, None)
    rango("recargo_urgente_pct", 0.0, 100.0)
    rango("inventario_stock_minimo_default", 0.0, None)
    rango("cotizacion_vigencia_dias", 1.0, 365.0)
    rango("ventas_descuento_max_perc", 0.0, 100.0)
    rango("produccion_merma_tolerancia_perc", 0.0, 100.0)
    rango("finanzas_redondeo_monto", 0.0, 6.0)

    metodo_costeo = str(values.get("inventario_metodo_costeo", "PROMEDIO")).upper()
    if metodo_costeo not in {"PROMEDIO", "FIFO", "MANUAL"}:
        errores.append("El método de costeo debe ser PROMEDIO, FIFO o MANUAL.")

    moneda_base = str(values.get("moneda_base", "USD")).upper()
    if moneda_base not in {"USD", "VES", "EUR"}:
        errores.append("La moneda base debe ser USD, VES o EUR.")

    return errores


# =========================================================
# UI principal
# =========================================================

def render_configuracion(usuario: str) -> None:
    if not require_permission("config.view", "🚫 No tienes acceso al módulo Configuración."):
        return

    ensure_config_tables()
    puede_editar = has_permission("config.edit")

    st.subheader("⚙️ Configuración del Sistema")
    st.info("Estos parámetros afectan cotizaciones, costos, inventario, producción y análisis financieros.")

    if not puede_editar:
        st.warning("Tienes permisos de solo lectura en Configuración.")

    try:
        config = get_current_config()
    except Exception as e:
        st.error("Error cargando configuración.")
        st.exception(e)
        return

    costo_tinta_detectado = _detectar_costo_tinta()

    with st.form("config_general"):
        st.subheader("🏢 Empresa")
        e1, e2, e3 = st.columns(3)
        empresa_nombre = e1.text_input(
            "Nombre empresa",
            value=_to_str(config, "empresa_nombre", DEFAULT_CONFIG["empresa_nombre"]),
            disabled=not puede_editar,
        )
        empresa_rif = e2.text_input(
            "RIF",
            value=_to_str(config, "empresa_rif", DEFAULT_CONFIG["empresa_rif"]),
            disabled=not puede_editar,
        )
        empresa_telefono = e3.text_input(
            "Teléfono",
            value=_to_str(config, "empresa_telefono", DEFAULT_CONFIG["empresa_telefono"]),
            disabled=not puede_editar,
        )

        e4, e5, e6 = st.columns(3)
        empresa_email = e4.text_input(
            "Email",
            value=_to_str(config, "empresa_email", DEFAULT_CONFIG["empresa_email"]),
            disabled=not puede_editar,
        )
        moneda_options = ["USD", "VES", "EUR"]
        moneda_actual = _to_str(config, "moneda_base", "USD")
        moneda_base = e5.selectbox(
            "Moneda base",
            moneda_options,
            index=moneda_options.index(moneda_actual) if moneda_actual in moneda_options else 0,
            disabled=not puede_editar,
        )
        zona_horaria = e6.text_input(
            "Zona horaria",
            value=_to_str(config, "zona_horaria", DEFAULT_CONFIG["zona_horaria"]),
            disabled=not puede_editar,
        )

        empresa_direccion = st.text_area(
            "Dirección fiscal",
            value=_to_str(config, "empresa_direccion", DEFAULT_CONFIG["empresa_direccion"]),
            disabled=not puede_editar,
        )

        st.divider()

        st.subheader("💵 Tasas")
        c1, c2 = st.columns(2)

        tasa_bcv = c1.number_input(
            "Tasa BCV (Bs/$)",
            min_value=0.0001,
            value=_to_float(config, "tasa_bcv", DEFAULT_CONFIG["tasa_bcv"]),
            format="%.2f",
            disabled=not puede_editar,
        )

        tasa_binance = c2.number_input(
            "Tasa Binance (Bs/$)",
            min_value=0.0001,
            value=_to_float(config, "tasa_binance", DEFAULT_CONFIG["tasa_binance"]),
            format="%.2f",
            disabled=not puede_editar,
        )

        st.divider()

        st.subheader("🎨 Costos / Producción")

        costo_tinta_auto = st.checkbox(
            "Calcular costo tinta desde inventario",
            value=_to_bool(config, "costo_tinta_auto", True),
            disabled=not puede_editar,
        )

        if costo_tinta_auto:
            if costo_tinta_detectado is not None:
                costo_tinta_ml = float(costo_tinta_detectado)
                st.success(f"Costo de tinta detectado: $ {costo_tinta_ml:.4f} / ml")
            else:
                costo_tinta_ml = _to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"])
                st.warning("No hay tintas válidas en inventario. Se mantiene el último valor guardado.")
        else:
            costo_tinta_ml = st.number_input(
                "Costo de tinta por ml ($)",
                min_value=0.0,
                value=_to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"]),
                step=0.0001,
                format="%.4f",
                disabled=not puede_editar,
            )

        c3, c4, c5 = st.columns(3)
        margen = c3.number_input(
            "Margen de ganancia (%)",
            min_value=0.0,
            value=_to_float(config, "margen_impresion", DEFAULT_CONFIG["margen_impresion"]),
            format="%.2f",
            disabled=not puede_editar,
        )
        costo_kwh = c4.number_input(
            "Costo electricidad kWh ($)",
            min_value=0.0,
            value=_to_float(config, "costo_kwh", DEFAULT_CONFIG["costo_kwh"]),
            format="%.4f",
            disabled=not puede_editar,
        )
        factor_desperdicio = c5.number_input(
            "Factor desperdicio CMYK",
            min_value=1.0,
            value=_to_float(config, "factor_desperdicio_cmyk", DEFAULT_CONFIG["factor_desperdicio_cmyk"]),
            format="%.3f",
            disabled=not puede_editar,
        )

        c6, c7, c8 = st.columns(3)
        desgaste_cabezal = c6.number_input(
            "Desgaste cabezal por ml ($)",
            min_value=0.0,
            value=_to_float(config, "desgaste_cabezal_ml", DEFAULT_CONFIG["desgaste_cabezal_ml"]),
            format="%.4f",
            disabled=not puede_editar,
        )
        costo_bajada = c7.number_input(
            "Bajada de plancha ($/u)",
            min_value=0.0,
            value=_to_float(config, "costo_bajada_plancha", DEFAULT_CONFIG["costo_bajada_plancha"]),
            format="%.3f",
            disabled=not puede_editar,
        )
        costo_limpieza = c8.number_input(
            "Limpieza cabezal por trabajo ($)",
            min_value=0.0,
            value=_to_float(config, "costo_limpieza_cabezal", DEFAULT_CONFIG["costo_limpieza_cabezal"]),
            format="%.3f",
            disabled=not puede_editar,
        )

        c9, c10 = st.columns(2)
        urgencia_options = [0.0, 25.0, 50.0]
        urgencia_actual = _to_float(config, "recargo_urgente_pct", DEFAULT_CONFIG["recargo_urgente_pct"])
        recargo_urgente = c9.selectbox(
            "Recargo urgencia global (%)",
            urgencia_options,
            index=urgencia_options.index(urgencia_actual) if urgencia_actual in urgencia_options else 0,
            disabled=not puede_editar,
        )
        produccion_merma_tolerancia_perc = c10.number_input(
            "Tolerancia merma producción (%)",
            min_value=0.0,
            value=_to_float(config, "produccion_merma_tolerancia_perc", DEFAULT_CONFIG["produccion_merma_tolerancia_perc"]),
            format="%.2f",
            disabled=not puede_editar,
        )

        produccion_reproceso_permitido = st.checkbox(
            "Permitir reproceso en producción",
            value=_to_bool(config, "produccion_reproceso_permitido", True),
            disabled=not puede_editar,
        )

        st.divider()

        st.subheader("🛡️ Impuestos y Comisiones")

        p1, p2, p3, p4, p5 = st.columns(5)
        iva_perc = p1.number_input(
            "IVA (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "iva_perc", DEFAULT_CONFIG["iva_perc"]),
            format="%.2f",
            disabled=not puede_editar,
        )
        igtf_perc = p2.number_input(
            "IGTF (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "igtf_perc", DEFAULT_CONFIG["igtf_perc"]),
            format="%.2f",
            disabled=not puede_editar,
        )
        banco_perc = p3.number_input(
            "Comisión bancaria (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "banco_perc", DEFAULT_CONFIG["banco_perc"]),
            format="%.3f",
            disabled=not puede_editar,
        )
        kontigo_perc = p4.number_input(
            "Comisión Kontigo (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"]),
            format="%.3f",
            disabled=not puede_editar,
        )
        finanzas_redondeo_monto = p5.number_input(
            "Redondeo montos (decimales)",
            min_value=0.0,
            max_value=6.0,
            value=_to_float(config, "finanzas_redondeo_monto", DEFAULT_CONFIG["finanzas_redondeo_monto"]),
            format="%.0f",
            disabled=not puede_editar,
        )

        p6, p7, p8 = st.columns(3)
        kontigo_entrada = p6.number_input(
            "Kontigo entrada (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "kontigo_perc_entrada", _to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"])),
            format="%.3f",
            disabled=not puede_editar,
        )
        kontigo_salida = p7.number_input(
            "Kontigo salida (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "kontigo_perc_salida", _to_float(config, "kontigo_perc", DEFAULT_CONFIG["kontigo_perc"])),
            format="%.3f",
            disabled=not puede_editar,
        )
        kontigo_saldo = p8.number_input(
            "Saldo cuenta Kontigo ($)",
            min_value=0.0,
            value=_to_float(config, "kontigo_saldo", DEFAULT_CONFIG["kontigo_saldo"]),
            format="%.2f",
            disabled=not puede_editar,
        )

        st.divider()

        st.subheader("📦 Inventario")
        i1, i2, i3 = st.columns(3)

        inventario_permitir_stock_negativo = i1.checkbox(
            "Permitir stock negativo",
            value=_to_bool(config, "inventario_permitir_stock_negativo", False),
            disabled=not puede_editar,
        )
        inventario_stock_minimo_default = i2.number_input(
            "Stock mínimo por defecto",
            min_value=0.0,
            value=_to_float(config, "inventario_stock_minimo_default", DEFAULT_CONFIG["inventario_stock_minimo_default"]),
            format="%.2f",
            disabled=not puede_editar,
        )
        metodo_costeo_actual = _to_str(config, "inventario_metodo_costeo", "PROMEDIO").upper()
        inventario_metodo_costeo = i3.selectbox(
            "Método de costeo",
            ["PROMEDIO", "FIFO", "MANUAL"],
            index=["PROMEDIO", "FIFO", "MANUAL"].index(metodo_costeo_actual) if metodo_costeo_actual in ["PROMEDIO", "FIFO", "MANUAL"] else 0,
            disabled=not puede_editar,
        )

        st.divider()

        st.subheader("💰 Ventas / Cotizaciones")
        v1, v2, v3 = st.columns(3)

        cotizacion_vigencia_dias = v1.number_input(
            "Vigencia cotización (días)",
            min_value=1.0,
            max_value=365.0,
            value=_to_float(config, "cotizacion_vigencia_dias", DEFAULT_CONFIG["cotizacion_vigencia_dias"]),
            format="%.0f",
            disabled=not puede_editar,
        )
        ventas_descuento_max_perc = v2.number_input(
            "Descuento máximo (%)",
            min_value=0.0,
            max_value=100.0,
            value=_to_float(config, "ventas_descuento_max_perc", DEFAULT_CONFIG["ventas_descuento_max_perc"]),
            format="%.2f",
            disabled=not puede_editar,
        )
        ventas_aprobar_descuento_mayor = v3.checkbox(
            "Exigir aprobación para descuentos altos",
            value=_to_bool(config, "ventas_aprobar_descuento_mayor", True),
            disabled=not puede_editar,
        )

        guardar = st.form_submit_button(
            "💾 Guardar cambios",
            disabled=not puede_editar,
        )

    if guardar:
        actualizaciones: Dict[str, Any] = {
            "empresa_nombre": empresa_nombre.strip(),
            "empresa_rif": empresa_rif.strip(),
            "empresa_direccion": empresa_direccion.strip(),
            "empresa_telefono": empresa_telefono.strip(),
            "empresa_email": empresa_email.strip(),
            "moneda_base": moneda_base,
            "zona_horaria": zona_horaria.strip(),

            "tasa_bcv": tasa_bcv,
            "tasa_binance": tasa_binance,

            "costo_tinta_ml": costo_tinta_ml,
            "costo_tinta_auto": 1 if costo_tinta_auto else 0,
            "margen_impresion": margen,
            "costo_kwh": costo_kwh,
            "factor_desperdicio_cmyk": factor_desperdicio,
            "desgaste_cabezal_ml": desgaste_cabezal,
            "costo_bajada_plancha": costo_bajada,
            "costo_limpieza_cabezal": costo_limpieza,
            "recargo_urgente_pct": recargo_urgente,
            "produccion_merma_tolerancia_perc": produccion_merma_tolerancia_perc,
            "produccion_reproceso_permitido": 1 if produccion_reproceso_permitido else 0,

            "iva_perc": iva_perc,
            "igtf_perc": igtf_perc,
            "banco_perc": banco_perc,
            "kontigo_perc": kontigo_perc,
            "kontigo_perc_entrada": kontigo_entrada,
            "kontigo_perc_salida": kontigo_salida,
            "kontigo_saldo": kontigo_saldo,
            "finanzas_redondeo_monto": int(finanzas_redondeo_monto),

            "inventario_permitir_stock_negativo": 1 if inventario_permitir_stock_negativo else 0,
            "inventario_stock_minimo_default": inventario_stock_minimo_default,
            "inventario_metodo_costeo": inventario_metodo_costeo,

            "cotizacion_vigencia_dias": int(cotizacion_vigencia_dias),
            "ventas_descuento_max_perc": ventas_descuento_max_perc,
            "ventas_aprobar_descuento_mayor": 1 if ventas_aprobar_descuento_mayor else 0,
        }

        errores = _validar_config(actualizaciones)
        if errores:
            st.error("No se pudo guardar la configuración. Revisa estos puntos:")
            for err in errores:
                st.write(f"- {err}")
            return

        try:
            set_config_values(actualizaciones, usuario)

            for key, value in actualizaciones.items():
                st.session_state[key] = value

            st.success("✅ Configuración actualizada y registrada en historial.")
            st.rerun()

        except Exception as e:
            st.error("Error guardando configuración.")
            st.exception(e)

    st.divider()
    st.subheader("📋 Tabla de control")

    try:
        config = get_current_config()
        tabla_cfg = build_rates_dataframe(config)
        tabla_cfg.loc[len(tabla_cfg)] = {
            "Concepto": "Costo Tinta por ml",
            "Valor": _to_float(config, "costo_tinta_ml", DEFAULT_CONFIG["costo_tinta_ml"]),
            "Unidad": "$/ml",
        }
        st.dataframe(tabla_cfg, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning("No se pudo construir la tabla de control.")
        st.exception(e)

    with st.expander("🧾 Ver configuración completa"):
        try:
            config_full = get_current_config()
            df_full = build_full_config_dataframe(config_full)
            st.dataframe(df_full, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning("No se pudo cargar la configuración completa.")
            st.exception(e)

    with st.expander("📜 Ver historial de cambios"):
        try:
            with db_transaction() as conn:
                historial = pd.read_sql_query(
                    """
                    SELECT fecha, parametro, valor_anterior, valor_nuevo, usuario
                    FROM historial_config
                    ORDER BY id DESC
                    LIMIT 100
                    """,
                    conn,
                )

            if historial.empty:
                st.info("Aún no hay cambios registrados.")
            else:
                st.dataframe(historial, use_container_width=True, hide_index=True)
        except Exception:
            st.info("Historial aún no disponible.")
