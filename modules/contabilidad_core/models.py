from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

TWOPLACES = Decimal("0.01")


class ContabilidadError(ValueError):
    """Base para errores funcionales del módulo contable."""


class PeriodoCerradoError(ContabilidadError):
    """Se intenta contabilizar sobre un periodo cerrado."""


class ValidacionContableError(ContabilidadError):
    """Error de validación del motor contable."""


EstadoPeriodo = Literal["abierto", "cerrado", "bloqueado"]
TipoCuenta = Literal["activo", "pasivo", "patrimonio", "ingreso", "costo", "gasto", "orden"]
NaturalezaCuenta = Literal["deudora", "acreedora"]
EstadoPoliza = Literal["borrador", "contabilizada", "conciliada", "anulada"]
AccionAuditoria = Literal[
    "creacion",
    "validacion",
    "alerta",
    "cierre",
    "conciliacion",
    "modificacion",
]
TipoDocumento = Literal["venta", "gasto", "compra", "tesoreria", "impuesto"]



def to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PeriodoContable:
    periodo: str
    fecha_inicio: date
    fecha_fin: date
    estado: EstadoPeriodo = "abierto"
    cerrado_por: str | None = None
    cerrado_en: datetime | None = None

    def __post_init__(self) -> None:
        if self.fecha_fin < self.fecha_inicio:
            raise ValidacionContableError("La fecha fin no puede ser menor a la fecha inicio.")
        if self.estado != "abierto" and not self.cerrado_por:
            object.__setattr__(self, "cerrado_por", self.cerrado_por or "sistema")
        if self.estado != "abierto" and not self.cerrado_en:
            object.__setattr__(self, "cerrado_en", datetime.combine(self.fecha_fin, datetime.min.time()))

    @property
    def abierto(self) -> bool:
        return self.estado == "abierto"


@dataclass(frozen=True)
class CuentaContable:
    id: str
    codigo: str
    nombre: str
    tipo: TipoCuenta
    naturaleza: NaturalezaCuenta
    cuenta_padre_id: str | None = None
    acepta_movimientos: bool = True

    def __post_init__(self) -> None:
        if not self.codigo or not self.nombre:
            raise ValidacionContableError("La cuenta contable debe tener código y nombre.")


@dataclass(frozen=True)
class MovimientoContable:
    asiento_id: str
    cuenta_id: str
    debito: Decimal = Decimal("0.00")
    credito: Decimal = Decimal("0.00")
    centro_costo: str | None = None
    tercero_id: str | None = None
    conciliado: bool = False
    documento_relacionado: str | None = None

    def __post_init__(self) -> None:
        debito = to_decimal(self.debito)
        credito = to_decimal(self.credito)
        object.__setattr__(self, "debito", debito)
        object.__setattr__(self, "credito", credito)
        if debito < 0 or credito < 0:
            raise ValidacionContableError("Los importes no pueden ser negativos.")
        if debito == Decimal("0.00") and credito == Decimal("0.00"):
            raise ValidacionContableError("Cada movimiento debe tener débito o crédito.")
        if debito > Decimal("0.00") and credito > Decimal("0.00"):
            raise ValidacionContableError("Un movimiento no puede tener débito y crédito simultáneamente.")


@dataclass(frozen=True)
class Asiento:
    id: str
    poliza_id: str
    comprobante: str
    descripcion: str
    fecha: date
    periodo: str
    origen_modelo: str
    movimientos: tuple[MovimientoContable, ...]
    total_debito: Decimal = field(default=Decimal("0.00"))
    total_credito: Decimal = field(default=Decimal("0.00"))
    conciliado: bool = False
    referencia_externa: str | None = None

    def __post_init__(self) -> None:
        if not self.movimientos:
            raise ValidacionContableError("El asiento debe incluir movimientos.")
        total_debito = sum((mov.debito for mov in self.movimientos), Decimal("0.00"))
        total_credito = sum((mov.credito for mov in self.movimientos), Decimal("0.00"))
        object.__setattr__(self, "total_debito", to_decimal(total_debito))
        object.__setattr__(self, "total_credito", to_decimal(total_credito))


@dataclass(frozen=True)
class Poliza:
    id: str
    numero: str
    origen: str
    fecha: date
    periodo: str
    estado: EstadoPoliza
    referencia_externa: str
    asientos: tuple[Asiento, ...]

    def __post_init__(self) -> None:
        if not self.asientos:
            raise ValidacionContableError("La póliza debe contener al menos un asiento.")


@dataclass(frozen=True)
class ReglaContabilizacion:
    id: str
    origen: str
    evento: str
    cuenta_debito: str
    cuenta_credito: str
    condicion: str
    prioridad: int = 1

    def __post_init__(self) -> None:
        if self.prioridad < 1:
            raise ValidacionContableError("La prioridad de la regla debe ser mayor o igual a 1.")


@dataclass(frozen=True)
class ImpuestoContable:
    id: str
    documento_tipo: TipoDocumento
    documento_id: str
    tasa: Decimal
    base_imponible: Decimal
    impuesto: Decimal
    asiento_id: str
    vencimiento: date
    estatus: str = "pendiente"
    tipo_impuesto: str = "IVA"
    evidencia: str | None = None

    def __post_init__(self) -> None:
        tasa = to_decimal(self.tasa)
        base = to_decimal(self.base_imponible)
        impuesto = to_decimal(self.impuesto)
        object.__setattr__(self, "tasa", tasa)
        object.__setattr__(self, "base_imponible", base)
        object.__setattr__(self, "impuesto", impuesto)
        if tasa < 0 or base < 0 or impuesto < 0:
            raise ValidacionContableError("Los impuestos no pueden ser negativos.")


@dataclass(frozen=True)
class EventoAuditoria:
    id: str
    entidad: str
    entidad_id: str
    accion: AccionAuditoria
    usuario: str
    fecha: datetime
    detalle: str
    severidad: Literal["info", "warning", "critical"] = "info"


@dataclass(frozen=True)
class VentaDocumento:
    id: str
    serie: str
    folio: str
    fecha: date
    periodo: str
    cliente_id: str
    subtotal: Decimal
    tasa_impuesto: Decimal
    cobro_inmediato: bool
    metodo_cobro: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subtotal", to_decimal(self.subtotal))
        object.__setattr__(self, "tasa_impuesto", to_decimal(self.tasa_impuesto))
        if not self.serie or not self.cliente_id:
            raise ValidacionContableError("La venta requiere serie y cliente.")


@dataclass(frozen=True)
class GastoDocumento:
    id: str
    documento: str
    fecha: date
    periodo: str
    proveedor_id: str
    centro_costo: str
    subtotal: Decimal
    tasa_iva: Decimal
    retencion_isr: Decimal = Decimal("0.00")
    retencion_iva: Decimal = Decimal("0.00")
    soportado: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "subtotal", to_decimal(self.subtotal))
        object.__setattr__(self, "tasa_iva", to_decimal(self.tasa_iva))
        object.__setattr__(self, "retencion_isr", to_decimal(self.retencion_isr))
        object.__setattr__(self, "retencion_iva", to_decimal(self.retencion_iva))
        if not self.documento or not self.centro_costo or not self.proveedor_id:
            raise ValidacionContableError("El gasto requiere documento, centro de costo y proveedor.")
        if not self.soportado:
            raise ValidacionContableError("El gasto requiere documento soporte.")


@dataclass(frozen=True)
class CompraDocumento:
    id: str
    factura: str
    recepcion_id: str
    fecha: date
    periodo: str
    proveedor_id: str
    destino: Literal["inventario", "gasto"]
    subtotal: Decimal
    tasa_iva: Decimal
    saldo_pendiente: Decimal
    vencimiento: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "subtotal", to_decimal(self.subtotal))
        object.__setattr__(self, "tasa_iva", to_decimal(self.tasa_iva))
        object.__setattr__(self, "saldo_pendiente", to_decimal(self.saldo_pendiente))
        if not self.factura or not self.recepcion_id or not self.proveedor_id:
            raise ValidacionContableError("La compra requiere factura, recepción y proveedor.")


@dataclass(frozen=True)
class MovimientoTesoreria:
    id: str
    tipo: Literal["cobro", "pago", "anticipo", "transferencia"]
    fecha: date
    periodo: str
    monto: Decimal
    cuenta_financiera: str
    contraparte_cuenta: str
    referencia: str
    tercero_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "monto", to_decimal(self.monto))
        if self.monto <= Decimal("0.00"):
            raise ValidacionContableError("El movimiento de tesorería debe tener monto positivo.")
        if not self.cuenta_financiera or not self.contraparte_cuenta:
            raise ValidacionContableError("Tesorería requiere cuenta financiera y contraparte.")


@dataclass(frozen=True)
class MovimientoBancario:
    id: str
    fecha: date
    referencia: str
    monto: Decimal
    cuenta_financiera: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "monto", to_decimal(self.monto))
