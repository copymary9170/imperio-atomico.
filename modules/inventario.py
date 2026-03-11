from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


# ============================================================
# CREAR PRODUCTO
# ============================================================

def create_producto(
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    unidad: str,
    costo: float,
    precio: float,
    stock_inicial: float = 0.0,
    stock_minimo: float = 0.0,
) -> int:
    sku = require_text(sku, "SKU")
    nombre = require_text(nombre, "Producto")
    categoria = require_text(categoria, "Categoría")
    unidad = require_text(unidad, "Unidad")

    costo = as_positive(costo, "Costo")
    precio = as_positive(precio, "Precio")
    stock_inicial = as_positive(stock_inicial, "Stock inicial")
    stock_minimo = as_positive(stock_minimo, "Stock mínimo")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO inventario (
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                stock_actual,
                stock_minimo,
                costo_unitario_usd,
                precio_venta_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                stock_inicial,
                stock_minimo,
                money(costo),
                money(precio),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# MOVIMIENTOS INVENTARIO
# ============================================================

def add_inventory_movement(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
) -> None:
    if tipo not in {"entrada", "salida", "ajuste"}:
        raise ValueError("Tipo de movimiento inválido")

    costo_unitario_usd = as_positive(costo_unitario_usd, "Costo unitario")
    referencia = clean_text(referencia)

    if tipo == "ajuste":
        try:
            delta = float(cantidad)
        except (TypeError, ValueError):
            raise ValueError("Cantidad inválida")
        if delta == 0:
            raise ValueError("En ajuste la cantidad no puede ser 0")
    else:
        qty = as_positive(cantidad, "Cantidad", allow_zero=False)
        delta = qty if tipo == "entrada" else -qty

    with db_transaction() as conn:
        current = conn.execute(
            """
            SELECT stock_actual
            FROM inventario
            WHERE id=? AND estado='activo'
            """,
            (inventario_id,),
        ).fetchone()

        if not current:
            raise ValueError("Producto no existe o está inactivo")

        stock_actual = float(current["stock_actual"] or 0.0)
        resulting_stock = stock_actual + float(delta)

        if resulting_stock < 0:
            raise ValueError("Stock insuficiente para registrar salida/ajuste")

        conn.execute(
            """
            INSERT INTO movimientos_inventario (
                usuario,
                inventario_id,
                tipo,
                cantidad,
                costo_unitario_usd,
                referencia
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                int(inventario_id),
                tipo,
                float(delta),
                money(costo_unitario_usd),
                referencia,
            ),
        )

        conn.execute(
            """
            UPDATE inventario
            SET stock_actual = stock_actual + ?
            WHERE id = ?
            """,
            (float(delta), int(inventario_id)),
        )


# ============================================================
# CARGA DE DATOS
# ============================================================

def _load_inventory_df() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    fecha,
                    sku,
                    nombre,
                    categoria,
                    unidad,
                    stock_actual,
                    stock_minimo,
                    costo_unitario_usd,
                    precio_venta_usd,
                    (stock_actual * costo_unitario_usd) AS valor_stock
                FROM inventario
                WHERE estado='activo'
                ORDER BY nombre ASC
                """
            ).fetchall()
        return pd.DataFrame(rows)
    except Exception as exc:
        st.error("No se pudo cargar inventario")
        st.exception(exc)
        return pd.DataFrame()


def _load_movements_df(limit: int = 500) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.id,
                    m.fecha,
                    m.usuario,
                    i.sku,
                    i.nombre,
                    m.tipo,
                    m.cantidad,
                    m.costo_unitario_usd,
                    (ABS(m.cantidad) * m.costo_unitario_usd) AS costo_total_usd,
                    m.referencia
                FROM movimientos_inventario m
                JOIN inventario i ON i.id = m.inventario_id
                WHERE m.estado='activo'
                ORDER BY m.fecha DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return pd.DataFrame(rows)
    except Exception as exc:
        st.error("No se pudo cargar kardex de inventario")
        st.exception(exc)
        return pd.DataFrame()


# ============================================================
# INTERFAZ INVENTARIO
# ============================================================

def render_inventario(usuario: str) -> None:
    st.subheader("📦 Centro de Control de Inventario")

    df = _load_inventory_df()

    c1, c2, c3, c4 = st.columns(4)
    total_productos = int(len(df))
    stock_total = float(df["stock_actual"].sum()) if not df.empty else 0.0
    valor_total = float(df["valor_stock"].sum()) if not df.empty else 0.0
    criticos = int((df["stock_actual"] <= df["stock_minimo"]).sum()) if not df.empty else 0

    c1.metric("📦 Productos activos", total_productos)
    c2.metric("🧮 Stock total", f"{stock_total:,.2f}")
    c3.metric("💰 Valor inventario", f"$ {valor_total:,.2f}")
    c4.metric("🚨 Stock bajo", criticos, delta="Revisar" if criticos else "OK", delta_color="inverse")

    tabs = st.tabs(["📋 Existencias", "➕ Producto", "📥 Movimientos", "📊 Kardex"])

    with tabs[0]:
        if df.empty:
            st.info("No hay productos registrados todavía.")
        else:
            f1, f2, f3 = st.columns([2, 1, 1])
            txt = f1.text_input("🔎 Buscar por SKU / nombre / categoría")
            categoria = f2.selectbox("Categoría", ["Todas"] + sorted(df["categoria"].dropna().astype(str).unique().tolist()))
            solo_critico = f3.checkbox("Solo críticos")

            view = df.copy()
            if txt:
                view = view[
                    view["sku"].astype(str).str.contains(txt, case=False, na=False)
                    | view["nombre"].astype(str).str.contains(txt, case=False, na=False)
                    | view["categoria"].astype(str).str.contains(txt, case=False, na=False)
                ]
            if categoria != "Todas":
                view = view[view["categoria"] == categoria]
            if solo_critico:
                view = view[view["stock_actual"] <= view["stock_minimo"]]

            st.dataframe(
                view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "fecha": None,
                    "sku": "SKU",
                    "nombre": "Producto",
                    "categoria": "Categoría",
                    "unidad": "Unidad",
                    "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
                    "stock_minimo": st.column_config.NumberColumn("Stock mínimo", format="%.3f"),
                    "costo_unitario_usd": st.column_config.NumberColumn("Costo USD", format="%.2f"),
                    "precio_venta_usd": st.column_config.NumberColumn("Precio USD", format="%.2f"),
                    "valor_stock": st.column_config.NumberColumn("Valor stock USD", format="%.2f"),
                },
            )

            st.divider()
            p1, p2 = st.columns([2, 1])
            selected = p1.selectbox(
                "Producto",
                options=df["id"].tolist(),
                format_func=lambda pid: f"{df.loc[df['id'] == pid, 'sku'].iloc[0]} · {df.loc[df['id'] == pid, 'nombre'].iloc[0]}",
            )
            current = df[df["id"] == selected].iloc[0]
            nuevo_min = p2.number_input("Nuevo mínimo", min_value=0.0, value=float(current["stock_minimo"] or 0.0))

            b1, b2 = st.columns(2)
            if b1.button("💾 Actualizar mínimo"):
                with db_transaction() as conn:
                    conn.execute("UPDATE inventario SET stock_minimo=? WHERE id=?", (float(nuevo_min), int(selected)))
                st.success("Stock mínimo actualizado")
                st.rerun()

            if b2.button("🗃️ Desactivar producto"):
                with db_transaction() as conn:
                    conn.execute("UPDATE inventario SET estado='inactivo' WHERE id=?", (int(selected),))
                st.success("Producto desactivado")
                st.rerun()

    with tabs[1]:
        with st.form("crear_producto"):
            c1, c2 = st.columns(2)
            sku = c1.text_input("SKU")
            nombre = c1.text_input("Producto")
            categoria = c2.text_input("Categoría", value="General")
            unidad = c2.text_input("Unidad", value="unidad")
            c3, c4 = st.columns(2)
            stock_inicial = c3.number_input("Stock inicial", min_value=0.0, value=0.0)
            stock_minimo = c4.number_input("Stock mínimo", min_value=0.0, value=0.0)
            costo = st.number_input("Costo USD", min_value=0.0)
            precio = st.number_input("Precio USD", min_value=0.0)
            guardar = st.form_submit_button("💾 Crear producto")

        if guardar:
            try:
                pid = create_producto(usuario, sku, nombre, categoria, unidad, costo, precio, stock_inicial, stock_minimo)
                st.success(f"Producto #{pid} creado")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error("Error creando producto")
                st.exception(exc)

    with tabs[2]:
        if df.empty:
            st.info("No hay productos disponibles para mover stock.")
        else:
            with st.form("registrar_mov"):
                m1, m2 = st.columns(2)
                inventario_id = m1.selectbox(
                    "Producto",
                    options=df["id"].tolist(),
                    format_func=lambda pid: f"{df.loc[df['id'] == pid, 'sku'].iloc[0]} · {df.loc[df['id'] == pid, 'nombre'].iloc[0]}",
                )
                tipo = m2.selectbox("Tipo", ["entrada", "salida", "ajuste"])

                m3, m4 = st.columns(2)
                if tipo == "ajuste":
                    cantidad = m3.number_input("Cantidad ajuste (+/-)", value=0.0, step=1.0)
                else:
                    cantidad = m3.number_input("Cantidad", min_value=0.001, value=1.0)

                costo_default = float(df[df["id"] == inventario_id]["costo_unitario_usd"].iloc[0] or 0.0)
                costo_u = m4.number_input("Costo unitario USD", min_value=0.0, value=costo_default)
                referencia = st.text_input("Referencia", placeholder="Factura, merma, conteo físico, etc.")
                submit = st.form_submit_button("✅ Registrar movimiento")

            if submit:
                try:
                    add_inventory_movement(usuario, int(inventario_id), tipo, float(cantidad), float(costo_u), referencia)
                    st.success("Movimiento registrado")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error("No se pudo registrar el movimiento")
                    st.exception(exc)

    with tabs[3]:
        render_kardex(usuario)


# ============================================================
# KARDEX INVENTARIO
# ============================================================

def render_kardex(usuario: str) -> None:
    _ = usuario
    df = _load_movements_df(limit=1000)

    if df.empty:
        st.info("No hay movimientos registrados.")
        return

    f1, f2 = st.columns([2, 1])
    buscar = f1.text_input("🔎 Buscar movimiento", placeholder="referencia, producto, usuario...")
    tipo = f2.selectbox("Tipo", ["Todos", "entrada", "salida", "ajuste"])

    view = df.copy()
    if buscar:
        view = view[
            view["referencia"].astype(str).str.contains(buscar, case=False, na=False)
            | view["nombre"].astype(str).str.contains(buscar, case=False, na=False)
            | view["sku"].astype(str).str.contains(buscar, case=False, na=False)
            | view["usuario"].astype(str).str.contains(buscar, case=False, na=False)
        ]
    if tipo != "Todos":
        view = view[view["tipo"] == tipo]

    st.metric("💵 Valor movimientos visibles", f"$ {float(view['costo_total_usd'].sum() if not view.empty else 0):,.2f}")

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": "ID",
            "fecha": "Fecha",
            "usuario": "Usuario",
            "sku": "SKU",
            "nombre": "Producto",
            "tipo": "Tipo",
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo unitario", format="%.2f"),
            "costo_total_usd": st.column_config.NumberColumn("Costo total", format="%.2f"),
            "referencia": "Referencia",
        },
    )
