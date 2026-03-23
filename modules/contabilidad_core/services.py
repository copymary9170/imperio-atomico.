from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import pandas as pd

from .models import (
    Asiento,
    CompraDocumento,
    ContabilidadError,
    CuentaContable,
    EventoAuditoria,
    GastoDocumento,
    ImpuestoContable,
    MovimientoBancario,
    MovimientoContable,
    MovimientoTesoreria,
    PeriodoCerradoError,
    PeriodoContable,
    Poliza,
    ReglaContabilizacion,
    ValidacionContableError,
    VentaDocumento,
    to_decimal,
)


@dataclass(frozen=True)
class DiferenciaConciliacion:
    referencia: str
    tipo: str
    detalle: str
    monto_erp: Decimal
    monto_banco: Decimal
    dias_diferencia: int
    severidad: str


@dataclass
class DemoLedger:
    cuentas: list[CuentaContable]
    periodos: list[PeriodoContable]
    reglas: list[ReglaContabilizacion]
    polizas: list[Poliza]
    impuestos: list[ImpuestoContable]
    auditoria: list[EventoAuditoria]
    ventas: list[VentaDocumento]
    gastos: list[GastoDocumento]
    compras: list[CompraDocumento]
    tesoreria: list[MovimientoTesoreria]
    movimientos_bancarios: list[MovimientoBancario]
    diferencias_conciliacion: list[DiferenciaConciliacion]
    alertas: list[str]


def validar_periodo_abierto(periodo: PeriodoContable) -> bool:
    if not periodo.abierto:
        raise PeriodoCerradoError(f"El periodo {periodo.periodo} se encuentra {periodo.estado}.")
    return True



def validar_asiento_balanceado(asiento: Asiento) -> bool:
    if asiento.total_debito != asiento.total_credito:
        raise ValidacionContableError(
            f"El asiento {asiento.id} está descuadrado: débito {asiento.total_debito} vs crédito {asiento.total_credito}."
        )
    return True



def validar_movimientos_contra_catalogo(asiento: Asiento, cuentas: Iterable[CuentaContable]) -> list[str]:
    cuentas_index = {cuenta.id: cuenta for cuenta in cuentas}
    errores: list[str] = []
    for movimiento in asiento.movimientos:
        cuenta = cuentas_index.get(movimiento.cuenta_id)
        if not cuenta:
            errores.append(f"Movimiento {movimiento.cuenta_id} sin cuenta válida en asiento {asiento.id}.")
            continue
        if not cuenta.acepta_movimientos:
            errores.append(f"La cuenta {cuenta.codigo} no acepta movimientos directos.")
    return errores



def _build_poliza(
    *,
    poliza_id: str,
    numero: str,
    origen: str,
    fecha: date,
    periodo: str,
    referencia_externa: str,
    descripcion: str,
    comprobante: str,
    origen_modelo: str,
    movimientos: list[MovimientoContable],
    estado: str = "contabilizada",
    conciliado: bool = False,
) -> Poliza:
    asiento = Asiento(
        id=f"ASI-{poliza_id}",
        poliza_id=poliza_id,
        comprobante=comprobante,
        descripcion=descripcion,
        fecha=fecha,
        periodo=periodo,
        origen_modelo=origen_modelo,
        movimientos=tuple(movimientos),
        conciliado=conciliado,
        referencia_externa=referencia_externa,
    )
    validar_asiento_balanceado(asiento)
    return Poliza(
        id=poliza_id,
        numero=numero,
        origen=origen,
        fecha=fecha,
        periodo=periodo,
        estado=estado,
        referencia_externa=referencia_externa,
        asientos=(asiento,),
    )



def generar_poliza_desde_venta(
    venta: VentaDocumento,
    periodo: PeriodoContable,
    reglas: Iterable[ReglaContabilizacion],
) -> tuple[Poliza, list[ImpuestoContable]]:
    validar_periodo_abierto(periodo)
    if not venta.serie:
        raise ValidacionContableError("La venta requiere serie.")
    iva = to_decimal(venta.subtotal * venta.tasa_impuesto)
    total = to_decimal(venta.subtotal + iva)
    cuenta_cobro = "110101" if venta.cobro_inmediato else "105101"
    movimientos = [
        MovimientoContable(
            asiento_id=f"ASI-POL-VTA-{venta.id}",
            cuenta_id=cuenta_cobro,
            debito=total,
            tercero_id=venta.cliente_id,
            documento_relacionado=venta.id,
            conciliado=venta.cobro_inmediato,
        ),
        MovimientoContable(
            asiento_id=f"ASI-POL-VTA-{venta.id}",
            cuenta_id="410101",
            credito=venta.subtotal,
            tercero_id=venta.cliente_id,
            documento_relacionado=venta.id,
        ),
        MovimientoContable(
            asiento_id=f"ASI-POL-VTA-{venta.id}",
            cuenta_id="210301",
            credito=iva,
            tercero_id=venta.cliente_id,
            documento_relacionado=venta.id,
        ),
    ]
    poliza = _build_poliza(
        poliza_id=f"POL-VTA-{venta.id}",
        numero=f"VTA-{venta.serie}-{venta.folio}",
        origen="ventas",
        fecha=venta.fecha,
        periodo=venta.periodo,
        referencia_externa=venta.id,
        descripcion=f"Venta {venta.serie}-{venta.folio}",
        comprobante=f"FAC-{venta.folio}",
        origen_modelo="ventas.factura",
        movimientos=movimientos,
        conciliado=venta.cobro_inmediato,
    )
    impuestos = [
        ImpuestoContable(
            id=f"IMP-VTA-{venta.id}",
            documento_tipo="venta",
            documento_id=venta.id,
            tasa=venta.tasa_impuesto,
            base_imponible=venta.subtotal,
            impuesto=iva,
            asiento_id=poliza.asientos[0].id,
            vencimiento=date(venta.fecha.year, venta.fecha.month, min(28, venta.fecha.day)) if venta.fecha.month == 2 else date(venta.fecha.year, venta.fecha.month, min(28, venta.fecha.day)),
            estatus="pendiente",
            tipo_impuesto="IVA trasladado",
            evidencia=f"XML-{venta.id}",
        )
    ]
    return poliza, impuestos



def generar_poliza_desde_gasto(gasto: GastoDocumento, periodo: PeriodoContable) -> tuple[Poliza, list[ImpuestoContable]]:
    validar_periodo_abierto(periodo)
    iva = to_decimal(gasto.subtotal * gasto.tasa_iva)
    total = to_decimal(gasto.subtotal + iva - gasto.retencion_isr - gasto.retencion_iva)
    movimientos = [
        MovimientoContable(
            asiento_id=f"ASI-POL-GTO-{gasto.id}",
            cuenta_id="510101",
            debito=gasto.subtotal,
            centro_costo=gasto.centro_costo,
            tercero_id=gasto.proveedor_id,
            documento_relacionado=gasto.id,
        ),
        MovimientoContable(
            asiento_id=f"ASI-POL-GTO-{gasto.id}",
            cuenta_id="118001",
            debito=iva,
            centro_costo=gasto.centro_costo,
            tercero_id=gasto.proveedor_id,
            documento_relacionado=gasto.id,
        ),
    ]
    if gasto.retencion_isr > Decimal("0.00"):
        movimientos.append(
            MovimientoContable(
                asiento_id=f"ASI-POL-GTO-{gasto.id}",
                cuenta_id="210401",
                credito=gasto.retencion_isr,
                tercero_id=gasto.proveedor_id,
                documento_relacionado=gasto.id,
            )
        )
    if gasto.retencion_iva > Decimal("0.00"):
        movimientos.append(
            MovimientoContable(
                asiento_id=f"ASI-POL-GTO-{gasto.id}",
                cuenta_id="210402",
                credito=gasto.retencion_iva,
                tercero_id=gasto.proveedor_id,
                documento_relacionado=gasto.id,
            )
        )
    movimientos.append(
        MovimientoContable(
            asiento_id=f"ASI-POL-GTO-{gasto.id}",
            cuenta_id="201201",
            credito=total,
            tercero_id=gasto.proveedor_id,
            documento_relacionado=gasto.id,
        )
    )
    poliza = _build_poliza(
        poliza_id=f"POL-GTO-{gasto.id}",
        numero=f"GTO-{gasto.documento}",
        origen="gastos",
        fecha=gasto.fecha,
        periodo=gasto.periodo,
        referencia_externa=gasto.id,
        descripcion=f"Gasto {gasto.documento}",
        comprobante=gasto.documento,
        origen_modelo="gastos.documento",
        movimientos=movimientos,
    )
    impuestos = [
        ImpuestoContable(
            id=f"IMP-GTO-{gasto.id}",
            documento_tipo="gasto",
            documento_id=gasto.id,
            tasa=gasto.tasa_iva,
            base_imponible=gasto.subtotal,
            impuesto=iva,
            asiento_id=poliza.asientos[0].id,
            vencimiento=date(gasto.fecha.year, gasto.fecha.month, 17),
            estatus="pendiente",
            tipo_impuesto="IVA acreditable",
            evidencia=f"PDF-{gasto.documento}",
        )
    ]
    return poliza, impuestos



def detectar_duplicidad_compra(compra: CompraDocumento, compras_existentes: Iterable[CompraDocumento]) -> str | None:
    for existente in compras_existentes:
        if existente.id == compra.id:
            continue
        if (
            existente.factura == compra.factura
            and existente.proveedor_id == compra.proveedor_id
            and existente.saldo_pendiente == compra.saldo_pendiente
        ):
            return (
                f"Posible duplicidad en compra {compra.factura}: proveedor {compra.proveedor_id} "
                f"ya tiene documento {existente.id} con mismo saldo pendiente."
            )
    return None



def generar_poliza_desde_compra(
    compra: CompraDocumento,
    periodo: PeriodoContable,
    compras_existentes: Iterable[CompraDocumento],
) -> tuple[Poliza, list[ImpuestoContable], str | None]:
    validar_periodo_abierto(periodo)
    duplicidad = detectar_duplicidad_compra(compra, compras_existentes)
    iva = to_decimal(compra.subtotal * compra.tasa_iva)
    cuenta_destino = "115101" if compra.destino == "inventario" else "510101"
    movimientos = [
        MovimientoContable(
            asiento_id=f"ASI-POL-CMP-{compra.id}",
            cuenta_id=cuenta_destino,
            debito=compra.subtotal,
            tercero_id=compra.proveedor_id,
            documento_relacionado=compra.factura,
        ),
        MovimientoContable(
            asiento_id=f"ASI-POL-CMP-{compra.id}",
            cuenta_id="118001",
            debito=iva,
            tercero_id=compra.proveedor_id,
            documento_relacionado=compra.factura,
        ),
        MovimientoContable(
            asiento_id=f"ASI-POL-CMP-{compra.id}",
            cuenta_id="201201",
            credito=to_decimal(compra.subtotal + iva),
            tercero_id=compra.proveedor_id,
            documento_relacionado=compra.factura,
        ),
    ]
    poliza = _build_poliza(
        poliza_id=f"POL-CMP-{compra.id}",
        numero=f"CMP-{compra.factura}",
        origen="compras",
        fecha=compra.fecha,
        periodo=compra.periodo,
        referencia_externa=compra.id,
        descripcion=f"Compra {compra.factura}",
        comprobante=compra.factura,
        origen_modelo="compras.factura",
        movimientos=movimientos,
    )
    impuestos = [
        ImpuestoContable(
            id=f"IMP-CMP-{compra.id}",
            documento_tipo="compra",
            documento_id=compra.id,
            tasa=compra.tasa_iva,
            base_imponible=compra.subtotal,
            impuesto=iva,
            asiento_id=poliza.asientos[0].id,
            vencimiento=compra.vencimiento,
            estatus="pendiente",
            tipo_impuesto="IVA acreditable",
            evidencia=f"OC-{compra.recepcion_id}",
        )
    ]
    return poliza, impuestos, duplicidad



def aplicar_movimiento_tesoreria(movimiento: MovimientoTesoreria, periodo: PeriodoContable) -> Poliza:
    validar_periodo_abierto(periodo)
    debito_cuenta = movimiento.cuenta_financiera if movimiento.tipo in {"cobro", "anticipo"} else movimiento.contraparte_cuenta
    credito_cuenta = movimiento.contraparte_cuenta if movimiento.tipo in {"cobro", "anticipo"} else movimiento.cuenta_financiera
    poliza = _build_poliza(
        poliza_id=f"POL-TES-{movimiento.id}",
        numero=f"TES-{movimiento.referencia}",
        origen="tesoreria",
        fecha=movimiento.fecha,
        periodo=movimiento.periodo,
        referencia_externa=movimiento.id,
        descripcion=f"Movimiento {movimiento.tipo} {movimiento.referencia}",
        comprobante=movimiento.referencia,
        origen_modelo="tesoreria.movimiento",
        movimientos=[
            MovimientoContable(
                asiento_id=f"ASI-POL-TES-{movimiento.id}",
                cuenta_id=debito_cuenta,
                debito=movimiento.monto,
                tercero_id=movimiento.tercero_id,
                documento_relacionado=movimiento.id,
                conciliado=True,
            ),
            MovimientoContable(
                asiento_id=f"ASI-POL-TES-{movimiento.id}",
                cuenta_id=credito_cuenta,
                credito=movimiento.monto,
                tercero_id=movimiento.tercero_id,
                documento_relacionado=movimiento.id,
                conciliado=True,
            ),
        ],
        conciliado=True,
    )
    return poliza



def registrar_evento_auditoria(
    auditoria: list[EventoAuditoria],
    *,
    entidad: str,
    entidad_id: str,
    accion: str,
    usuario: str,
    detalle: str,
    severidad: str = "info",
) -> EventoAuditoria:
    evento = EventoAuditoria(
        id=f"AUD-{len(auditoria) + 1:04d}",
        entidad=entidad,
        entidad_id=entidad_id,
        accion=accion,  # type: ignore[arg-type]
        usuario=usuario,
        fecha=datetime.utcnow(),
        detalle=detalle,
        severidad=severidad,  # type: ignore[arg-type]
    )
    auditoria.append(evento)
    return evento



def detectar_diferencias_conciliacion(
    polizas: Iterable[Poliza],
    movimientos_bancarios: Iterable[MovimientoBancario],
) -> list[DiferenciaConciliacion]:
    banco_index = {mov.referencia: mov for mov in movimientos_bancarios}
    diferencias: list[DiferenciaConciliacion] = []
    for poliza in polizas:
        if poliza.origen != "tesoreria":
            continue
        asiento = poliza.asientos[0]
        banco = banco_index.get(poliza.numero.replace("TES-", ""))
        erp_monto = asiento.total_debito
        if not banco:
            diferencias.append(
                DiferenciaConciliacion(
                    referencia=poliza.numero,
                    tipo="faltante_banco",
                    detalle="No existe movimiento bancario para la referencia contabilizada.",
                    monto_erp=erp_monto,
                    monto_banco=Decimal("0.00"),
                    dias_diferencia=0,
                    severidad="critical",
                )
            )
            continue
        dias = abs((poliza.fecha - banco.fecha).days)
        if erp_monto != banco.monto or dias > 1:
            diferencias.append(
                DiferenciaConciliacion(
                    referencia=poliza.numero,
                    tipo="monto_fecha",
                    detalle="Diferencia detectada entre tesorería y extracto bancario.",
                    monto_erp=erp_monto,
                    monto_banco=banco.monto,
                    dias_diferencia=dias,
                    severidad="warning" if dias <= 2 else "critical",
                )
            )
    return diferencias



def detectar_alertas_cambios_restringidos(polizas: Iterable[Poliza], periodos: Iterable[PeriodoContable]) -> list[str]:
    periodos_index = {periodo.periodo: periodo for periodo in periodos}
    alertas: list[str] = []
    for poliza in polizas:
        periodo = periodos_index.get(poliza.periodo)
        if not periodo:
            continue
        if poliza.estado == "conciliada" and not periodo.abierto:
            alertas.append(
                f"La póliza {poliza.numero} está conciliada y pertenece a un periodo {periodo.estado}; cualquier cambio debe bloquearse."
            )
    return alertas



def _iter_asientos(polizas: Iterable[Poliza]) -> Iterable[Asiento]:
    for poliza in polizas:
        for asiento in poliza.asientos:
            yield asiento



def libro_diario_df(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> pd.DataFrame:
    cuentas_index = {cuenta.id: cuenta for cuenta in cuentas}
    rows: list[dict[str, object]] = []
    for poliza in polizas:
        for asiento in poliza.asientos:
            for movimiento in asiento.movimientos:
                cuenta = cuentas_index.get(movimiento.cuenta_id)
                rows.append(
                    {
                        "Fecha": asiento.fecha,
                        "Póliza": poliza.numero,
                        "Origen": poliza.origen,
                        "Comprobante": asiento.comprobante,
                        "Cuenta": f"{cuenta.codigo} - {cuenta.nombre}" if cuenta else movimiento.cuenta_id,
                        "Centro costo": movimiento.centro_costo or "-",
                        "Tercero": movimiento.tercero_id or "-",
                        "Débito": float(movimiento.debito),
                        "Crédito": float(movimiento.credito),
                        "Conciliado": "Sí" if movimiento.conciliado else "No",
                    }
                )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Fecha", "Póliza", "Cuenta"]).reset_index(drop=True)
    return df



def libro_mayor_df(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> pd.DataFrame:
    cuentas_index = {cuenta.id: cuenta for cuenta in cuentas}
    acumulado: dict[str, dict[str, Decimal | str]] = defaultdict(lambda: {"debito": Decimal("0.00"), "credito": Decimal("0.00")})
    for asiento in _iter_asientos(polizas):
        for movimiento in asiento.movimientos:
            cuenta = cuentas_index.get(movimiento.cuenta_id)
            if not cuenta:
                continue
            item = acumulado[cuenta.id]
            item["codigo"] = cuenta.codigo
            item["cuenta"] = cuenta.nombre
            item["tipo"] = cuenta.tipo
            item["debito"] = to_decimal(item["debito"] + movimiento.debito)  # type: ignore[operator]
            item["credito"] = to_decimal(item["credito"] + movimiento.credito)  # type: ignore[operator]
    rows: list[dict[str, object]] = []
    for item in acumulado.values():
        saldo = to_decimal(item["debito"] - item["credito"])  # type: ignore[operator]
        rows.append(
            {
                "Código": item["codigo"],
                "Cuenta": item["cuenta"],
                "Tipo": item["tipo"],
                "Débito": float(item["debito"]),
                "Crédito": float(item["credito"]),
                "Saldo": float(saldo),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Código").reset_index(drop=True)
    return df



def calcular_balanza_comprobacion(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> pd.DataFrame:
    cuentas_index = {cuenta.id: cuenta for cuenta in cuentas}
    balanza: dict[str, dict[str, Decimal | str]] = defaultdict(
        lambda: {"debito": Decimal("0.00"), "credito": Decimal("0.00"), "tipo": "", "naturaleza": ""}
    )
    for asiento in _iter_asientos(polizas):
        for movimiento in asiento.movimientos:
            cuenta = cuentas_index.get(movimiento.cuenta_id)
            if not cuenta:
                continue
            item = balanza[cuenta.id]
            item["codigo"] = cuenta.codigo
            item["cuenta"] = cuenta.nombre
            item["tipo"] = cuenta.tipo
            item["naturaleza"] = cuenta.naturaleza
            item["debito"] = to_decimal(item["debito"] + movimiento.debito)  # type: ignore[operator]
            item["credito"] = to_decimal(item["credito"] + movimiento.credito)  # type: ignore[operator]
    rows: list[dict[str, object]] = []
    for item in balanza.values():
        saldo = to_decimal(item["debito"] - item["credito"])  # type: ignore[operator]
        rows.append(
            {
                "Código": item["codigo"],
                "Cuenta": item["cuenta"],
                "Tipo": item["tipo"],
                "Naturaleza": item["naturaleza"],
                "Débito": float(item["debito"]),
                "Crédito": float(item["credito"]),
                "Saldo": float(saldo),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Código").reset_index(drop=True)
    return df



def calcular_estado_resultados(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> pd.DataFrame:
    balanza = calcular_balanza_comprobacion(polizas, cuentas)
    if balanza.empty:
        return pd.DataFrame(columns=["Rubro", "Saldo"])
    ingresos = balanza[balanza["Tipo"] == "ingreso"]["Crédito"].sum() - balanza[balanza["Tipo"] == "ingreso"]["Débito"].sum()
    costos = balanza[balanza["Tipo"] == "costo"]["Débito"].sum() - balanza[balanza["Tipo"] == "costo"]["Crédito"].sum()
    gastos = balanza[balanza["Tipo"] == "gasto"]["Débito"].sum() - balanza[balanza["Tipo"] == "gasto"]["Crédito"].sum()
    utilidad = ingresos - costos - gastos
    return pd.DataFrame(
        [
            {"Rubro": "Ingresos netos", "Saldo": float(ingresos)},
            {"Rubro": "Costos", "Saldo": float(costos)},
            {"Rubro": "Gastos operativos", "Saldo": float(gastos)},
            {"Rubro": "Utilidad del periodo", "Saldo": float(utilidad)},
        ]
    )



def calcular_balance_general(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> pd.DataFrame:
    balanza = calcular_balanza_comprobacion(polizas, cuentas)
    if balanza.empty:
        return pd.DataFrame(columns=["Sección", "Saldo"])
    activos = balanza[balanza["Tipo"] == "activo"]["Saldo"].sum()
    pasivos = -balanza[balanza["Tipo"] == "pasivo"]["Saldo"].sum()
    patrimonio = -balanza[balanza["Tipo"] == "patrimonio"]["Saldo"].sum()
    resultado = calcular_estado_resultados(polizas, cuentas)
    utilidad = float(resultado.loc[resultado["Rubro"] == "Utilidad del periodo", "Saldo"].iloc[0]) if not resultado.empty else 0.0
    return pd.DataFrame(
        [
            {"Sección": "Activos", "Saldo": float(activos)},
            {"Sección": "Pasivos", "Saldo": float(pasivos)},
            {"Sección": "Patrimonio", "Saldo": float(patrimonio)},
            {"Sección": "Resultado del periodo", "Saldo": float(utilidad)},
            {"Sección": "Pasivo + Patrimonio + Resultado", "Saldo": float(pasivos + patrimonio + utilidad)},
        ]
    )



def generar_resumen_iva(impuestos: Iterable[ImpuestoContable]) -> pd.DataFrame:
    resumen: dict[str, dict[str, Decimal | str]] = defaultdict(lambda: {"base": Decimal("0.00"), "impuesto": Decimal("0.00")})
    for item in impuestos:
        bucket = resumen[item.tipo_impuesto]
        bucket["tipo"] = item.tipo_impuesto
        bucket["base"] = to_decimal(bucket["base"] + item.base_imponible)  # type: ignore[operator]
        bucket["impuesto"] = to_decimal(bucket["impuesto"] + item.impuesto)  # type: ignore[operator]
    rows = [
        {"Tipo": item["tipo"], "Base imponible": float(item["base"]), "Impuesto": float(item["impuesto"])}
        for item in resumen.values()
    ]
    df = pd.DataFrame(rows)
    if not df.empty:
        total_trasladado = df.loc[df["Tipo"] == "IVA trasladado", "Impuesto"].sum()
        total_acreditable = df.loc[df["Tipo"] == "IVA acreditable", "Impuesto"].sum()
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [
                        {
                            "Tipo": "IVA por pagar",
                            "Base imponible": float(df["Base imponible"].sum()),
                            "Impuesto": float(total_trasladado - total_acreditable),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    return df



def calendario_fiscal_df(impuestos: Iterable[ImpuestoContable]) -> pd.DataFrame:
    rows = [
        {
            "Documento": impuesto.documento_id,
            "Tipo": impuesto.tipo_impuesto,
            "Vencimiento": impuesto.vencimiento,
            "Estatus": impuesto.estatus,
            "Evidencia": impuesto.evidencia or "-",
            "Importe": float(impuesto.impuesto),
        }
        for impuesto in impuestos
    ]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Vencimiento", "Documento"]).reset_index(drop=True)
    return df



def auditoria_df(eventos: Iterable[EventoAuditoria]) -> pd.DataFrame:
    rows = [
        {
            "Fecha": evento.fecha,
            "Entidad": evento.entidad,
            "ID": evento.entidad_id,
            "Acción": evento.accion,
            "Usuario": evento.usuario,
            "Severidad": evento.severidad,
            "Detalle": evento.detalle,
        }
        for evento in eventos
    ]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Fecha", ascending=False).reset_index(drop=True)
    return df



def polizas_por_origen_df(polizas: Iterable[Poliza]) -> pd.DataFrame:
    rows = []
    for poliza in polizas:
        rows.append(
            {
                "Número": poliza.numero,
                "Origen": poliza.origen,
                "Fecha": poliza.fecha,
                "Periodo": poliza.periodo,
                "Estado": poliza.estado,
                "Referencia": poliza.referencia_externa,
                "Débito": float(poliza.asientos[0].total_debito),
                "Crédito": float(poliza.asientos[0].total_credito),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Origen", "Fecha"]).reset_index(drop=True)
    return df



def validar_polizas(polizas: Iterable[Poliza], cuentas: Iterable[CuentaContable]) -> list[str]:
    errores: list[str] = []
    for poliza in polizas:
        for asiento in poliza.asientos:
            try:
                validar_asiento_balanceado(asiento)
            except ContabilidadError as exc:
                errores.append(str(exc))
            errores.extend(validar_movimientos_contra_catalogo(asiento, cuentas))
    return errores
