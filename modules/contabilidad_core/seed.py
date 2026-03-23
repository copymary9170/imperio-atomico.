from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from .models import (
    CompraDocumento,
    CuentaContable,
    EventoAuditoria,
    GastoDocumento,
    MovimientoBancario,
    MovimientoTesoreria,
    PeriodoContable,
    Poliza,
    ReglaContabilizacion,
    VentaDocumento,
)
from .services import (
    DemoLedger,
    aplicar_movimiento_tesoreria,
    detectar_alertas_cambios_restringidos,
    detectar_diferencias_conciliacion,
    detectar_duplicidad_compra,
    generar_poliza_desde_compra,
    generar_poliza_desde_gasto,
    generar_poliza_desde_venta,
    registrar_evento_auditoria,
    validar_polizas,
)



def build_demo_ledger(usuario: str | None = None) -> DemoLedger:
    usuario = usuario or "Sistema"
    cuentas = [
        CuentaContable(id="110101", codigo="1101.01", nombre="Caja general", tipo="activo", naturaleza="deudora"),
        CuentaContable(id="110201", codigo="1102.01", nombre="Banco principal", tipo="activo", naturaleza="deudora"),
        CuentaContable(id="105101", codigo="1051.01", nombre="Clientes nacionales", tipo="activo", naturaleza="deudora"),
        CuentaContable(id="115101", codigo="1151.01", nombre="Inventario de insumos", tipo="activo", naturaleza="deudora"),
        CuentaContable(id="118001", codigo="1180.01", nombre="IVA acreditable", tipo="activo", naturaleza="deudora"),
        CuentaContable(id="201201", codigo="2012.01", nombre="Proveedores nacionales", tipo="pasivo", naturaleza="acreedora"),
        CuentaContable(id="210301", codigo="2103.01", nombre="IVA trasladado", tipo="pasivo", naturaleza="acreedora"),
        CuentaContable(id="210401", codigo="2104.01", nombre="ISR retenido", tipo="pasivo", naturaleza="acreedora"),
        CuentaContable(id="210402", codigo="2104.02", nombre="IVA retenido", tipo="pasivo", naturaleza="acreedora"),
        CuentaContable(id="310101", codigo="3101.01", nombre="Capital social", tipo="patrimonio", naturaleza="acreedora"),
        CuentaContable(id="410101", codigo="4101.01", nombre="Ventas sublimación", tipo="ingreso", naturaleza="acreedora"),
        CuentaContable(id="510101", codigo="5101.01", nombre="Gastos operativos", tipo="gasto", naturaleza="deudora"),
        CuentaContable(id="599999", codigo="5999.99", nombre="Control contable", tipo="orden", naturaleza="deudora", acepta_movimientos=False),
    ]

    periodos = [
        PeriodoContable(
            periodo="2026-02",
            fecha_inicio=date(2026, 2, 1),
            fecha_fin=date(2026, 2, 28),
            estado="cerrado",
            cerrado_por="contabilidad",
            cerrado_en=datetime(2026, 3, 2, 18, 30),
        ),
        PeriodoContable(periodo="2026-03", fecha_inicio=date(2026, 3, 1), fecha_fin=date(2026, 3, 31), estado="abierto"),
    ]
    periodos_index = {periodo.periodo: periodo for periodo in periodos}

    reglas = [
        ReglaContabilizacion(id="R-VENTA-1", origen="ventas", evento="factura_emitida", cuenta_debito="105101", cuenta_credito="410101", condicion="venta a crédito", prioridad=1),
        ReglaContabilizacion(id="R-VENTA-2", origen="ventas", evento="factura_contado", cuenta_debito="110101", cuenta_credito="410101", condicion="venta de contado", prioridad=1),
        ReglaContabilizacion(id="R-GASTO-1", origen="gastos", evento="factura_recibida", cuenta_debito="510101", cuenta_credito="201201", condicion="gasto operativo", prioridad=1),
        ReglaContabilizacion(id="R-COMPRA-1", origen="compras", evento="recepcion_facturada", cuenta_debito="115101", cuenta_credito="201201", condicion="compra inventariable", prioridad=1),
        ReglaContabilizacion(id="R-TES-1", origen="tesoreria", evento="cobro_cliente", cuenta_debito="110201", cuenta_credito="105101", condicion="cobro bancario", prioridad=1),
    ]

    ventas = [
        VentaDocumento(id="VTA-001", serie="A", folio="1045", fecha=date(2026, 3, 5), periodo="2026-03", cliente_id="CLI-ACME", subtotal=Decimal("12500.00"), tasa_impuesto=Decimal("0.16"), cobro_inmediato=False, metodo_cobro="credito"),
        VentaDocumento(id="VTA-002", serie="A", folio="1046", fecha=date(2026, 3, 9), periodo="2026-03", cliente_id="CLI-BETA", subtotal=Decimal("4800.00"), tasa_impuesto=Decimal("0.16"), cobro_inmediato=True, metodo_cobro="transferencia"),
    ]

    gastos = [
        GastoDocumento(id="GTO-001", documento="F-889", fecha=date(2026, 3, 10), periodo="2026-03", proveedor_id="PRV-ENERGIA", centro_costo="PRODUCCION", subtotal=Decimal("3200.00"), tasa_iva=Decimal("0.16"), retencion_isr=Decimal("320.00"), retencion_iva=Decimal("170.67"), soportado=True),
        GastoDocumento(id="GTO-002", documento="F-903", fecha=date(2026, 3, 15), periodo="2026-03", proveedor_id="PRV-LOGISTICA", centro_costo="OPERACIONES", subtotal=Decimal("1450.00"), tasa_iva=Decimal("0.16"), soportado=True),
    ]

    compras = [
        CompraDocumento(id="CMP-001", factura="OC-774", recepcion_id="REC-774", fecha=date(2026, 3, 12), periodo="2026-03", proveedor_id="PRV-PAPEL", destino="inventario", subtotal=Decimal("5600.00"), tasa_iva=Decimal("0.16"), saldo_pendiente=Decimal("6496.00"), vencimiento=date(2026, 4, 15)),
        CompraDocumento(id="CMP-002", factura="OC-774", recepcion_id="REC-774-B", fecha=date(2026, 3, 13), periodo="2026-03", proveedor_id="PRV-PAPEL", destino="inventario", subtotal=Decimal("5600.00"), tasa_iva=Decimal("0.16"), saldo_pendiente=Decimal("6496.00"), vencimiento=date(2026, 4, 15)),
    ]

    tesoreria = [
        MovimientoTesoreria(id="TES-001", tipo="cobro", fecha=date(2026, 3, 18), periodo="2026-03", monto=Decimal("14500.00"), cuenta_financiera="110201", contraparte_cuenta="105101", referencia="COBRO-145", tercero_id="CLI-ACME"),
        MovimientoTesoreria(id="TES-002", tipo="pago", fecha=date(2026, 3, 20), periodo="2026-03", monto=Decimal("6496.00"), cuenta_financiera="110201", contraparte_cuenta="201201", referencia="PAGO-OC774", tercero_id="PRV-PAPEL"),
    ]

    movimientos_bancarios = [
        MovimientoBancario(id="BNK-001", fecha=date(2026, 3, 18), referencia="COBRO-145", monto=Decimal("14500.00"), cuenta_financiera="110201"),
        MovimientoBancario(id="BNK-002", fecha=date(2026, 3, 22), referencia="PAGO-OC774", monto=Decimal("6400.00"), cuenta_financiera="110201"),
    ]

    apertura = aplicar_movimiento_tesoreria(
        MovimientoTesoreria(
            id="TES-OPEN-001",
            tipo="anticipo",
            fecha=date(2026, 2, 28),
            periodo="2026-02X",
            monto=Decimal("50000.00"),
            cuenta_financiera="110201",
            contraparte_cuenta="310101",
            referencia="APORTACION-CAPITAL",
            tercero_id="SOCIOS",
        ),
        PeriodoContable(periodo="2026-02X", fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28), estado="abierto"),
    )
    polizas: list[Poliza] = [
        Poliza(
            id="POL-OPEN-001",
            numero="APER-2026-02",
            origen="apertura",
            fecha=date(2026, 2, 28),
            periodo="2026-02",
            estado="conciliada",
            referencia_externa="OPEN-001",
            asientos=apertura.asientos,
        )
    ]
    impuestos = []
    auditoria: list[EventoAuditoria] = [
        EventoAuditoria(id="AUD-0001", entidad="periodo", entidad_id="2026-02", accion="cierre", usuario="contabilidad", fecha=datetime(2026, 3, 2, 18, 30), detalle="Cierre mensual ejecutado con balanza en cero y conciliación aprobada.", severidad="info"),
        EventoAuditoria(id="AUD-0002", entidad="asiento", entidad_id=apertura.asientos[0].id, accion="alerta", usuario="auditoria", fecha=datetime(2026, 3, 4, 9, 15), detalle="Intento detectado de modificar un asiento conciliado del periodo 2026-02.", severidad="critical"),
    ]

    for venta in ventas:
        poliza, impuestos_venta = generar_poliza_desde_venta(venta, periodos_index[venta.periodo], reglas)
        polizas.append(poliza)
        impuestos.extend(impuestos_venta)
        registrar_evento_auditoria(
            auditoria,
            entidad="venta",
            entidad_id=venta.id,
            accion="creacion",
            usuario=usuario,
            detalle=f"Venta {venta.serie}-{venta.folio} traducida a póliza {poliza.numero}.",
        )

    for gasto in gastos:
        poliza, impuestos_gasto = generar_poliza_desde_gasto(gasto, periodos_index[gasto.periodo])
        polizas.append(poliza)
        impuestos.extend(impuestos_gasto)
        registrar_evento_auditoria(
            auditoria,
            entidad="gasto",
            entidad_id=gasto.id,
            accion="creacion",
            usuario=usuario,
            detalle=f"Gasto {gasto.documento} contabilizado con soporte y centro {gasto.centro_costo}.",
        )

    compras_existentes: list[CompraDocumento] = []
    for compra in compras:
        poliza, impuestos_compra, alerta_duplicidad = generar_poliza_desde_compra(compra, periodos_index[compra.periodo], compras_existentes)
        polizas.append(poliza)
        impuestos.extend(impuestos_compra)
        compras_existentes.append(compra)
        registrar_evento_auditoria(
            auditoria,
            entidad="compra",
            entidad_id=compra.id,
            accion="creacion",
            usuario=usuario,
            detalle=f"Compra {compra.factura} vinculada con recepción {compra.recepcion_id}.",
        )
        if alerta_duplicidad:
            registrar_evento_auditoria(
                auditoria,
                entidad="compra",
                entidad_id=compra.id,
                accion="alerta",
                usuario="auditoria",
                detalle=alerta_duplicidad,
                severidad="warning",
            )

    for movimiento in tesoreria:
        poliza = aplicar_movimiento_tesoreria(movimiento, periodos_index[movimiento.periodo])
        polizas.append(
            Poliza(
                id=poliza.id,
                numero=poliza.numero,
                origen=poliza.origen,
                fecha=poliza.fecha,
                periodo=poliza.periodo,
                estado="conciliada" if movimiento.id == "TES-001" else "contabilizada",
                referencia_externa=poliza.referencia_externa,
                asientos=poliza.asientos,
            )
        )
        registrar_evento_auditoria(
            auditoria,
            entidad="tesoreria",
            entidad_id=movimiento.id,
            accion="conciliacion" if movimiento.id == "TES-001" else "creacion",
            usuario=usuario,
            detalle=f"Movimiento {movimiento.referencia} aplicado a bancos y cartera.",
        )

    diferencias = detectar_diferencias_conciliacion(polizas, movimientos_bancarios)
    for diferencia in diferencias:
        registrar_evento_auditoria(
            auditoria,
            entidad="conciliacion",
            entidad_id=diferencia.referencia,
            accion="alerta",
            usuario="auditoria",
            detalle=f"{diferencia.detalle} ERP={diferencia.monto_erp} Banco={diferencia.monto_banco} Días={diferencia.dias_diferencia}.",
            severidad=diferencia.severidad,
        )

    alertas = validar_polizas(polizas, cuentas)
    alertas.extend(detectar_alertas_cambios_restringidos(polizas, periodos))
    for compra in compras:
        duplicidad = detectar_duplicidad_compra(compra, [c for c in compras if c.id != compra.id])
        if duplicidad and duplicidad not in alertas:
            alertas.append(duplicidad)

    return DemoLedger(
        cuentas=cuentas,
        periodos=periodos,
        reglas=reglas,
        polizas=polizas,
        impuestos=impuestos,
        auditoria=auditoria,
        ventas=ventas,
        gastos=gastos,
        compras=compras,
        tesoreria=tesoreria,
        movimientos_bancarios=movimientos_bancarios,
        diferencias_conciliacion=diferencias,
        alertas=alertas,
    )
