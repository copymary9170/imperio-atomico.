from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import money
from modules.inventario import (
    _ensure_inventory_support_tables,
    _load_cuentas_por_pagar_df,
    _load_pagos_proveedores_df,
)
from services.cxp_proveedores_service import registrar_pago_cuenta_por_pagar


_ESTADOS_ABIERTOS = ["pendiente", "parcial", "vencida"]


def _enhance_cxp(df_cxp: pd.DataFrame) -> pd.DataFrame:
    if df_cxp.empty:
        return df_cxp
    df = df_cxp.copy()
    hoy = pd.Timestamp(date.today())
    fecha_venc = pd.to_datetime(df["fecha_vencimiento"], errors="coerce")
    df["dias_para_vencer"] = (fecha_venc - hoy).dt.days
    df["dias_mora"] = df["dias_para_vencer"].apply(lambda d: abs(int(d)) if pd.notna(d) and d < 0 else 0)

    def _bucket(days):
        if pd.isna(days):
            return "Sin fecha"
        if days >= 0:
            return "Al día"
        vencido = abs(int(days))
        if vencido <= 30:
            return "1-30"
        if vencido <= 60:
            return "31-60"
        if vencido <= 90:
            return "61-90"
        return "90+"

    df["aging"] = df["dias_para_vencer"].apply(_bucket)
    return df


def render_cuentas_por_pagar(usuario: str) -> None:
    _ensure_inventory_support_tables()

    st.title("💸 Cuentas por pagar")
    st.caption("Módulo independiente para controlar deuda de proveedores, riesgo de mora y ejecución de pagos.")

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)

    raw = _load_cuentas_por_pagar_df()
    df_cxp = _enhance_cxp(raw)

    if df_cxp.empty:
        st.info("No hay cuentas por pagar registradas.")
        return

    abiertas = df_cxp[df_cxp["estado"].isin(_ESTADOS_ABIERTOS)].copy()
    deuda_total = float(abiertas["saldo_usd"].sum()) if not abiertas.empty else 0.0
    vencidas = abiertas[abiertas["dias_para_vencer"] < 0].copy() if not abiertas.empty else abiertas
    por_vencer_7 = abiertas[(abiertas["dias_para_vencer"] >= 0) & (abiertas["dias_para_vencer"] <= 7)].copy() if not abiertas.empty else abiertas

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deuda abierta", f"${deuda_total:,.2f}")
    c2.metric("Vencidas", int(len(vencidas)), delta=f"${float(vencidas['saldo_usd'].sum()):,.2f}")
    c3.metric("Vencen en 7 días", int(len(por_vencer_7)), delta=f"${float(por_vencer_7['saldo_usd'].sum()):,.2f}")
    c4.metric("Ticket promedio", f"${(deuda_total / len(abiertas)) if len(abiertas) else 0:,.2f}")

    k1, k2 = st.columns(2)
    with k1:
        st.write("#### Aging de deuda (USD)")
        aging = (
            abiertas.groupby("aging", as_index=False)["saldo_usd"]
            .sum()
            .sort_values("saldo_usd", ascending=False)
        )
        st.dataframe(aging, use_container_width=True, hide_index=True)
    with k2:
        st.write("#### Top proveedores con mayor saldo")
        top_proveedores = (
            abiertas.groupby("proveedor", as_index=False)["saldo_usd"]
            .sum()
            .sort_values("saldo_usd", ascending=False)
            .head(10)
        )
        st.dataframe(top_proveedores, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📋 Control operativo")
    f1, f2, f3 = st.columns([2, 1, 1])
    filtro_proveedor = f1.text_input("🔍 Filtrar proveedor", key="cxp_mod_filtro_proveedor")
    filtro_estado = f2.multiselect("Estado", ["pendiente", "parcial", "pagada", "vencida"], default=_ESTADOS_ABIERTOS)
    solo_riesgo = f3.checkbox("Solo en riesgo (vencidas o <=7 días)", value=False)

    df_view = df_cxp.copy()
    if filtro_proveedor:
        df_view = df_view[df_view["proveedor"].astype(str).str.contains(filtro_proveedor, case=False, na=False)]
    if filtro_estado:
        df_view = df_view[df_view["estado"].isin(filtro_estado)]
    if solo_riesgo:
        df_view = df_view[(df_view["dias_para_vencer"] < 0) | (df_view["dias_para_vencer"].between(0, 7))]

    cols = [
        "id",
        "compra_id",
        "proveedor",
        "item",
        "estado",
        "fecha_vencimiento",
        "dias_para_vencer",
        "aging",
        "monto_original_usd",
        "monto_pagado_usd",
        "saldo_usd",
        "notas",
    ]
    st.dataframe(df_view[cols], use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Exportar CxP (CSV)",
        data=df_view[cols].to_csv(index=False).encode("utf-8"),
        file_name=f"cuentas_por_pagar_{date.today().isoformat()}.csv",
        mime="text/csv",
    )

    abiertas_view = df_view[df_view["saldo_usd"] > 0].copy()
    if abiertas_view.empty:
        st.warning("No hay documentos abiertos en la selección actual para registrar pagos.")
        return

    st.divider()
    st.subheader("💳 Registrar abono")
    opciones = {
        f"#{int(r.id)} | Compra #{int(r.compra_id)} | {r.proveedor} | Saldo ${float(r.saldo_usd):,.2f}": int(r.id)
        for r in abiertas_view.itertuples()
    }
    cuenta_sel = st.selectbox("Seleccionar cuenta", list(opciones.keys()))
    cuenta_id = opciones[cuenta_sel]
    cuenta_row = abiertas_view[abiertas_view["id"] == cuenta_id].iloc[0]

    d1, d2, d3 = st.columns(3)
    d1.metric("Estado", str(cuenta_row["estado"]).capitalize())
    d2.metric("Saldo", f"${float(cuenta_row['saldo_usd']):,.2f}")
    d3.metric("Días para vencer", int(cuenta_row["dias_para_vencer"]) if pd.notna(cuenta_row["dias_para_vencer"]) else "N/A")

    p1, p2, p3 = st.columns(3)
    abono_usd = p1.number_input(
        "Monto a abonar (USD)",
        min_value=0.0,
        max_value=float(cuenta_row["saldo_usd"] or 0.0),
        value=0.0,
        key=f"cxp_mod_abono_{cuenta_id}",
    )
    moneda_abono = p2.selectbox("Moneda pago", ["USD", "BS", "USDT"], key=f"cxp_mod_moneda_{cuenta_id}")
    tasa_abono = p3.number_input(
        "Tasa",
        min_value=0.0001,
        value=1.0 if moneda_abono == "USD" else tasa_bcv,
        key=f"cxp_mod_tasa_{cuenta_id}",
    )
    p4, p5 = st.columns(2)
    referencia_abono = p4.text_input("Referencia", key=f"cxp_mod_ref_{cuenta_id}")
    observacion_abono = p5.text_input("Observaciones", key=f"cxp_mod_obs_{cuenta_id}")

    if st.button("💸 Registrar pago", use_container_width=True):
        if abono_usd <= 0:
            st.error("Debes indicar un monto válido para el abono.")
        else:
            monto_moneda = abono_usd if moneda_abono == "USD" else money(abono_usd * float(tasa_abono))
            with db_transaction() as conn:
                registrar_pago_cuenta_por_pagar(
                    conn,
                    usuario=usuario,
                    cuenta_por_pagar_id=int(cuenta_id),
                    monto_usd=float(abono_usd),
                    moneda_pago=moneda_abono,
                    monto_moneda_pago=float(monto_moneda),
                    tasa_cambio=float(tasa_abono),
                    referencia=referencia_abono,
                    observaciones=observacion_abono,
                )
            st.success("Pago registrado correctamente.")
            st.rerun()

    st.write("#### Historial de pagos de la cuenta")
    df_pagos = _load_pagos_proveedores_df(int(cuenta_id))
    if df_pagos.empty:
        st.caption("Todavía no hay pagos registrados para esta cuenta.")
    else:
        st.dataframe(df_pagos, use_container_width=True, hide_index=True)





