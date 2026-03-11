from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


# ============================================================
# AUXILIARES
# ============================================================

def _rate_from_label(label: str, tasa_bcv: float, tasa_binance: float) -> float:
    if "BCV" in label:
        return float(tasa_bcv or 1.0)
    if "Binance" in label:
        return float(tasa_binance or 1.0)
    return 1.0


def _ensure_inventory_support_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                telefono TEXT,
                rif TEXT,
                contacto TEXT,
                observaciones TEXT,
                activo INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                inventario_id INTEGER,
                proveedor_id INTEGER,
                item TEXT,
                cantidad REAL,
                unidad TEXT,
                costo_total_usd REAL,
                costo_unit_usd REAL,
                impuestos REAL DEFAULT 0,
                delivery REAL DEFAULT 0,
                tasa_usada REAL DEFAULT 1,
                moneda_pago TEXT,
                activo INTEGER DEFAULT 1
            )
            """
        )


# ============================================================
# PRODUCTOS Y MOVIMIENTOS
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


def add_inventory_movement(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
    conn=None,
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

    def _exec(connection):
        current = connection.execute(
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

        connection.execute(
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

        connection.execute(
            """
            UPDATE inventario
            SET stock_actual = stock_actual + ?
            WHERE id = ?
            """,
            (float(delta), int(inventario_id)),
        )

    if conn is not None:
        _exec(conn)
    else:
        with db_transaction() as tx:
            _exec(tx)


def registrar_compra(
    usuario: str,
    inventario_id: int,
    cantidad: float,
    costo_total_usd: float,
    proveedor_id: int | None,
    proveedor_nombre: str,
    impuestos_pct: float,
    delivery_usd: float,
    tasa_usada: float,
    moneda_pago: str,
) -> None:
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_total_usd = as_positive(costo_total_usd, "Costo total", allow_zero=False)
    costo_unit = costo_total_usd / cantidad

    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT nombre, unidad, stock_actual, costo_unitario_usd
            FROM inventario WHERE id=? AND estado='activo'
            """,
            (int(inventario_id),),
        ).fetchone()

        if not row:
            raise ValueError("Producto no encontrado")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nueva_cantidad = stock_actual + cantidad

        costo_promedio = (
            ((stock_actual * costo_actual) + (cantidad * costo_unit)) / nueva_cantidad
            if nueva_cantidad > 0
            else costo_unit
        )

        conn.execute(
            "UPDATE inventario SET costo_unitario_usd=? WHERE id=?",
            (money(costo_promedio), int(inventario_id)),
        )

        add_inventory_movement(
            usuario=usuario,
            inventario_id=int(inventario_id),
            tipo="entrada",
            cantidad=float(cantidad),
            costo_unitario_usd=float(costo_unit),
            referencia=f"Compra proveedor: {proveedor_nombre or 'N/A'}",
            conn=conn,
        )

        conn.execute(
            """
            INSERT INTO historial_compras
            (usuario, inventario_id, proveedor_id, item, cantidad, unidad, costo_total_usd, costo_unit_usd,
             impuestos, delivery, tasa_usada, moneda_pago, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                usuario,
                int(inventario_id),
                int(proveedor_id) if proveedor_id is not None else None,
                str(row["nombre"]),
                float(cantidad),
                str(row["unidad"]),
                money(costo_total_usd),
                money(costo_unit),
                float(impuestos_pct),
                money(delivery_usd),
                float(tasa_usada),
                str(moneda_pago),
            ),
        )


# ============================================================
# CARGA DE DATOS
# ============================================================

def _load_inventory_df() -> pd.DataFrame:
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


def _load_movements_df(limit: int = 500) -> pd.DataFrame:
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


def _load_proveedores_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, nombre, telefono, rif, contacto, observaciones, fecha_creacion
            FROM proveedores
            WHERE COALESCE(activo,1)=1
            ORDER BY nombre ASC
            """
        ).fetchall()
    return pd.DataFrame(rows)


# ============================================================
# INTERFAZ INVENTARIO
# ============================================================

def render_inventario(usuario: str) -> None:
    _ensure_inventory_support_tables()

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)
    tasa_binance = float(st.session_state.get("tasa_binance", 38.0) or 38.0)

    st.subheader("📦 Centro de Control de Inventario")

    df = _load_inventory_df()

    c1, c2, c3, c4 = st.columns(4)
    total_productos = int(len(df))
    stock_total = float(df["stock_actual"].sum()) if not df.empty else 0.0
    valor_total = float(df["valor_stock"].sum()) if not df.empty else 0.0
    criticos = int((df["stock_actual"] <= df["stock_minimo"]).sum()) if not df.empty else 0
    salud = ((total_productos - criticos) / total_productos * 100) if total_productos else 0.0

    c1.metric("💰 Capital Inventario", f"$ {valor_total:,.2f}")
    c2.metric("📦 Total Ítems", total_productos)
    c3.metric("🚨 Stock Bajo", criticos, delta="Revisar" if criticos else "OK", delta_color="inverse")
    c4.metric("🧠 Salud Almacén", f"{salud:.0f}%")

    tabs = st.tabs(["📋 Existencias", "📥 Registrar compra", "📊 Historial compras", "👤 Proveedores", "🔧 Ajustes"]) 

    with tabs[0]:
        if df.empty:
            st.info("Inventario vacío.")
        else:
            col1, col2, col3 = st.columns([2, 1, 1])
            filtro = col1.text_input("🔍 Buscar producto")
            moneda_vista = col2.selectbox("Moneda", ["USD ($)", "BCV (Bs)", "Binance (Bs)"])
            solo_bajo = col3.checkbox("🚨 Solo stock bajo")

            tasa_vista = _rate_from_label(moneda_vista, tasa_bcv, tasa_binance)
            simbolo = "Bs" if tasa_vista != 1 else "$"

            df_v = df.copy()
            if filtro:
                df_v = df_v[
                    df_v["sku"].astype(str).str.contains(filtro, case=False, na=False)
                    | df_v["nombre"].astype(str).str.contains(filtro, case=False, na=False)
                    | df_v["categoria"].astype(str).str.contains(filtro, case=False, na=False)
                ]
            if solo_bajo:
                df_v = df_v[df_v["stock_actual"] <= df_v["stock_minimo"]]

            df_v["Costo Unitario Vista"] = df_v["costo_unitario_usd"] * tasa_vista
            df_v["Valor Total Vista"] = df_v["stock_actual"] * df_v["Costo Unitario Vista"]

            st.dataframe(
                df_v,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "fecha": None,
                    "sku": "SKU",
                    "nombre": "Insumo",
                    "categoria": "Categoría",
                    "unidad": "Unidad",
                    "stock_actual": st.column_config.NumberColumn("Stock", format="%.3f"),
                    "stock_minimo": st.column_config.NumberColumn("Mínimo", format="%.3f"),
                    "costo_unitario_usd": None,
                    "precio_venta_usd": st.column_config.NumberColumn("Precio venta $", format="%.2f"),
                    "valor_stock": None,
                    "Costo Unitario Vista": st.column_config.NumberColumn(f"Costo ({simbolo})", format="%.2f"),
                    "Valor Total Vista": st.column_config.NumberColumn(f"Valor ({simbolo})", format="%.2f"),
                },
            )

            st.divider()
            st.subheader("🛠 Gestión rápida")
            p1, p2, p3 = st.columns(3)
            selected = p1.selectbox(
                "Producto",
                options=df["id"].tolist(),
                format_func=lambda pid: f"{df.loc[df['id'] == pid, 'sku'].iloc[0]} · {df.loc[df['id'] == pid, 'nombre'].iloc[0]}",
            )
            row = df[df["id"] == selected].iloc[0]
            nuevo_min = p2.number_input("Nuevo stock mínimo", min_value=0.0, value=float(row["stock_minimo"] or 0.0))
            ajuste = p3.number_input("Ajuste rápido (+/-)", value=0.0, step=1.0)

            b1, b2, b3 = st.columns(3)
            if b1.button("💾 Actualizar mínimo"):
                with db_transaction() as conn:
                    conn.execute("UPDATE inventario SET stock_minimo=? WHERE id=?", (float(nuevo_min), int(selected)))
                st.success("Stock mínimo actualizado")
                st.rerun()

            if b2.button("⚖️ Aplicar ajuste") and float(ajuste) != 0.0:
                add_inventory_movement(
                    usuario=usuario,
                    inventario_id=int(selected),
                    tipo="ajuste",
                    cantidad=float(ajuste),
                    costo_unitario_usd=float(row["costo_unitario_usd"] or 0.0),
                    referencia="Ajuste rápido desde inventario",
                )
                st.success("Ajuste aplicado")
                st.rerun()

            if b3.button("🗃️ Desactivar"):
                with db_transaction() as conn:
                    conn.execute("UPDATE inventario SET estado='inactivo' WHERE id=?", (int(selected),))
                st.success("Producto desactivado")
                st.rerun()

    with tabs[1]:
        st.subheader("📥 Registrar compra")

        if df.empty:
            st.info("Primero registra un producto en inventario.")
        else:
            with db_transaction() as conn:
                provs = conn.execute("SELECT id, nombre FROM proveedores WHERE COALESCE(activo,1)=1 ORDER BY nombre").fetchall()

            opciones_prov = ["(Sin proveedor)", "➕ Nuevo proveedor"] + [str(r["nombre"]) for r in provs]

            colp1, colp2 = st.columns(2)
            producto_id = colp1.selectbox(
                "Producto",
                options=df["id"].tolist(),
                format_func=lambda pid: f"{df.loc[df['id'] == pid, 'sku'].iloc[0]} · {df.loc[df['id'] == pid, 'nombre'].iloc[0]}",
            )
            prov_sel = colp2.selectbox("Proveedor", opciones_prov)
            proveedor_nombre = ""
            proveedor_id = None

            if prov_sel == "➕ Nuevo proveedor":
                proveedor_nombre = st.text_input("Nombre del nuevo proveedor")
            elif prov_sel != "(Sin proveedor)":
                proveedor_nombre = prov_sel
                proveedor_id = next((int(r["id"]) for r in provs if str(r["nombre"]) == prov_sel), None)

            c1, c2 = st.columns(2)
            cantidad = c1.number_input("Cantidad comprada", min_value=0.001, value=1.0)
            monto_factura = c2.number_input("Monto factura", min_value=0.0, value=0.0)

            c3, c4, c5 = st.columns(3)
            moneda_pago = c3.selectbox("Moneda pago", ["USD $", "Bs (BCV)", "Bs (Binance)"])
            iva = c4.checkbox(f"IVA (+{st.session_state.get('iva_perc', 16)}%)")
            igtf = c5.checkbox(f"IGTF (+{st.session_state.get('igtf_perc', 3)}%)")

            c6, c7 = st.columns(2)
            banco = c6.checkbox(f"Banco (+{st.session_state.get('banco_perc', 0.5)}%)")
            delivery_usd = c7.number_input("Delivery en USD", min_value=0.0, value=float(st.session_state.get("inv_delivery_default", 0.0) or 0.0))

            if st.button("💾 Registrar compra"):
                if monto_factura <= 0:
                    st.error("Monto factura debe ser mayor a 0")
                else:
                    if prov_sel == "➕ Nuevo proveedor" and proveedor_nombre.strip():
                        with db_transaction() as conn:
                            conn.execute(
                                "INSERT OR IGNORE INTO proveedores(nombre, activo) VALUES(?,1)",
                                (proveedor_nombre.strip(),),
                            )
                            row_prov = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (proveedor_nombre.strip(),)).fetchone()
                            proveedor_id = int(row_prov["id"]) if row_prov else None

                    tasa_usada = _rate_from_label(moneda_pago, tasa_bcv, tasa_binance)
                    impuestos_pct = 0.0
                    if iva:
                        impuestos_pct += float(st.session_state.get("iva_perc", 16) or 16)
                    if igtf:
                        impuestos_pct += float(st.session_state.get("igtf_perc", 3) or 3)
                    if banco:
                        impuestos_pct += float(st.session_state.get("banco_perc", 0.5) or 0.5)

                    costo_total_usd = ((monto_factura / max(tasa_usada, 0.0001)) * (1 + impuestos_pct / 100.0)) + delivery_usd

                    registrar_compra(
                        usuario=usuario,
                        inventario_id=int(producto_id),
                        cantidad=float(cantidad),
                        costo_total_usd=float(costo_total_usd),
                        proveedor_id=proveedor_id,
                        proveedor_nombre=proveedor_nombre,
                        impuestos_pct=float(impuestos_pct),
                        delivery_usd=float(delivery_usd),
                        tasa_usada=float(tasa_usada),
                        moneda_pago=moneda_pago,
                    )
                    st.success("Compra registrada correctamente")
                    st.rerun()

    with tabs[2]:
        st.subheader("📊 Historial de compras")
        with db_transaction() as conn:
            df_hist = pd.read_sql(
                """
                SELECT h.id compra_id,
                       h.fecha,
                       h.item,
                       h.cantidad,
                       h.unidad,
                       h.costo_total_usd,
                       h.costo_unit_usd,
                       h.impuestos,
                       h.delivery,
                       h.moneda_pago,
                       COALESCE(p.nombre,'SIN PROVEEDOR') AS proveedor,
                       h.inventario_id
                FROM historial_compras h
                LEFT JOIN proveedores p ON p.id = h.proveedor_id
                WHERE COALESCE(h.activo,1)=1
                ORDER BY h.fecha DESC
                """,
                conn,
            )

        if df_hist.empty:
            st.info("Sin compras registradas")
        else:
            h1, h2 = st.columns(2)
            f_item = h1.text_input("🔍 Filtrar insumo")
            f_prov = h2.text_input("🔍 Filtrar proveedor")

            df_view = df_hist.copy()
            if f_item:
                df_view = df_view[df_view["item"].astype(str).str.contains(f_item, case=False, na=False)]
            if f_prov:
                df_view = df_view[df_view["proveedor"].astype(str).str.contains(f_prov, case=False, na=False)]

            st.metric("💰 Total comprado", f"$ {float(df_view['costo_total_usd'].sum()):,.2f}")
            st.dataframe(df_view, use_container_width=True, hide_index=True)

            st.divider()
            opciones = {f"#{r.compra_id} | {r.item} | {r.cantidad} {r.unidad}": int(r.compra_id) for r in df_hist.itertuples()}
            sel = st.selectbox("Compra a corregir", list(opciones.keys()))
            compra_id = opciones[sel]
            row = df_hist[df_hist["compra_id"] == compra_id].iloc[0]

            if st.button("🧹 Anular compra"):
                with db_transaction() as conn:
                    add_inventory_movement(
                        usuario=usuario,
                        inventario_id=int(row["inventario_id"]),
                        tipo="salida",
                        cantidad=float(row["cantidad"]),
                        costo_unitario_usd=float(row["costo_unit_usd"] or 0.0),
                        referencia=f"Anulación compra #{int(compra_id)}",
                        conn=conn,
                    )
                    conn.execute("UPDATE historial_compras SET activo=0 WHERE id=?", (int(compra_id),))
                st.success("Compra anulada y stock corregido")
                st.rerun()

    with tabs[3]:
        st.subheader("👤 Proveedores")
        df_prov = _load_proveedores_df()

        if df_prov.empty:
            st.info("No hay proveedores registrados.")
        else:
            filtro = st.text_input("🔍 Buscar proveedor")
            df_pv = df_prov.copy()
            if filtro:
                df_pv = df_pv[df_pv.astype(str).apply(lambda x: x.str.contains(filtro, case=False, na=False)).any(axis=1)]
            st.dataframe(df_pv, use_container_width=True, hide_index=True)

        st.divider()
        with st.form("form_proveedor"):
            nombre = st.text_input("Nombre")
            telefono = st.text_input("Teléfono")
            rif = st.text_input("RIF")
            contacto = st.text_input("Contacto")
            observaciones = st.text_area("Observaciones")
            save_prov = st.form_submit_button("💾 Guardar proveedor")

        if save_prov:
            if not nombre.strip():
                st.error("Nombre obligatorio")
            else:
                with db_transaction() as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO proveedores(nombre, telefono, rif, contacto, observaciones, activo)
                        VALUES(?, ?, ?, ?, ?, 1)
                        """,
                        (nombre.strip(), telefono.strip(), rif.strip(), contacto.strip(), observaciones.strip()),
                    )
                st.success("Proveedor guardado")
                st.rerun()

    with tabs[4]:
        st.subheader("🔧 Ajustes de inventario")

        defaults = {
            "inv_alerta_dias": 14,
            "inv_impuesto_default": 16.0,
            "inv_delivery_default": 0.0,
        }

        with db_transaction() as conn:
            for k, v in defaults.items():
                found = conn.execute("SELECT 1 FROM configuracion WHERE parametro=?", (k,)).fetchone()
                if not found:
                    conn.execute("INSERT INTO configuracion(parametro, valor) VALUES(?,?)", (k, str(v)))
            cfg = pd.read_sql("SELECT parametro, valor FROM configuracion", conn)

        cfg_map = {str(r.parametro): float(r.valor) for r in cfg.itertuples() if str(r.valor).strip() != ""}

        a1, a2, a3 = st.columns(3)
        a1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
        a2.metric("🛡️ Impuesto sugerido", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
        a3.metric("🚚 Delivery sugerido", f"$ {cfg_map.get('inv_delivery_default', 0.0):.2f}")

        with st.form("form_config_inv"):
            alerta = st.number_input("Días alerta reposición", min_value=1, max_value=365, value=int(cfg_map.get("inv_alerta_dias", 14)))
            impuesto = st.number_input("Impuesto default (%)", min_value=0.0, max_value=100.0, value=float(cfg_map.get("inv_impuesto_default", 16.0)))
            delivery = st.number_input("Delivery default USD", min_value=0.0, value=float(cfg_map.get("inv_delivery_default", 0.0)))
            save_cfg = st.form_submit_button("💾 Guardar configuración")

        if save_cfg:
            with db_transaction() as conn:
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_alerta_dias'", (str(int(alerta)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_impuesto_default'", (str(float(impuesto)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_delivery_default'", (str(float(delivery)),))
            st.session_state["inv_alerta_dias"] = int(alerta)
            st.session_state["inv_impuesto_default"] = float(impuesto)
            st.session_state["inv_delivery_default"] = float(delivery)
            st.success("Configuración actualizada")
            st.rerun()


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
