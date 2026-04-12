from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.integration_hub import render_module_inbox
from services.tesoreria_service import (
    ORIGENES_TESORERIA,
    listar_movimientos_tesoreria,
    listar_vencimientos,
    obtener_resumen_tesoreria,
    registrar_movimiento_tesoreria,
)


METODOS_TESORERIA = [
    "efectivo",
    "transferencia",
    "zelle",
    "binance",
    "pago móvil",
    "kontigo",
    "tarjeta",
    "credito",
]

MONEDAS_TESORERIA = ["USD", "BS", "USDT", "KONTIGO"]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _money(value: object) -> str:
    return f"$ {_safe_float(value):,.2f}"


def _normalize_text(value: object, default: str = "") -> str:
    return str(value or default).strip()


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _build_saldos_por_metodo(movimientos: pd.DataFrame) -> pd.DataFrame:
    if movimientos is None or movimientos.empty:
        return _empty_df(["metodo_pago", "ingresos_usd", "egresos_usd", "saldo_neto_usd"])

    df = movimientos.copy()
    df["metodo_pago"] = df.get("metodo_pago", "").fillna("sin definir").astype(str)
    df["tipo"] = df.get("tipo", "").fillna("").astype(str).str.lower()
    df["monto_usd"] = pd.to_numeric(df.get("monto_usd", 0), errors="coerce").fillna(0.0)

    resumen = (
        df.groupby(["metodo_pago", "tipo"], as_index=False)["monto_usd"]
        .sum()
        .pivot_table(index="metodo_pago", columns="tipo", values="monto_usd", aggfunc="sum", fill_value=0.0)
        .reset_index()
    )

    if "ingreso" not in resumen.columns:
        resumen["ingreso"] = 0.0
    if "egreso" not in resumen.columns:
        resumen["egreso"] = 0.0

    resumen = resumen.rename(
        columns={
            "ingreso": "ingresos_usd",
            "egreso": "egresos_usd",
        }
    )
    resumen["saldo_neto_usd"] = resumen["ingresos_usd"] - resumen["egresos_usd"]
    return resumen.sort_values("saldo_neto_usd", ascending=False).reset_index(drop=True)


def _build_resumen_origen(movimientos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if movimientos is None or movimientos.empty:
        return (
            _empty_df(["origen", "tipo", "monto_usd"]),
            _empty_df(["origen", "ingreso", "egreso", "flujo_neto"]),
        )

    df = movimientos.copy()
    df["origen"] = df.get("origen", "").fillna("sin definir").astype(str)
    df["tipo"] = df.get("tipo", "").fillna("").astype(str).str.lower()
    df["monto_usd"] = pd.to_numeric(df.get("monto_usd", 0), errors="coerce").fillna(0.0)

    resumen_origen = (
        df.groupby(["origen", "tipo"], as_index=False)["monto_usd"]
        .sum()
        .sort_values(["tipo", "monto_usd"], ascending=[True, False])
    )

    pivot = resumen_origen.pivot_table(
        index="origen",
        columns="tipo",
        values="monto_usd",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    if "ingreso" not in pivot.columns:
        pivot["ingreso"] = 0.0
    if "egreso" not in pivot.columns:
        pivot["egreso"] = 0.0

    pivot["flujo_neto"] = pivot["ingreso"] - pivot["egreso"]
    pivot = pivot.sort_values("flujo_neto", ascending=False).reset_index(drop=True)

    return resumen_origen, pivot


def _build_proyeccion(vencimientos: dict[str, pd.DataFrame], saldo_base: float) -> pd.DataFrame:
    cxp = vencimientos.get("cxp_proximas", pd.DataFrame()).copy()
    cxc = vencimientos.get("cxc_pendientes", pd.DataFrame()).copy()

    frames: list[pd.DataFrame] = []

    if not cxc.empty:
        fecha_col = "fecha_vencimiento" if "fecha_vencimiento" in cxc.columns else None
        monto_col = "saldo_usd" if "saldo_usd" in cxc.columns else None
        if fecha_col and monto_col:
            cxc["fecha"] = pd.to_datetime(cxc[fecha_col], errors="coerce")
            cxc["monto_usd"] = pd.to_numeric(cxc[monto_col], errors="coerce").fillna(0.0)
            cxc["tipo"] = "ingreso_esperado"
            cxc["impacto_usd"] = cxc["monto_usd"]
            frames.append(cxc[["fecha", "tipo", "monto_usd", "impacto_usd"]])

    if not cxp.empty:
        fecha_col = "fecha_vencimiento" if "fecha_vencimiento" in cxp.columns else None
        monto_col = "saldo_usd" if "saldo_usd" in cxp.columns else None
        if fecha_col and monto_col:
            cxp["fecha"] = pd.to_datetime(cxp[fecha_col], errors="coerce")
            cxp["monto_usd"] = pd.to_numeric(cxp[monto_col], errors="coerce").fillna(0.0)
            cxp["tipo"] = "egreso_programado"
            cxp["impacto_usd"] = -cxp["monto_usd"]
            frames.append(cxp[["fecha", "tipo", "monto_usd", "impacto_usd"]])

    if not frames:
        return _empty_df(["fecha", "tipo", "monto_usd", "impacto_usd", "saldo_proyectado_usd"])

    proy = pd.concat(frames, ignore_index=True)
    proy = proy.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    proy["saldo_proyectado_usd"] = float(saldo_base) + proy["impacto_usd"].cumsum()
    return proy


def _render_metricas(resumen: dict[str, float]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Saldo neto período", _money(resumen.get("saldo_neto_periodo_usd", 0.0)))
    c2.metric("Ingresos", _money(resumen.get("total_ingresos_usd", 0.0)))
    c3.metric("Egresos", _money(resumen.get("total_egresos_usd", 0.0)))
    c4.metric("Flujo neto", _money(resumen.get("flujo_neto_usd", 0.0)))
    c5.metric("CXP próximas", _money(resumen.get("cxp_proximas_usd", 0.0)))
    c6.metric("CXC pendientes", _money(resumen.get("cxc_pendientes_usd", 0.0)))


def _render_metricas_ejecutivas(
    resumen: dict[str, float],
    saldos_metodo: pd.DataFrame,
    proyeccion: pd.DataFrame,
) -> None:
    saldo_operativo = _safe_float(resumen.get("saldo_neto_periodo_usd", 0.0))
    ingresos = _safe_float(resumen.get("total_ingresos_usd", 0.0))
    egresos = _safe_float(resumen.get("total_egresos_usd", 0.0))
    cxp = _safe_float(resumen.get("cxp_proximas_usd", 0.0))
    cxc = _safe_float(resumen.get("cxc_pendientes_usd", 0.0))

    saldo_cuentas = _safe_float(saldos_metodo["saldo_neto_usd"].sum(), 0.0) if not saldos_metodo.empty else 0.0
    saldo_proyectado = (
        _safe_float(proyeccion["saldo_proyectado_usd"].iloc[-1], saldo_operativo)
        if not proyeccion.empty
        else saldo_operativo
    )

    st.markdown("### 📌 Vista ejecutiva")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Saldo operativo", _money(saldo_operativo))
    r2.metric("Saldo por cuentas", _money(saldo_cuentas))
    r3.metric("Ingresos esperados", _money(cxc))
    r4.metric("Egresos programados", _money(cxp))

    r5, r6, r7, r8 = st.columns(4)
    r5.metric("Ingresos reales", _money(ingresos))
    r6.metric("Egresos reales", _money(egresos))
    r7.metric("Flujo real", _money(ingresos - egresos))
    r8.metric("Saldo proyectado", _money(saldo_proyectado))


def _render_form_ajuste_manual(usuario: str) -> None:
    st.write("### Registrar ajuste manual")

    prefill = st.session_state.get("tesoreria_prefill", {})
    default_tipo = "ingreso" if _safe_float(prefill.get("total", 0.0)) > 0 else "egreso"
    default_monto = max(_safe_float(prefill.get("total", 0.01), 0.01), 0.01)
    default_metodo = _normalize_text(prefill.get("metodo_pago", "transferencia"), "transferencia")

    with st.form("tesoreria_ajuste_manual", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tipo = c1.selectbox("Tipo", ["ingreso", "egreso"], index=0 if default_tipo == "ingreso" else 1)
        monto_usd = c2.number_input("Monto USD", min_value=0.01, value=float(default_monto), format="%.2f")
        fecha_mov = c3.date_input("Fecha", value=date.today())

        c4, c5, c6 = st.columns(3)
        moneda = c4.selectbox("Moneda", MONEDAS_TESORERIA)
        tasa = c5.number_input("Tasa", min_value=0.0001, value=1.0, format="%.4f")
        metodo_idx = METODOS_TESORERIA.index(default_metodo) if default_metodo in METODOS_TESORERIA else 1
        metodo_pago = c6.selectbox("Método", METODOS_TESORERIA, index=metodo_idx)

        descripcion = st.text_input(
            "Descripción",
            value=_normalize_text(prefill.get("referencia")),
            placeholder="Ajuste de caja, aporte de socios, retiro, traslado, etc.",
        )
        referencia_id = st.number_input(
            "Referencia opcional",
            min_value=0,
            value=int(prefill.get("venta_id") or 0),
            step=1,
        )
        submit = st.form_submit_button("Guardar ajuste", use_container_width=True)

    if not submit:
        return

    if not _normalize_text(descripcion):
        st.error("La descripción es obligatoria.")
        return

    with db_transaction() as conn:
        registrar_movimiento_tesoreria(
            conn,
            tipo=tipo,
            origen="ajuste_manual",
            referencia_id=int(referencia_id) if referencia_id else None,
            descripcion=_normalize_text(descripcion),
            monto_usd=float(monto_usd),
            moneda=moneda,
            monto_moneda=float(monto_usd if moneda == "USD" else monto_usd * tasa),
            tasa_cambio=float(tasa),
            metodo_pago=metodo_pago,
            usuario=usuario,
            allow_duplicate=referencia_id == 0,
        )

    st.success("Ajuste manual registrado correctamente.")
    st.rerun()


def _render_tab_movimientos(movimientos: pd.DataFrame) -> None:
    st.write("### Movimientos de tesorería")

    if movimientos.empty:
        st.info("No hay movimientos registrados para el filtro seleccionado.")
        return

    st.dataframe(
        movimientos,
        use_container_width=True,
        hide_index=True,
        column_config={
            "monto_usd": st.column_config.NumberColumn("Monto USD", format="%.2f"),
            "monto_moneda": st.column_config.NumberColumn("Monto moneda", format="%.2f"),
            "tasa_cambio": st.column_config.NumberColumn("Tasa", format="%.4f"),
        },
    )

    st.download_button(
        "Exportar CSV",
        data=movimientos.to_csv(index=False).encode("utf-8"),
        file_name="tesoreria_movimientos.csv",
        mime="text/csv",
    )

    st.write("### Ver detalle de referencia")
    opciones = {
        f"#{int(row.id)} · {row.tipo} · {row.origen} · ${float(row.monto_usd):,.2f}": int(row.id)
        for row in movimientos.itertuples()
    }
    seleccionado = st.selectbox("Movimiento", list(opciones.keys()), key="tes_detalle_mov")
    detalle = movimientos[movimientos["id"] == opciones[seleccionado]].iloc[0].to_dict()
    st.json(detalle)


def _render_tab_vencimientos(vencimientos: dict[str, pd.DataFrame]) -> None:
    st.write("### Próximos vencimientos")

    cxp = vencimientos.get("cxp_proximas", pd.DataFrame())
    cxc = vencimientos.get("cxc_pendientes", pd.DataFrame())

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Cuentas por pagar próximas a vencer")
        if cxp.empty:
            st.info("Sin cuentas por pagar en el rango.")
        else:
            st.dataframe(cxp, use_container_width=True, hide_index=True)

    with c2:
        st.caption("Cuentas por cobrar pendientes")
        if cxc.empty:
            st.info("Sin cuentas por cobrar pendientes.")
        else:
            st.dataframe(cxc, use_container_width=True, hide_index=True)


def _render_tab_resumen_origen(movimientos: pd.DataFrame) -> None:
    st.write("### Resumen por origen")

    resumen_origen, pivot = _build_resumen_origen(movimientos)

    if resumen_origen.empty or pivot.empty:
        st.info("Sin datos para resumir.")
        return

    st.dataframe(
        pivot,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ingreso": st.column_config.NumberColumn("Ingresos", format="%.2f"),
            "egreso": st.column_config.NumberColumn("Egresos", format="%.2f"),
            "flujo_neto": st.column_config.NumberColumn("Flujo neto", format="%.2f"),
        },
    )
    st.bar_chart(resumen_origen.set_index(["origen", "tipo"])["monto_usd"])


def _render_tab_saldos(movimientos: pd.DataFrame) -> None:
    st.write("### Saldos por cuenta / método")

    saldos = _build_saldos_por_metodo(movimientos)
    if saldos.empty:
        st.info("No hay movimientos suficientes para calcular saldos por método.")
        return

    st.dataframe(
        saldos,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ingresos_usd": st.column_config.NumberColumn("Ingresos USD", format="%.2f"),
            "egresos_usd": st.column_config.NumberColumn("Egresos USD", format="%.2f"),
            "saldo_neto_usd": st.column_config.NumberColumn("Saldo neto USD", format="%.2f"),
        },
    )

    chart = saldos.set_index("metodo_pago")[["saldo_neto_usd"]]
    st.bar_chart(chart)


def _render_tab_proyeccion(vencimientos: dict[str, pd.DataFrame], resumen: dict[str, float]) -> None:
    st.write("### Flujo proyectado")

    saldo_base = _safe_float(resumen.get("saldo_neto_periodo_usd", 0.0))
    proyeccion = _build_proyeccion(vencimientos, saldo_base=saldo_base)

    if proyeccion.empty:
        st.info("No hay datos suficientes para construir proyección.")
        return

    tabla = proyeccion.copy()
    tabla["fecha"] = pd.to_datetime(tabla["fecha"], errors="coerce")
    tabla["fecha"] = tabla["fecha"].dt.strftime("%Y-%m-%d")

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "monto_usd": st.column_config.NumberColumn("Monto USD", format="%.2f"),
            "impacto_usd": st.column_config.NumberColumn("Impacto", format="%.2f"),
            "saldo_proyectado_usd": st.column_config.NumberColumn("Saldo proyectado", format="%.2f"),
        },
    )

    chart_df = proyeccion.copy()
    chart_df["fecha"] = pd.to_datetime(chart_df["fecha"], errors="coerce")
    chart_df = chart_df.groupby("fecha", as_index=False)["saldo_proyectado_usd"].last()
    st.line_chart(chart_df.set_index("fecha")[["saldo_proyectado_usd"]])

    st.caption(
        f"Saldo base usado para proyección: {_money(saldo_base)} | "
        f"Saldo proyectado final: {_money(proyeccion['saldo_proyectado_usd'].iloc[-1])}"
    )


def render_tesoreria(usuario: str) -> None:
    st.title("🏦 Tesorería / Flujo de caja")
    st.caption("Control financiero ampliado: movimientos, vencimientos, saldos por cuenta y proyección de flujo.")

    def _apply_inbox(inbox: dict) -> None:
        st.session_state["tesoreria_prefill"] = dict(inbox.get("payload_data", {}))

    render_module_inbox("tesorería", apply_callback=_apply_inbox, clear_after_apply=False)

    filtro1, filtro2, filtro3, filtro4 = st.columns(4)
    fecha_desde = filtro1.date_input("Desde", value=date.today() - timedelta(days=30), key="tes_desde")
    fecha_hasta = filtro2.date_input("Hasta", value=date.today(), key="tes_hasta")
    tipo = filtro3.selectbox("Tipo", ["Todos", "ingreso", "egreso"], key="tes_tipo")
    origen = filtro4.selectbox("Origen", ["Todos"] + list(ORIGENES_TESORERIA), key="tes_origen")

    filtro5, _ = st.columns([1, 3])
    metodo_pago = filtro5.selectbox(
        "Método de pago",
        ["Todos"] + METODOS_TESORERIA + ["usd", "bs", "usdt"],
        key="tes_metodo",
    )

    if fecha_desde > fecha_hasta:
        st.error("La fecha inicial no puede ser mayor a la fecha final.")
        return

    with db_transaction() as conn:
        resumen = obtener_resumen_tesoreria(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
        )
        movimientos = listar_movimientos_tesoreria(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
            tipo=None if tipo == "Todos" else tipo,
            origen=None if origen == "Todos" else origen,
            metodo_pago=None if metodo_pago == "Todos" else metodo_pago,
        )
        vencimientos = listar_vencimientos(
            conn,
            fecha_desde=fecha_desde.isoformat(),
            fecha_hasta=fecha_hasta.isoformat(),
        )

    saldos_metodo = _build_saldos_por_metodo(movimientos)
    proyeccion = _build_proyeccion(vencimientos, _safe_float(resumen.get("saldo_neto_periodo_usd", 0.0)))

    _render_metricas(resumen)
    _render_metricas_ejecutivas(resumen, saldos_metodo, proyeccion)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Movimientos",
            "Vencimientos",
            "Resumen por origen",
            "Saldos por cuenta",
            "Flujo proyectado",
            "Ajustes manuales",
        ]
    )

    with tab1:
        _render_tab_movimientos(movimientos)

    with tab2:
        _render_tab_vencimientos(vencimientos)

    with tab3:
        _render_tab_resumen_origen(movimientos)

    with tab4:
        _render_tab_saldos(movimientos)

    with tab5:
        _render_tab_proyeccion(vencimientos, resumen)

    with tab6:
        _render_form_ajuste_manual(usuario)
