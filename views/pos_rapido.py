from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

SERVICIOS_RAPIDOS = [
    {"codigo": "COP-BN", "nombre": "Copia B/N", "precio": 0.10, "tipo": "impresion", "clics": 1},
    {"codigo": "COP-COLOR", "nombre": "Copia Color", "precio": 0.50, "tipo": "impresion", "clics": 1},
    {"codigo": "IMP-BN", "nombre": "Impresion B/N", "precio": 0.15, "tipo": "impresion", "clics": 1},
    {"codigo": "IMP-COLOR", "nombre": "Impresion Color", "precio": 0.60, "tipo": "impresion", "clics": 1},
    {"codigo": "SCAN", "nombre": "Escaneo", "precio": 0.25, "tipo": "servicio", "clics": 0},
    {"codigo": "PLAST", "nombre": "Plastificado", "precio": 1.00, "tipo": "servicio", "clics": 0},
]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_pos_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pos_ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                cliente TEXT NOT NULL DEFAULT 'Cliente General',
                subtotal_usd REAL NOT NULL DEFAULT 0,
                descuento_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                efectivo_recibido_usd REAL NOT NULL DEFAULT 0,
                vuelto_usd REAL NOT NULL DEFAULT 0,
                metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
                moneda TEXT NOT NULL DEFAULT 'USD',
                notas TEXT,
                estado TEXT NOT NULL DEFAULT 'pagada'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pos_venta_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                codigo TEXT,
                descripcion TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'servicio',
                cantidad REAL NOT NULL DEFAULT 1,
                precio_unitario_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                clics_cobrados INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (venta_id) REFERENCES pos_ventas(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comprobantes_pos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Ticket',
                cliente TEXT NOT NULL DEFAULT 'Cliente General',
                telefono TEXT,
                venta_id INTEGER,
                referencia TEXT,
                metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
                subtotal_usd REAL NOT NULL DEFAULT 0,
                descuento_usd REAL NOT NULL DEFAULT 0,
                impuesto_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                monto_recibido_usd REAL NOT NULL DEFAULT 0,
                vuelto_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Emitido',
                notas TEXT,
                cuerpo TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comprobantes_pos_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comprobante_id INTEGER NOT NULL,
                descripcion TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 1,
                precio_unitario_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (comprobante_id) REFERENCES comprobantes_pos(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_ventas_fecha ON pos_ventas(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_detalle_venta ON pos_venta_detalle(venta_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comprobantes_pos_fecha ON comprobantes_pos(fecha)")


def _build_comprobante_body(*, comprobante_id: int | None, cliente: str, metodo: str, items: list[dict[str, Any]], subtotal: float, descuento: float, total: float, recibido: float, vuelto: float, referencia: str, notas: str) -> str:
    numero = f"#{comprobante_id:06d}" if comprobante_id else "BORRADOR"
    lines = [
        "⚛️ IMPERIO ATÓMICO",
        f"TICKET POS {numero}",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Cliente: {cliente or 'Cliente General'}",
        f"Referencia: {referencia}",
        "-" * 34,
    ]
    for item in items:
        desc = str(item.get("descripcion") or "Item")
        cantidad = float(item.get("cantidad") or 0)
        precio = float(item.get("precio") or 0)
        total_item = float(item.get("total_usd") or 0)
        lines.append(desc)
        lines.append(f"  {cantidad:,.2f} x ${precio:,.2f} = ${total_item:,.2f}")
    lines.extend([
        "-" * 34,
        f"Subtotal: ${subtotal:,.2f}",
        f"Descuento: ${descuento:,.2f}",
        f"TOTAL: ${total:,.2f}",
        f"Método: {metodo}",
        f"Recibido: ${recibido:,.2f}",
        f"Vuelto: ${vuelto:,.2f}",
    ])
    if notas:
        lines.extend(["-" * 34, f"Notas: {notas}"])
    lines.extend(["-" * 34, "Gracias por su compra."])
    return "\n".join(lines)


def _create_pos_comprobante(conn, *, usuario: str, pos_id: int, cliente: str, items: list[dict[str, Any]], subtotal: float, descuento: float, total: float, efectivo: float, vuelto: float, metodo: str, notas: str) -> int:
    referencia = f"POS-{pos_id}"
    existing = conn.execute("SELECT id FROM comprobantes_pos WHERE referencia=?", (referencia,)).fetchone()
    if existing:
        return int(existing[0])
    cuerpo = _build_comprobante_body(comprobante_id=None, cliente=cliente, metodo=metodo, items=items, subtotal=subtotal, descuento=descuento, total=total, recibido=efectivo, vuelto=vuelto, referencia=referencia, notas=notas)
    cur = conn.execute(
        """
        INSERT INTO comprobantes_pos(usuario, tipo, cliente, venta_id, referencia, metodo_pago, subtotal_usd, descuento_usd, impuesto_usd, total_usd, monto_recibido_usd, vuelto_usd, estado, notas, cuerpo)
        VALUES (?, 'Ticket', ?, NULL, ?, ?, ?, ?, 0, ?, ?, ?, 'Emitido', ?, ?)
        """,
        (usuario, cliente or "Cliente General", referencia, metodo, float(subtotal), float(descuento or 0), float(total), float(efectivo or 0), float(vuelto or 0), notas, cuerpo),
    )
    comp_id = int(cur.lastrowid)
    cuerpo_final = _build_comprobante_body(comprobante_id=comp_id, cliente=cliente, metodo=metodo, items=items, subtotal=subtotal, descuento=descuento, total=total, recibido=efectivo, vuelto=vuelto, referencia=referencia, notas=notas)
    conn.execute("UPDATE comprobantes_pos SET cuerpo=? WHERE id=?", (cuerpo_final, comp_id))
    for item in items:
        conn.execute(
            "INSERT INTO comprobantes_pos_items(comprobante_id, descripcion, cantidad, precio_unitario_usd, total_usd) VALUES (?, ?, ?, ?, ?)",
            (comp_id, item.get("descripcion", ""), float(item.get("cantidad", 1)), float(item.get("precio", 0)), float(item.get("total_usd", 0))),
        )
    return comp_id


def _load_pos_history() -> pd.DataFrame:
    _ensure_pos_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT p.id, p.fecha, p.usuario, p.cliente, p.total_usd, p.metodo_pago, p.efectivo_recibido_usd, p.vuelto_usd, p.estado,
                   c.id AS comprobante_id
            FROM pos_ventas p
            LEFT JOIN comprobantes_pos c ON c.referencia = ('POS-' || p.id)
            ORDER BY p.id DESC
            LIMIT 200
            """,
            conn,
        )


def _save_sale(usuario: str, cliente: str, items: list[dict[str, Any]], descuento: float, efectivo: float, metodo: str, moneda: str, notas: str, generar_comprobante: bool = True) -> tuple[int, int | None]:
    subtotal = sum(float(i["total_usd"]) for i in items)
    total = max(0.0, subtotal - float(descuento or 0))
    vuelto = max(0.0, float(efectivo or 0) - total) if metodo == "efectivo" else 0.0
    _ensure_pos_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO pos_ventas(usuario, cliente, subtotal_usd, descuento_usd, total_usd, efectivo_recibido_usd, vuelto_usd, metodo_pago, moneda, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, cliente or "Cliente General", subtotal, float(descuento or 0), total, float(efectivo or 0), vuelto, metodo, moneda, notas),
        )
        venta_id = int(cur.lastrowid)
        for item in items:
            conn.execute(
                """
                INSERT INTO pos_venta_detalle(venta_id, codigo, descripcion, tipo, cantidad, precio_unitario_usd, total_usd, clics_cobrados)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venta_id,
                    item.get("codigo", ""),
                    item.get("descripcion", ""),
                    item.get("tipo", "servicio"),
                    float(item.get("cantidad", 1)),
                    float(item.get("precio", 0)),
                    float(item.get("total_usd", 0)),
                    int(item.get("clics_cobrados", 0)),
                ),
            )
        comp_id = _create_pos_comprobante(conn, usuario=usuario, pos_id=venta_id, cliente=cliente, items=items, subtotal=subtotal, descuento=float(descuento or 0), total=total, efectivo=float(efectivo or 0), vuelto=vuelto, metodo=metodo, notas=notas) if generar_comprobante else None
    return venta_id, comp_id


def render_pos_rapido(usuario: str = "Sistema") -> None:
    st.subheader("🖥️ POS / Facturación rápida")
    st.caption("Venta de mostrador con Cliente General, cobro rápido, vuelto, clics cobrados y comprobante automático.")
    _ensure_pos_tables()

    if "pos_items" not in st.session_state:
        st.session_state["pos_items"] = []

    col_a, col_b, col_c = st.columns([2, 1, 1])
    servicio = col_a.selectbox("Servicio rápido", SERVICIOS_RAPIDOS, format_func=lambda x: f"{x['codigo']} · {x['nombre']} · ${x['precio']:.2f}")
    cantidad = col_b.number_input("Cantidad", min_value=1.0, value=1.0, step=1.0)
    if col_c.button("Agregar", use_container_width=True):
        st.session_state["pos_items"].append({"codigo": servicio["codigo"], "descripcion": servicio["nombre"], "tipo": servicio["tipo"], "cantidad": float(cantidad), "precio": float(servicio["precio"]), "total_usd": float(cantidad) * float(servicio["precio"]), "clics_cobrados": int(float(cantidad) * int(servicio.get("clics", 0)))})
        st.rerun()

    with st.expander("Agregar item libre"):
        l1, l2, l3, l4 = st.columns([2, 1, 1, 1])
        desc = l1.text_input("Descripción")
        qty = l2.number_input("Cant.", min_value=1.0, value=1.0, step=1.0, key="pos_libre_qty")
        price = l3.number_input("Precio USD", min_value=0.0, value=0.0, step=0.05)
        clics = l4.number_input("Clics", min_value=0, value=0, step=1)
        if st.button("Agregar item libre", use_container_width=True):
            if desc.strip():
                st.session_state["pos_items"].append({"codigo": "LIBRE", "descripcion": desc.strip(), "tipo": "servicio", "cantidad": float(qty), "precio": float(price), "total_usd": float(qty) * float(price), "clics_cobrados": int(clics)})
                st.rerun()

    items = st.session_state.get("pos_items", [])
    if items:
        df = pd.DataFrame(items)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Agrega productos o servicios para cobrar.")

    subtotal = sum(float(i["total_usd"]) for i in items)
    clics = sum(int(i.get("clics_cobrados", 0)) for i in items)
    c1, c2, c3 = st.columns(3)
    c1.metric("Subtotal", f"${subtotal:,.2f}")
    c2.metric("Clics cobrados", clics)
    c3.metric("Items", len(items))

    cliente = st.text_input("Cliente", value="Cliente General")
    p1, p2, p3, p4 = st.columns(4)
    descuento = p1.number_input("Descuento USD", min_value=0.0, value=0.0, step=0.05)
    metodo = p2.selectbox("Método", ["efectivo", "transferencia", "tarjeta", "mixto"])
    moneda = p3.selectbox("Moneda", ["USD", "VES", "COP", "EUR"])
    efectivo = p4.number_input("Efectivo recibido USD", min_value=0.0, value=max(0.0, subtotal - descuento), step=0.05)
    generar_comprobante = st.checkbox("Generar comprobante automático", value=True)
    total = max(0.0, subtotal - descuento)
    vuelto = max(0.0, efectivo - total) if metodo == "efectivo" else 0.0
    st.metric("Total a cobrar", f"${total:,.2f}", f"Vuelto: ${vuelto:,.2f}")
    notas = st.text_area("Notas / archivo / instrucción rápida")

    b1, b2 = st.columns(2)
    if b1.button("Cobrar venta", type="primary", use_container_width=True, disabled=not bool(items)):
        venta_id, comp_id = _save_sale(usuario, cliente, items, descuento, efectivo, metodo, moneda, notas, generar_comprobante=generar_comprobante)
        st.session_state["pos_items"] = []
        comp_msg = f" · Comprobante #{comp_id:06d}" if comp_id else ""
        st.success(f"Venta POS #{venta_id} cobrada{comp_msg}. Total: ${total:,.2f}. Vuelto: ${vuelto:,.2f}")
        st.rerun()
    if b2.button("Vaciar ticket", use_container_width=True):
        st.session_state["pos_items"] = []
        st.rerun()

    st.divider()
    st.subheader("Historial POS")
    hist = _load_pos_history()
    if hist.empty:
        st.info("Sin ventas POS todavía.")
    else:
        st.dataframe(hist, use_container_width=True, hide_index=True)
