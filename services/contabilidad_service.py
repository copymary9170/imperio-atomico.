from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from modules.common import money


@dataclass(frozen=True)
class AsientoLinea:
    cuenta_codigo: str
    debe_usd: float = 0.0
    haber_usd: float = 0.0
    descripcion: str = ""
    tercero_tipo: str | None = None
    tercero_id: int | None = None


def _metodo_a_cuenta_caja_banco(metodo_pago: str) -> str:
    metodo = str(metodo_pago or "").strip().lower()
    return "110101" if metodo in {"efectivo", "cash", "caja"} else "110201"


def _asiento_existe(conn: Any, *, evento_tipo: str, referencia_tabla: str, referencia_id: int) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM asientos_contables
        WHERE evento_tipo=? AND referencia_tabla=? AND referencia_id=?
        LIMIT 1
        """,
        (evento_tipo, referencia_tabla, int(referencia_id)),
    ).fetchone()
    return bool(row)


def crear_asiento(
    conn: Any,
    *,
    fecha: str,
    evento_tipo: str,
    referencia_tabla: str,
    referencia_id: int,
    descripcion: str,
    usuario: str,
    lineas: list[AsientoLinea],
) -> int:
    if not lineas:
        raise ValueError("El asiento contable requiere al menos una línea")

    total_debe = round(sum(float(l.debe_usd or 0.0) for l in lineas), 2)
    total_haber = round(sum(float(l.haber_usd or 0.0) for l in lineas), 2)
    if abs(total_debe - total_haber) > 0.01:
        raise ValueError("El asiento está descuadrado")

    cur = conn.execute(
        """
        INSERT INTO asientos_contables
        (fecha, evento_tipo, referencia_tabla, referencia_id, descripcion,
         total_debe_usd, total_haber_usd, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            evento_tipo,
            referencia_tabla,
            int(referencia_id),
            str(descripcion),
            float(total_debe),
            float(total_haber),
            str(usuario or "Sistema"),
        ),
    )
    asiento_id = int(cur.lastrowid)

    conn.executemany(
        """
        INSERT INTO asientos_contables_detalle
        (asiento_id, cuenta_codigo, descripcion, tercero_tipo, tercero_id, debe_usd, haber_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                asiento_id,
                ln.cuenta_codigo,
                ln.descripcion,
                ln.tercero_tipo,
                int(ln.tercero_id) if ln.tercero_id is not None else None,
                float(money(ln.debe_usd)),
                float(money(ln.haber_usd)),
            )
            for ln in lineas
        ],
    )
    return asiento_id


def contabilizar_venta(conn: Any, venta_id: int, usuario: str = "Sistema") -> int | None:
    venta = conn.execute(
        """
        SELECT id, fecha, cliente_id, metodo_pago, subtotal_usd, impuesto_usd, total_usd
        FROM ventas
        WHERE id=?
        """,
        (int(venta_id),),
    ).fetchone()
    if not venta:
        return None

    metodo = str(venta["metodo_pago"] or "").lower()
    evento_tipo = "venta_credito" if metodo == "credito" else "venta_contado"
    if _asiento_existe(conn, evento_tipo=evento_tipo, referencia_tabla="ventas", referencia_id=int(venta["id"])):
        return None

    cuenta_cobro = "120101" if metodo == "credito" else _metodo_a_cuenta_caja_banco(metodo)
    subtotal = float(money(venta["subtotal_usd"] or 0.0))
    impuesto = float(money(venta["impuesto_usd"] or 0.0))
    total = float(money(venta["total_usd"] or (subtotal + impuesto)))

    lineas = [
        AsientoLinea(cuenta_codigo=cuenta_cobro, debe_usd=total, descripcion=f"Venta #{int(venta['id'])}", tercero_tipo="cliente", tercero_id=venta["cliente_id"]),
        AsientoLinea(cuenta_codigo="410101", haber_usd=subtotal, descripcion="Ingreso por venta", tercero_tipo="cliente", tercero_id=venta["cliente_id"]),
    ]
    if impuesto > 0:
        lineas.append(
            AsientoLinea(cuenta_codigo="210301", haber_usd=impuesto, descripcion="IVA débito fiscal", tercero_tipo="cliente", tercero_id=venta["cliente_id"])
        )

    return crear_asiento(
        conn,
        fecha=str(venta["fecha"]),
        evento_tipo=evento_tipo,
        referencia_tabla="ventas",
        referencia_id=int(venta["id"]),
        descripcion=f"Contabilización automática venta #{int(venta['id'])}",
        usuario=usuario,
        lineas=lineas,
    )


ef contabilizar_cobro_cliente(conn: Any, movimiento_id: int, usuario: str = "Sistema") -> int | None:
    mov = conn.execute(
        """
        SELECT id, fecha, referencia_id, metodo_pago, monto_usd, metadata
        FROM movimientos_tesoreria
        WHERE id=? AND origen='cobro_cliente' AND estado='confirmado'
        """,
        (int(movimiento_id),),
    ).fetchone()
    if not mov:
        return None

    if _asiento_existe(conn, evento_tipo="cobro_cliente", referencia_tabla="movimientos_tesoreria", referencia_id=int(mov["id"])):
        return None

    metadata = {}
    try:
        metadata = json.loads(str(mov["metadata"] or "{}"))
    except Exception:
        metadata = {}

    cliente_id = None
    venta_id = None
    pago_cliente_id = metadata.get("pago_cliente_id")
    if pago_cliente_id:
        pago = conn.execute(
            """
            SELECT cliente_id, venta_id
            FROM pagos_clientes
            WHERE id=?
            """,
            (int(pago_cliente_id),),
        ).fetchone()
        if pago:
            cliente_id = int(pago["cliente_id"]) if pago["cliente_id"] is not None else None
            venta_id = int(pago["venta_id"]) if pago["venta_id"] is not None else None

    if cliente_id is None:
        venta = conn.execute("SELECT id, cliente_id FROM ventas WHERE id=?", (int(mov["referencia_id"] or 0),)).fetchone()
        cliente_id = int(venta["cliente_id"]) if venta and venta["cliente_id"] is not None else None
        venta_id = int(venta["id"]) if venta else None

    monto = float(money(mov["monto_usd"] or 0.0))
    cuenta_financiera = _metodo_a_cuenta_caja_banco(str(mov["metodo_pago"] or ""))

    return crear_asiento(
        conn,
        fecha=str(mov["fecha"]),
        evento_tipo="cobro_cliente",
        referencia_tabla="movimientos_tesoreria",
        referencia_id=int(mov["id"]),
        descripcion=f"Cobro de cuenta por cobrar venta #{int(venta_id or mov['referencia_id'] or 0)}",
        usuario=usuario,
        lineas=[
            AsientoLinea(cuenta_codigo=cuenta_financiera, debe_usd=monto, descripcion="Entrada de tesorería", tercero_tipo="cliente", tercero_id=cliente_id),
            AsientoLinea(cuenta_codigo="120101", haber_usd=monto, descripcion="Aplicación CxC", tercero_tipo="cliente", tercero_id=cliente_id),
        ],
    )


def contabilizar_compra(conn: Any, compra_id: int, usuario: str = "Sistema") -> int | None:
    compra = conn.execute(
        """
        SELECT id, fecha, proveedor_id, costo_total_usd, tipo_pago
        FROM historial_compras
        WHERE id=? AND COALESCE(activo,1)=1
        """,
        (int(compra_id),),
    ).fetchone()
    if not compra:
        return None

    tipo_pago = str(compra["tipo_pago"] or "contado").lower()
    evento_tipo = "compra_contado" if tipo_pago == "contado" else "compra_credito"
    if _asiento_existe(conn, evento_tipo=evento_tipo, referencia_tabla="historial_compras", referencia_id=int(compra["id"])):
        return None

    total = float(money(compra["costo_total_usd"] or 0.0))
    lineas = [
        AsientoLinea(cuenta_codigo="130101", debe_usd=total, descripcion=f"Compra #{int(compra['id'])}", tercero_tipo="proveedor", tercero_id=compra["proveedor_id"]),
    ]
    if tipo_pago == "contado":
        lineas.append(
            AsientoLinea(cuenta_codigo="110101", haber_usd=total, descripcion="Salida de caja", tercero_tipo="proveedor", tercero_id=compra["proveedor_id"])
        )
    else:
        lineas.append(
            AsientoLinea(cuenta_codigo="220101", haber_usd=total, descripcion="Registro de CxP", tercero_tipo="proveedor", tercero_id=compra["proveedor_id"])
        )

    return crear_asiento(
        conn,
        fecha=str(compra["fecha"]),
        evento_tipo=evento_tipo,
        referencia_tabla="historial_compras",
        referencia_id=int(compra["id"]),
        descripcion=f"Contabilización automática compra #{int(compra['id'])}",
        usuario=usuario,
        lineas=lineas,
    )


def contabilizar_pago_proveedor(conn: Any, pago_id: int, usuario: str = "Sistema") -> int | None:
    pago = conn.execute(
        """
        SELECT
            p.id,
            p.fecha,
            p.proveedor_id,
            p.monto_usd,
            p.moneda_pago,
            p.cuenta_por_pagar_id,
            cxp.compra_id
        FROM pagos_proveedores p
        INNER JOIN cuentas_por_pagar_proveedores cxp ON cxp.id = p.cuenta_por_pagar_id
        WHERE p.id=?
        """,
        (int(pago_id),),
    ).fetchone()
    if not pago:
        return None

    if _asiento_existe(conn, evento_tipo="pago_proveedor", referencia_tabla="pagos_proveedores", referencia_id=int(pago["id"])):
        return None

    monto = float(money(pago["monto_usd"] or 0.0))
    cuenta_financiera = _metodo_a_cuenta_caja_banco(str(pago["moneda_pago"] or ""))

    return crear_asiento(
        conn,
        fecha=str(pago["fecha"]),
        evento_tipo="pago_proveedor",
        referencia_tabla="pagos_proveedores",
        referencia_id=int(pago["id"]),
        descripcion=f"Pago a proveedor compra #{int(pago['compra_id'])}",
        usuario=usuario,
        lineas=[
            AsientoLinea(cuenta_codigo="220101", debe_usd=monto, descripcion="Aplicación CxP", tercero_tipo="proveedor", tercero_id=pago["proveedor_id"]),
            AsientoLinea(cuenta_codigo=cuenta_financiera, haber_usd=monto, descripcion="Salida de tesorería", tercero_tipo="proveedor", tercero_id=pago["proveedor_id"]),
        ],
    )


def contabilizar_gasto(conn: Any, gasto_id: int, usuario: str = "Sistema") -> int | None:
    gasto = conn.execute(
        """
        SELECT id, fecha, descripcion, metodo_pago, monto_usd
        FROM gastos
        WHERE id=? AND estado='activo'
        """,
        (int(gasto_id),),
    ).fetchone()
    if not gasto:
        return None

    if _asiento_existe(conn, evento_tipo="gasto_pagado", referencia_tabla="gastos", referencia_id=int(gasto["id"])):
        return None

    monto = float(money(gasto["monto_usd"] or 0.0))
    cuenta_financiera = _metodo_a_cuenta_caja_banco(str(gasto["metodo_pago"] or ""))

    return crear_asiento(
        conn,
        fecha=str(gasto["fecha"]),
        evento_tipo="gasto_pagado",
        referencia_tabla="gastos",
        referencia_id=int(gasto["id"]),
        descripcion=f"Gasto pagado #{int(gasto['id'])}: {gasto['descripcion']}",
        usuario=usuario,
        lineas=[
            AsientoLinea(cuenta_codigo="510101", debe_usd=monto, descripcion=str(gasto["descripcion"])),
            AsientoLinea(cuenta_codigo=cuenta_financiera, haber_usd=monto, descripcion="Salida de tesorería"),
        ],
    )


def contabilizar_ajuste_manual_tesoreria(conn: Any, movimiento_id: int, usuario: str = "Sistema") -> int | None:
    mov = conn.execute(
        """
        SELECT id, fecha, tipo, metodo_pago, monto_usd, descripcion
        FROM movimientos_tesoreria
        WHERE id=? AND origen='ajuste_manual' AND estado='confirmado'
        """,
        (int(movimiento_id),),
    ).fetchone()
    if not mov:
        return None

    if _asiento_existe(conn, evento_tipo="ajuste_manual_tesoreria", referencia_tabla="movimientos_tesoreria", referencia_id=int(mov["id"])):
        return None

    monto = float(money(mov["monto_usd"] or 0.0))
    cuenta_financiera = _metodo_a_cuenta_caja_banco(str(mov["metodo_pago"] or ""))

    if str(mov["tipo"]).lower() == "ingreso":
        lineas = [
            AsientoLinea(cuenta_codigo=cuenta_financiera, debe_usd=monto, descripcion="Ingreso por ajuste"),
            AsientoLinea(cuenta_codigo="420101", haber_usd=monto, descripcion=str(mov["descripcion"] or "Ajuste manual")),
        ]
    else:
        lineas = [
            AsientoLinea(cuenta_codigo="590101", debe_usd=monto, descripcion=str(mov["descripcion"] or "Ajuste manual")),
            AsientoLinea(cuenta_codigo=cuenta_financiera, haber_usd=monto, descripcion="Egreso por ajuste"),
        ]

    return crear_asiento(
        conn,
        fecha=str(mov["fecha"]),
        evento_tipo="ajuste_manual_tesoreria",
        referencia_tabla="movimientos_tesoreria",
        referencia_id=int(mov["id"]),
        descripcion=f"Ajuste manual de tesorería #{int(mov['id'])}",
        usuario=usuario,
        lineas=lineas,
    )


def sincronizar_contabilidad(conn: Any, usuario: str = "Sistema") -> dict[str, int]:
    resumen = {
        "ventas": 0,
        "cobros": 0,
        "compras": 0,
        "pagos_proveedores": 0,
        "gastos": 0,
        "ajustes": 0,
    }

    for row in conn.execute("SELECT id FROM ventas ORDER BY id").fetchall():
        if contabilizar_venta(conn, int(row["id"]), usuario=usuario):
            resumen["ventas"] += 1

    for row in conn.execute("SELECT id FROM movimientos_tesoreria WHERE origen='cobro_cliente' AND estado='confirmado' ORDER BY id").fetchall():
        if contabilizar_cobro_cliente(conn, int(row["id"]), usuario=usuario):
            resumen["cobros"] += 1

    compras_activo = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='historial_compras'").fetchone()
    if compras_activo:
        for row in conn.execute("SELECT id FROM historial_compras WHERE COALESCE(activo,1)=1 ORDER BY id").fetchall():
            if contabilizar_compra(conn, int(row["id"]), usuario=usuario):
                resumen["compras"] += 1

    for row in conn.execute("SELECT id FROM pagos_proveedores ORDER BY id").fetchall():
        if contabilizar_pago_proveedor(conn, int(row["id"]), usuario=usuario):
            resumen["pagos_proveedores"] += 1

    for row in conn.execute("SELECT id FROM gastos WHERE estado='activo' ORDER BY id").fetchall():
        if contabilizar_gasto(conn, int(row["id"]), usuario=usuario):
            resumen["gastos"] += 1

    for row in conn.execute("SELECT id FROM movimientos_tesoreria WHERE origen='ajuste_manual' AND estado='confirmado' ORDER BY id").fetchall():
        if contabilizar_ajuste_manual_tesoreria(conn, int(row["id"]), usuario=usuario):
            resumen["ajustes"] += 1

    return resumen


def obtener_libro_diario(conn: Any, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> pd.DataFrame:
    filtros = []
    params: list[Any] = []
    if fecha_desde:
        filtros.append("date(a.fecha) >= date(?)")
        params.append(fecha_desde)
    if fecha_hasta:
        filtros.append("date(a.fecha) <= date(?)")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    query = f"""
        SELECT
            a.id AS asiento_id,
            a.fecha,
            a.evento_tipo,
            a.descripcion AS asiento_descripcion,
            d.cuenta_codigo,
            c.nombre AS cuenta_nombre,
            d.descripcion AS linea_descripcion,
            d.debe_usd,
            d.haber_usd,
            a.referencia_tabla,
            a.referencia_id
        FROM asientos_contables a
        INNER JOIN asientos_contables_detalle d ON d.asiento_id = a.id
        LEFT JOIN catalogo_cuentas c ON c.codigo = d.cuenta_codigo
        {where_sql}
        ORDER BY datetime(a.fecha) DESC, a.id DESC, d.id ASC
    """
    return pd.read_sql_query(query, conn, params=params)


def obtener_libro_mayor(conn: Any, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> pd.DataFrame:
    filtros = []
    params: list[Any] = []
    if fecha_desde:
        filtros.append("date(a.fecha) >= date(?)")
        params.append(fecha_desde)
    if fecha_hasta:
        filtros.append("date(a.fecha) <= date(?)")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    query = f"""
        SELECT
            d.cuenta_codigo,
            COALESCE(c.nombre, d.cuenta_codigo) AS cuenta_nombre,
            ROUND(SUM(d.debe_usd), 2) AS total_debe_usd,
            ROUND(SUM(d.haber_usd), 2) AS total_haber_usd,
            ROUND(SUM(d.debe_usd - d.haber_usd), 2) AS saldo_neto_usd,
            COUNT(DISTINCT d.asiento_id) AS asientos
        FROM asientos_contables_detalle d
        INNER JOIN asientos_contables a ON a.id = d.asiento_id
        LEFT JOIN catalogo_cuentas c ON c.codigo = d.cuenta_codigo
        {where_sql}
        GROUP BY d.cuenta_codigo, COALESCE(c.nombre, d.cuenta_codigo)
        ORDER BY d.cuenta_codigo
    """
    return pd.read_sql_query(query, conn, params=params)


def obtener_resumen_contable(conn: Any, fecha_desde: str | None = None, fecha_hasta: str | None = None) -> dict[str, float]:
    diario = obtener_libro_diario(conn, fecha_desde, fecha_hasta)
    if diario.empty:
        return {
            "asientos": 0,
            "lineas": 0,
            "debe_usd": 0.0,
            "haber_usd": 0.0,
        }

    return {
        "asientos": int(diario["asiento_id"].nunique()),
        "lineas": int(len(diario.index)),
        "debe_usd": round(float(diario["debe_usd"].sum()), 2),
        "haber_usd": round(float(diario["haber_usd"].sum()), 2),
    }
