from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from database.connection import db_transaction
from services.domain_events import record_domain_event


@dataclass(frozen=True)
class VentaLinea:
    descripcion: str
    cantidad: float
    precio_unitario_usd: float
    costo_unitario_usd: float = 0.0
    inventario_id: int | None = None

    @property
    def subtotal_usd(self) -> float:
        return round(float(self.cantidad) * float(self.precio_unitario_usd), 4)


@dataclass(frozen=True)
class VentaResultado:
    venta_id: int
    total_usd: float
    total_bs: float
    evento_id: int


def normalizar_lineas(lineas: list[VentaLinea | dict[str, Any]]) -> list[VentaLinea]:
    normalizadas: list[VentaLinea] = []
    for linea in lineas:
        if isinstance(linea, VentaLinea):
            item = linea
        else:
            item = VentaLinea(
                descripcion=str(linea.get("descripcion", "")).strip(),
                cantidad=float(linea.get("cantidad", 0) or 0),
                precio_unitario_usd=float(linea.get("precio_unitario_usd", 0) or 0),
                costo_unitario_usd=float(linea.get("costo_unitario_usd", 0) or 0),
                inventario_id=linea.get("inventario_id"),
            )
        if not item.descripcion:
            raise ValueError("Cada linea de venta debe tener descripcion.")
        if item.cantidad <= 0:
            raise ValueError(f"La cantidad de {item.descripcion} debe ser mayor a cero.")
        normalizadas.append(item)
    if not normalizadas:
        raise ValueError("La venta debe tener al menos una linea.")
    return normalizadas


def registrar_venta_transaccional(
    *,
    usuario: str,
    lineas: list[VentaLinea | dict[str, Any]],
    cliente_id: int | None = None,
    moneda: str = "USD",
    tasa_cambio: float = 1.0,
    metodo_pago: str = "efectivo",
    impuesto_usd: float = 0.0,
    condicion_pago: str = "contado",
    observaciones: str | None = None,
) -> VentaResultado:
    """Registra una venta y deja listo el encadenamiento transaccional del ERP."""
    usuario = str(usuario or "Sistema").strip() or "Sistema"
    tasa_cambio = float(tasa_cambio or 1)
    if tasa_cambio <= 0:
        raise ValueError("La tasa de cambio debe ser mayor a cero.")

    venta_lineas = normalizar_lineas(lineas)
    subtotal_usd = round(sum(linea.subtotal_usd for linea in venta_lineas), 4)
    impuesto_usd = round(float(impuesto_usd or 0), 4)
    total_usd = round(subtotal_usd + impuesto_usd, 4)
    total_bs = round(total_usd * tasa_cambio, 2)
    condicion_pago = str(condicion_pago or "contado").strip().lower()

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ventas (
                usuario, estado, cliente_id, moneda, tasa_cambio, metodo_pago,
                subtotal_usd, impuesto_usd, total_usd, total_bs, observaciones
            ) VALUES (?, 'registrado', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal_usd, impuesto_usd, total_usd, total_bs, observaciones),
        )
        venta_id = int(cur.lastrowid)

        for linea in venta_lineas:
            conn.execute(
                """
                INSERT INTO ventas_detalle (
                    usuario, venta_id, inventario_id, descripcion, cantidad,
                    precio_unitario_usd, costo_unitario_usd, subtotal_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (usuario, venta_id, linea.inventario_id, linea.descripcion, linea.cantidad, linea.precio_unitario_usd, linea.costo_unitario_usd, linea.subtotal_usd),
            )

            if linea.inventario_id is not None:
                conn.execute(
                    """
                    INSERT INTO movimientos_inventario (usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
                    VALUES (?, ?, 'salida', ?, ?, ?)
                    """,
                    (usuario, linea.inventario_id, linea.cantidad, linea.costo_unitario_usd, f"venta:{venta_id}"),
                )
                conn.execute(
                    """
                    UPDATE inventario
                    SET stock_actual = stock_actual - ?, actualizado_por = ?, actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (linea.cantidad, usuario, linea.inventario_id),
                )

        if condicion_pago == "credito":
            if cliente_id is None:
                raise ValueError("Una venta a credito debe tener cliente_id.")
            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar (usuario, cliente_id, venta_id, tipo_documento, monto_original_usd, monto_cobrado_usd, saldo_usd, notas)
                VALUES (?, ?, ?, 'venta', ?, 0, ?, ?)
                """,
                (usuario, cliente_id, venta_id, total_usd, total_usd, observaciones),
            )
        else:
            conn.execute(
                """
                INSERT INTO movimientos_tesoreria (tipo, origen, referencia_id, descripcion, monto_usd, moneda, monto_moneda, tasa_cambio, metodo_pago, usuario)
                VALUES ('ingreso', 'venta', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (venta_id, f"Venta #{venta_id}", total_usd, moneda, total_usd, tasa_cambio, metodo_pago, usuario),
            )

    evento_id = record_domain_event(
        tipo_evento="venta_registrada",
        modulo_origen="ventas",
        usuario=usuario,
        referencia_tabla="ventas",
        referencia_id=venta_id,
        payload={"cliente_id": cliente_id, "condicion_pago": condicion_pago, "total_usd": total_usd, "total_bs": total_bs, "lineas": len(venta_lineas)},
    )
    return VentaResultado(venta_id=venta_id, total_usd=total_usd, total_bs=total_bs, evento_id=evento_id)
