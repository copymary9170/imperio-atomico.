from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, require_text
from modules.configuracion import DEFAULT_CONFIG, get_current_config
from utils.currency import convert_to_bs, convert_to_usd


CATEGORIAS_GASTO = [
    "Materia Prima",
    "Mantenimiento de Equipos",
    "Servicios (Luz/Internet)",
    "Publicidad",
    "Sueldos/Retiros",
    "Logística",
    "Otros",
]

METODOS_GASTO = [
    "efectivo",
    "transferencia",
    "pago móvil",
    "zelle",
    "binance",
    "kontigo",
]

PERIODICIDADES_GASTO = {
    "Único": {"dias": None, "factor_mensual": 1.0, "descripcion": "Se registra solo una vez."},
    "Semanal": {"dias": 7, "factor_mensual": 30 / 7, "descripcion": "Se convierte a equivalente mensual usando 30/7."},
    "Cada 15 días": {"dias": 15, "factor_mensual": 2.0, "descripcion": "Se multiplica por 2 para estimar el mes."},
    "Mensual": {"dias": 30, "factor_mensual": 1.0, "descripcion": "Ya corresponde a un ciclo mensual."},
    "Bimestral": {"dias": 60, "factor_mensual": 0.5, "descripcion": "Se divide entre 2 para el equivalente mensual."},
    "Trimestral": {"dias": 90, "factor_mensual": 1 / 3, "descripcion": "Se divide entre 3 para el equivalente mensual."},
}

MONEDAS_GASTO = ["USD", "BS", "USDT", "KONTIGO"]


# ============================================================
# HELPERS
# ============================================================

def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_config_snapshot() -> dict[str, object]:
    try:
        return get_current_config()
    except Exception:
        return {}


def _resolve_rate_for_currency(moneda: str, config: dict[str, object] | None = None) -> float:
    cfg = config or _load_config_snapshot()
    tasa_bcv = _to_float(cfg.get("tasa_bcv"), DEFAULT_CONFIG["tasa_bcv"])
    tasa_binance = _to_float(cfg.get("tasa_binance"), DEFAULT_CONFIG["tasa_binance"])

    moneda_normalizada = str(moneda or "USD").upper().strip()
    if moneda_normalizada in {"USDT", "KONTIGO"}:
        return tasa_binance
    return tasa_bcv


def _resolve_rate(moneda: str, metodo_pago: str, config: dict[str, object] | None = None) -> float:
    cfg = config or _load_config_snapshot()
    metodo_normalizado = str(metodo_pago or "").strip().lower()

    if metodo_normalizado in {"binance", "kontigo"}:
        return _to_float(cfg.get("tasa_binance"), DEFAULT_CONFIG["tasa_binance"])

    return _resolve_rate_for_currency(moneda, cfg)


def _suggest_tax_flags(metodo_pago: str) -> dict[str, bool]:
    metodo_normalizado = str(metodo_pago or "").strip().lower()
    return {
        "iva": False,
        "igtf": False,
        "banco": metodo_normalizado in {"transferencia", "pago móvil"},
        "kontigo": metodo_normalizado == "kontigo",
    }


def _build_tax_breakdown(
    config: dict[str, object],
    aplicar_iva: bool,
    aplicar_igtf: bool,
    aplicar_banco: bool,
    aplicar_kontigo: bool,
) -> tuple[float, dict[str, float]]:
    breakdown = {
        "IVA": _to_float(config.get("iva_perc"), DEFAULT_CONFIG["iva_perc"]) if aplicar_iva else 0.0,
        "IGTF": _to_float(config.get("igtf_perc"), DEFAULT_CONFIG["igtf_perc"]) if aplicar_igtf else 0.0,
        "Banco": _to_float(config.get("banco_perc"), DEFAULT_CONFIG["banco_perc"]) if aplicar_banco else 0.0,
        "Kontigo": _to_float(config.get("kontigo_perc_salida"), _to_float(config.get("kontigo_perc"), DEFAULT_CONFIG["kontigo_perc"])) if aplicar_kontigo else 0.0,
    }
    impuesto_pct = round(sum(breakdown.values()), 4)
    return impuesto_pct, breakdown


def _tax_flags_from_pct(config: dict[str, object], impuesto_pct: float, metodo_pago: str) -> dict[str, bool]:
    impuesto_pct = round(float(impuesto_pct or 0.0), 4)
    base_flags = _suggest_tax_flags(metodo_pago)
    if impuesto_pct <= 0:
        return base_flags

    options = {
        "iva": _to_float(config.get("iva_perc"), DEFAULT_CONFIG["iva_perc"]),
        "igtf": _to_float(config.get("igtf_perc"), DEFAULT_CONFIG["igtf_perc"]),
        "banco": _to_float(config.get("banco_perc"), DEFAULT_CONFIG["banco_perc"]),
        "kontigo": _to_float(
            config.get("kontigo_perc_salida"),
            _to_float(config.get("kontigo_perc"), DEFAULT_CONFIG["kontigo_perc"]),
        ),
    }

    ordered_keys = list(options.keys())
    for mask in range(1, 1 << len(ordered_keys)):
        flags = {key: bool(mask & (1 << idx)) for idx, key in enumerate(ordered_keys)}
        total = round(sum(options[key] for key, active in flags.items() if active), 4)
        if abs(total - impuesto_pct) < 0.0001:
            return flags

    return base_flags


def _periodicidad_meta(periodicidad: str) -> dict[str, float | int | None | str]:
   return PERIODICIDADES_GASTO.get(periodicidad, PERIODICIDADES_GASTO["Único"])


def _sync_rate_state(
    rate_key: str,
    moneda: str,
    metodo_pago: str,
    config: dict[str, object] | None = None,
    initial_rate: float | None = None,
) -> float:
    cfg = config or _load_config_snapshot()
    suggested_rate = float(_resolve_rate(moneda, metodo_pago, cfg))
    combo_key = f"{rate_key}__combo"
    current_combo = (str(moneda), str(metodo_pago))

    if rate_key not in st.session_state:
        st.session_state[rate_key] = float(initial_rate if initial_rate is not None else suggested_rate)
        st.session_state[combo_key] = current_combo
    elif st.session_state.get(combo_key) != current_combo:
        st.session_state[rate_key] = suggested_rate
        st.session_state[combo_key] = current_combo

    return float(st.session_state.get(rate_key, suggested_rate))


def _render_currency_rate_inputs(
    moneda_key: str,
    tasa_key: str,
    metodo_pago: str,
    config: dict[str, object],
    *,
    moneda_default: str = "USD",
    tasa_inicial: float | None = None,
    moneda_label: str = "Moneda",
    tasa_label: str = "Tasa",
) -> tuple[str, float, float]:
    moneda_actual = str(st.session_state.get(moneda_key, moneda_default) or moneda_default).upper().strip()
    if moneda_actual not in MONEDAS_GASTO:
        moneda_actual = moneda_default if moneda_default in MONEDAS_GASTO else MONEDAS_GASTO[0]
        st.session_state[moneda_key] = moneda_actual

    col_moneda, col_tasa = st.columns(2)
    moneda = col_moneda.selectbox(
        moneda_label,
        MONEDAS_GASTO,
        index=MONEDAS_GASTO.index(moneda_actual),
        key=moneda_key,
    )
    tasa_sugerida = _resolve_rate(moneda, metodo_pago, config)
    _sync_rate_state(tasa_key, moneda, metodo_pago, config, initial_rate=tasa_inicial)
    tasa = col_tasa.number_input(
        tasa_label,
        min_value=0.0001,
        format="%.4f",
        key=tasa_key,
    )
    return moneda, float(tasa), float(tasa_sugerida)


# ============================================================
# REGISTRAR GASTO
# ============================================================


def registrar_gasto(
    usuario: str,
    descripcion: str,
    categoria: str,
    metodo_pago: str,
    moneda: str,
    tasa_cambio: float,
    monto: float,
    periodicidad: str,
    impuesto_pct: float = 0.0,
) -> int:
    descripcion = require_text(descripcion, "Descripción")
    categoria = require_text(categoria, "Categoría")
    metodo_pago = require_text(metodo_pago, "Método de pago")
    periodicidad = require_text(periodicidad, "Periodicidad")

    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    monto = as_positive(monto, "Monto", allow_zero=False)
    impuesto_pct = as_positive(impuesto_pct, "Impuestos", allow_zero=True)

    subtotal_usd = round(convert_to_usd(monto, moneda, tasa_cambio), 4)
    impuesto_usd = round(subtotal_usd * (impuesto_pct / 100), 4)
    monto_usd = round(subtotal_usd + impuesto_usd, 4)
    monto_bs = round(convert_to_bs(monto_usd, tasa_cambio), 2)

    periodicidad_info = _periodicidad_meta(periodicidad)
    factor_mensual = float(periodicidad_info["factor_mensual"] or 1.0)
    dias_periodicidad = periodicidad_info["dias"]
    monto_mensual_usd = round(monto_usd * factor_mensual, 4)
    monto_mensual_bs = round(convert_to_bs(monto_mensual_usd, tasa_cambio), 2)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO gastos (
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                subtotal_usd,
                impuesto_pct,
                impuesto_usd,
                monto_usd,
                monto_bs,
                periodicidad,
                dias_periodicidad,
                factor_mensual,
                monto_mensual_usd,
                monto_mensual_bs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                subtotal_usd,
                impuesto_pct,
                impuesto_usd,
                monto_usd,
                monto_bs,
                periodicidad,
                dias_periodicidad,
                factor_mensual,
                monto_mensual_usd,
                monto_mensual_bs,
            ),
        )

        return int(cur.lastrowid)


def _render_tab_registro(usuario: str) -> None:
    config = _load_config_snapshot()

    c1, c2 = st.columns([2, 1])
    descripcion = c1.text_input("Descripción del gasto", key="gastos_registro_descripcion")
    categoria = c2.selectbox("Categoría", CATEGORIAS_GASTO, key="gastos_registro_categoria")

    c3, c4 = st.columns(2)
    monto = c3.number_input("Monto", min_value=0.01, format="%.2f", key="gastos_registro_monto")
    metodo = c4.selectbox("Método de pago", METODOS_GASTO, key="gastos_registro_metodo")
    moneda, tasa, tasa_sugerida = _render_currency_rate_inputs(
        "gastos_registro_moneda",
        "gastos_registro_tasa",
        metodo,
        config,
    )

    taxes_default = _suggest_tax_flags(metodo)
    tx1, tx2, tx3, tx4 = st.columns(4)
    aplicar_iva = tx1.checkbox("IVA", value=taxes_default["iva"], key="gastos_registro_iva")
    aplicar_igtf = tx2.checkbox("IGTF", value=taxes_default["igtf"], key="gastos_registro_igtf")
    aplicar_banco = tx3.checkbox("Banco", value=taxes_default["banco"], key="gastos_registro_banco")
    aplicar_kontigo = tx4.checkbox("Kontigo", value=taxes_default["kontigo"], key="gastos_registro_kontigo")
    impuesto_pct, impuestos_detalle = _build_tax_breakdown(config, aplicar_iva, aplicar_igtf, aplicar_banco, aplicar_kontigo)

    c7, c8 = st.columns([1, 2])
    periodicidad = c7.selectbox("Periodicidad", list(PERIODICIDADES_GASTO.keys()), index=0, key="gastos_registro_periodicidad")
    info_periodicidad = _periodicidad_meta(periodicidad)
    c8.caption(
        f"{info_periodicidad['descripcion']} Tasa aplicada automáticamente desde Configuración: {tasa_sugerida:,.2f}."
    )

    subtotal_usd = round(convert_to_usd(float(monto), moneda, float(tasa)), 4)
    impuesto_usd = round(subtotal_usd * (impuesto_pct / 100), 4)
    monto_usd = subtotal_usd + impuesto_usd
    monto_bs = convert_to_bs(monto_usd, float(tasa))
    monto_mensual_usd = monto_usd * float(info_periodicidad["factor_mensual"] or 1.0)
    monto_mensual_bs = convert_to_bs(monto_mensual_usd, float(tasa))

    detalle_impuestos = ", ".join(f"{nombre} {valor:,.2f}%" for nombre, valor in impuestos_detalle.items() if valor > 0)
    st.caption(
        f"Impuestos/comisiones aplicados: {detalle_impuestos if detalle_impuestos else 'ninguno'}."
    )

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Subtotal USD", f"$ {subtotal_usd:,.2f}")
    p2.metric("Impuestos USD", f"$ {impuesto_usd:,.2f}")
    p3.metric("Total Bs", f"Bs {monto_bs:,.2f}")
    p4.metric("Equivalente mensual", f"$ {monto_mensual_usd:,.2f}")

    submit = st.button("📉 Registrar egreso", key="gastos_registro_submit")

    if not submit:
        return

    try:
        gid = registrar_gasto(
            usuario=usuario,
            descripcion=descripcion,
            categoria=categoria,
            metodo_pago=metodo,
            moneda=moneda,
            tasa_cambio=float(tasa),
            monto=float(monto),
            periodicidad=periodicidad,
            impuesto_pct=impuesto_pct,
        )
        st.success(f"✅ Gasto #{gid} registrado")
        st.caption(
            f"Subtotal: $ {subtotal_usd:,.2f} | Impuestos: $ {impuesto_usd:,.2f} | "
            f"Equivalente mensual estimado: $ {monto_mensual_usd:,.2f} / Bs {monto_mensual_bs:,.2f}"
        )
        st.balloons()
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
    except Exception as e:
        st.error("Error registrando gasto")
        st.exception(e)


def _load_gastos() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                subtotal_usd,
                impuesto_pct,
                impuesto_usd,
                monto_usd,
                monto_bs,
                periodicidad,
                dias_periodicidad,
                factor_mensual,
                monto_mensual_usd,
                monto_mensual_bs,
                estado
            FROM gastos
            WHERE estado='activo'
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )


def _render_tab_historial() -> None:
    st.subheader("Historial de gastos")

    try:
        df = _load_gastos()
    except Exception as e:
        st.error("Error cargando historial")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay gastos registrados.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir")
    df["periodicidad"] = df["periodicidad"].fillna("Único")
    if "monto_mensual_usd" not in df.columns:
        df["monto_mensual_usd"] = df["monto_usd"]
    if "monto_mensual_bs" not in df.columns:
        df["monto_mensual_bs"] = df["monto_bs"]

    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 2, 1, 1, 1])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="gastos_desde")
    hasta = c2.date_input("Hasta", date.today(), key="gastos_hasta")
    buscar = c3.text_input("Buscar por descripción")
    categoria_f = c4.selectbox("Categoría", ["Todas"] + sorted(df["categoria"].dropna().unique().tolist()))
    metodo_f = c5.selectbox("Método", ["Todos"] + sorted(df["metodo_pago"].str.title().unique().tolist()))
    periodicidad_f = c6.selectbox("Periodicidad", ["Todas"] + list(PERIODICIDADES_GASTO.keys()))

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if buscar:
        df_fil = df_fil[df_fil["descripcion"].str.contains(buscar, case=False, na=False)]
    if categoria_f != "Todas":
        df_fil = df_fil[df_fil["categoria"] == categoria_f]
    if metodo_f != "Todos":
        df_fil = df_fil[df_fil["metodo_pago"].str.lower() == metodo_f.lower()]
    if periodicidad_f != "Todas":
        df_fil = df_fil[df_fil["periodicidad"] == periodicidad_f]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total del periodo", f"$ {float(df_fil['monto_usd'].sum()):,.2f}")
    k2.metric("N° gastos", str(len(df_fil)))
    promedio = float(df_fil["monto_usd"].mean()) if not df_fil.empty else 0.0
    k3.metric("Promedio por gasto", f"$ {promedio:,.2f}")
    k4.metric("Equiv. mensual total", f"$ {float(df_fil['monto_mensual_usd'].sum()):,.2f}")

    columnas_tabla = [
        "fecha",
        "usuario",
        "descripcion",
        "categoria",
        "metodo_pago",
        "moneda",
        "tasa_cambio",
        "subtotal_usd",
        "impuesto_pct",
        "impuesto_usd",
        "monto_usd",
        "monto_bs",
        "periodicidad",
        "monto_mensual_usd",
        "monto_mensual_bs",
    ]
    st.dataframe(df_fil[columnas_tabla], use_container_width=True, hide_index=True)

    if not df_fil.empty:
        g1, g2 = st.columns(2)
        with g1:
            por_cat = df_fil.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
            st.caption("Distribución por categoría")
            st.bar_chart(por_cat.set_index("categoria")["monto_usd"])
        with g2:
            por_periodicidad = (
                df_fil.groupby("periodicidad", as_index=False)["monto_mensual_usd"]
                .sum()
                .sort_values("monto_mensual_usd", ascending=False)
            )
            st.caption("Equivalente mensual por periodicidad")
            st.bar_chart(por_periodicidad.set_index("periodicidad")["monto_mensual_usd"])

        diaria = (
            df_fil.assign(dia=df_fil["fecha"].dt.date)
            .groupby("dia", as_index=False)["monto_usd"]
            .sum()
            .sort_values("dia")
        )
        st.caption("Tendencia de egresos")
        st.line_chart(diaria.set_index("dia")["monto_usd"])

    st.subheader("Gestión de gastos")

    if not df_fil.empty:
        opciones = {f"#{int(r['id'])} · {r['descripcion']}": int(r["id"]) for _, r in df_fil.iterrows()}
        gasto_sel = st.selectbox("Seleccionar gasto", list(opciones.keys()))
        gasto_id = opciones[gasto_sel]

        row = df_fil[df_fil["id"] == gasto_id].iloc[0]

        with st.expander("✏️ Editar gasto"):
            config = _load_config_snapshot()

            e1, e2 = st.columns([2, 1])
            nueva_desc = e1.text_input("Descripción", value=str(row["descripcion"]), key=f"desc_gasto_{gasto_id}")
            nueva_cat = e2.selectbox(
                "Categoría",
                CATEGORIAS_GASTO,
                index=CATEGORIAS_GASTO.index(row["categoria"]) if row["categoria"] in CATEGORIAS_GASTO else 0,
                key=f"cat_gasto_{gasto_id}",
            )

            nuevo_metodo = st.selectbox(
                "Método de pago",
                METODOS_GASTO,
                index=METODOS_GASTO.index(row["metodo_pago"]) if row["metodo_pago"] in METODOS_GASTO else 0,
                key=f"metodo_gasto_{gasto_id}",
            )
            subtotal_base = float(row.get("subtotal_usd", row["monto_usd"]) or 0)
            monto_referencia = float(row["monto_bs"]) if row["moneda"] == "BS" else float(row["monto_usd"])
            if subtotal_base > 0:
                monto_referencia = (
                    round(convert_to_bs(subtotal_base, float(row["tasa_cambio"] or 1)), 2)
                    if row["moneda"] == "BS"
                    else subtotal_base
                )
            nuevo_monto = st.number_input(
                "Monto",
                min_value=0.01,
                value=monto_referencia,
                format="%.2f",
                key=f"monto_gasto_{gasto_id}",
            )
            nueva_moneda, nueva_tasa, tasa_sugerida_edit = _render_currency_rate_inputs(
                f"moneda_gasto_{gasto_id}",
                f"tasa_gasto_{gasto_id}",
                nuevo_metodo,
                config,
                moneda_default=str(row["moneda"] or "USD"),
                tasa_inicial=float(row["tasa_cambio"] or _resolve_rate(str(row["moneda"] or "USD"), nuevo_metodo, config)),
            )

            impuesto_pct_actual = float(row["impuesto_pct"]) if "impuesto_pct" in row.index else 0.0
            taxes_flags = _tax_flags_from_pct(config, impuesto_pct_actual, nuevo_metodo)
            txe1, txe2, txe3, txe4 = st.columns(4)
            edit_iva = txe1.checkbox("IVA", value=taxes_flags["iva"], key=f"iva_gasto_{gasto_id}")
            edit_igtf = txe2.checkbox("IGTF", value=taxes_flags["igtf"], key=f"igtf_gasto_{gasto_id}")
            edit_banco = txe3.checkbox("Banco", value=taxes_flags["banco"], key=f"banco_gasto_{gasto_id}")
            edit_kontigo = txe4.checkbox("Kontigo", value=taxes_flags["kontigo"], key=f"kontigo_gasto_{gasto_id}")
            impuesto_edit_pct, impuestos_detalle_edit = _build_tax_breakdown(config, edit_iva, edit_igtf, edit_banco, edit_kontigo)

            e7, e8 = st.columns([1, 2])
            periodicidad_actual = row["periodicidad"] if row["periodicidad"] in PERIODICIDADES_GASTO else "Único"
            nueva_periodicidad = e7.selectbox(
                "Periodicidad",
                list(PERIODICIDADES_GASTO.keys()),
                index=list(PERIODICIDADES_GASTO.keys()).index(periodicidad_actual),
                key=f"periodicidad_gasto_{gasto_id}",
            )
            info_periodicidad = _periodicidad_meta(nueva_periodicidad)
            e8.caption(
                f"Tasa sugerida actual en Configuración para {nuevo_metodo}/{nueva_moneda}: {tasa_sugerida_edit:,.2f}."
            )

            subtotal_edit_usd = round(convert_to_usd(float(nuevo_monto), nueva_moneda, float(nueva_tasa)), 4)
            impuesto_edit_usd = round(subtotal_edit_usd * (impuesto_edit_pct / 100), 4)
            monto_edit_usd = subtotal_edit_usd + impuesto_edit_usd
            monto_edit_bs = convert_to_bs(monto_edit_usd, float(nueva_tasa))
            factor_mensual = float(info_periodicidad["factor_mensual"] or 1.0)
            monto_edit_mensual_usd = round(monto_edit_usd * factor_mensual, 4)
            monto_edit_mensual_bs = round(convert_to_bs(monto_edit_mensual_usd, float(nueva_tasa)), 2)
            detalle_edit = ", ".join(f"{nombre} {valor:,.2f}%" for nombre, valor in impuestos_detalle_edit.items() if valor > 0)
            st.caption(f"Impuestos/comisiones aplicados: {detalle_edit if detalle_edit else 'ninguno'}.")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Subtotal USD", f"$ {subtotal_edit_usd:,.2f}")
            p2.metric("Impuestos USD", f"$ {impuesto_edit_usd:,.2f}")
            p3.metric("Total Bs", f"Bs {monto_edit_bs:,.2f}")
            p4.metric("Equiv. mensual", f"$ {monto_edit_mensual_usd:,.2f}")

            if st.button("💾 Guardar cambios", key=f"edit_gasto_{gasto_id}"):
                try:
                    with db_transaction() as conn:
                        conn.execute(
                            """
                            UPDATE gastos
                            SET descripcion=?, categoria=?, metodo_pago=?, moneda=?, tasa_cambio=?, subtotal_usd=?, impuesto_pct=?, impuesto_usd=?, monto_usd=?, monto_bs=?, periodicidad=?, dias_periodicidad=?, factor_mensual=?, monto_mensual_usd=?, monto_mensual_bs=?
                            WHERE id=?

                            """,
                            (
                                require_text(nueva_desc, "Descripción"),
                                nueva_cat,
                                require_text(nuevo_metodo, "Método de pago"),
                                nueva_moneda,
                                as_positive(float(nueva_tasa), "Tasa de cambio", allow_zero=False),
                                subtotal_edit_usd,
                                impuesto_edit_pct,
                                impuesto_edit_usd,
                                monto_edit_usd,
                                monto_edit_bs,
                                nueva_periodicidad,
                                info_periodicidad["dias"],
                                factor_mensual,
                                monto_edit_mensual_usd,
                                monto_edit_mensual_bs,
                                int(gasto_id),
                            ),
                        )
                    st.success("Actualizado")
                    st.rerun()
                except Exception as e:
                    st.error("Error actualizando")
                    st.exception(e)

        with st.expander("🗑️ Eliminar gasto"):
            confirmar = st.checkbox("Confirmo eliminación", key=f"confirm_gasto_{gasto_id}")
            if st.button("Eliminar", key=f"del_gasto_{gasto_id}"):
                if not confirmar:
                    st.warning("Debes confirmar para eliminar")
                else:
                    try:
                        with db_transaction() as conn:
                            conn.execute(
                                "UPDATE gastos SET estado='cancelado', cancelado_motivo='Eliminado desde interfaz' WHERE id=?",
                                (int(gasto_id),),
                            )
                        st.success("Gasto eliminado")
                        st.rerun()
                    except Exception as e:
                        st.error("Error eliminando")
                        st.exception(e)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_fil.to_excel(writer, index=False, sheet_name="Gastos")

    st.download_button(
        "📥 Exportar Excel",
        buffer.getvalue(),
        file_name="historial_gastos.xlsx",
    )


def _render_tab_resumen() -> None:
    st.subheader("Resumen financiero de egresos")

    try:
        df = _load_gastos()
    except Exception as e:
        st.error("Error cargando resumen")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay gastos para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["periodicidad"] = df["periodicidad"].fillna("Único")
    if "monto_mensual_usd" not in df.columns:
        df["monto_mensual_usd"] = df["monto_usd"]

    total = float(df["monto_usd"].sum())
    total_mensual = float(df["monto_mensual_usd"].sum())
    por_cat = df.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
    por_metodo = df.groupby("metodo_pago", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
    por_periodicidad = df.groupby("periodicidad", as_index=False)["monto_mensual_usd"].sum().sort_values("monto_mensual_usd", ascending=False)

    periodo_30 = df[df["fecha"].dt.date >= (date.today() - timedelta(days=30))]
    periodo_prev = df[
        (df["fecha"].dt.date < (date.today() - timedelta(days=30)))
        & (df["fecha"].dt.date >= (date.today() - timedelta(days=60)))
    ]
    actual_30 = float(periodo_30["monto_usd"].sum())
    anterior_30 = float(periodo_prev["monto_usd"].sum())
    delta = actual_30 - anterior_30

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total gastado", f"$ {total:,.2f}")
    c2.metric("Equiv. mensual", f"$ {total_mensual:,.2f}")
    c3.metric("Categoría principal", str(por_cat.iloc[0]["categoria"]))
    c4.metric("Últimos 30 días", f"$ {actual_30:,.2f}", delta=f"{delta:,.2f}")
    c5.metric("Ticket promedio", f"$ {float(df['monto_usd'].mean()):,.2f}")

    g1, g2, g3 = st.columns(3)
    with g1:
        st.caption("Gastos por categoría")
        st.bar_chart(por_cat.set_index("categoria")["monto_usd"])
    with g2:
        st.caption("Gastos por método")
        st.bar_chart(por_metodo.set_index("metodo_pago")["monto_usd"])
    with g3:
        st.caption("Equivalente mensual por periodicidad")
        st.bar_chart(por_periodicidad.set_index("periodicidad")["monto_mensual_usd"])

    st.subheader("Control de presupuesto")
    presupuesto = st.number_input("Presupuesto mensual objetivo (USD)", min_value=0.0, value=max(total_mensual, 1.0), step=50.0)
    uso = (total_mensual / presupuesto * 100) if presupuesto > 0 else 0.0
    st.progress(min(int(uso), 100))
    if uso >= 100:
        st.error(f"🚨 Presupuesto excedido: {uso:,.1f}%")
    elif uso >= 80:
        st.warning(f"⚠️ Presupuesto en zona de riesgo: {uso:,.1f}%")
    else:
        st.success(f"✅ Uso saludable del presupuesto: {uso:,.1f}%")


# ============================================================
# INTERFAZ DE GASTOS
# ============================================================

def render_gastos(usuario: str) -> None:
    st.subheader("📉 Control integral de gastos")
    st.caption("Las tasas sugeridas salen de Configuración según método/moneda, y puedes sumar impuestos o comisiones cuando sí te los cobran.")

    rol = st.session_state.get("rol", "Admin")
    if rol not in ["Admin", "Administration", "Administracion"]:
        st.error("🚫 Solo administración puede gestionar gastos.")
        return

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar gasto",
        "📜 Historial",
        "📊 Resumen",
    ])

    with tab1:
        _render_tab_registro(usuario)

    with tab2:
        _render_tab_historial()

    with tab3:
        _render_tab_resumen()
