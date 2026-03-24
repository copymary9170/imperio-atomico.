from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from modules.common import as_positive, clean_text, money
from services.contabilidad_service import contabilizar_cobro_cliente
from services.tesoreria_service import registrar_ingreso

ESTADOS_CXC = ("pendiente", "parcial", "pagada", "vencida", "incobrable")


@dataclass(frozen=True)
class CobranzaInput:
    cuenta_por_cobrar_id: int
    monto_usd: float
    moneda_pago: str = "USD"
    monto_moneda_pago: float | None = None
    tasa_cambio: float = 1.0
    metodo_pago: str = "efectivo"
    referencia: str = ""
    observaciones: str = ""
    promesa_pago_fecha: str | None = None
    proxima_gestion_fecha: str | None = None


def calcular_estado_cxc(
    saldo_usd: float,
    fecha_vencimiento: str | None = None,
    estado_actual: str | None = None,
) -> str:
    saldo = float(money(saldo_usd or 0.0))
    if saldo <= 0:
        return "pagada"

    estado_norm = clean_text(estado_actual).lower()
    if estado_norm == "incobrable":
        return "incobrable"

    if fecha_vencimiento:
        try:
            if date.fromisoformat(str(fecha_vencimiento)[:10]) < date.today():
                return "vencida"
        except ValueError:
            pass

    return "parcial" if saldo > 0 and estado_norm in {"parcial", "vencida"} else "pendiente"


def registrar_abono_cuenta_por_cobrar(conn: Any, *, usuario: str, payload: CobranzaInput) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT id, cliente_id, venta_id, monto_original_usd, monto_cobrado_usd, saldo_usd, fecha_vencimiento, estado
        FROM cuentas_por_cobrar
        WHERE id=?
        """,
        (int(payload.cuenta_por_cobrar_id),),
    ).fetchone()
    if not row:
        raise ValueError("La cuenta por cobrar no existe")

    if clean_text(row["estado"]).lower() == "incobrable":
        raise ValueError("La cuenta por cobrar está marcada como incobrable")

    saldo_actual = float(money(row["saldo_usd"] or 0.0))
    if saldo_actual <= 0:
        raise ValueError("La cuenta por cobrar ya está pagada")

    monto = float(money(as_positive(payload.monto_usd, "Monto abono", allow_zero=False)))
    if monto > saldo_actual:
        raise ValueError(f"El abono ({monto:,.2f}) no puede ser mayor al saldo ({saldo_actual:,.2f})")

    tasa = as_positive(payload.tasa_cambio, "Tasa de cambio", allow_zero=False)
    monto_moneda = float(money(monto if payload.monto_moneda_pago is None else as_positive(payload.monto_moneda_pago, "Monto moneda", allow_zero=False)))

    cur_pago = conn.execute(
        """
        INSERT INTO pagos_clientes
        (usuario, cuenta_por_cobrar_id, cliente_id, venta_id, monto_usd,
         moneda_pago, monto_moneda_pago, tasa_cambio, referencia, observaciones,
         promesa_pago_fecha, proxima_gestion_fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(usuario or "Sistema"),
            int(row["id"]),
            int(row["cliente_id"]),
            int(row["venta_id"]) if row["venta_id"] is not None else None,
            monto,
            clean_text(payload.moneda_pago).upper() or "USD",
            monto_moneda,
            float(tasa),
            clean_text(payload.referencia) or None,
            clean_text(payload.observaciones) or None,
            clean_text(payload.promesa_pago_fecha) or None,
            clean_text(payload.proxima_gestion_fecha) or None,
        ),
    )
    pago_id = int(cur_pago.lastrowid)

    nuevo_cobrado = float(money((row["monto_cobrado_usd"] or 0.0) + monto))
    nuevo_saldo = float(money(max(saldo_actual - monto, 0.0)))
    nuevo_estado = "parcial" if nuevo_saldo > 0 else "pagada"

    if nuevo_saldo > 0:
        nuevo_estado = calcular_estado_cxc(
            saldo_usd=nuevo_saldo,
            fecha_vencimiento=row["fecha_vencimiento"],
            estado_actual=nuevo_estado,
        )

    conn.execute(
        """
        UPDATE cuentas_por_cobrar
        SET monto_cobrado_usd=?,
            saldo_usd=?,
            estado=?
        WHERE id=?
        """,
        (nuevo_cobrado, nuevo_saldo, nuevo_estado, int(row["id"])),
    )

    conn.execute(
        """
        UPDATE clientes
        SET saldo_por_cobrar_usd = CASE
            WHEN COALESCE(saldo_por_cobrar_usd, 0) - ? < 0 THEN 0
            ELSE COALESCE(saldo_por_cobrar_usd, 0) - ?
        END
        WHERE id=?
        """,
        (monto, monto, int(row["cliente_id"])),
    )

    movimiento_id = registrar_ingreso(
        conn,
        origen="cobro_cliente",
        referencia_id=pago_id,
        descripcion=f"Abono CxC venta #{int(row['venta_id'] or 0)}",
        monto_usd=monto,
        moneda=clean_text(payload.moneda_pago).upper() or "USD",
        monto_moneda=monto_moneda,
        tasa_cambio=float(tasa),
        metodo_pago=clean_text(payload.metodo_pago).lower() or "efectivo",
        usuario=str(usuario or "Sistema"),
        metadata={
            "pago_cliente_id": pago_id,
            "cuenta_por_cobrar_id": int(row["id"]),
            "venta_id": int(row["venta_id"]) if row["venta_id"] is not None else None,
            "cliente_id": int(row["cliente_id"]),
        },
    )

    contabilizar_cobro_cliente(conn, movimiento_id=movimiento_id, usuario=str(usuario or "Sistema"))

    return {
        "pago_id": pago_id,
        "movimiento_tesoreria_id": int(movimiento_id),
        "cuenta_por_cobrar_id": int(row["id"]),
        "nuevo_saldo_usd": nuevo_saldo,
        "nuevo_estado": nuevo_estado,
    }


def registrar_gestion_cobranza(
    conn: Any,
    *,
    usuario: str,
    cuenta_por_cobrar_id: int,
    observaciones: str,
    promesa_pago_fecha: str | None = None,
    proxima_gestion_fecha: str | None = None,
) -> int:
    cuenta = conn.execute(
        "SELECT id FROM cuentas_por_cobrar WHERE id=?",
        (int(cuenta_por_cobrar_id),),
    ).fetchone()
    if not cuenta:
        raise ValueError("Cuenta por cobrar no encontrada")

    cur = conn.execute(
        """
        INSERT INTO gestiones_cobranza
        (usuario, cuenta_por_cobrar_id, observaciones, promesa_pago_fecha, proxima_gestion_fecha)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(usuario or "Sistema"),
            int(cuenta_por_cobrar_id),
            clean_text(observaciones),
            clean_text(promesa_pago_fecha) or None,
            clean_text(proxima_gestion_fecha) or None,
        ),
    )
    return int(cur.lastrowid)


def marcar_cuenta_incobrable(conn: Any, *, cuenta_por_cobrar_id: int, usuario: str, motivo: str = "") -> None:
    cuenta = conn.execute(
        "SELECT id, saldo_usd FROM cuentas_por_cobrar WHERE id=?",
        (int(cuenta_por_cobrar_id),),
    ).fetchone()
    if not cuenta:
        raise ValueError("Cuenta por cobrar no encontrada")
    if float(money(cuenta["saldo_usd"] or 0.0)) <= 0:
        raise ValueError("No se puede marcar como incobrable una cuenta sin saldo")

    conn.execute(
        "UPDATE cuentas_por_cobrar SET estado='incobrable' WHERE id=?",
        (int(cuenta_por_cobrar_id),),
    )
    if motivo:
        registrar_gestion_cobranza(
            conn,
            usuario=usuario,
            cuenta_por_cobrar_id=int(cuenta_por_cobrar_id),
            observaciones=f"Marcada incobrable: {clean_text(motivo)}",
        )


def obtener_reporte_cartera(conn: Any) -> dict[str, pd.DataFrame]:
    cartera = pd.read_sql_query(
        """
        SELECT
            cxc.id,
            cxc.fecha,
            cxc.estado,
            cxc.cliente_id,
            COALESCE(c.nombre, 'Sin cliente') AS cliente,
            cxc.venta_id,
            cxc.monto_original_usd,
            cxc.monto_cobrado_usd,
            cxc.saldo_usd,
            cxc.fecha_vencimiento,
            cxc.dias_vencimiento,
            cxc.notas
        FROM cuentas_por_cobrar cxc
        LEFT JOIN clientes c ON c.id = cxc.cliente_id
        WHERE COALESCE(cxc.saldo_usd, 0) > 0
           OR cxc.estado IN ('incobrable')
        ORDER BY CASE WHEN cxc.fecha_vencimiento IS NULL THEN 1 ELSE 0 END,
                 date(cxc.fecha_vencimiento),
                 cxc.id DESC
        """,
        conn,
    )

    if cartera.empty:
        empty = pd.DataFrame()
        return {
            "cartera": empty,
            "top_deudores": empty,
            "antiguedad": empty,
            "vencimientos": empty,
            "historial_abonos": empty,
        }

    cartera["fecha_vencimiento"] = pd.to_datetime(cartera["fecha_vencimiento"], errors="coerce")
    hoy = pd.Timestamp.today().normalize()
    cartera["dias_mora"] = (hoy - cartera["fecha_vencimiento"]).dt.days
    cartera.loc[cartera["fecha_vencimiento"].isna(), "dias_mora"] = 0

    top_deudores = (
        cartera.groupby(["cliente_id", "cliente"], as_index=False)["saldo_usd"]
        .sum()
        .sort_values("saldo_usd", ascending=False)
        .head(10)
    )

    bins = [-1, 0, 30, 60, 90, 999999]
    labels = ["Al día", "1-30", "31-60", "61-90", "+90"]
    cartera["bucket"] = pd.cut(cartera["dias_mora"], bins=bins, labels=labels)
    antiguedad = (
        cartera.groupby("bucket", as_index=False, observed=False)["saldo_usd"]
        .sum()
        .rename(columns={"bucket": "rango"})
    )

    vencimientos = cartera[cartera["fecha_vencimiento"].notna()].copy()
    vencimientos = vencimientos.sort_values("fecha_vencimiento").head(50)

    historial_abonos = pd.read_sql_query(
        """
        SELECT
            p.id,
            p.fecha,
            p.cuenta_por_cobrar_id,
            p.venta_id,
            COALESCE(c.nombre, 'Sin cliente') AS cliente,
            p.monto_usd,
            p.metodo_pago,
            p.referencia,
            p.observaciones,
            p.promesa_pago_fecha,
            p.proxima_gestion_fecha
        FROM pagos_clientes p
        LEFT JOIN clientes c ON c.id = p.cliente_id
        ORDER BY datetime(p.fecha) DESC, p.id DESC
        LIMIT 200
        """,
        conn,
    )

    return {
        "cartera": cartera,
        "top_deudores": top_deudores,
        "antiguedad": antiguedad,
        "vencimientos": vencimientos,
        "historial_abonos": historial_abonos,
    }
