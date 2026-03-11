from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


# ============================================================
# AUXILIARES
# ============================================================

def _rate_from_label(label: str, tasa_bcv: float, tasa_binance: float) -> float:
    if "BCV" in str(label):
        return float(tasa_bcv or 1.0)
    if "Binance" in str(label):
        return float(tasa_binance or 1.0)
    return 1.0


def _slug(text: str) -> str:
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", clean_text(text).lower()).strip("-")
    return txt or "item"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def _ensure_config_defaults() -> None:
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


def _calc_stock_by_unit_type(tipo_unidad: str) -> tuple[float, str, str]:
    if tipo_unidad == "Área (cm²)":
        c1, c2, c3 = st.columns(3)
        ancho = c1.number_input("Ancho (cm)", min_value=0.1, value=1.0, key="inv_area_ancho")
        alto = c2.number_input("Alto (cm)", min_value=0.1, value=1.0, key="inv_area_alto")
        pliegos = c3.number_input("Cantidad de pliegos", min_value=0.001, value=1.0, key="inv_area_pliegos")
        area_por_pliego = ancho * alto
        area_total = area_por_pliego * pliegos
        st.caption(f"Referencia: {area_por_pliego:,.2f} cm²/pliego | Área total: {area_total:,.2f} cm²")
        return float(pliegos), "pliegos", f"area_ref={area_por_pliego:.2f}cm2_por_pliego"

    if tipo_unidad == "Líquido (ml)":
        c1, c2 = st.columns(2)
        ml_envase = c1.number_input("ml por envase", min_value=1.0, value=100.0, key="inv_ml_envase")
        envases = c2.number_input("Cantidad de envases", min_value=0.001, value=1.0, key="inv_ml_envases")
        return float(ml_envase * envases), "ml", ""

    if tipo_unidad == "Peso (gr)":
        c1, c2 = st.columns(2)
        gr_envase = c1.number_input("gr por envase", min_value=1.0, value=100.0, key="inv_gr_envase")
        envases = c2.number_input("Cantidad de envases", min_value=0.001, value=1.0, key="inv_gr_envases")
        return float(gr_envase * envases), "gr", ""

    qty = st.number_input("Cantidad comprada", min_value=0.001, value=1.0, key="inv_qty_unidad")
    return float(qty), "unidad", ""


def _resolve_delivery_usd(
    delivery_monto: float,
    delivery_moneda: str,
    tasa_bcv: float,
    tasa_binance: float,
    manual: bool,
) -> tuple[float, float]:
    auto = _rate_from_label(delivery_moneda, tasa_bcv, tasa_binance)
    tasa = auto
    if manual:
        tasa = st.number_input(
            "Tasa usada en delivery",
            min_value=0.0001,
            value=float(auto),
            format="%.4f",
            key="inv_tasa_delivery_manual",
        )
    delivery_usd = float(delivery_monto) / max(float(tasa), 0.0001)
    return float(delivery_usd), float(tasa)


def _build_unique_sku(conn, desired: str) -> str:
    base = _slug(desired)
    sku = base
    i = 1
    while conn.execute("SELECT 1 FROM inventario WHERE sku=?", (sku,)).fetchone():
        i += 1
        sku = f"{base}-{i}"
    return sku


def _get_or_create_provider(conn, proveedor_nombre: str) -> int | None:
    name = clean_text(proveedor_nombre)
    if not name:
        return None
    row = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    conn.execute("INSERT INTO proveedores(nombre, activo) VALUES(?,1)", (name,))
    new_row = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (name,)).fetchone()
    return int(new_row["id"]) if new_row else None


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
                usuario, sku, nombre, categoria, unidad,
                stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, sku, nombre, categoria, unidad, stock_inicial, stock_minimo, money(costo), money(precio)),
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
        delta = float(cantidad)
        if delta == 0:
            raise ValueError("En ajuste la cantidad no puede ser 0")
    else:
        qty = as_positive(cantidad, "Cantidad", allow_zero=False)
        delta = qty if tipo == "entrada" else -qty

    def _exec(connection):
        row = connection.execute(
            "SELECT stock_actual FROM inventario WHERE id=? AND estado='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Producto no existe o está inactivo")

        stock_actual = float(row["stock_actual"] or 0.0)
        nuevo = stock_actual + float(delta)
        if nuevo < 0:
            raise ValueError("Stock insuficiente para registrar salida/ajuste")

        connection.execute(
            """
            INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (usuario, int(inventario_id), tipo, float(delta), money(costo_unitario_usd), referencia),
        )
        connection.execute(
            "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id=?",
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
    referencia_extra: str = "",
) -> None:
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_total_usd = as_positive(costo_total_usd, "Costo total", allow_zero=False)
    costo_unit = costo_total_usd / cantidad

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT nombre, unidad, stock_actual, costo_unitario_usd FROM inventario WHERE id=? AND estado='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Producto no encontrado")

        stock_actual = float(row["stock_actual"] or 0.0)
        costo_actual = float(row["costo_unitario_usd"] or 0.0)
        nueva_cantidad = stock_actual + cantidad
        costo_promedio = (((stock_actual * costo_actual) + (cantidad * costo_unit)) / nueva_cantidad) if nueva_cantidad > 0 else costo_unit

        conn.execute(
            "UPDATE inventario SET costo_unitario_usd=? WHERE id=?",
            (money(costo_promedio), int(inventario_id)),
        )

        ref = f"Compra proveedor: {proveedor_nombre or 'N/A'}"
        if referencia_extra:
            ref = f"{ref} | {referencia_extra}"

        add_inventory_movement(
            usuario=usuario,
            inventario_id=int(inventario_id),
            tipo="entrada",
            cantidad=float(cantidad),
            costo_unitario_usd=float(costo_unit),
            referencia=ref,
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


def _create_inventory_item_for_purchase(
    usuario: str,
    sku_base: str,
    nombre: str,
    categoria: str,
    unidad: str,
    minimo: float,
    costo_inicial: float,
    precio_inicial: float,
) -> int:
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id FROM inventario WHERE nombre=? AND estado='activo'",
            (clean_text(nombre),),
        ).fetchone()
        if row:
            return int(row["id"])

        desired_sku = sku_base if clean_text(sku_base) else nombre
        sku = _build_unique_sku(conn, desired_sku)
        cur = conn.execute(
            """
            INSERT INTO inventario(usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                usuario,
                sku,
                clean_text(nombre),
                clean_text(categoria) or "General",
                clean_text(unidad) or "unidad",
                float(minimo or 0.0),
                money(costo_inicial),
                money(precio_inicial),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# DATA LOADERS
# ============================================================

def _load_inventory_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, fecha, sku, nombre, categoria, unidad, stock_actual, stock_minimo,
                   costo_unitario_usd, precio_venta_usd,
                   (stock_actual * costo_unitario_usd) AS valor_stock
            FROM inventario
            WHERE estado='activo'
            ORDER BY nombre ASC
            """
        ).fetchall()
    return pd.DataFrame(rows)


def _load_movements_df(limit: int = 1000) -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.fecha, m.usuario, i.sku, i.nombre, m.tipo, m.cantidad,
                   m.costo_unitario_usd, (ABS(m.cantidad) * m.costo_unitario_usd) AS costo_total_usd,
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
# UI
# ============================================================

def render_inventario(usuario: str) -> None:
    _ensure_inventory_support_tables()
    _ensure_config_defaults()

    tasa_bcv = float(st.session_state.get("tasa_bcv", 36.5) or 36.5)
    tasa_binance = float(st.session_state.get("tasa_binance", 38.0) or 38.0)

    st.subheader("📦 Centro de Control de Suministros")
    df = _load_inventory_df()

    c1, c2, c3, c4 = st.columns(4)
    total_items = int(len(df))
    capital_total = float(df["valor_stock"].sum()) if not df.empty else 0.0
    criticos = int((df["stock_actual"] <= df["stock_minimo"]).sum()) if not df.empty else 0
    salud = ((total_items - criticos) / total_items * 100) if total_items else 0.0
    c1.metric("💰 Capital en Inventario", f"${capital_total:,.2f}")
    c2.metric("📦 Total Ítems", total_items)
    c3.metric("🚨 Stock Bajo", criticos, delta="Revisar" if criticos else "OK", delta_color="inverse")
    c4.metric("🧠 Salud del Almacén", f"{salud:.0f}%")
    st.progress(min(max(salud / 100.0, 0.0), 1.0))

    tabs = st.tabs(["📋 Existencias", "📥 Registrar Compra", "📊 Historial Compras", "👤 Proveedores", "🔧 Ajustes"])

    with tabs[0]:
        if df.empty:
            st.info("Inventario vacío.")
        else:
            col1, col2, col3 = st.columns([2, 1, 1])
            filtro = col1.text_input("🔍 Buscar insumo")
            moneda_vista = col2.selectbox("Moneda", ["USD ($)", "BCV (Bs)", "Binance (Bs)"], key="inv_moneda_vista")
            solo_bajo = col3.checkbox("🚨 Solo stock bajo")

            tasa_vista = _rate_from_label(moneda_vista, tasa_bcv, tasa_binance)
            simbolo = "$" if tasa_vista == 1 else "Bs"

            df_v = df.copy()
            if filtro:
                df_v = df_v[
                    df_v["nombre"].astype(str).str.contains(filtro, case=False, na=False)
                    | df_v["sku"].astype(str).str.contains(filtro, case=False, na=False)
                    | df_v["categoria"].astype(str).str.contains(filtro, case=False, na=False)
                ]
            if solo_bajo:
                df_v = df_v[df_v["stock_actual"] <= df_v["stock_minimo"]]

            df_v["Costo Unitario"] = df_v["costo_unitario_usd"] * tasa_vista
            df_v["Valor Total"] = df_v["stock_actual"] * df_v["Costo Unitario"]

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
                    "valor_stock": None,
                    "Costo Unitario": st.column_config.NumberColumn(f"Costo ({simbolo})", format="%.2f"),
                    "Valor Total": st.column_config.NumberColumn(f"Valor Total ({simbolo})", format="%.2f"),
                },
            )

            st.download_button(
                "⬇️ Exportar existencias (CSV)",
                data=df_v.to_csv(index=False).encode("utf-8"),
                file_name="inventario_existencias.csv",
                mime="text/csv",
            )

            st.divider()
            st.subheader("🛠 Gestión de Insumo Existente")
            insumo_id = st.selectbox(
                "Seleccionar Insumo",
                df["id"].tolist(),
                format_func=lambda i: f"{df.loc[df['id']==i,'nombre'].iloc[0]} ({df.loc[df['id']==i,'sku'].iloc[0]})",
            )
            fila = df[df["id"] == insumo_id].iloc[0]
            colA, colB, colC = st.columns(3)
            nuevo_min = colA.number_input("Nuevo Stock Mínimo", min_value=0.0, value=float(fila["stock_minimo"] or 0.0))

            if colA.button("Actualizar Mínimo"):
                with db_transaction() as conn:
                    conn.execute("UPDATE inventario SET stock_minimo=? WHERE id=?", (float(nuevo_min), int(insumo_id)))
                st.success("Stock mínimo actualizado.")
                st.rerun()

            merma_qty = colB.number_input("Registrar merma", min_value=0.0, value=0.0, key="inv_merma_qty")
            if colB.button("⚠️ Registrar merma") and merma_qty > 0:
                add_inventory_movement(
                    usuario=usuario,
                    inventario_id=int(insumo_id),
                    tipo="salida",
                    cantidad=float(merma_qty),
                    costo_unitario_usd=float(fila["costo_unitario_usd"] or 0.0),
                    referencia="Merma/Material dañado",
                )
                st.success("Merma registrada")
                st.rerun()

            if str(fila["unidad"]).lower() == "cm2":
                st.warning("Este insumo está en cm²; conviene convertirlo a pliegos.")
                cm2_por_hoja = colC.number_input("cm² por pliego", min_value=1.0, value=1000.0)
                if colC.button("🔄 Convertir cm2 → pliegos"):
                    stock_actual = float(fila["stock_actual"] or 0.0)
                    pliegos = stock_actual / max(cm2_por_hoja, 0.0001)
                    delta = pliegos - stock_actual
                    add_inventory_movement(
                        usuario,
                        int(insumo_id),
                        "ajuste",
                        float(delta),
                        float(fila["costo_unitario_usd"] or 0.0),
                        "Conversión cm2 -> pliegos",
                    )
                    with db_transaction() as conn:
                        conn.execute("UPDATE inventario SET unidad='pliegos' WHERE id=?", (int(insumo_id),))
                    st.success(f"Convertido a {pliegos:.3f} pliegos")
                    st.rerun()

    with tabs[1]:
        st.subheader("📥 Registrar Nueva Compra")

        if df.empty:
            modo_producto = "Crear nuevo producto"
            st.info("No hay productos activos: se habilita solo creación de nuevo producto.")
        else:
            modo_producto = st.radio("Modo", ["Producto existente", "Crear nuevo producto"], horizontal=True)

        with db_transaction() as conn:
            prov_rows = conn.execute("SELECT id, nombre FROM proveedores WHERE COALESCE(activo,1)=1 ORDER BY nombre").fetchall()
        proveedores = [str(r["nombre"]) for r in prov_rows]

        col_base1, col_base2 = st.columns(2)
        proveedor_sel = col_base2.selectbox("Proveedor", ["(Sin proveedor)", "➕ Nuevo proveedor"] + proveedores, key="inv_proveedor_compra")
        proveedor_nombre = ""
        proveedor_id = None
        if proveedor_sel == "➕ Nuevo proveedor":
            proveedor_nombre = st.text_input("Nombre del nuevo proveedor", key="inv_proveedor_nuevo")
        elif proveedor_sel != "(Sin proveedor)":
            proveedor_nombre = proveedor_sel
            p = next((r for r in prov_rows if str(r["nombre"]) == proveedor_sel), None)
            proveedor_id = int(p["id"]) if p else None

        categoria = col_base1.text_input("Categoría", value="General")
        minimo_stock = st.number_input("Stock mínimo", min_value=0.0, value=0.0)

        if modo_producto == "Producto existente":
            producto_id = st.selectbox(
                "Producto",
                df["id"].tolist(),
                format_func=lambda i: f"{df.loc[df['id']==i,'nombre'].iloc[0]} ({df.loc[df['id']==i,'sku'].iloc[0]})",
                key="inv_producto_existente",
            )
            producto_nombre = str(df[df["id"] == producto_id]["nombre"].iloc[0])
            unidad_base = str(df[df["id"] == producto_id]["unidad"].iloc[0])
            st.caption(f"Producto seleccionado: **{producto_nombre}** | Unidad actual: **{unidad_base}**")
            sku_base = ""
        else:
            cnp1, cnp2 = st.columns(2)
            producto_nombre = cnp1.text_input("Nombre del insumo")
            sku_base = cnp2.text_input("SKU base (opcional)")

        tipo_unidad = st.selectbox("Tipo de Unidad", ["Unidad", "Área (cm²)", "Líquido (ml)", "Peso (gr)"])
        stock_real, unidad_final, referencia_unidad = _calc_stock_by_unit_type(tipo_unidad)

        col4, col5 = st.columns(2)
        monto_factura = col4.number_input("Monto Factura", min_value=0.0, value=0.0)
        moneda_pago = col5.selectbox("Moneda", ["USD $", "Bs (BCV)", "Bs (Binance)"], key="inv_moneda_pago")

        col6, col7, col8 = st.columns(3)
        iva_activo = col6.checkbox(f"IVA (+{st.session_state.get('iva_perc',16)}%)")
        igtf_activo = col7.checkbox(f"IGTF (+{st.session_state.get('igtf_perc',3)}%)")
        banco_activo = col8.checkbox(f"Banco (+{st.session_state.get('banco_perc',0.5)}%)")

        st.caption(f"Sugerencia impuesto compras: {st.session_state.get('inv_impuesto_default', 16.0):.2f}%")

        d1, d2, d3 = st.columns([1.3, 1, 1])
        delivery_monto = d1.number_input("Gastos Logística / Delivery", min_value=0.0, value=float(st.session_state.get("inv_delivery_default", 0.0) or 0.0))
        delivery_moneda = d2.selectbox("Moneda Delivery", ["USD $", "Bs (BCV)", "Bs (Binance)"], key="inv_delivery_moneda")
        tasa_manual = d3.checkbox("Tasa manual delivery")
        delivery_usd, tasa_delivery = _resolve_delivery_usd(delivery_monto, delivery_moneda, tasa_bcv, tasa_binance, tasa_manual)
        st.caption(f"Delivery equivalente: ${delivery_usd:.2f} | Tasa usada: {tasa_delivery:.4f}")

        tasa_usada_preview = _rate_from_label(moneda_pago, tasa_bcv, tasa_binance)
        impuestos_pct_preview = 0.0
        if iva_activo:
            impuestos_pct_preview += float(st.session_state.get("iva_perc", 16) or 16)
        if igtf_activo:
            impuestos_pct_preview += float(st.session_state.get("igtf_perc", 3) or 3)
        if banco_activo:
            impuestos_pct_preview += float(st.session_state.get("banco_perc", 0.5) or 0.5)
        costo_factura_total_preview = ((monto_factura / max(tasa_usada_preview, 0.0001)) * (1 + impuestos_pct_preview / 100.0)) + float(delivery_usd)
        costo_unit_preview = costo_factura_total_preview / max(float(stock_real), 0.0001)

        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Costo total estimado (USD)", f"${costo_factura_total_preview:,.2f}")
        pc2.metric("Costo unitario estimado", f"${costo_unit_preview:,.4f}")
        pc3.metric("Cantidad efectiva", f"{float(stock_real):,.3f}")

        hay_variantes = st.checkbox("¿Hay variantes?", value=False)
        variantes_payload: dict[str, float] = {}

        if hay_variantes:
            st.subheader("🎨 Variantes rápidas")
            if "variantes_editor" not in st.session_state:
                st.session_state.variantes_editor = {}

            v1, v2 = st.columns([2, 1])
            nombre_base_var = v1.text_input("Nombre base", value=producto_nombre)
            variantes_txt = v1.text_input("Variantes separadas por coma", placeholder="Rojo, Azul, Verde", key="inv_lista_variantes")

            if v2.button("Crear barras"):
                lista = [clean_text(x) for x in str(variantes_txt).split(",") if clean_text(x)]
                st.session_state.variantes_editor = {x: 0.0 for x in lista}

            if st.session_state.variantes_editor:
                st.write("### Cantidades por variante")
                for var in list(st.session_state.variantes_editor.keys()):
                    qty_var = st.number_input(f"{nombre_base_var} - {var}", min_value=0.0, value=0.0, key=f"inv_var_{var}")
                    variantes_payload[var] = float(qty_var)

        if st.button("💾 Guardar compra"):
            if monto_factura <= 0:
                st.error("Debes colocar un monto de factura válido")
                st.stop()

            tasa_usada = _rate_from_label(moneda_pago, tasa_bcv, tasa_binance)
            impuestos_pct = 0.0
            if iva_activo:
                impuestos_pct += float(st.session_state.get("iva_perc", 16) or 16)
            if igtf_activo:
                impuestos_pct += float(st.session_state.get("igtf_perc", 3) or 3)
            if banco_activo:
                impuestos_pct += float(st.session_state.get("banco_perc", 0.5) or 0.5)

            costo_factura_total = ((monto_factura / max(tasa_usada, 0.0001)) * (1 + impuestos_pct / 100.0)) + float(delivery_usd)

            if proveedor_nombre.strip() and proveedor_id is None:
                with db_transaction() as conn:
                    proveedor_id = _get_or_create_provider(conn, proveedor_nombre)

            if hay_variantes:
                if modo_producto != "Crear nuevo producto":
                    st.error("Las variantes aplican en modo 'Crear nuevo producto'.")
                    st.stop()
                total_var = float(sum(variantes_payload.values()))
                if total_var <= 0:
                    st.error("Debes colocar cantidades válidas para variantes")
                    st.stop()

                costo_unitario_var = costo_factura_total / total_var
                base_name = clean_text(nombre_base_var or producto_nombre)
                base_sku = clean_text(sku_base or _slug(base_name))

                for var, qty in variantes_payload.items():
                    if qty <= 0:
                        continue
                    nombre_final = f"{base_name} - {var}"
                    sku_variant = f"{base_sku}-{_slug(var)}"
                    inv_id = _create_inventory_item_for_purchase(
                        usuario=usuario,
                        sku_base=sku_variant,
                        nombre=nombre_final,
                        categoria=categoria,
                        unidad=unidad_final,
                        minimo=float(minimo_stock),
                        costo_inicial=float(costo_unitario_var),
                        precio_inicial=float(costo_unitario_var * 1.3),
                    )
                    registrar_compra(
                        usuario=usuario,
                        inventario_id=inv_id,
                        cantidad=float(qty),
                        costo_total_usd=float(qty * costo_unitario_var),
                        proveedor_id=proveedor_id,
                        proveedor_nombre=proveedor_nombre,
                        impuestos_pct=float(impuestos_pct),
                        delivery_usd=float(delivery_usd) * (qty / total_var),
                        tasa_usada=float(tasa_usada),
                        moneda_pago=moneda_pago,
                        referencia_extra=referencia_unidad,
                    )

                st.session_state.variantes_editor = {}
                st.success("✅ Variantes guardadas correctamente")
                st.rerun()

            else:
                if stock_real <= 0:
                    st.error("Debes colocar una cantidad válida")
                    st.stop()

                if modo_producto == "Producto existente":
                    inv_id = int(producto_id)
                else:
                    if not clean_text(producto_nombre):
                        st.error("Debes colocar el nombre del insumo")
                        st.stop()
                    inv_id = _create_inventory_item_for_purchase(
                        usuario=usuario,
                        sku_base=sku_base or producto_nombre,
                        nombre=producto_nombre,
                        categoria=categoria,
                        unidad=unidad_final,
                        minimo=float(minimo_stock),
                        costo_inicial=float(costo_factura_total / max(stock_real, 0.0001)),
                        precio_inicial=float(costo_factura_total / max(stock_real, 0.0001) * 1.3),
                    )

                registrar_compra(
                    usuario=usuario,
                    inventario_id=inv_id,
                    cantidad=float(stock_real),
                    costo_total_usd=float(costo_factura_total),
                    proveedor_id=proveedor_id,
                    proveedor_nombre=proveedor_nombre,
                    impuestos_pct=float(impuestos_pct),
                    delivery_usd=float(delivery_usd),
                    tasa_usada=float(tasa_usada),
                    moneda_pago=moneda_pago,
                    referencia_extra=referencia_unidad,
                )
                st.success("✅ Compra guardada correctamente")
                st.rerun()

    with tabs[2]:
        st.subheader("📊 Historial Profesional de Compras")
        with db_transaction() as conn:
            df_hist = pd.read_sql(
                """
                SELECT h.id compra_id, h.fecha, h.item, h.cantidad, h.unidad,
                       h.costo_total_usd, h.costo_unit_usd, h.impuestos, h.delivery, h.moneda_pago,
                       COALESCE(p.nombre,'SIN PROVEEDOR') proveedor, h.inventario_id
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
            c1, c2 = st.columns(2)
            filtro_item = c1.text_input("🔍 Filtrar Insumo")
            filtro_proveedor = c2.text_input("🔍 Filtrar Proveedor")

            df_view = df_hist.copy()
            if filtro_item:
                df_view = df_view[df_view["item"].astype(str).str.contains(filtro_item, case=False, na=False)]
            if filtro_proveedor:
                df_view = df_view[df_view["proveedor"].astype(str).str.contains(filtro_proveedor, case=False, na=False)]

            st.metric("💰 Total Comprado", f"${float(df_view['costo_total_usd'].sum()):,.2f}")
            st.dataframe(df_view, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Exportar historial compras (CSV)",
                data=df_view.to_csv(index=False).encode("utf-8"),
                file_name="inventario_historial_compras.csv",
                mime="text/csv",
            )

            st.divider()
            opciones = {f"#{r.compra_id} | {r.item} | {r.cantidad} {r.unidad}": int(r.compra_id) for r in df_hist.itertuples()}
            sel = st.selectbox("Seleccionar", list(opciones.keys()))
            compra_id = opciones[sel]
            row = df_hist[df_hist["compra_id"] == compra_id].iloc[0]

            if st.button("🗑 Eliminar compra"):
                with db_transaction() as conn:
                    add_inventory_movement(
                        usuario=usuario,
                        inventario_id=int(row["inventario_id"]),
                        tipo="salida",
                        cantidad=float(row["cantidad"]),
                        costo_unitario_usd=float(row["costo_unit_usd"] or 0.0),
                        referencia=f"Corrección compra #{int(compra_id)}",
                        conn=conn,
                    )
                    conn.execute("UPDATE historial_compras SET activo=0 WHERE id=?", (int(compra_id),))
                st.success("Compra eliminada")
                st.rerun()

    with tabs[3]:
        st.subheader("👤 Directorio de Proveedores")
        df_prov = _load_proveedores_df()

        if df_prov.empty:
            st.info("No hay proveedores registrados todavía.")
        else:
            filtro = st.text_input("🔍 Buscar proveedor")
            df_view = df_prov.copy()
            if filtro:
                df_view = df_view[df_view.astype(str).apply(lambda x: x.str.contains(filtro, case=False, na=False)).any(axis=1)]
            st.dataframe(df_view, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("➕ Registrar / Editar proveedor")
        with st.form("form_proveedor"):
            nombre = st.text_input("Nombre")
            telefono = st.text_input("Teléfono")
            rif = st.text_input("RIF")
            contacto = st.text_input("Contacto")
            observaciones = st.text_area("Observaciones")
            guardar = st.form_submit_button("💾 Guardar", use_container_width=True)

        if guardar:
            if not clean_text(nombre):
                st.error("Nombre obligatorio")
            else:
                with db_transaction() as conn:
                    exists = conn.execute("SELECT id FROM proveedores WHERE nombre=?", (clean_text(nombre),)).fetchone()
                    if exists:
                        conn.execute(
                            "UPDATE proveedores SET telefono=?, rif=?, contacto=?, observaciones=?, activo=1 WHERE id=?",
                            (clean_text(telefono), clean_text(rif), clean_text(contacto), clean_text(observaciones), int(exists["id"])),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO proveedores(nombre, telefono, rif, contacto, observaciones, activo) VALUES(?,?,?,?,?,1)",
                            (clean_text(nombre), clean_text(telefono), clean_text(rif), clean_text(contacto), clean_text(observaciones)),
                        )
                st.success("Proveedor guardado")
                st.rerun()

        if not df_prov.empty:
            sel = st.selectbox("Proveedor a eliminar", df_prov["id"].tolist(), format_func=lambda i: str(df_prov[df_prov["id"] == i]["nombre"].iloc[0]))
            if st.button("🗑 Eliminar proveedor"):
                with db_transaction() as conn:
                    compras = conn.execute("SELECT COUNT(*) AS c FROM historial_compras WHERE proveedor_id=? AND COALESCE(activo,1)=1", (int(sel),)).fetchone()
                    if int(compras["c"] or 0) > 0:
                        st.error("Tiene compras asociadas")
                    else:
                        conn.execute("UPDATE proveedores SET activo=0 WHERE id=?", (int(sel),))
                        st.success("Proveedor eliminado")
                        st.rerun()

    with tabs[4]:
        st.subheader("🔧 Configuración estratégica del Inventario")
        with db_transaction() as conn:
            cfg = pd.read_sql("SELECT parametro, valor FROM configuracion", conn)
        cfg_map = {str(r.parametro): _safe_float(r.valor, 0.0) for r in cfg.itertuples() if str(r.valor).strip() != ""}

        c1, c2, c3 = st.columns(3)
        c1.metric("⏱️ Alerta reposición", f"{int(cfg_map.get('inv_alerta_dias', 14))} días")
        c2.metric("🛡️ Impuesto sugerido", f"{cfg_map.get('inv_impuesto_default', 16.0):.2f}%")
        c3.metric("🚚 Delivery sugerido", f"${cfg_map.get('inv_delivery_default', 0.0):.2f}")

        with st.form("form_config_inventario"):
            alerta = st.number_input("Días alerta reposición", min_value=1, max_value=365, value=int(cfg_map.get("inv_alerta_dias", 14)))
            impuesto = st.number_input("Impuesto default compras (%)", min_value=0.0, max_value=100.0, value=float(cfg_map.get("inv_impuesto_default", 16.0)), format="%.2f")
            delivery = st.number_input("Delivery default ($)", min_value=0.0, value=float(cfg_map.get("inv_delivery_default", 0.0)), format="%.2f")
            guardar = st.form_submit_button("💾 Guardar Configuración", use_container_width=True)

        if guardar:
            with db_transaction() as conn:
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_alerta_dias'", (str(int(alerta)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_impuesto_default'", (str(float(impuesto)),))
                conn.execute("UPDATE configuracion SET valor=? WHERE parametro='inv_delivery_default'", (str(float(delivery)),))
            st.session_state.inv_alerta_dias = int(alerta)
            st.session_state.inv_impuesto_default = float(impuesto)
            st.session_state.inv_delivery_default = float(delivery)
            st.success("✅ Configuración actualizada correctamente")
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
