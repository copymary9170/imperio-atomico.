from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import DEFAULT_CONFIG, get_current_config
from services.costeo_integral_service import (
    BASE_UNITS,
    allocate_amount,
    calculate_conversion_factor,
    calculate_recipe_cost,
    ensure_integrated_costing_schema,
    price_from_margin,
    save_integrated_quote,
)

UPLOAD_DIR = Path("uploads/clientes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _df(sql: str, params: tuple = ()) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def _inventory() -> pd.DataFrame:
    try:
        return _df("SELECT id, sku, nombre, COALESCE(unidad,'unidad') unidad, COALESCE(costo,0) costo, COALESCE(cantidad,0) cantidad FROM inventario WHERE COALESCE(estado,'activo')='activo' ORDER BY nombre")
    except Exception:
        return pd.DataFrame(columns=["id", "sku", "nombre", "unidad", "costo", "cantidad"])


def _clients() -> pd.DataFrame:
    try:
        return _df("SELECT id, nombre, COALESCE(telefono,'') telefono FROM clientes WHERE COALESCE(estado,'activo')='activo' ORDER BY nombre")
    except Exception:
        return pd.DataFrame(columns=["id", "nombre", "telefono"])


def _rates() -> tuple[float, str]:
    try:
        cfg = get_current_config()
    except Exception:
        cfg = DEFAULT_CONFIG
    return float(cfg.get("tasa_bcv", 0) or 0), datetime.now().isoformat(timespec="seconds")


def _render_units() -> None:
    st.subheader("📐 Unidades, conversiones y merma estándar")
    inv = _inventory()
    if inv.empty:
        st.warning("Primero registra productos en Inventario.")
        return
    item_id = st.selectbox("Producto", inv["id"].tolist(), format_func=lambda x: f"{inv.loc[inv.id.eq(x),'nombre'].iloc[0]} · {inv.loc[inv.id.eq(x),'sku'].iloc[0]}")
    c1, c2, c3 = st.columns(3)
    unit_purchase = c1.text_input("Unidad de compra", value="paquete")
    presentations = c2.number_input("Contenido por presentación", min_value=0.000001, value=1.0)
    base_unit = c3.selectbox("Unidad base de consumo", BASE_UNITS)
    d1, d2, d3, d4, d5 = st.columns(5)
    width = d1.number_input("Ancho cm", min_value=0.0, value=0.0)
    height = d2.number_input("Alto cm", min_value=0.0, value=0.0)
    length = d3.number_input("Largo cm", min_value=0.0, value=0.0)
    weight = d4.number_input("Peso g", min_value=0.0, value=0.0)
    volume = d5.number_input("Volumen ml", min_value=0.0, value=0.0)
    waste = st.number_input("Merma estándar (%)", min_value=0.0, value=0.0, step=0.5)
    factor = calculate_conversion_factor(content=presentations, unit_base=base_unit, width_cm=width, height_cm=height, length_cm=length, weight_g=weight, volume_ml=volume)
    st.metric("Unidades base por presentación", f"{factor:,.4f} {base_unit}")
    if st.button("Guardar conversión", type="primary", use_container_width=True):
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO unidades_conversion(inventario_id, unidad_compra, contenido_presentacion, unidad_base, ancho_cm, alto_cm, largo_cm, peso_g, volumen_ml, factor_conversion, merma_estandar_pct, activo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(inventario_id) DO UPDATE SET unidad_compra=excluded.unidad_compra, contenido_presentacion=excluded.contenido_presentacion,
                unidad_base=excluded.unidad_base, ancho_cm=excluded.ancho_cm, alto_cm=excluded.alto_cm, largo_cm=excluded.largo_cm,
                peso_g=excluded.peso_g, volumen_ml=excluded.volumen_ml, factor_conversion=excluded.factor_conversion,
                merma_estandar_pct=excluded.merma_estandar_pct, activo=1
                """,
                (int(item_id), unit_purchase.strip(), float(presentations), base_unit, width, height, length, weight, volume, factor, waste),
            )
        st.success("Conversión guardada.")
    data = _df("SELECT uc.*, i.nombre, i.sku FROM unidades_conversion uc JOIN inventario i ON i.id=uc.inventario_id ORDER BY i.nombre")
    st.dataframe(data, use_container_width=True, hide_index=True)


def _render_purchase(usuario: str) -> None:
    st.subheader("🧾 Compra con IVA, delivery y costo puesto en almacén")
    st.caption("Registra la factura completa y reparte los costos adicionales entre sus artículos.")
    with st.form("integral_purchase_header"):
        h1, h2, h3, h4 = st.columns(4)
        supplier = h1.text_input("Proveedor")
        invoice = h2.text_input("N.º factura")
        currency = h3.selectbox("Moneda", ["USD", "VES", "EUR"])
        rate = h4.number_input("Tasa histórica a USD", min_value=0.000001, value=1.0)
        a1, a2, a3, a4, a5 = st.columns(5)
        discount = a1.number_input("Descuento total USD", min_value=0.0, value=0.0)
        tax = a2.number_input("IVA no recuperable USD", min_value=0.0, value=0.0)
        other_tax = a3.number_input("Otros impuestos USD", min_value=0.0, value=0.0)
        delivery = a4.number_input("Delivery/flete USD", min_value=0.0, value=0.0)
        other = a5.number_input("Otros gastos USD", min_value=0.0, value=0.0)
        allocation = st.selectbox("Método de reparto", ["valor", "cantidad"])
        submitted = st.form_submit_button("Preparar factura")
    if submitted:
        st.session_state["purchase_header"] = {"supplier": supplier, "invoice": invoice, "currency": currency, "rate": rate, "discount": discount, "tax": tax, "other_tax": other_tax, "delivery": delivery, "other": other, "allocation": allocation}
    st.markdown("#### Artículos")
    inv = _inventory()
    with st.form("purchase_add_item"):
        i1, i2, i3 = st.columns([2, 1, 1])
        product = i1.selectbox("Producto de inventario", [0] + inv["id"].tolist(), format_func=lambda x: "Sin vincular / nuevo" if x == 0 else inv.loc[inv.id.eq(x), "nombre"].iloc[0])
        description = i1.text_input("Descripción de factura")
        qty = i2.number_input("Cantidad comprada", min_value=0.000001, value=1.0)
        unit_price = i3.number_input("Precio por presentación USD", min_value=0.0, value=0.0)
        unit_purchase = i2.text_input("Unidad compra", value="unidad")
        content = i3.number_input("Contenido por presentación", min_value=0.000001, value=1.0, key="purchase_content")
        base_unit = st.selectbox("Unidad base", BASE_UNITS, key="purchase_base_unit")
        add = st.form_submit_button("Agregar artículo")
    if add:
        st.session_state.setdefault("purchase_items", []).append({"inventario_id": int(product) or None, "descripcion": description or (inv.loc[inv.id.eq(product), "nombre"].iloc[0] if product else "Artículo"), "cantidad": qty, "precio_unitario": unit_price, "subtotal": qty * unit_price, "unidad_compra": unit_purchase, "contenido": content, "unidad_base": base_unit})
        st.rerun()
    items = st.session_state.get("purchase_items", [])
    if not items:
        st.info("Agrega los artículos de la factura.")
        return
    work = pd.DataFrame(items)
    header = st.session_state.get("purchase_header", {"supplier": supplier, "invoice": invoice, "currency": currency, "rate": rate, "discount": discount, "tax": tax, "other_tax": other_tax, "delivery": delivery, "other": other, "allocation": allocation})
    bases = work["cantidad"].tolist() if header.get("allocation") == "cantidad" else work["subtotal"].tolist()
    work["descuento_asignado"] = allocate_amount(header.get("discount", 0), bases)
    work["iva_asignado"] = allocate_amount(header.get("tax", 0) + header.get("other_tax", 0), bases)
    work["delivery_asignado"] = allocate_amount(header.get("delivery", 0), bases)
    work["otros_asignados"] = allocate_amount(header.get("other", 0), bases)
    work["costo_final"] = work["subtotal"] - work["descuento_asignado"] + work["iva_asignado"] + work["delivery_asignado"] + work["otros_asignados"]
    work["cantidad_base"] = work["cantidad"] * work["contenido"]
    work["costo_unitario_base"] = work["costo_final"] / work["cantidad_base"].clip(lower=0.000001)
    subtotal = float(work["subtotal"].sum())
    total = subtotal - float(header.get("discount", 0)) + float(header.get("tax", 0)) + float(header.get("other_tax", 0)) + float(header.get("delivery", 0)) + float(header.get("other", 0))
    st.dataframe(work, use_container_width=True, hide_index=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Subtotal artículos", f"${subtotal:,.2f}")
    m2.metric("Costos adicionales netos", f"${total-subtotal:,.2f}")
    m3.metric("Total pagado", f"${total:,.2f}")
    if st.button("Registrar compra y actualizar costos", type="primary", use_container_width=True):
        with db_transaction() as conn:
            cur = conn.execute(
                """INSERT INTO compras_costeo_cabecera(usuario, proveedor, numero_factura, moneda, tasa_cambio, fecha_tasa, fuente_tasa, subtotal_usd, descuento_usd, iva_usd, otros_impuestos_usd, delivery_usd, otros_gastos_usd, total_pagado_usd, iva_tratamiento, metodo_reparto)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (usuario, header.get("supplier"), header.get("invoice"), header.get("currency", "USD"), header.get("rate", 1), date.today().isoformat(), "Manual/factura", subtotal, header.get("discount", 0), header.get("tax", 0), header.get("other_tax", 0), header.get("delivery", 0), header.get("other", 0), total, "costo", header.get("allocation", "valor")),
            )
            purchase_id = int(cur.lastrowid)
            for _, row in work.iterrows():
                conn.execute(
                    """INSERT INTO compras_costeo_items(compra_id,inventario_id,descripcion,cantidad_presentaciones,precio_unitario_compra_usd,subtotal_linea_usd,descuento_asignado_usd,iva_asignado_usd,delivery_asignado_usd,otros_asignados_usd,costo_final_linea_usd,unidad_compra,contenido_presentacion,unidad_base,cantidad_base_ingresada,costo_unitario_base_usd)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (purchase_id, row.inventario_id if pd.notna(row.inventario_id) else None, row.descripcion, row.cantidad, row.precio_unitario, row.subtotal, row.descuento_asignado, row.iva_asignado, row.delivery_asignado, row.otros_asignados, row.costo_final, row.unidad_compra, row.contenido, row.unidad_base, row.cantidad_base, row.costo_unitario_base),
                )
                if pd.notna(row.inventario_id):
                    old = conn.execute("SELECT COALESCE(cantidad,0) cantidad, COALESCE(costo,0) costo FROM inventario WHERE id=?", (int(row.inventario_id),)).fetchone()
                    old_qty = float(old["cantidad"] or 0) if old else 0
                    old_cost = float(old["costo"] or 0) if old else 0
                    new_qty = old_qty + float(row.cantidad_base)
                    avg = ((old_qty * old_cost) + float(row.costo_final)) / max(new_qty, 0.000001)
                    conn.execute("UPDATE inventario SET cantidad=?, costo=?, unidad=? WHERE id=?", (new_qty, avg, row.unidad_base, int(row.inventario_id)))
                    conn.execute("INSERT INTO unidades_conversion(inventario_id,unidad_compra,contenido_presentacion,unidad_base,factor_conversion,activo) VALUES (?,?,?,?,?,1) ON CONFLICT(inventario_id) DO UPDATE SET unidad_compra=excluded.unidad_compra,contenido_presentacion=excluded.contenido_presentacion,unidad_base=excluded.unidad_base,factor_conversion=excluded.factor_conversion,activo=1", (int(row.inventario_id), row.unidad_compra, row.contenido, row.unidad_base, row.contenido))
        st.session_state["purchase_items"] = []
        st.success(f"Compra #{purchase_id} registrada y costos actualizados.")
        st.rerun()


def _render_assets() -> None:
    st.subheader("🏗️ Activos productivos y costo por uso")
    with st.form("asset_form"):
        a, b, c = st.columns(3)
        code = a.text_input("Código")
        name = b.text_input("Equipo")
        kind = c.selectbox("Tipo", ["Impresora", "Laminadora", "Cameo", "Plancha", "Guillotina", "Computadora", "Otro"])
        d, e, f, g = st.columns(4)
        cost = d.number_input("Costo adquisición USD", min_value=0.0, value=0.0)
        residual = e.number_input("Valor residual USD", min_value=0.0, value=0.0)
        life_type = f.selectbox("Vida útil en", ["paginas", "ciclos", "minutos", "horas", "años"])
        life = g.number_input("Vida útil total", min_value=0.000001, value=1.0)
        power = st.number_input("Potencia W", min_value=0.0, value=0.0)
        save = st.form_submit_button("Registrar activo")
    if save:
        with db_transaction() as conn:
            conn.execute("INSERT INTO activos_productivos_costeo(codigo,nombre,tipo,fecha_compra,costo_adquisicion_usd,valor_residual_usd,vida_util_tipo,vida_util_total,potencia_w) VALUES (?,?,?,?,?,?,?,?,?)", (code.strip(), name.strip(), kind, date.today().isoformat(), cost, residual, life_type, life, power))
        st.success("Activo registrado.")
    assets = _df("SELECT *, CASE WHEN vida_util_total>0 THEN (costo_adquisicion_usd-valor_residual_usd+mantenimiento_acumulado_usd)/vida_util_total ELSE 0 END costo_por_uso_usd FROM activos_productivos_costeo ORDER BY id DESC")
    st.dataframe(assets, use_container_width=True, hide_index=True)


def _render_recipes() -> None:
    st.subheader("🧪 Recetas y fichas técnicas de servicios")
    with st.form("recipe_header"):
        r1, r2, r3 = st.columns(3)
        code = r1.text_input("Código receta")
        name = r2.text_input("Nombre")
        margin = r3.number_input("Margen objetivo sobre venta (%)", min_value=0.0, max_value=99.0, value=40.0)
        create = st.form_submit_button("Crear receta")
    if create:
        with db_transaction() as conn:
            conn.execute("INSERT INTO recetas_costeo(codigo,nombre,margen_objetivo_pct) VALUES (?,?,?)", (code.strip(), name.strip(), margin))
        st.success("Receta creada.")
    recipes = _df("SELECT * FROM recetas_costeo WHERE estado='activa' ORDER BY nombre")
    if recipes.empty:
        return
    recipe_id = st.selectbox("Receta a editar", recipes.id.tolist(), format_func=lambda x: recipes.loc[recipes.id.eq(x), "nombre"].iloc[0])
    inv = _inventory()
    assets = _df("SELECT id,nombre FROM activos_productivos_costeo WHERE estado='activo' ORDER BY nombre")
    with st.form("recipe_component"):
        c1, c2, c3 = st.columns(3)
        component_type = c1.selectbox("Tipo", ["material", "activo", "mano_obra", "indirecto"])
        inventory_id = c2.selectbox("Material", [0] + inv.id.tolist(), format_func=lambda x: "No aplica" if x == 0 else inv.loc[inv.id.eq(x), "nombre"].iloc[0])
        asset_id = c3.selectbox("Activo", [0] + assets.id.tolist(), format_func=lambda x: "No aplica" if x == 0 else assets.loc[assets.id.eq(x), "nombre"].iloc[0])
        d1, d2, d3, d4 = st.columns(4)
        desc = d1.text_input("Descripción")
        qty = d2.number_input("Cantidad teórica", min_value=0.0, value=1.0)
        unit = d3.selectbox("Unidad", BASE_UNITS)
        waste = d4.number_input("Merma (%)", min_value=0.0, value=0.0)
        e1, e2 = st.columns(2)
        manual_cost = e1.number_input("Costo manual USD/unidad o minuto", min_value=0.0, value=0.0)
        minutes = e2.number_input("Minutos", min_value=0.0, value=0.0)
        add = st.form_submit_button("Agregar componente")
    if add:
        with db_transaction() as conn:
            conn.execute("INSERT INTO recetas_costeo_componentes(receta_id,tipo_componente,inventario_id,activo_id,descripcion,cantidad_teorica,unidad_base,merma_pct,costo_manual_usd,minutos) VALUES (?,?,?,?,?,?,?,?,?,?)", (int(recipe_id), component_type, int(inventory_id) or None, int(asset_id) or None, desc.strip() or component_type, qty, unit, waste, manual_cost, minutes))
        st.success("Componente agregado.")
    comps = _df("SELECT rc.*, i.nombre material, a.nombre activo FROM recetas_costeo_componentes rc LEFT JOIN inventario i ON i.id=rc.inventario_id LEFT JOIN activos_productivos_costeo a ON a.id=rc.activo_id WHERE rc.receta_id=?", (int(recipe_id),))
    st.dataframe(comps, use_container_width=True, hide_index=True)


def _render_quote(usuario: str) -> None:
    st.subheader("💵 Cotización integral")
    recipes = _df("SELECT * FROM recetas_costeo WHERE estado='activa' ORDER BY nombre")
    if recipes.empty:
        st.warning("Crea al menos una receta.")
        return
    clients = _clients()
    c1, c2 = st.columns(2)
    client_id = c1.selectbox("Cliente", [0] + clients.id.tolist(), format_func=lambda x: "Cliente General" if x == 0 else clients.loc[clients.id.eq(x), "nombre"].iloc[0])
    recipe_id = c2.selectbox("Receta", recipes.id.tolist(), format_func=lambda x: recipes.loc[recipes.id.eq(x), "nombre"].iloc[0])
    q1, q2, q3 = st.columns(3)
    quantity = q1.number_input("Cantidad", min_value=0.000001, value=1.0)
    labor_rate = q2.number_input("Mano de obra USD/min", min_value=0.0, value=0.0)
    indirect_pct = q3.number_input("Indirectos (%)", min_value=0.0, value=0.0)
    description = st.text_area("Descripción del trabajo")
    uploaded = st.file_uploader("Archivo del cliente", type=["pdf", "png", "jpg", "jpeg"])
    confidential = st.checkbox("Documento confidencial: eliminar después de la entrega")
    result = calculate_recipe_cost(int(recipe_id), quantity, labor_rate, indirect_pct)
    rate, rate_date = _rates()
    custom_margin = st.number_input("Margen sobre venta (%)", min_value=0.0, max_value=99.0, value=float(result["margen_pct"]))
    price = price_from_margin(result["costo_total_usd"], custom_margin)
    bs = price * rate
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Costo total", f"${result['costo_total_usd']:,.4f}")
    m2.metric("Precio USD", f"${price:,.2f}")
    m3.metric("BCV activa", f"{rate:,.2f} Bs/USD")
    m4.metric("Precio Bs", f"Bs {bs:,.2f}")
    st.dataframe(pd.DataFrame(result["detalle"]), use_container_width=True, hide_index=True)
    if rate <= 0:
        st.error("La tasa BCV está en cero. Actualízala antes de guardar.")
    if st.button("Guardar cotización integral", type="primary", use_container_width=True, disabled=rate <= 0):
        file_name = file_path = ""
        if uploaded is not None:
            safe = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded.name.replace('/', '_')}"
            path = UPLOAD_DIR / safe
            path.write_bytes(uploaded.getvalue())
            file_name, file_path = uploaded.name, str(path)
        client_name = "Cliente General" if not client_id else clients.loc[clients.id.eq(client_id), "nombre"].iloc[0]
        phone = "" if not client_id else clients.loc[clients.id.eq(client_id), "telefono"].iloc[0]
        quote_id = save_integrated_quote({"usuario": usuario, "cliente_id": int(client_id) or None, "cliente": client_name, "telefono": phone, "receta_id": int(recipe_id), "descripcion": description or result["receta"]["nombre"], "cantidad": quantity, "archivo_nombre": file_name, "archivo_ruta": file_path, "confidencial": confidential, "materiales_usd": result["materiales_usd"], "merma_usd": result["merma_usd"], "activos_usd": result["activos_usd"], "mano_obra_usd": result["mano_obra_usd"], "indirectos_usd": result["indirectos_usd"], "costo_total_usd": result["costo_total_usd"], "margen_pct": custom_margin, "precio_usd": price, "tasa_bcv": rate, "fecha_tasa": rate_date, "precio_bs": bs, "detalle": result})
        st.success(f"Cotización integral #{quote_id} guardada con la tasa histórica usada.")
    history = _df("SELECT id,fecha,cliente,descripcion,cantidad,costo_total_usd,margen_pct,precio_usd,tasa_bcv,precio_bs,estado,archivo_nombre FROM cotizaciones_costeo_integral ORDER BY id DESC")
    st.dataframe(history, use_container_width=True, hide_index=True)


def _render_consumption(usuario: str) -> None:
    st.subheader("♻️ Consumo real, merma y sobrante recuperable")
    quotes = _df("SELECT id,cliente,descripcion FROM cotizaciones_costeo_integral ORDER BY id DESC")
    inv = _inventory()
    if quotes.empty or inv.empty:
        st.info("Se necesitan cotizaciones y materiales registrados.")
        return
    with st.form("real_consumption"):
        qid = st.selectbox("Cotización", quotes.id.tolist(), format_func=lambda x: f"#{x} · {quotes.loc[quotes.id.eq(x),'cliente'].iloc[0]} · {quotes.loc[quotes.id.eq(x),'descripcion'].iloc[0]}")
        iid = st.selectbox("Material", inv.id.tolist(), format_func=lambda x: inv.loc[inv.id.eq(x), "nombre"].iloc[0])
        c1, c2, c3, c4 = st.columns(4)
        theoretical = c1.number_input("Consumo teórico", min_value=0.0, value=0.0)
        real = c2.number_input("Consumo real total", min_value=0.0, value=0.0)
        waste = c3.number_input("Merma real", min_value=0.0, value=0.0)
        reusable = c4.number_input("Sobrante recuperable", min_value=0.0, value=0.0)
        reason = st.text_input("Motivo de merma")
        save = st.form_submit_button("Registrar y descontar inventario")
    if save:
        row = inv[inv.id.eq(iid)].iloc[0]
        cost = float(row.costo or 0) * real
        with db_transaction() as conn:
            current = conn.execute("SELECT COALESCE(cantidad,0) cantidad FROM inventario WHERE id=?", (int(iid),)).fetchone()
            current_qty = float(current["cantidad"] or 0) if current else 0
            if real > current_qty:
                raise ValueError("El consumo real supera el stock disponible.")
            conn.execute("UPDATE inventario SET cantidad=cantidad-? WHERE id=?", (real, int(iid)))
            conn.execute("INSERT INTO produccion_consumos_integrales(cotizacion_integral_id,inventario_id,descripcion,consumo_teorico,consumo_real,merma_real,sobrante_recuperable,unidad_base,costo_real_usd,motivo_merma,usuario) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (int(qid), int(iid), row.nombre, theoretical, real, waste, reusable, row.unidad, cost, reason, usuario))
        st.success("Consumo, merma y sobrante registrados.")
    history = _df("SELECT pci.*, i.nombre material FROM produccion_consumos_integrales pci LEFT JOIN inventario i ON i.id=pci.inventario_id ORDER BY pci.id DESC")
    st.dataframe(history, use_container_width=True, hide_index=True)


def render_costeo_integral(usuario: str) -> None:
    ensure_integrated_costing_schema()
    st.markdown("### 🔗 Centro de costeo integral")
    st.caption("Factura → costo puesto en almacén → unidades mínimas → activos → receta → cotización BCV → consumo y merma real.")
    tabs = st.tabs(["Compras", "Unidades", "Activos", "Recetas", "Cotizar", "Consumo real"])
    with tabs[0]:
        _render_purchase(usuario)
    with tabs[1]:
        _render_units()
    with tabs[2]:
        _render_assets()
    with tabs[3]:
        _render_recipes()
    with tabs[4]:
        _render_quote(usuario)
    with tabs[5]:
        _render_consumption(usuario)
