from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.gastos_operativos_manual_service import (
    CATEGORIAS_GASTO_MANUAL,
    listar_gastos_operativos_manual,
    registrar_gasto_manual,
)
from services.gastos_operativos_service import listar_gastos_operativos


def _normalizar_factura(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["origen_gasto"] = "Factura de compra"
    return out


def _normalizar_manual(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["origen_gasto"] = "Manual"
    if "factura" not in out.columns:
        out["factura"] = out.get("comprobante", "")
    return out


def _render_form_manual(usuario: str) -> None:
    st.subheader("➕ Registrar gasto manual")
    st.caption("Para gastos sin factura formal: pasajes, recargas, limpieza, pago a ayudantes, publicidad, etc.")

    with st.form("form_gasto_manual"):
        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=date.today())
        categoria = c2.selectbox("Categoría", CATEGORIAS_GASTO_MANUAL, index=CATEGORIAS_GASTO_MANUAL.index("Otros"))
        monto_usd = c3.number_input("Monto USD", min_value=0.0, step=0.25, format="%.2f")

        concepto = st.text_input("Concepto", placeholder="Ej: Pasaje para buscar material, Adobe, limpieza, pago hermana")
        c4, c5, c6 = st.columns(3)
        proveedor = c4.text_input("Proveedor / persona", placeholder="Opcional")
        metodo_pago = c5.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "zelle", "binance", "tarjeta", "otro"])
        cuenta_origen = c6.text_input("Cuenta origen", placeholder="Caja, banco, Binance...")

        c7, c8, c9 = st.columns(3)
        tiene_factura = c7.checkbox("Tiene factura")
        es_deducible = c8.checkbox("Es deducible")
        moneda = c9.selectbox("Moneda", ["USD", "VES"])

        comprobante = st.text_input("Comprobante / referencia", placeholder="Opcional")
        observaciones = st.text_area("Observaciones", placeholder="Opcional")
        submit = st.form_submit_button("Guardar gasto manual", use_container_width=True)

    if submit:
        try:
            result = registrar_gasto_manual(
                usuario=usuario,
                fecha=fecha.isoformat(),
                categoria=categoria,
                concepto=concepto,
                proveedor=proveedor,
                monto_usd=float(monto_usd),
                moneda=moneda,
                metodo_pago=metodo_pago,
                cuenta_origen=cuenta_origen,
                tiene_factura=bool(tiene_factura),
                es_deducible=bool(es_deducible),
                comprobante=comprobante,
                observaciones=observaciones,
            )
            st.success(f"✅ Gasto manual #{result['gasto_id']} registrado y egreso #{result['movimiento_tesoreria_id']} creado.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo registrar el gasto manual.")
            st.exception(exc)


def _render_listado() -> None:
    df_facturas = _normalizar_factura(listar_gastos_operativos())
    df_manual = _normalizar_manual(listar_gastos_operativos_manual())
    df = pd.concat([df_facturas, df_manual], ignore_index=True, sort=False)

    if df.empty:
        st.info("Aún no hay gastos operativos registrados.")
        st.caption("Registra una factura con línea tipo 'Gasto' o 'Servicio', o usa la pestaña '➕ Registrar gasto manual'.")
        return

    df["monto_usd"] = pd.to_numeric(df["monto_usd"], errors="coerce").fillna(0)
    total = float(df["monto_usd"].sum())
    categorias = int(df["categoria"].nunique()) if "categoria" in df.columns else 0
    manual_total = float(df.loc[df["origen_gasto"].astype(str) == "Manual", "monto_usd"].sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros", len(df))
    c2.metric("Total gastos", f"${total:,.2f}")
    c3.metric("Gastos manuales", f"${manual_total:,.2f}")
    c4.metric("Categorías", categorias)

    c_buscar, c_categoria, c_origen = st.columns([2, 1, 1])
    buscar = c_buscar.text_input("Buscar concepto / proveedor / factura", key="buscar_gastos_operativos")
    categorias_opciones = ["Todas"] + sorted(df["categoria"].dropna().astype(str).unique().tolist())
    categoria = c_categoria.selectbox("Categoría", categorias_opciones, key="filtro_categoria_gastos_operativos")
    origen = c_origen.selectbox("Origen", ["Todos"] + sorted(df["origen_gasto"].dropna().astype(str).unique().tolist()))

    vista = df.copy()
    if categoria != "Todas":
        vista = vista[vista["categoria"].astype(str) == categoria]
    if origen != "Todos":
        vista = vista[vista["origen_gasto"].astype(str) == origen]
    if buscar.strip():
        txt = buscar.strip()
        mask = (
            vista["concepto"].astype(str).str.contains(txt, case=False, na=False)
            | vista["proveedor"].astype(str).str.contains(txt, case=False, na=False)
            | vista["factura"].astype(str).str.contains(txt, case=False, na=False)
            | vista["categoria"].astype(str).str.contains(txt, case=False, na=False)
        )
        vista = vista[mask]

    if vista.empty:
        st.warning("No hay gastos con esos filtros.")
        return

    resumen = vista.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
    st.caption("Resumen por categoría")
    st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.caption("Detalle")
    st.dataframe(vista, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Descargar gastos operativos CSV",
        data=vista.to_csv(index=False).encode("utf-8-sig"),
        file_name="gastos_operativos.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_gastos_operativos(usuario: str) -> None:
    st.subheader("📌 Gastos operativos")
    st.caption("Gastos y servicios desde facturas de compra, más gastos manuales del día a día.")

    tab_listado, tab_manual = st.tabs(["📋 Listado / resumen", "➕ Registrar gasto manual"])
    with tab_listado:
        _render_listado()
    with tab_manual:
        _render_form_manual(usuario)

    st.caption(f"Usuario: {usuario}")
