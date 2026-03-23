from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from modules.common import as_positive, clean_text, money


TIPOS_PAGO_COMPRA = ("contado", "credito", "mixto")
ESTADOS_CXP = ("pendiente", "parcial", "pagada", "vencida")


@dataclass(frozen=True)
class CompraFinancialInput:
    tipo_pago: str = "contado"
    monto_pagado_inicial_usd: float = 0.0
    fecha_vencimiento: str | None = None
    notas: str = ""


def _parse_date(value: str | None) -> date | None:
    if not clean_text(value):
        return None
    return date.fromisoformat(str(value))


def calcular_estado_cxp(saldo_usd: float, fecha_vencimiento: str | None = None) -> str:
    saldo = round(float(saldo_usd or 0.0), 2)
    if saldo <= 0:
        return "pagada"

    vencimiento = _parse_date(fecha_vencimiento)
    if vencimiento and vencimiento < date.today():
        return "vencida"

    return "pendiente"


def validar_condicion_compra(
    total_compra_usd: float,
    tipo_pago: str,
    monto_pagado_inicial_usd: float = 0.0,
    fecha_vencimiento: str | None = None,
) -> tuple[float, float]:
    total = as_positive(total_compra_usd, "Total compra", allow_zero=False)
    tipo = clean_text(tipo_pago).lower()
    if tipo not in TIPOS_PAGO_COMPRA:
        raise ValueError("Tipo de pago inválido")

    pagado = as_positive(monto_pagado_inicial_usd, "Monto pagado inicial")
    if pagado > total:
        raise ValueError("El monto pagado inicial no puede ser mayor al total de la compra")

    saldo = money(total - pagado)

    if tipo == "contado":
        if saldo > 0:
            raise ValueError("Una compra de contado debe quedar totalmente pagada")
        return money(total), 0.0

    if tipo == "credito":
        if pagado > 0:
            raise ValueError("Una compra a crédito no debe registrar pago inicial")
        if not clean_text(fecha_vencimiento):
            raise ValueError("Debes indicar fecha de vencimiento para compras a crédito")
        return 0.0, money(total)

    if saldo <= 0:
        raise ValueError("Una compra mixta debe dejar saldo pendiente")
    if not clean_text(fecha_vencimiento):
        raise ValueError("Debes indicar fecha de vencimiento para compras mixtas")
    return money(pagado), saldo


def crear_cuenta_por_pagar_desde_compra(
    conn: Any,
    *,
    usuario: str,
    compra_id: int,
    proveedor_id: int | None,
    total_compra_usd: float,
    financial_input: CompraFinancialInput,
) -> int | None:
    pagado_inicial, saldo = validar_condicion_compra(
        total_compra_usd=total_compra_usd,
        tipo_pago=financial_input.tipo_pago,
        monto_pagado_inicial_usd=financial_input.monto_pagado_inicial_usd,
        fecha_vencimiento=financial_input.fecha_vencimiento,
    )

    if saldo <= 0:
        return None

    estado = "parcial" if pagado_inicial > 0 else calcular_estado_cxp(saldo, financial_input.fecha_vencimiento)

    cur = conn.execute(
        """
        INSERT INTO cuentas_por_pagar_proveedores
        (usuario, estado, proveedor_id, compra_id, tipo_documento, monto_original_usd,
         monto_pagado_usd, saldo_usd, fecha_vencimiento, notas)
        VALUES (?, ?, ?, ?, 'compra', ?, ?, ?, ?, ?)
        """,
        (
            clean_text(usuario),
            estado,
            int(proveedor_id) if proveedor_id is not None else None,
            int(compra_id),
            money(total_compra_usd),
            money(pagado_inicial),
            money(saldo),
            financial_input.fecha_vencimiento,
            clean_text(financial_input.notas or f"Generada desde compra #{int(compra_id)}"),
        ),
    )
    cuenta_id = int(cur.lastrowid)

    if pagado_inicial > 0:
        conn.execute(
            """
            INSERT INTO pagos_proveedores
            (usuario, cuenta_por_pagar_id, proveedor_id, monto_usd, moneda_pago,
             monto_moneda_pago, tasa_cambio, referencia, observaciones)
            VALUES (?, ?, ?, ?, 'USD', ?, 1, ?, ?)
            """,
            (
                clean_text(usuario),
                cuenta_id,
                int(proveedor_id) if proveedor_id is not None else None,
                money(pagado_inicial),
                money(pagado_inicial),
                f"Pago inicial compra #{int(compra_id)}",
                clean_text(financial_input.notas or "Pago inicial registrado al crear la compra"),
            ),
        )

    return cuenta_id


def registrar_pago_cuenta_por_pagar(
    conn: Any,
    *,
    usuario: str,
    cuenta_por_pagar_id: int,
    monto_usd: float,
    moneda_pago: str = "USD",
    monto_moneda_pago: float | None = None,
    tasa_cambio: float = 1.0,
    referencia: str = "",
    observaciones: str = "",
) -> int:
    monto = as_positive(monto_usd, "Monto del pago", allow_zero=False)
    tasa = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)

    row = conn.execute(
        """
        SELECT id, proveedor_id, compra_id, monto_pagado_usd, saldo_usd, fecha_vencimiento, estado
        FROM cuentas_por_pagar_proveedores
        WHERE id=?
        """,
        (int(cuenta_por_pagar_id),),
    ).fetchone()
    if not row:
        raise ValueError("La cuenta por pagar no existe")

    saldo_actual = money(row["saldo_usd"] or 0.0)
    if monto > saldo_actual:
        raise ValueError("El pago no puede ser mayor al saldo pendiente")

    monto_moneda = money(monto if monto_moneda_pago is None else monto_moneda_pago)
    cur = conn.execute(
        """
        INSERT INTO pagos_proveedores
        (usuario, cuenta_por_pagar_id, proveedor_id, monto_usd, moneda_pago,
         monto_moneda_pago, tasa_cambio, referencia, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_text(usuario),
            int(cuenta_por_pagar_id),
            int(row["proveedor_id"]) if row["proveedor_id"] is not None else None,
            money(monto),
            clean_text(moneda_pago) or "USD",
            monto_moneda,
            float(tasa),
            clean_text(referencia or f"Pago compra #{int(row['compra_id'])}"),
            clean_text(observaciones),
        ),
    )

    nuevo_pagado = money(float(row["monto_pagado_usd"] or 0.0) + monto)
    nuevo_saldo = money(saldo_actual - monto)
    nuevo_estado = "pagada" if nuevo_saldo <= 0 else "parcial"
    if nuevo_saldo > 0 and clean_text(row["fecha_vencimiento"]):
        nuevo_estado = calcular_estado_cxp(nuevo_saldo, row["fecha_vencimiento"])
        if nuevo_estado != "vencida":
            nuevo_estado = "parcial"

    conn.execute(
        """
        UPDATE cuentas_por_pagar_proveedores
        SET monto_pagado_usd=?, saldo_usd=?, estado=?
        WHERE id=?
        """,
        (nuevo_pagado, nuevo_saldo, nuevo_estado, int(cuenta_por_pagar_id)),
    )
    return int(cur.lastrowid)
