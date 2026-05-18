from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission

METODOS = ["efectivo", "transferencia", "zelle", "binance", "mixto"]
TIPOS = ["Ticket", "Factura rápida", "Nota de entrega", "Recibo"]


def _ensure_tables() -> None:
    with db_transaction() as conn:
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comprobantes_pos_fecha ON comprobantes_pos(fecha)")


def _load_comprobantes() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM comprobantes_pos ORDER BY id DESC LIMIT 300", conn)


def _safe_items_from_editor(df: pd.DataFrame) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if df is None or df.empty:
        return items
    for _, row in df.iterrows():
        descripcion = str(row.get("descripcion") or "").strip()
        if not descripcion:
            continue
        cantidad = float(row.get("cantidad") or 0)
        precio = float(row.get("precio_unitario_usd") or 0)
        total = cantidad * precio
        if cantidad <= 0:
            continue
        items.append({"descripcion": descripcion, "cantidad": cantidad, "precio_unitario_usd": precio, "total_usd": total})
    return items


def _build_body(*, comprobante_id: int | None, tipo: str, cliente: str, telefono: str, referencia: str, metodo: str, items: list[dict[str, Any]], subtotal: float, descuento: float, impuesto: float, total: float, recibido: float, vuelto: float, notas: str) -> str:
    numero = f"#{comprobante_id:06d}" if comprobante_id else "BORRADOR"
    lines = [
        "⚛️ IMPERIO ATÓMICO",
        f"{tipo.upper()} {numero}",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Cliente: {cliente or 'Cliente General'}",
    ]
    if telefono:
        lines.append(f"Teléfono: {telefono}")
    if referencia:
        lines.append(f"Referencia: {referencia}")
    lines.append("-" * 34)
    for item in items:
        lines.append(f"{item['descripcion']}")
        lines.append(f"  {item['cantidad']:,.2f} x ${item['precio_unitario_usd']:,.2f} = ${item['total_usd']:,.2f}")
    lines.extend([
        "-" * 34,
        f"Subtotal: ${subtotal:,.2f}",
        f"Descuento: ${descuento:,.2f}",
        f"Impuesto: ${impuesto:,.2f}",
        f"TOTAL: ${total:,.2f}",
        f"Método: {metodo}",
        f"Recibido: ${recibido:,.2f}",
        f"Vuelto: ${vuelto:,.2f}",
    ])
    if notas:
        lines.extend(["-" * 34, f"Notas: {notas}"])
    lines.extend(["-" * 34, "Gracias por su compra."])
    return "\n".join(lines)


def _save_comprobante(data: dict[str, Any], items: list[dict[str, Any]]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO comprobantes_pos(
                usuario, tipo, cliente, telefono, venta_id, referencia, metodo_pago,
                subtotal_usd, descuento_usd, impuesto_usd, total_usd, monto_recibido_usd,
                vuelto_usd, estado, notas, cuerpo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["tipo"], data["cliente"], data.get("telefono"), data.get("venta_id"),
                data.get("referencia"), data["metodo_pago"], float(data["subtotal_usd"]), float(data["descuento_usd"]),
                float(data["impuesto_usd"]), float(data["total_usd"]), float(data["monto_recibido_usd"]),
                float(data["vuelto_usd"]), data.get("estado", "Emitido"), data.get("notas"), data["cuerpo"],
            ),
        )
        comp_id = int(cur.lastrowid)
        cuerpo_final = _build_body(
            comprobante_id=comp_id,
            tipo=data["tipo"],
            cliente=data["cliente"],
            telefono=data.get("telefono") or "",
            referencia=data.get("referencia") or "",
            metodo=data["metodo_pago"],
            items=items,
            subtotal=float(data["subtotal_usd"]),
            descuento=float(data["descuento_usd"]),
            impuesto=float(data["impuesto_usd"]),
            total=float(data["total_usd"]),
            recibido=float(data["monto_recibido_usd"]),
            vuelto=float(data["vuelto_usd"]),
            notas=data.get("notas") or "",
        )
        conn.execute("UPDATE comprobantes_pos SET cuerpo=? WHERE id=?", (cuerpo_final, comp_id))
        for item in items:
            conn.execute(
                "INSERT INTO comprobantes_pos_items(comprobante_id, descripcion, cantidad, precio_unitario_usd, total_usd) VALUES (?, ?, ?, ?, ?)",
                (comp_id, item["descripcion"], item["cantidad"], item["precio_unitario_usd"], item["total_usd"]),
            )
        return comp_id


def render_ticket_pos(usuario: str = "Sistema") -> None:
    if not require_any_permission(["pos.view", "pos.ticket"], "🚫 No tienes acceso a tickets/comprobantes POS."):
        return

    puede_emitir = has_permission("pos.ticket")

    st.subheader("🧾 Ticket / comprobante POS")
    st.caption("Genera comprobantes rápidos para imprimir, copiar o enviar al cliente por WhatsApp/correo.")
    if not puede_emitir:
        st.info("Modo consulta: puedes ver historial y plantilla, pero no emitir nuevos comprobantes.")
    _ensure_tables()

    tab_nuevo, tab_historial, tab_plantilla = st.tabs(["Nuevo comprobante", "Historial", "Plantilla"])

    with tab_nuevo:
        base_items = pd.DataFrame([
            {"descripcion": "Impresión / producto", "cantidad": 1.0, "precio_unitario_usd": 0.0},
        ])
        a, b, c = st.columns(3)
        tipo = a.selectbox("Tipo", TIPOS, disabled=not puede_emitir)
        cliente = b.text_input("Cliente", value="Cliente General", disabled=not puede_emitir)
        telefono = c.text_input("Teléfono", disabled=not puede_emitir)
        d, e, f = st.columns(3)
        venta_id = d.number_input("Venta ID opcional", min_value=0, value=0, step=1, disabled=not puede_emitir)
        referencia = e.text_input("Referencia", disabled=not puede_emitir)
        metodo = f.selectbox("Método pago", METODOS, disabled=not puede_emitir)

        st.markdown("#### Items")
        items_df = st.data_editor(
            base_items,
            num_rows="dynamic",
            use_container_width=True,
            disabled=not puede_emitir,
            column_config={
                "descripcion": st.column_config.TextColumn("Descripción"),
                "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0, step=1.0),
                "precio_unitario_usd": st.column_config.NumberColumn("Precio unitario USD", min_value=0.0, step=0.01, format="$%.2f"),
            },
        )
        items = _safe_items_from_editor(items_df)
        subtotal = sum(item["total_usd"] for item in items)
        g, h, i = st.columns(3)
        descuento = g.number_input("Descuento USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_emitir)
        impuesto = h.number_input("Impuesto USD", min_value=0.0, value=0.0, step=0.01, disabled=not puede_emitir)
        total = max(subtotal - descuento + impuesto, 0.0)
        recibido = i.number_input("Monto recibido USD", min_value=0.0, value=float(total), step=0.01, disabled=not puede_emitir)
        vuelto = max(recibido - total, 0.0)
        notas = st.text_area("Notas", disabled=not puede_emitir)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Subtotal", f"${subtotal:,.2f}")
        m2.metric("Total", f"${total:,.2f}")
        m3.metric("Recibido", f"${recibido:,.2f}")
        m4.metric("Vuelto", f"${vuelto:,.2f}")

        cuerpo = _build_body(
            comprobante_id=None,
            tipo=tipo,
            cliente=cliente.strip() or "Cliente General",
            telefono=telefono.strip(),
            referencia=referencia.strip(),
            metodo=metodo,
            items=items,
            subtotal=subtotal,
            descuento=descuento,
            impuesto=impuesto,
            total=total,
            recibido=recibido,
            vuelto=vuelto,
            notas=notas.strip(),
        )
        st.markdown("#### Vista previa")
        st.code(cuerpo, language="text")

        col_a, col_b = st.columns(2)
        if col_a.button("Guardar comprobante", type="primary", disabled=not puede_emitir):
            if not items:
                st.error("Agrega al menos un item con cantidad válida.")
            elif recibido < total and metodo in {"efectivo", "mixto"}:
                st.error("El monto recibido no puede ser menor al total para efectivo/mixto.")
            else:
                comp_id = _save_comprobante({
                    "usuario": usuario,
                    "tipo": tipo,
                    "cliente": cliente.strip() or "Cliente General",
                    "telefono": telefono.strip(),
                    "venta_id": int(venta_id) or None,
                    "referencia": referencia.strip(),
                    "metodo_pago": metodo,
                    "subtotal_usd": subtotal,
                    "descuento_usd": descuento,
                    "impuesto_usd": impuesto,
                    "total_usd": total,
                    "monto_recibido_usd": recibido,
                    "vuelto_usd": vuelto,
                    "notas": notas.strip(),
                    "cuerpo": cuerpo,
                }, items)
                st.success(f"Comprobante #{comp_id:06d} guardado.")
                st.rerun()

        whatsapp_text = cuerpo.replace("\n", "%0A")
        col_b.markdown(f"[Abrir para WhatsApp](https://wa.me/?text={whatsapp_text})")

    with tab_historial:
        df = _load_comprobantes()
        if df.empty:
            st.info("No hay comprobantes emitidos.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            elegido = st.selectbox("Ver comprobante", df["id"].astype(int).tolist(), format_func=lambda x: f"#{x:06d}")
            cuerpo_hist = df.loc[df["id"].eq(elegido), "cuerpo"].iloc[0]
            st.code(cuerpo_hist, language="text")

    with tab_plantilla:
        st.markdown("#### Formato recomendado")
        st.code(
            """⚛️ IMPERIO ATÓMICO
TICKET #000001
Fecha: AAAA-MM-DD HH:MM
Cliente: Cliente General
----------------------------------
Producto / servicio
  Cantidad x Precio = Total
----------------------------------
Subtotal
Descuento
Impuesto
TOTAL
Método
Recibido
Vuelto
----------------------------------
Gracias por su compra.""",
            language="text",
        )
