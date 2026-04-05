from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text
from modules.integration_hub import dispatch_to_module, render_send_buttons
from services.contabilidad_service import contabilizar_venta
from services.conciliacion_service import periodo_esta_cerrado
from services.costeo_service import actualizar_vinculos_costeo
from services.cxc_cobranza_service import CobranzaInput, registrar_abono_cuenta_por_cobrar
from services.tesoreria_service import registrar_ingreso
from utils.currency import convert_to_bs


METODOS_PAGO_VENTA = [
    "efectivo",
    "transferencia",
    "zelle",
    "binance",
    "kontigo",
    "credito",
]

MONEDAS_VENTA = ["USD", "BS", "USDT", "KONTIGO"]


# ============================================================
# AUXILIARES
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_text(value: Any, default: str = "") -> str:
    txt = clean_text(value)
    return txt if txt else default


def _safe_date_text(value: Any) -> str:
    txt = clean_text(value)
    if not txt:
        return ""
    try:
        return pd.to_datetime(txt).date().isoformat()
    except Exception:
        return ""


def _normalize_currency(moneda: str) -> str:
    txt = clean_text(moneda).upper()
    if txt in {"BS", "VES", "BOLIVARES", "BOLÍVARES"}:
        return "BS"
    if txt in {"USDT"}:
        return "USDT"
    if txt in {"KONTIGO"}:
        return "KONTIGO"
    return "USD"


def _ensure_sales_state() -> None:
    if "ventas_items" not in st.session_state:
        st.session_state.ventas_items = []


def _clear_sales_state() -> None:
    st.session_state.ventas_items = []


def _infer_fiscal_type(iva_pct: float) -> str:
    return "gravada" if float(iva_pct or 0.0) > 0 else "exenta"


def _get_price_for_item(producto_row: dict[str, Any], override_price: float | None = None) -> float:
    if override_price is not None and float(override_price) > 0:
        return float(override_price)
    return float(producto_row.get("precio_venta_usd") or 0.0)


def _calcular_totales_items(
    items: list[dict[str, Any]],
    descuento_global_usd: float = 0.0,
    iva_pct: float = 16.0,
) -> dict[str, float]:
    subtotal = 0.0
    costo_total = 0.0

    for item in items:
        cantidad = as_positive(item.get("cantidad", 0), "Cantidad", allow_zero=False)
        precio = as_positive(item.get("precio_unitario_usd", 0), "Precio unitario")
        costo = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario")
        descuento_item = max(0.0, float(item.get("descuento_usd", 0.0) or 0.0))

        subtotal_linea = max((cantidad * precio) - descuento_item, 0.0)
        subtotal += subtotal_linea
        costo_total += cantidad * costo

    descuento_global_usd = max(0.0, float(descuento_global_usd or 0.0))
    subtotal_neto = max(subtotal - descuento_global_usd, 0.0)

    iva_pct = max(0.0, float(iva_pct or 0.0))
    impuesto = round(subtotal_neto * (iva_pct / 100.0), 2)
    total = round(subtotal_neto + impuesto, 2)
    utilidad = round(subtotal_neto - costo_total, 2)

    return {
        "subtotal_bruto_usd": round(subtotal, 2),
        "descuento_global_usd": round(descuento_global_usd, 2),
        "subtotal_usd": round(subtotal_neto, 2),
        "impuesto_usd": round(impuesto, 2),
        "total_usd": round(total, 2),
        "costo_total_usd": round(costo_total, 2),
        "utilidad_estimada_usd": round(utilidad, 2),
    }


def _load_clientes() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT id, nombre
                FROM clientes
                WHERE COALESCE(estado, 'activo') = 'activo'
                ORDER BY nombre
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(columns=["id", "nombre"])
    return df


def _load_productos() -> pd.DataFrame:
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                sku,
                nombre,
                categoria,
                unidad,
                COALESCE(stock_actual, 0) AS stock_actual,
                COALESCE(costo_unitario_usd, 0) AS costo_unitario_usd,
                COALESCE(precio_venta_usd, 0) AS precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY nombre
            """,
            conn,
        )

    if df.empty:
        return df

    df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce").fillna(0.0)
    df["costo_unitario_usd"] = pd.to_numeric(df["costo_unitario_usd"], errors="coerce").fillna(0.0)
    df["precio_venta_usd"] = pd.to_numeric(df["precio_venta_usd"], errors="coerce").fillna(0.0)
    return df


def _load_historial_ventas() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT
                    v.id,
                    v.fecha,
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    COALESCE(vd.descripcion, 'Sin detalle') AS detalle,
                    COALESCE(vd.cantidad, 0) AS cantidad,
                    COALESCE(vd.precio_unitario_usd, 0) AS precio_unitario_usd,
                    COALESCE(vd.costo_unitario_usd, 0) AS costo_unitario_usd,
                    COALESCE(vd.subtotal_usd, 0) AS subtotal_linea_usd,
                    COALESCE(v.moneda, 'USD') AS moneda,
                    COALESCE(v.tasa_cambio, 1) AS tasa_cambio,
                    COALESCE(v.metodo_pago, 'efectivo') AS metodo_pago,
                    COALESCE(v.subtotal_usd, 0) AS subtotal_usd,
                    COALESCE(v.impuesto_usd, 0) AS impuesto_usd,
                    COALESCE(v.total_usd, 0) AS total_usd,
                    COALESCE(v.total_bs, 0) AS total_bs,
                    COALESCE(v.estado, 'registrada') AS estado
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
                WHERE COALESCE(v.estado, 'registrada') = 'registrada'
                ORDER BY v.fecha DESC, v.id DESC
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(
                columns=[
                    "id",
                    "fecha",
                    "cliente",
                    "detalle",
                    "cantidad",
                    "precio_unitario_usd",
                    "costo_unitario_usd",
                    "subtotal_linea_usd",
                    "moneda",
                    "tasa_cambio",
                    "metodo_pago",
                    "subtotal_usd",
                    "impuesto_usd",
                    "total_usd",
                    "total_bs",
                    "estado",
                ]
            )

    if df.empty:
        return df

    numeric_cols = [
        "cantidad",
        "precio_unitario_usd",
        "costo_unitario_usd",
        "subtotal_linea_usd",
        "tasa_cambio",
        "subtotal_usd",
        "impuesto_usd",
        "total_usd",
        "total_bs",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["utilidad_estimada"] = df["subtotal_linea_usd"] - (df["cantidad"] * df["costo_unitario_usd"])
    return df


def _load_cuentas_por_cobrar_df() -> pd.DataFrame:
    with db_transaction() as conn:
        try:
            df = pd.read_sql_query(
                """
                SELECT
                    cxc.id,
                    cxc.fecha,
                    cxc.venta_id,
                    COALESCE(cl.nombre, 'Sin cliente') AS cliente,
                    COALESCE(cxc.tipo_documento, 'venta') AS tipo_documento,
                    COALESCE(cxc.monto_original_usd, 0) AS monto_original_usd,
                    COALESCE(cxc.monto_cobrado_usd, 0) AS monto_cobrado_usd,
                    COALESCE(cxc.saldo_usd, 0) AS saldo_usd,
                    COALESCE(cxc.estado, 'pendiente') AS estado,
                    COALESCE(cxc.dias_vencimiento, 0) AS dias_vencimiento,
                    COALESCE(cxc.notas, '') AS notas
                FROM cuentas_por_cobrar cxc
                LEFT JOIN ventas v ON v.id = cxc.venta_id
                LEFT JOIN clientes cl ON cl.id = cxc.cliente_id
                ORDER BY cxc.fecha DESC, cxc.id DESC
                """,
                conn,
            )
        except Exception:
            df = pd.DataFrame(
                columns=[
                    "id",
                    "fecha",
                    "venta_id",
                    "cliente",
                    "tipo_documento",
                    "monto_original_usd",
                    "monto_cobrado_usd",
                    "saldo_usd",
                    "estado",
                    "dias_vencimiento",
                    "notas",
                ]
            )

    if df.empty:
        return df

    for col in ["monto_original_usd", "monto_cobrado_usd", "saldo_usd", "dias_vencimiento"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


# ============================================================
# REGISTRO DE VENTA
# ============================================================

def registrar_venta(
    usuario: str,
    cliente_id: int | None,
    moneda: str,
    tasa_cambio: float,
    metodo_pago: str,
    items: list[dict[str, Any]],
    descuento_global_usd: float = 0.0,
    iva_pct: float = 16.0,
    dias_credito: int = 30,
    observacion: str = "",
    costeo_orden_id: int | None = None,
) -> int:
    if not items:
        raise ValueError("Debe agregar al menos un ítem.")

    metodo_pago = clean_text(metodo_pago).lower()
    moneda = _normalize_currency(moneda)
    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    dias_credito = max(0, int(dias_credito or 0))

    totales = _calcular_totales_items(
        items=items,
        descuento_global_usd=float(descuento_global_usd or 0.0),
        iva_pct=float(iva_pct or 0.0),
    )

    subtotal = float(totales["subtotal_usd"])
    impuesto = float(totales["impuesto_usd"])
    total = float(totales["total_usd"])
    total_bs = round(convert_to_bs(total, tasa_cambio), 2)

    if total <= 0:
        raise ValueError("El total de la venta debe ser mayor a cero.")

    with db_transaction() as conn:
        if periodo_esta_cerrado(conn, fecha_movimiento=date.today().isoformat(), tipo_cierre="mensual"):
            raise ValueError("Periodo mensual cerrado: no se permiten nuevas ventas en esta fecha.")

        cur = conn.execute(
            """
            INSERT INTO ventas
            (
                usuario,
                cliente_id,
                moneda,
                tasa_cambio,
                metodo_pago,
                subtotal_usd,
                impuesto_usd,
                fiscal_tipo,
                fiscal_tasa_iva,
                fiscal_iva_debito_usd,
                total_usd,
                total_bs,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'registrada')
            """,
            (
                usuario,
                cliente_id,
                moneda,
                float(tasa_cambio),
                metodo_pago,
                money(subtotal),
                money(impuesto),
                _infer_fiscal_type(iva_pct),
                float(iva_pct or 0.0) / 100.0,
                money(impuesto),
                money(total),
                money(total_bs),
            ),
        )
        venta_id = int(cur.lastrowid)

        for item in items:
            inventario_id = item.get("inventario_id")
            descripcion = require_text(item.get("descripcion") or "Ítem", "Descripción")
            cantidad = as_positive(item.get("cantidad", 0), "Cantidad", allow_zero=False)
            precio_u = as_positive(item.get("precio_unitario_usd", 0), "Precio unitario")
            costo_u = as_positive(item.get("costo_unitario_usd", 0), "Costo unitario")
            descuento_item = max(0.0, float(item.get("descuento_usd", 0.0) or 0.0))
            subtotal_linea = round(max((cantidad * precio_u) - descuento_item, 0.0), 2)

            conn.execute(
                """
                INSERT INTO ventas_detalle
                (
                    usuario,
                    venta_id,
                    inventario_id,
                    descripcion,
                    cantidad,
                    precio_unitario_usd,
                    costo_unitario_usd,
                    subtotal_usd
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    int(venta_id),
                    int(inventario_id) if inventario_id else None,
                    descripcion,
                    float(cantidad),
                    money(precio_u),
                    money(costo_u),
                    money(subtotal_linea),
                ),
            )

            if inventario_id:
                current = conn.execute(
                    """
                    SELECT id, nombre, stock_actual
                    FROM inventario
                    WHERE id=? AND COALESCE(estado, 'activo')='activo'
                    """,
                    (int(inventario_id),),
                ).fetchone()

                if not current:
                    raise ValueError(f"Inventario #{inventario_id} no existe.")

                stock_actual = float(current["stock_actual"] or 0.0)
                if stock_actual < float(cantidad):
                    raise ValueError(f"Stock insuficiente para {current['nombre']}.")

                conn.execute(
                    """
                    UPDATE inventario
                    SET stock_actual = stock_actual - ?
                    WHERE id = ?
                    """,
                    (float(cantidad), int(inventario_id)),
                )

                conn.execute(
                    """
                    INSERT INTO movimientos_inventario
                    (
                        usuario,
                        inventario_id,
                        tipo,
                        cantidad,
                        costo_unitario_usd,
                        referencia
                    )
                    VALUES (?, ?, 'salida', ?, ?, ?)
                    """,
                    (
                        usuario,
                        int(inventario_id),
                        -abs(float(cantidad)),
                        money(costo_u),
                        f"Venta #{venta_id}",
                    ),
                )

        if metodo_pago == "credito":
            if not cliente_id:
                raise ValueError("Para una venta a crédito debes seleccionar un cliente.")

            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar
                (
                    usuario,
                    cliente_id,
                    venta_id,
                    tipo_documento,
                    monto_original_usd,
                    monto_cobrado_usd,
                    saldo_usd,
                    estado,
                    dias_vencimiento,
                    notas
                )
                VALUES (?, ?, ?, 'venta', ?, 0, ?, 'pendiente', ?, ?)
                """,
                (
                    usuario,
                    int(cliente_id),
                    int(venta_id),
                    money(total),
                    money(total),
                    int(dias_credito),
                    clean_text(observacion) or "Generada desde ventas",
                ),
            )

            conn.execute(
                """
                UPDATE clientes
                SET saldo_por_cobrar_usd = COALESCE(saldo_por_cobrar_usd, 0) + ?
                WHERE id = ?
                """,
                (money(total), int(cliente_id)),
            )
        else:
            registrar_ingreso(
                conn,
                origen="venta",
                referencia_id=int(venta_id),
                descripcion=f"Venta #{venta_id}",
                monto_usd=float(total),
                moneda=str(moneda),
                monto_moneda=float(total if moneda in {"USD", "USDT", "KONTIGO"} else total_bs),
                tasa_cambio=float(tasa_cambio),
                metodo_pago=metodo_pago,
                usuario=usuario,
                metadata={
                    "cliente_id": int(cliente_id) if cliente_id is not None else None,
                    "metodo_pago": metodo_pago,
                    "observacion": clean_text(observacion),
                },
            )

        contabilizar_venta(conn, venta_id=venta_id, usuario=usuario)

    if costeo_orden_id:
        actualizar_vinculos_costeo(
            orden_id=int(costeo_orden_id),
            venta_id=int(venta_id),
            estado="aprobado",
        )

    return int(venta_id)


# ============================================================
# CARRITO
# ============================================================

def _add_item_to_cart(
    producto_row: dict[str, Any],
    cantidad: float,
    precio_unitario_usd: float,
    descuento_usd: float = 0.0,
) -> None:
    _ensure_sales_state()

    inventario_id = int(producto_row["id"])
    nombre = str(producto_row["nombre"])
    sku = str(producto_row.get("sku") or "")
    costo_u = float(producto_row.get("costo_unitario_usd") or 0.0)
    precio_u = float(precio_unitario_usd or 0.0)
    cantidad = float(cantidad or 0.0)
    descuento_usd = max(0.0, float(descuento_usd or 0.0))

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")

    if precio_u < 0:
        raise ValueError("El precio no puede ser negativo.")

    stock_disp = float(producto_row.get("stock_actual") or 0.0)
    if cantidad > stock_disp:
        raise ValueError("La cantidad supera el stock disponible.")

    carrito = st.session_state.ventas_items
    idx_existente = next((i for i, x in enumerate(carrito) if int(x["inventario_id"]) == inventario_id), None)

    if idx_existente is None:
        carrito.append(
            {
                "inventario_id": inventario_id,
                "sku": sku,
                "descripcion": nombre,
                "cantidad": cantidad,
                "precio_unitario_usd": precio_u,
                "costo_unitario_usd": costo_u,
                "descuento_usd": descuento_usd,
                "stock_disponible": stock_disp,
            }
        )
    else:
        nueva_cantidad = float(carrito[idx_existente]["cantidad"]) + cantidad
        if nueva_cantidad > stock_disp:
            raise ValueError("La suma de cantidades supera el stock disponible para ese producto.")
        carrito[idx_existente]["cantidad"] = nueva_cantidad
        carrito[idx_existente]["precio_unitario_usd"] = precio_u
        carrito[idx_existente]["descuento_usd"] = descuento_usd

    st.session_state.ventas_items = carrito


def _render_carrito_editor() -> list[dict[str, Any]]:
    _ensure_sales_state()
    items = st.session_state.ventas_items

    st.markdown("### Carrito de venta")

    if not items:
        st.info("Todavía no has agregado productos al carrito.")
        return []

    df_carrito = pd.DataFrame(items)
    df_carrito["subtotal_usd"] = (
        df_carrito["cantidad"].astype(float) * df_carrito["precio_unitario_usd"].astype(float)
        - df_carrito["descuento_usd"].astype(float)
    ).clip(lower=0.0)

    edited = st.data_editor(
        df_carrito[
            [
                "sku",
                "descripcion",
                "cantidad",
                "precio_unitario_usd",
                "descuento_usd",
                "stock_disponible",
                "subtotal_usd",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "sku": st.column_config.TextColumn("SKU", disabled=True),
            "descripcion": st.column_config.TextColumn("Producto", disabled=True),
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0, format="%.3f"),
            "precio_unitario_usd": st.column_config.NumberColumn("Precio USD", min_value=0.0, format="%.4f"),
            "descuento_usd": st.column_config.NumberColumn("Descuento USD", min_value=0.0, format="%.2f"),
            "stock_disponible": st.column_config.NumberColumn("Stock", disabled=True, format="%.3f"),
            "subtotal_usd": st.column_config.NumberColumn("Subtotal", disabled=True, format="%.2f"),
        },
        key="ventas_carrito_editor",
    )

    nuevos_items: list[dict[str, Any]] = []
    for original, (_, row) in zip(items, edited.iterrows()):
        cantidad = max(0.0, float(row["cantidad"] or 0.0))
        precio = max(0.0, float(row["precio_unitario_usd"] or 0.0))
        descuento = max(0.0, float(row["descuento_usd"] or 0.0))
        stock_disp = float(original.get("stock_disponible") or 0.0)

        if cantidad == 0:
            continue
        if cantidad > stock_disp:
            cantidad = stock_disp

        nuevos_items.append(
            {
                **original,
                "cantidad": cantidad,
                "precio_unitario_usd": precio,
                "descuento_usd": descuento,
            }
        )

    st.session_state.ventas_items = nuevos_items

    c1, c2 = st.columns(2)
    if c1.button("🧹 Vaciar carrito", use_container_width=True):
        _clear_sales_state()
        st.rerun()

    if c2.button("🗑 Quitar último producto", use_container_width=True):
        if st.session_state.ventas_items:
            st.session_state.ventas_items.pop()
            st.rerun()

    return st.session_state.ventas_items


# ============================================================
# TAB REGISTRO
# ============================================================

def _render_tab_registro(usuario: str) -> None:
    _ensure_sales_state()

    try:
        df_clientes = _load_clientes()
        df_productos = _load_productos()
    except Exception as exc:
        st.error("Error cargando datos para ventas.")
        st.exception(exc)
        return

    st.subheader("Nueva venta profesional")

    if df_productos.empty:
        st.warning("No hay productos activos en inventario para vender.")
        return

    with st.container(border=True):
        st.markdown("### Agregar producto al carrito")

        productos_ids = df_productos["id"].tolist()
        c1, c2, c3, c4 = st.columns(4)

        producto_id = c1.selectbox(
            "Producto",
            productos_ids,
            format_func=lambda pid: (
                f"{df_productos.loc[df_productos['id'] == pid, 'nombre'].iloc[0]} "
                f"({df_productos.loc[df_productos['id'] == pid, 'sku'].iloc[0]})"
            ),
            key="ventas_producto_id",
        )

        producto_row = df_productos[df_productos["id"] == producto_id].iloc[0].to_dict()
        cantidad = c2.number_input("Cantidad", min_value=0.001, value=1.0, format="%.3f", key="ventas_cantidad_item")
        precio_manual = c3.number_input(
            "Precio unitario USD",
            min_value=0.0,
            value=float(producto_row.get("precio_venta_usd") or 0.0),
            format="%.4f",
            key="ventas_precio_item",
        )
        descuento_item = c4.number_input(
            "Descuento item USD",
            min_value=0.0,
            value=0.0,
            format="%.2f",
            key="ventas_desc_item",
        )

        p1, p2, p3 = st.columns(3)
        p1.metric("Stock disponible", f"{float(producto_row.get('stock_actual') or 0.0):,.3f}")
        p2.metric("Costo unitario", f"$ {float(producto_row.get('costo_unitario_usd') or 0.0):,.4f}")
        p3.metric("Precio sugerido", f"$ {float(producto_row.get('precio_venta_usd') or 0.0):,.4f}")

        if st.button("➕ Agregar al carrito", use_container_width=True):
            try:
                _add_item_to_cart(
                    producto_row=producto_row,
                    cantidad=float(cantidad),
                    precio_unitario_usd=float(precio_manual),
                    descuento_usd=float(descuento_item),
                )
                st.success("Producto agregado al carrito.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    items = _render_carrito_editor()

    if not items:
        return

    st.divider()
    st.markdown("### Datos generales de la venta")

    cliente_map: dict[str, int | None] = {"Sin cliente": None}
    if not df_clientes.empty:
        for _, row in df_clientes.iterrows():
            cliente_map[str(row["nombre"])] = int(row["id"])

    f1, f2, f3, f4 = st.columns(4)
    cliente_nombre = f1.selectbox("Cliente", list(cliente_map.keys()), key="ventas_cliente")
    metodo_pago = f2.selectbox("Método de pago", METODOS_PAGO_VENTA, key="ventas_metodo")
    moneda = f3.selectbox("Moneda", MONEDAS_VENTA, key="ventas_moneda")
    tasa = f4.number_input("Tasa de referencia", min_value=0.0001, value=36.5, format="%.4f", key="ventas_tasa")

    f5, f6, f7 = st.columns(3)
    descuento_global = f5.number_input("Descuento global USD", min_value=0.0, value=0.0, format="%.2f", key="ventas_desc_global")
    iva_pct = f6.number_input("IVA (%)", min_value=0.0, max_value=100.0, value=16.0, format="%.2f", key="ventas_iva")
    dias_credito = f7.number_input("Días de crédito", min_value=0, max_value=365, value=30, step=1, key="ventas_dias_credito")

    observacion = st.text_area("Observación", key="ventas_observacion")

    totales = _calcular_totales_items(
        items=items,
        descuento_global_usd=float(descuento_global),
        iva_pct=float(iva_pct),
    )

    total_bs = float(convert_to_bs(float(totales["total_usd"]), float(tasa)))

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Subtotal bruto", f"$ {float(totales['subtotal_bruto_usd']):,.2f}")
    k2.metric("Descuento", f"$ {float(descuento_global):,.2f}")
    k3.metric("Subtotal neto", f"$ {float(totales['subtotal_usd']):,.2f}")
    k4.metric("IVA", f"$ {float(totales['impuesto_usd']):,.2f}")
    k5.metric("Total", f"$ {float(totales['total_usd']):,.2f}")

    s1, s2 = st.columns(2)
    s1.metric("Total en Bs", f"{float(total_bs):,.2f}")
    s2.metric("Utilidad estimada", f"$ {float(totales['utilidad_estimada_usd']):,.2f}")

    st.markdown("### 🔗 Enviar referencia a otros módulos")

    def _build_to_tesoreria():
        total_usd = float(totales["total_usd"])
        monto_pagado = total_usd if metodo_pago != "credito" else 0.0
        return (
            "venta_preparada",
            {
                "venta_id": None,
                "cliente": cliente_nombre,
                "total": round(total_usd, 2),
                "monto_pagado": round(monto_pagado, 2),
                "saldo": round(max(total_usd - monto_pagado, 0.0), 2),
                "metodo_pago": metodo_pago,
                "referencia": f"VENTA-{cliente_nombre}",
            },
        )

    render_send_buttons(
        source_module="ventas",
        payload_builders={
            "tesorería": _build_to_tesoreria,
            "caja empresarial": _build_to_tesoreria,
        },
    )

    if metodo_pago == "credito" and cliente_map[cliente_nombre] is None:
        st.warning("Para registrar una venta a crédito debes seleccionar un cliente.")

    if st.button("🚀 Registrar venta", use_container_width=True):
        try:
            if metodo_pago == "credito" and cliente_map[cliente_nombre] is None:
                raise ValueError("Debes seleccionar un cliente para una venta a crédito.")

            venta_id = registrar_venta(
                usuario=usuario,
                cliente_id=cliente_map[cliente_nombre],
                moneda=str(moneda),
                tasa_cambio=float(tasa),
                metodo_pago=str(metodo_pago),
                items=items,
                descuento_global_usd=float(descuento_global),
                iva_pct=float(iva_pct),
                dias_credito=int(dias_credito),
                observacion=observacion,
            )
            total_usd = float(totales["total_usd"])
            monto_pagado = total_usd if metodo_pago != "credito" else 0.0
            dispatch_to_module(
                source_module="ventas",
                target_module="tesorería",
                payload={
                    "source_module": "ventas",
                    "source_action": "venta_registrada",
                    "record_id": venta_id,
                    "referencia": f"VENTA-{venta_id}",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "usuario": usuario,
                    "payload_data": {
                        "venta_id": int(venta_id),
                        "cliente": cliente_nombre,
                        "total": round(total_usd, 2),
                        "monto_pagado": round(monto_pagado, 2),
                        "saldo": round(max(total_usd - monto_pagado, 0.0), 2),
                        "metodo_pago": metodo_pago,
                    },
                },
            )

            _clear_sales_state()
            st.success(f"✅ Venta #{venta_id} registrada correctamente.")
            st.balloons()
            st.rerun()

        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("Ocurrió un error registrando la venta.")
            st.exception(exc)


# ============================================================
# TAB HISTORIAL
# ============================================================

def _render_tab_historial() -> None:
    st.subheader("Historial de ventas")

    try:
        df = _load_historial_ventas()
    except Exception as exc:
        st.error("Error cargando historial de ventas.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay ventas registradas.")
        return

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="hist_ventas_desde")
    hasta = c2.date_input("Hasta", date.today(), key="hist_ventas_hasta")
    metodo = c3.selectbox(
        "Método",
        ["Todos"] + sorted(df["metodo_pago"].astype(str).str.lower().unique().tolist()),
        key="hist_ventas_metodo",
    )
    buscar = c4.text_input("Buscar por cliente o detalle", key="hist_ventas_buscar")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if metodo != "Todos":
        df_fil = df_fil[df_fil["metodo_pago"].astype(str).str.lower() == metodo.lower()]

    if buscar:
        txt = clean_text(buscar)
        df_fil = df_fil[
            df_fil["cliente"].astype(str).str.contains(txt, case=False, na=False)
            | df_fil["detalle"].astype(str).str.contains(txt, case=False, na=False)
        ]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total filtrado", f"$ {float(df_fil['total_usd'].sum()):,.2f}")
    k2.metric("Ventas únicas", f"{int(df_fil['id'].nunique())}")
    ticket = float(df_fil["total_usd"].sum()) / max(int(df_fil["id"].nunique()), 1)
    k3.metric("Ticket promedio", f"$ {ticket:,.2f}")
    k4.metric("Utilidad estimada", f"$ {float(df_fil['utilidad_estimada'].sum()):,.2f}")

    st.dataframe(
        df_fil,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "precio_unitario_usd": st.column_config.NumberColumn("Precio", format="%.4f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo", format="%.4f"),
            "subtotal_linea_usd": st.column_config.NumberColumn("Subtotal línea", format="%.2f"),
            "subtotal_usd": st.column_config.NumberColumn("Subtotal venta", format="%.2f"),
            "impuesto_usd": st.column_config.NumberColumn("IVA", format="%.2f"),
            "total_usd": st.column_config.NumberColumn("Total USD", format="%.2f"),
            "total_bs": st.column_config.NumberColumn("Total Bs", format="%.2f"),
            "utilidad_estimada": st.column_config.NumberColumn("Utilidad estimada", format="%.2f"),
        },
    )

    if not df_fil.empty:
        tendencia = (
            df_fil.assign(dia=df_fil["fecha"].dt.date)
            .groupby("dia", as_index=False)["total_usd"]
            .sum()
            .sort_values("dia")
        )
        metodos = (
            df_fil.groupby("metodo_pago", as_index=False)["total_usd"]
            .sum()
            .sort_values("total_usd", ascending=False)
        )

        g1, g2 = st.columns(2)
        with g1:
            st.caption("Tendencia de ventas")
            st.line_chart(tendencia.set_index("dia")["total_usd"])
        with g2:
            st.caption("Ventas por método")
            st.bar_chart(metodos.set_index("metodo_pago")["total_usd"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_fil.to_excel(writer, index=False, sheet_name="Ventas")

    st.download_button(
        "📥 Exportar historial Excel",
        buffer.getvalue(),
        file_name="historial_ventas.xlsx",
        use_container_width=True,
    )


# ============================================================
# TAB CUENTAS POR COBRAR
# ============================================================

def _render_tab_cuentas_por_cobrar(usuario: str) -> None:
    st.subheader("Cuentas por cobrar")

    try:
        df = _load_cuentas_por_cobrar_df()
    except Exception as exc:
        st.error("Error cargando cuentas por cobrar.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay cuentas por cobrar registradas.")
        return

    f1, f2 = st.columns([2, 1])
    buscar = f1.text_input("Buscar cliente / notas", key="cxc_buscar")
    estado = f2.selectbox("Estado", ["Todos", "pendiente", "pagada", "vencida"], key="cxc_estado")

    view = df.copy()
    if buscar:
        txt = clean_text(buscar)
        view = view[
            view["cliente"].astype(str).str.contains(txt, case=False, na=False)
            | view["notas"].astype(str).str.contains(txt, case=False, na=False)
        ]

    if estado != "Todos":
        view = view[view["estado"].astype(str).str.lower() == estado.lower()]

    k1, k2, k3 = st.columns(3)
    k1.metric("Monto original", f"$ {float(view['monto_original_usd'].sum()):,.2f}")
    k2.metric("Cobrado", f"$ {float(view['monto_cobrado_usd'].sum()):,.2f}")
    k3.metric("Saldo", f"$ {float(view['saldo_usd'].sum()):,.2f}")

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "monto_original_usd": st.column_config.NumberColumn("Monto original", format="%.2f"),
            "monto_cobrado_usd": st.column_config.NumberColumn("Cobrado", format="%.2f"),
            "saldo_usd": st.column_config.NumberColumn("Saldo", format="%.2f"),
            "dias_vencimiento": st.column_config.NumberColumn("Días vencimiento", format="%d"),
        },
    )

    st.divider()
    st.markdown("### Registrar abono")

    cuentas_ids = view["id"].tolist()
    if not cuentas_ids:
        st.info("No hay cuentas visibles para abonar.")
        return

    cta_id = st.selectbox(
        "Cuenta por cobrar",
        cuentas_ids,
        format_func=lambda cid: (
            f"Cuenta #{cid} · "
            f"{view.loc[view['id'] == cid, 'cliente'].iloc[0]} · "
            f"Saldo: $ {float(view.loc[view['id'] == cid, 'saldo_usd'].iloc[0]):,.2f}"
        ),
        key="cxc_select_id",
    )

    row = view[view["id"] == cta_id].iloc[0]
    c1, c2, c3 = st.columns(3)
    monto_abono = c1.number_input(
        "Monto abono USD",
        min_value=0.0,
        value=float(row["saldo_usd"] or 0.0),
        format="%.2f",
        key="cxc_abono_monto",
    )
    metodo_pago = c2.selectbox("Método", [x for x in METODOS_PAGO_VENTA if x != "credito"], key="cxc_abono_metodo")
    observaciones = c3.text_input("Observación", value="Abono desde módulo de ventas", key="cxc_abono_obs")

    if st.button("💵 Registrar abono", use_container_width=True):
        try:
            with db_transaction() as conn:
                registrar_abono_cuenta_por_cobrar(
                    conn,
                    usuario=usuario,
                    payload=CobranzaInput(
                        cuenta_por_cobrar_id=int(cta_id),
                        monto_usd=float(monto_abono),
                        metodo_pago=str(metodo_pago),
                        observaciones=str(observaciones),
                    ),
                )
            st.success("Abono registrado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error("No se pudo registrar el abono.")
            st.exception(exc)


# ============================================================
# TAB RESUMEN
# ============================================================

def _render_tab_resumen() -> None:
    st.subheader("Resumen comercial")

    try:
        with db_transaction() as conn:
            df = pd.read_sql_query(
                """
                SELECT
                    id,
                    fecha,
                    metodo_pago,
                    total_usd,
                    subtotal_usd,
                    impuesto_usd,
                    cliente_id
                FROM ventas
                WHERE COALESCE(estado, 'registrada') = 'registrada'
                """,
                conn,
            )

            top_clientes = pd.read_sql_query(
                """
                SELECT
                    COALESCE(c.nombre, 'Sin cliente') AS cliente,
                    SUM(v.total_usd) AS total
                FROM ventas v
                LEFT JOIN clientes c ON c.id = v.cliente_id
                WHERE COALESCE(v.estado, 'registrada') = 'registrada'
                GROUP BY COALESCE(c.nombre, 'Sin cliente')
                ORDER BY total DESC
                """,
                conn,
            )

            top_productos = pd.read_sql_query(
                """
                SELECT
                    vd.descripcion AS producto,
                    SUM(vd.cantidad) AS unidades,
                    SUM(vd.subtotal_usd) AS ventas_usd,
                    SUM(vd.cantidad * vd.costo_unitario_usd) AS costo_usd
                FROM ventas_detalle vd
                JOIN ventas v ON v.id = vd.venta_id
                WHERE COALESCE(v.estado, 'registrada') = 'registrada'
                GROUP BY vd.descripcion
                ORDER BY ventas_usd DESC
                LIMIT 10
                """,
                conn,
            )
    except Exception as exc:
        st.error("Error cargando el resumen.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay ventas para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["total_usd"] = pd.to_numeric(df["total_usd"], errors="coerce").fillna(0.0)
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir").astype(str)

    total = float(df["total_usd"].sum())
    por_cobrar = float(df[df["metodo_pago"].str.lower() == "credito"]["total_usd"].sum())
    ticket_promedio = total / max(int(df["id"].nunique()), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas totales", f"$ {total:,.2f}")
    c2.metric("Por cobrar", f"$ {por_cobrar:,.2f}")
    c3.metric("Ticket promedio", f"$ {ticket_promedio:,.2f}")
    c4.metric("Mejor cliente", "N/A" if top_clientes.empty else str(top_clientes.iloc[0]["cliente"]))

    diaria = (
        df.assign(dia=df["fecha"].dt.date)
        .groupby("dia", as_index=False)["total_usd"]
        .sum()
        .sort_values("dia")
    )

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Evolución diaria")
        st.area_chart(diaria.set_index("dia")["total_usd"])
    with g2:
        if not top_clientes.empty:
            st.caption("Top clientes")
            st.bar_chart(top_clientes.head(8).set_index("cliente")["total"])

    if not top_productos.empty:
        top_productos["margen_usd"] = top_productos["ventas_usd"] - top_productos["costo_usd"].fillna(0.0)
        st.markdown("### Productos estrella")
        st.dataframe(
            top_productos,
            use_container_width=True,
            hide_index=True,
            column_config={
                "unidades": st.column_config.NumberColumn("Unidades", format="%.3f"),
                "ventas_usd": st.column_config.NumberColumn("Ventas USD", format="%.2f"),
                "costo_usd": st.column_config.NumberColumn("Costo USD", format="%.2f"),
                "margen_usd": st.column_config.NumberColumn("Margen USD", format="%.2f"),
            },
        )


# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

def render_ventas(usuario: str) -> None:
    st.subheader("💰 Centro de Ventas")
    st.caption("Ventas directas, crédito, cobranza, historial y resumen comercial en un solo módulo.")

    tabs = st.tabs(
        [
            "📝 Nueva venta",
            "📜 Historial",
            "💳 Cuentas por cobrar",
            "📊 Resumen",
        ]
    )

    with tabs[0]:
        _render_tab_registro(usuario)

    with tabs[1]:
        _render_tab_historial()

    with tabs[2]:
        _render_tab_cuentas_por_cobrar(usuario)

    with tabs[3]:
        _render_tab_resumen()
