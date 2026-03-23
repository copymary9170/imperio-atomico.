from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from .seed import build_demo_ledger
from .services import (
    auditoria_df,
    calcular_balance_general,
    calcular_balanza_comprobacion,
    calcular_estado_resultados,
    calendario_fiscal_df,
    generar_resumen_iva,
    libro_diario_df,
    libro_mayor_df,
    polizas_por_origen_df,
)



def _currency(value: float) -> str:
    return f"${value:,.2f}"



def _show_dataframe(df: pd.DataFrame, *, height: int = 280) -> None:
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)



def _render_resumen(ledger) -> None:
    balanza = calcular_balanza_comprobacion(ledger.polizas, ledger.cuentas)
    resultados = calcular_estado_resultados(ledger.polizas, ledger.cuentas)
    iva = generar_resumen_iva(ledger.impuestos)
    utilidad = float(resultados.loc[resultados["Rubro"] == "Utilidad del periodo", "Saldo"].iloc[0]) if not resultados.empty else 0.0
    iva_pagar = float(iva.loc[iva["Tipo"] == "IVA por pagar", "Impuesto"].iloc[0]) if not iva.empty else 0.0

    st.title("📚 Contabilidad")
    st.caption("Módulo contable operativo del ERP con datos demo consistentes y flujos automatizados.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pólizas", len(ledger.polizas))
    c2.metric("Asientos", sum(len(poliza.asientos) for poliza in ledger.polizas))
    c3.metric("Utilidad", _currency(utilidad))
    c4.metric("IVA por pagar", _currency(iva_pagar))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Periodos", len(ledger.periodos))
    c6.metric("Cuentas", len(ledger.cuentas))
    c7.metric("Alertas", len(ledger.alertas) + len(ledger.diferencias_conciliacion))
    c8.metric("Eventos auditoría", len(ledger.auditoria))

    st.info(
        "El dashboard usa pólizas reales generadas desde ventas, gastos, compras y tesorería; los reportes se recalculan a partir del libro diario."
    )

    col1, col2 = st.columns((1.5, 1))
    with col1:
        st.markdown("#### Estado rápido del cierre")
        _show_dataframe(resultados, height=220)
    with col2:
        st.markdown("#### Validaciones activas")
        validaciones = pd.DataFrame(
            [
                {"Validación": "Periodo abierto requerido", "Estado": "Activa"},
                {"Validación": "Asiento balanceado", "Estado": "Activa"},
                {"Validación": "Cuenta válida", "Estado": "Activa"},
                {"Validación": "Duplicidad compras/CxP", "Estado": "Activa"},
                {"Validación": "Conciliación bancaria", "Estado": "Activa"},
                {"Validación": "Bloqueo de conciliados/cerrados", "Estado": "Activa"},
            ]
        )
        _show_dataframe(validaciones, height=220)



def _render_alcance() -> None:
    st.subheader("Alcance funcional")
    alcance = pd.DataFrame(
        [
            {"Frente": "Motor contable", "Entregables": "Libro diario, libro mayor, pólizas por origen"},
            {"Frente": "Cierre y balances", "Entregables": "Balanza, estado de resultados, balance general"},
            {"Frente": "Control tributario", "Entregables": "Resumen IVA, base imponible, calendario fiscal"},
            {"Frente": "Auditoría y trazabilidad", "Entregables": "Bitácora, rastreo documental, alertas"},
        ]
    )
    _show_dataframe(alcance, height=210)


def _render_flujos() -> None:
    st.subheader("Flujos contables")
    flujos = pd.DataFrame(
        [
            {"Origen": "Ventas", "Contabilización": "Clientes/Caja vs Ventas + IVA trasladado", "Control": "Serie, cliente, impuesto, periodo abierto"},
            {"Origen": "Gastos", "Contabilización": "Gasto + IVA acreditable vs Proveedores/retenciones", "Control": "Documento, centro de costo, proveedor"},
            {"Origen": "Compras / CxP", "Contabilización": "Inventario/Gasto + IVA acreditable vs Proveedores", "Control": "Factura, recepción, saldo pendiente"},
            {"Origen": "Caja / Tesorería", "Contabilización": "Banco/Caja vs cartera o proveedores", "Control": "Conciliar fecha y monto"},
            {"Origen": "Impuestos", "Contabilización": "Bases imponibles y saldos fiscales", "Control": "Vencimientos y evidencia"},
            {"Origen": "Conciliación / Auditoría", "Contabilización": "Alertas y bitácora sobre pólizas", "Control": "Bloquear conciliados y cerrados"},
        ]
    )
    _show_dataframe(flujos, height=260)



def _render_modelo_datos(ledger) -> None:
    st.subheader("Modelo de datos")
    tablas = pd.DataFrame(
        [
            {"Entidad": "conta_catalogo_cuentas", "Campos": "codigo, nombre, tipo, naturaleza, cuenta_padre_id, acepta_movimientos"},
            {"Entidad": "conta_periodos", "Campos": "periodo, fecha_inicio, fecha_fin, estado, cerrado_por, cerrado_en"},
            {"Entidad": "conta_polizas", "Campos": "numero, origen, fecha, periodo, estado, referencia_externa"},
            {"Entidad": "conta_asientos", "Campos": "poliza_id, comprobante, descripcion, total_debito, total_credito, origen_modelo"},
            {"Entidad": "conta_movimientos", "Campos": "asiento_id, cuenta_id, debito, credito, centro_costo, tercero_id"},
            {"Entidad": "conta_reglas_origen", "Campos": "origen, evento, cuenta_debito, cuenta_credito, condicion, prioridad"},
            {"Entidad": "conta_impuestos", "Campos": "documento_tipo, tasa, base_imponible, impuesto, asiento_id, vencimiento"},
            {"Entidad": "conta_auditoria", "Campos": "entidad, entidad_id, accion, usuario, fecha, detalle"},
        ]
    )
    _show_dataframe(tablas, height=310)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Catálogo de cuentas demo")
        cuentas_df = pd.DataFrame([asdict(cuenta) for cuenta in ledger.cuentas])
        _show_dataframe(cuentas_df, height=260)
    with col2:
        st.markdown("#### Periodos contables")
        periodos_df = pd.DataFrame([asdict(periodo) for periodo in ledger.periodos])
        _show_dataframe(periodos_df, height=260)

    with st.expander("Ver reglas de contabilización"):
        reglas_df = pd.DataFrame([asdict(regla) for regla in ledger.reglas])
        _show_dataframe(reglas_df, height=240)



def _render_reportes(ledger) -> None:
    st.subheader("Reportes contables")
    periodos = sorted({poliza.periodo for poliza in ledger.polizas})
    origenes = ["todos"] + sorted({poliza.origen for poliza in ledger.polizas})
    c1, c2 = st.columns(2)
    periodo_sel = c1.selectbox("Periodo", periodos, index=len(periodos) - 1)
    origen_sel = c2.selectbox("Origen", origenes)

    polizas = [poliza for poliza in ledger.polizas if poliza.periodo == periodo_sel]
    if origen_sel != "todos":
        polizas = [poliza for poliza in polizas if poliza.origen == origen_sel]

    diario = libro_diario_df(polizas, ledger.cuentas)
    mayor = libro_mayor_df(polizas, ledger.cuentas)
    balanza = calcular_balanza_comprobacion(polizas, ledger.cuentas)
    er = calcular_estado_resultados(polizas, ledger.cuentas)
    bg = calcular_balance_general(polizas, ledger.cuentas)
    po = polizas_por_origen_df(polizas)

    tabs = st.tabs(["Libro diario", "Libro mayor", "Balanza", "Estado resultados", "Balance general", "Pólizas por origen"])
    with tabs[0]:
        _show_dataframe(diario, height=340)
    with tabs[1]:
        _show_dataframe(mayor, height=340)
    with tabs[2]:
        _show_dataframe(balanza, height=340)
    with tabs[3]:
        _show_dataframe(er, height=220)
    with tabs[4]:
        _show_dataframe(bg, height=240)
    with tabs[5]:
        _show_dataframe(po, height=280)



def _render_tributacion(ledger) -> None:
    st.subheader("Tributación")
    iva = generar_resumen_iva(ledger.impuestos)
    calendario = calendario_fiscal_df(ledger.impuestos)
    impuestos_df = pd.DataFrame([asdict(impuesto) for impuesto in ledger.impuestos])

    col1, col2 = st.columns((1, 1.2))
    with col1:
        st.markdown("#### Resumen de IVA")
        _show_dataframe(iva, height=220)
    with col2:
        st.markdown("#### Calendario fiscal")
        _show_dataframe(calendario, height=220)

    with st.expander("Base imponible y detalle documental"):
        _show_dataframe(impuestos_df, height=280)



def _render_auditoria(ledger) -> None:
    st.subheader("Auditoría y trazabilidad")
    audit_df = auditoria_df(ledger.auditoria)
    diferencias_df = pd.DataFrame([asdict(d) for d in ledger.diferencias_conciliacion])
    alertas_df = pd.DataFrame({"Alerta": ledger.alertas}) if ledger.alertas else pd.DataFrame(columns=["Alerta"])

    c1, c2 = st.columns((1.1, 1))
    with c1:
        st.markdown("#### Bitácora contable")
        _show_dataframe(audit_df, height=320)
    with c2:
        st.markdown("#### Alertas de diferencias")
        _show_dataframe(diferencias_df if not diferencias_df.empty else pd.DataFrame(columns=["referencia", "detalle"]), height=320)

    st.markdown("#### Rastreo por documento")
    trazabilidad = pd.DataFrame(
        [
            {"Documento": venta.id, "Origen": "Venta", "Póliza": f"POL-VTA-{venta.id}", "Comprobante": venta.folio}
            for venta in ledger.ventas
        ]
        + [
            {"Documento": gasto.id, "Origen": "Gasto", "Póliza": f"POL-GTO-{gasto.id}", "Comprobante": gasto.documento}
            for gasto in ledger.gastos
        ]
        + [
            {"Documento": compra.id, "Origen": "Compra", "Póliza": f"POL-CMP-{compra.id}", "Comprobante": compra.factura}
            for compra in ledger.compras
        ]
        + [
            {"Documento": movimiento.id, "Origen": "Tesorería", "Póliza": f"POL-TES-{movimiento.id}", "Comprobante": movimiento.referencia}
            for movimiento in ledger.tesoreria
        ]
    )
    _show_dataframe(trazabilidad, height=240)

    with st.expander("Alertas funcionales del motor"):
        _show_dataframe(alertas_df, height=220)



def _render_roadmap() -> None:
    st.subheader("Hoja de ruta")
    roadmap = pd.DataFrame(
        [
            {"Fase": "Fase 1 · Base contable", "Estado": "Implementada", "Entregable": "Modelos, reglas, periodos, pólizas y asientos"},
            {"Fase": "Fase 2 · Automatización", "Estado": "Implementada", "Entregable": "Ventas, gastos, compras y tesorería generan pólizas"},
            {"Fase": "Fase 3 · Reportes", "Estado": "Implementada", "Entregable": "Libro diario, mayor, balanza, ER, BG e IVA"},
            {"Fase": "Fase 4 · Cierre y cumplimiento", "Estado": "Base lista", "Entregable": "Periodos cerrados, conciliación, auditoría y calendario fiscal"},
        ]
    )
    _show_dataframe(roadmap, height=220)



def render_contabilidad_dashboard(usuario: str | None = None) -> None:
    ledger = build_demo_ledger(usuario)

    tabs = st.tabs(
        [
            "📊 Resumen ejecutivo",
            "📌 Alcance funcional",
            "🔄 Flujos contables",
            "🗃️ Modelo de datos",
            "📒 Reportes contables",
            "🧾 Tributación",
            "🛡️ Auditoría",
            "🛣️ Hoja de ruta",
        ]
    )

    with tabs[0]:
        _render_resumen(ledger)
    with tabs[1]:
        _render_alcance()
    with tabs[2]:
        _render_flujos()
    with tabs[3]:
        _render_modelo_datos(ledger)
    with tabs[4]:
        _render_reportes(ledger)
    with tabs[5]:
        _render_tributacion(ledger)
    with tabs[6]:
        _render_auditoria(ledger)
    with tabs[7]:
        _render_roadmap()
