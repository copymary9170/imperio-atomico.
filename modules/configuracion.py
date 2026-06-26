from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_permission
from services.backup_service import create_backup, get_backup_status
from services.persistent_config_service import save_persistent_rates

DEFAULT_CONFIG: Dict[str, Any] = {
    "tasa_bcv": 36.50,
    "tasa_binance": 38.00,
    "tasa_euro": 40.00,
    "tasa_menudeo": 38.00,
    "tasa_kontigo": 38.00,
    "tasa_kontigo_entrada": 38.00,
    "tasa_kontigo_salida": 38.00,
    "banco_perc": 0.5,
    "kontigo_perc": 5.0,
    "kontigo_perc_entrada": 5.0,
    "kontigo_perc_salida": 5.0,
    "kontigo_pago_movil_envio_perc": 0.0,
    "kontigo_tarjeta_envio_perc": 0.0,
    "kontigo_tarjeta_envio_fija_usd": 0.0,
    "menudeo_comision_perc": 0.0,
    "menudeo_comision_fija_usd": 0.0,
    "menudeo_minimo_usd": 0.0,
    "costo_tinta_ml": 0.10,
    "costo_tinta_auto": 1.0,
    "factor_desperdicio_cmyk": 1.15,
    "desgaste_cabezal_ml": 0.005,
    "costo_bajada_plancha": 0.03,
    "costo_limpieza_cabezal": 0.02,
    "margen_impresion": 30.0,
    "costo_kwh": 0.10,
    "recargo_urgente_pct": 0.0,
    "empresa_nombre": "Mi Empresa",
    "empresa_rif": "",
    "empresa_direccion": "",
    "empresa_telefono": "",
    "empresa_email": "",
    "moneda_base": "USD",
    "zona_horaria": "America/Caracas",
    "inventario_permitir_stock_negativo": 0.0,
    "inventario_stock_minimo_default": 0.0,
    "inventario_metodo_costeo": "PROMEDIO",
    "cotizacion_vigencia_dias": 7.0,
    "ventas_descuento_max_perc": 20.0,
    "ventas_aprobar_descuento_mayor": 1.0,
    "produccion_merma_tolerancia_perc": 5.0,
    "produccion_reproceso_permitido": 1.0,
    "finanzas_redondeo_monto": 2.0,
}

RATE_FIELDS = [
    ("tasa_bcv", "BCV", "Bs/$", 2),
    ("tasa_binance", "Binance", "Bs/$", 2),
    ("tasa_euro", "Euro", "Bs/€", 2),
    ("tasa_menudeo", "Menudeo", "Bs/$", 2),
    ("tasa_kontigo_entrada", "Kontigo entrada", "Bs/$", 2),
    ("tasa_kontigo_salida", "Kontigo salida", "Bs/$", 2),
]

FEE_FIELDS = [
    ("banco_perc", "Comisión bancaria", "%", 3),
    ("kontigo_perc", "Kontigo general", "%", 3),
    ("kontigo_perc_entrada", "Kontigo comisión entrada", "%", 3),
    ("kontigo_perc_salida", "Kontigo comisión salida", "%", 3),
    ("kontigo_pago_movil_envio_perc", "Pago móvil → Kontigo", "%", 3),
    ("kontigo_tarjeta_envio_perc", "Kontigo → tarjeta", "%", 3),
    ("kontigo_tarjeta_envio_fija_usd", "Cargo fijo tarjeta", "$", 2),
    ("menudeo_comision_perc", "Comisión menudeo", "%", 3),
    ("menudeo_comision_fija_usd", "Cargo fijo menudeo", "$", 2),
    ("menudeo_minimo_usd", "Mínimo menudeo", "$", 2),
]
RATE_HISTORY_KEYS = tuple(k for k, *_ in RATE_FIELDS + FEE_FIELDS)


def ensure_config_tables() -> None:
    with db_transaction() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS configuracion (parametro TEXT PRIMARY KEY, valor TEXT)")
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
        for key, value in DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT INTO configuracion (parametro, valor) VALUES (?, ?) ON CONFLICT(parametro) DO NOTHING",
                (key, str(value)),
            )


def get_current_config() -> Dict[str, object]:
    ensure_config_tables()
    with db_transaction() as conn:
        rows = conn.execute("SELECT parametro, valor FROM configuracion").fetchall()
    config = {row["parametro"]: row["valor"] for row in rows}
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, value)
    return config


def set_config_values(values: Dict[str, Any], usuario: str) -> None:
    ensure_config_tables()
    with db_transaction() as conn:
        for key, value in values.items():
            old = conn.execute("SELECT valor FROM configuracion WHERE parametro=?", (key,)).fetchone()
            old_value = old["valor"] if old else None
            new_value = str(value)
            conn.execute(
                "INSERT INTO configuracion (parametro, valor) VALUES (?, ?) ON CONFLICT(parametro) DO UPDATE SET valor=excluded.valor",
                (key, new_value),
            )
            if old_value != new_value:
                conn.execute(
                    "INSERT INTO historial_config (parametro, valor_anterior, valor_nuevo, usuario) VALUES (?, ?, ?, ?)",
                    (key, old_value, new_value, usuario),
                )


def _to_float(config: Dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = config.get(key, default)
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _number_value(config: Dict[str, object], key: str, default: float, minimum: float) -> float:
    value = _to_float(config, key, default)
    return max(value, minimum)


def _to_bool(config: Dict[str, object], key: str, default: bool = False) -> bool:
    try:
        return bool(int(float(config.get(key, 1 if default else 0))))
    except Exception:
        return default


def _to_str(config: Dict[str, object], key: str, default: str = "") -> str:
    value = config.get(key, default)
    return default if value is None else str(value)


def _table_exists(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _detectar_costo_tinta() -> Optional[float]:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "inventario"):
                return None
            df = pd.read_sql_query(
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
        return None if df.empty else float(df["costo_unitario_usd"].mean())
    except Exception:
        return None


def _ultima_actualizacion(parametro: str) -> str:
    try:
        with db_transaction() as conn:
            row = conn.execute(
                "SELECT fecha FROM historial_config WHERE parametro=? ORDER BY fecha DESC LIMIT 1",
                (parametro,),
            ).fetchone()
        return str(row["fecha"]) if row else "Sin historial"
    except Exception:
        return "Sin historial"


def _horas_desde(fecha: str) -> Optional[float]:
    if not fecha or fecha == "Sin historial":
        return None
    try:
        dt = datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return max((datetime.now() - dt).total_seconds() / 3600, 0.0)
    except Exception:
        return None


def _historial_tasas(limit: int = 100) -> pd.DataFrame:
    try:
        placeholders = ",".join("?" for _ in RATE_HISTORY_KEYS)
        with db_transaction() as conn:
            return pd.read_sql_query(
                f"SELECT parametro, valor_anterior, valor_nuevo, usuario, fecha FROM historial_config WHERE parametro IN ({placeholders}) ORDER BY fecha DESC LIMIT ?",
                conn,
                params=(*RATE_HISTORY_KEYS, limit),
            )
    except Exception:
        return pd.DataFrame()


def _validar(values: Dict[str, Any]) -> List[str]:
    errores: List[str] = []
    for key, *_ in RATE_FIELDS:
        if float(values.get(key, 0) or 0) <= 0:
            errores.append(f"{key} debe ser mayor que cero.")
    for key, *_ in FEE_FIELDS:
        value = float(values.get(key, 0) or 0)
        if value < 0:
            errores.append(f"{key} no puede ser negativo.")
        if key.endswith("_perc") and value > 100:
            errores.append(f"{key} debe estar entre 0 y 100.")
    if float(values.get("factor_desperdicio_cmyk", 1) or 1) < 1:
        errores.append("El factor de desperdicio CMYK no puede ser menor que 1.")
    return errores


def _guardar(values: Dict[str, Any], usuario: str) -> None:
    errores = _validar({k: v for k, v in values.items() if k in DEFAULT_CONFIG})
    if errores:
        for error in errores:
            st.error(error)
        return
    set_config_values(values, usuario)
    ok_persist, persist_msg = save_persistent_rates(values)
    try:
        backup = create_backup("cambio_configuracion", upload_external=True)
        backup_msg = f" Respaldo: {backup.name}." if backup else " No se detectó base para respaldo."
    except Exception as exc:
        backup_msg = f" El respaldo falló: {exc}"
    if ok_persist:
        st.success(f"Configuración guardada y persistida. {persist_msg}.{backup_msg}")
    else:
        st.warning(f"Configuración guardada. Persistencia externa: {persist_msg}.{backup_msg}")


def _render_estado_general() -> None:
    st.subheader("🩺 Estado general")
    try:
        status = get_backup_status()
    except Exception as exc:
        st.warning(f"No se pudo consultar el estado de respaldos: {exc}")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Base de datos", "Detectada" if status.get("db_exists") else "No detectada")
    c2.metric("Respaldos locales", status.get("total_backups", 0))
    c3.metric("GitHub Backup", "Configurado" if status.get("github_configured") else "No configurado")
    c4.metric("Último respaldo", status.get("last_backup_at", "Nunca"))
    st.caption(f"Ruta: {status.get('db_path', 'No detectada')}")
    if st.button("💾 Probar respaldo ahora", use_container_width=True):
        try:
            backup = create_backup("prueba_configuracion", upload_external=True)
            st.success(f"Respaldo creado: {backup.name}") if backup else st.error("No se detectó la base de datos.")
        except Exception as exc:
            st.error(f"No se pudo crear el respaldo: {exc}")


def _render_tasas(usuario: str, puede_editar: bool) -> None:
    st.subheader("💱 Tasas y comisiones")
    st.caption("IVA e IGTF fueron retirados. Aquí solo se administran tasas, comisiones operativas y mínimos.")
    config = get_current_config()

    cols = st.columns(3)
    for idx, (key, label, unit, decimals) in enumerate(RATE_FIELDS):
        value = _number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0001)
        fecha = _ultima_actualizacion(key)
        horas = _horas_desde(fecha)
        help_text = "Sin historial" if horas is None else f"Actualizada hace {horas:.1f} h"
        cols[idx % 3].metric(label, f"{value:.{decimals}f} {unit}", help_text)

    with st.form("config_tasas_avanzadas"):
        st.markdown("##### Tasas de cambio")
        values: Dict[str, Any] = {}
        rate_cols = st.columns(3)
        for idx, (key, label, unit, decimals) in enumerate(RATE_FIELDS):
            values[key] = rate_cols[idx % 3].number_input(
                f"{label} ({unit})",
                min_value=0.0001,
                value=_number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0001),
                step=0.01,
                format=f"%.{decimals}f",
                disabled=not puede_editar,
                key=f"rate_{key}",
            )
        st.markdown("##### Comisiones operativas")
        fee_cols = st.columns(3)
        for idx, (key, label, unit, decimals) in enumerate(FEE_FIELDS):
            values[key] = fee_cols[idx % 3].number_input(
                f"{label} ({unit})",
                min_value=0.0,
                value=_number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0),
                step=0.01 if decimals <= 2 else 0.001,
                format=f"%.{decimals}f",
                disabled=not puede_editar,
                key=f"fee_{key}",
            )
        if st.form_submit_button("💾 Guardar tasas y comisiones", disabled=not puede_editar):
            values["tasa_kontigo"] = values["tasa_kontigo_entrada"]
            _guardar(values, usuario)

    st.markdown("##### Simulador de ruta Kontigo")
    s1, s2 = st.columns(2)
    ruta = s1.selectbox("Ruta", ["Efectivo USD → Kontigo", "Pago móvil Bs → Kontigo", "Kontigo → tarjeta"])
    monto = s2.number_input("Monto", min_value=0.0, step=1.0, format="%.2f")
    entrada = _number_value(config, "tasa_kontigo_entrada", 38.0, 0.0001)
    salida = _number_value(config, "tasa_kontigo_salida", 38.0, 0.0001)
    if ruta == "Efectivo USD → Kontigo":
        bruto = monto
        tasa = entrada
        comision = bruto * _to_float(config, "kontigo_perc_entrada", 0.0) / 100
    elif ruta == "Pago móvil Bs → Kontigo":
        tasa = entrada
        bruto = monto / tasa
        comision = bruto * (_to_float(config, "kontigo_pago_movil_envio_perc", 0.0) + _to_float(config, "kontigo_perc_entrada", 0.0)) / 100
    else:
        bruto = monto
        tasa = salida
        comision = bruto * _to_float(config, "kontigo_tarjeta_envio_perc", 0.0) / 100 + _to_float(config, "kontigo_tarjeta_envio_fija_usd", 0.0)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Tasa usada", f"{tasa:,.2f} Bs/$")
    r2.metric("Bruto", f"$ {bruto:,.2f}")
    r3.metric("Comisiones", f"$ {comision:,.2f}")
    r4.metric("Neto estimado", f"$ {max(bruto - comision, 0):,.2f}")

    with st.expander("📜 Historial de tasas y comisiones"):
        history = _historial_tasas()
        st.info("Todavía no hay cambios registrados.") if history.empty else st.dataframe(history, use_container_width=True, hide_index=True)


def _render_config_general(usuario: str, puede_editar: bool) -> None:
    config = get_current_config()
    tinta_detectada = _detectar_costo_tinta()
    with st.form("config_general"):
        st.subheader("🏢 Empresa")
        e1, e2, e3 = st.columns(3)
        empresa_nombre = e1.text_input("Nombre empresa", _to_str(config, "empresa_nombre", "Mi Empresa"), disabled=not puede_editar)
        empresa_rif = e2.text_input("RIF", _to_str(config, "empresa_rif"), disabled=not puede_editar)
        empresa_telefono = e3.text_input("Teléfono", _to_str(config, "empresa_telefono"), disabled=not puede_editar)
        e4, e5, e6 = st.columns(3)
        empresa_email = e4.text_input("Email", _to_str(config, "empresa_email"), disabled=not puede_editar)
        monedas = ["USD", "VES", "EUR"]
        moneda_actual = _to_str(config, "moneda_base", "USD")
        moneda = e5.selectbox("Moneda base", monedas, index=monedas.index(moneda_actual) if moneda_actual in monedas else 0, disabled=not puede_editar)
        zona = e6.text_input("Zona horaria", _to_str(config, "zona_horaria", "America/Caracas"), disabled=not puede_editar)
        direccion = st.text_area("Dirección fiscal", _to_str(config, "empresa_direccion"), disabled=not puede_editar)

        st.divider()
        st.subheader("🎨 Costos / Producción")
        costo_auto = st.checkbox("Calcular costo de tinta desde inventario", _to_bool(config, "costo_tinta_auto", True), disabled=not puede_editar)
        if costo_auto and tinta_detectada is not None:
            costo_tinta = tinta_detectada
            st.success(f"Costo detectado: $ {costo_tinta:.4f}/ml")
        else:
            costo_tinta = st.number_input("Costo tinta por ml ($)", min_value=0.0, value=_number_value(config, "costo_tinta_ml", 0.10, 0.0), format="%.4f", disabled=not puede_editar)
            if costo_auto:
                st.warning("No hay tintas válidas en inventario; se mantiene el valor manual.")
        c1, c2, c3 = st.columns(3)
        margen = c1.number_input("Margen de ganancia (%)", min_value=0.0, value=_number_value(config, "margen_impresion", 30.0, 0.0), disabled=not puede_editar)
        kwh = c2.number_input("Costo electricidad kWh ($)", min_value=0.0, value=_number_value(config, "costo_kwh", 0.10, 0.0), format="%.4f", disabled=not puede_editar)
        desperdicio = c3.number_input("Factor desperdicio CMYK", min_value=1.0, value=_number_value(config, "factor_desperdicio_cmyk", 1.15, 1.0), format="%.3f", disabled=not puede_editar)
        c4, c5, c6 = st.columns(3)
        desgaste = c4.number_input("Desgaste cabezal por ml ($)", min_value=0.0, value=_number_value(config, "desgaste_cabezal_ml", 0.005, 0.0), format="%.4f", disabled=not puede_editar)
        bajada = c5.number_input("Bajada de plancha ($/u)", min_value=0.0, value=_number_value(config, "costo_bajada_plancha", 0.03, 0.0), format="%.3f", disabled=not puede_editar)
        limpieza = c6.number_input("Limpieza cabezal por trabajo ($)", min_value=0.0, value=_number_value(config, "costo_limpieza_cabezal", 0.02, 0.0), format="%.3f", disabled=not puede_editar)
        c7, c8 = st.columns(2)
        urgencia = c7.number_input("Recargo urgencia global (%)", min_value=0.0, max_value=100.0, value=_number_value(config, "recargo_urgente_pct", 0.0, 0.0), disabled=not puede_editar)
        merma = c8.number_input("Tolerancia merma producción (%)", min_value=0.0, max_value=100.0, value=_number_value(config, "produccion_merma_tolerancia_perc", 5.0, 0.0), disabled=not puede_editar)
        reproceso = st.checkbox("Permitir reproceso en producción", _to_bool(config, "produccion_reproceso_permitido", True), disabled=not puede_editar)

        st.divider()
        st.subheader("📦 Inventario")
        i1, i2, i3 = st.columns(3)
        stock_negativo = i1.checkbox("Permitir stock negativo", _to_bool(config, "inventario_permitir_stock_negativo"), disabled=not puede_editar)
        stock_minimo = i2.number_input("Stock mínimo por defecto", min_value=0.0, value=_number_value(config, "inventario_stock_minimo_default", 0.0, 0.0), disabled=not puede_editar)
        metodos = ["PROMEDIO", "FIFO", "MANUAL"]
        metodo_actual = _to_str(config, "inventario_metodo_costeo", "PROMEDIO").upper()
        metodo = i3.selectbox("Método de costeo", metodos, index=metodos.index(metodo_actual) if metodo_actual in metodos else 0, disabled=not puede_editar)

        st.divider()
        st.subheader("💰 Ventas / Cotizaciones")
        v1, v2, v3 = st.columns(3)
        vigencia = v1.number_input("Vigencia cotización (días)", min_value=1.0, max_value=365.0, value=_number_value(config, "cotizacion_vigencia_dias", 7.0, 1.0), disabled=not puede_editar)
        descuento = v2.number_input("Descuento máximo (%)", min_value=0.0, max_value=100.0, value=_number_value(config, "ventas_descuento_max_perc", 20.0, 0.0), disabled=not puede_editar)
        aprobar = v3.checkbox("Exigir aprobación para descuentos altos", _to_bool(config, "ventas_aprobar_descuento_mayor", True), disabled=not puede_editar)
        redondeo = st.number_input("Redondeo financiero (decimales)", min_value=0.0, max_value=6.0, value=min(_number_value(config, "finanzas_redondeo_monto", 2.0, 0.0), 6.0), format="%.0f", disabled=not puede_editar)

        if st.form_submit_button("💾 Guardar configuración general", disabled=not puede_editar):
            _guardar({
                "empresa_nombre": empresa_nombre,
                "empresa_rif": empresa_rif,
                "empresa_telefono": empresa_telefono,
                "empresa_email": empresa_email,
                "empresa_direccion": direccion,
                "moneda_base": moneda,
                "zona_horaria": zona,
                "costo_tinta_auto": 1.0 if costo_auto else 0.0,
                "costo_tinta_ml": costo_tinta,
                "margen_impresion": margen,
                "costo_kwh": kwh,
                "factor_desperdicio_cmyk": desperdicio,
                "desgaste_cabezal_ml": desgaste,
                "costo_bajada_plancha": bajada,
                "costo_limpieza_cabezal": limpieza,
                "recargo_urgente_pct": urgencia,
                "produccion_merma_tolerancia_perc": merma,
                "produccion_reproceso_permitido": 1.0 if reproceso else 0.0,
                "inventario_permitir_stock_negativo": 1.0 if stock_negativo else 0.0,
                "inventario_stock_minimo_default": stock_minimo,
                "inventario_metodo_costeo": metodo,
                "cotizacion_vigencia_dias": vigencia,
                "ventas_descuento_max_perc": descuento,
                "ventas_aprobar_descuento_mayor": 1.0 if aprobar else 0.0,
                "finanzas_redondeo_monto": redondeo,
            }, usuario)


def render_rates_overview(config: Dict[str, object]) -> None:
    rows = []
    for key, label, unit, decimals in RATE_FIELDS + FEE_FIELDS[:4]:
        rows.append({"Concepto": label, "Valor": round(_number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0), decimals), "Unidad": unit})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def build_rates_dataframe(config: Dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame([{"Concepto": label, "Valor": _number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0), "Unidad": unit} for key, label, unit, _ in RATE_FIELDS + FEE_FIELDS])


def build_full_config_dataframe(config: Dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame([{"Parámetro": key, "Valor": config.get(key, value)} for key, value in DEFAULT_CONFIG.items()])


def render_sidebar_config_snapshot() -> None:
    try:
        config = get_current_config()
    except Exception:
        st.sidebar.warning("No se pudo cargar la configuración.")
        return
    with st.sidebar.expander("👀 Configuración activa", expanded=False):
        for key, label, unit, decimals in RATE_FIELDS:
            st.metric(label, f"{_number_value(config, key, float(DEFAULT_CONFIG[key]), 0.0001):.{decimals}f} {unit}")


def render_configuracion(usuario: str) -> None:
    if not require_permission("config.view", "🚫 No tienes acceso al módulo Configuración."):
        return
    ensure_config_tables()
    puede_editar = has_permission("config.edit")
    st.subheader("⚙️ Configuración del Sistema")
    st.info("Administra empresa, tasas, comisiones, costos, inventario, producción, ventas y respaldos.")
    if not puede_editar:
        st.warning("Tienes permisos de solo lectura.")
    tab_estado, tab_tasas, tab_general = st.tabs(["🩺 Estado y respaldos", "💱 Tasas y comisiones", "⚙️ Configuración general"])
    with tab_estado:
        _render_estado_general()
    with tab_tasas:
        _render_tasas(usuario, puede_editar)
    with tab_general:
        _render_config_general(usuario, puede_editar)
