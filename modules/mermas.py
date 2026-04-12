rom __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text
from modules.integration_hub import render_module_inbox


TIPOS_MERMA = [
    "Desperdicio normal",
    "Desperdicio anormal",
    "Prueba / calibración",
    "Error humano",
    "Corte incorrecto",
    "Impresión fallida",
    "Daño por almacenamiento",
    "Rotura",
    "Vencimiento",
    "Sobrante no reutilizable",
    "Otro",
]

CAUSAS_MERMA = [
    "Error operativo",
    "Falla de máquina",
    "Falla de material",
    "Mala manipulación",
    "Calibración",
    "Transporte",
    "Almacenamiento",
    "Humedad / calor",
    "Vencimiento",
    "Prueba interna",
    "Otro",
]

AREAS_MERMA = [
    "Producción",
    "Corte",
    "Sublimación",
    "Impresión",
    "Acabado",
    "Almacén",
    "Despacho",
    "Administración",
    "Otro",
]

DESTINOS_RECUPERACION = [
    "No recuperable",
    "Reutilizable",
    "Reciclable",
    "Chatarra",
    "Devuelto a inventario",
]

UNIDADES_BASE = [
    "unidad",
    "und",
    "cm",
    "cm2",
    "ml",
    "gr",
    "kg",
    "m",
    "m2",
    "litro",
    "pliego",
    "paquete",
    "caja",
]


# ============================================================
# SCHEMA
# ============================================================

def _ensure_mermas_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mermas_desperdicio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                inventario_id INTEGER,
                producto TEXT NOT NULL,
                sku TEXT,
                categoria TEXT,
                unidad TEXT DEFAULT 'unidad',
                cantidad REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                tipo_merma TEXT NOT NULL,
                causa TEXT NOT NULL,
                area TEXT,
                proceso TEXT,
                orden_produccion TEXT,
                maquina TEXT,
                operador TEXT,
                lote TEXT,
                cliente TEXT,
                observacion TEXT,
                recuperable INTEGER NOT NULL DEFAULT 0,
                cantidad_recuperada REAL NOT NULL DEFAULT 0,
                valor_recuperado_usd REAL NOT NULL DEFAULT 0,
                destino_recuperacion TEXT,
                evidencia_url TEXT,
                estado TEXT NOT NULL DEFAULT 'activo'
            )
            """
        )

        cols = {r[1] for r in conn.execute("PRAGMA table_info(mermas_desperdicio)").fetchall()}

        extras = {
            "proceso": "TEXT",
            "orden_produccion": "TEXT",
            "maquina": "TEXT",
            "operador": "TEXT",
            "lote": "TEXT",
            "cliente": "TEXT",
            "evidencia_url": "TEXT",
            "destino_recuperacion": "TEXT",
            "cantidad_recuperada": "REAL NOT NULL DEFAULT 0",
            "valor_recuperado_usd": "REAL NOT NULL DEFAULT 0",
            "recuperable": "INTEGER NOT NULL DEFAULT 0",
            "estado": "TEXT NOT NULL DEFAULT 'activo'",
            "sku": "TEXT",
            "categoria": "TEXT",
            "unidad": "TEXT DEFAULT 'unidad'",
        }

        for col, sql_type in extras.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE mermas_desperdicio ADD COLUMN {col} {sql_type}")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_fecha ON mermas_desperdicio(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_tipo ON mermas_desperdicio(tipo_merma)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_causa ON mermas_desperdicio(causa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_area ON mermas_desperdicio(area)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_inventario ON mermas_desperdicio(inventario_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mermas_estado ON mermas_desperdicio(estado)")


# ============================================================
# HELPERS
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _sum_method(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _load_inventory_df() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                nombre,
                sku,
                categoria,
                unidad,
                stock_actual,
                costo_unitario_usd,
                precio_venta_usd
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY nombre ASC
            """
        ).fetchall()

    return pd.DataFrame(
        rows,
        columns=[
            "id",
            "nombre",
            "sku",
            "categoria",
            "unidad",
            "stock_actual",
            "costo_unitario_usd",
            "precio_venta_usd",
        ],
    )


def _load_mermas_df() -> pd.DataFrame:
    _ensure_mermas_tables()
    with db_transaction() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                inventario_id,
                producto,
                sku,
                categoria,
                unidad,
                cantidad,
                costo_unitario_usd,
                costo_total_usd,
                tipo_merma,
                causa,
                area,
                proceso,
                orden_produccion,
                maquina,
                operador,
                lote,
                cliente,
                observacion,
                recuperable,
                cantidad_recuperada,
                valor_recuperado_usd,
                destino_recuperacion,
                evidencia_url,
                estado
            FROM mermas_desperdicio
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )
    return df


def _filter_mermas(
    df: pd.DataFrame,
    buscar: str,
    tipo: str,
    causa: str,
    area: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    view = df.copy()

    if buscar:
        txt = clean_text(buscar)
        mask = (
            view["producto"].astype(str).str.contains(txt, case=False, na=False)
            | view["sku"].astype(str).str.contains(txt, case=False, na=False)
            | view["observacion"].astype(str).str.contains(txt, case=False, na=False)
            | view["orden_produccion"].astype(str).str.contains(txt, case=False, na=False)
            | view["operador"].astype(str).str.contains(txt, case=False, na=False)
            | view["maquina"].astype(str).str.contains(txt, case=False, na=False)
            | view["cliente"].astype(str).str.contains(txt, case=False, na=False)
        )
        view = view[mask]

    if tipo != "Todos":
        view = view[view["tipo_merma"].astype(str) == tipo]

    if causa != "Todas":
        view = view[view["causa"].astype(str) == causa]

    if area != "Todas":
        view = view[view["area"].astype(str) == area]

    return view


def _registrar_salida_inventario_por_merma(
    conn,
    usuario: str,
    inventario_id: int,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str,
) -> None:
    row = conn.execute(
        """
        SELECT stock_actual
        FROM inventario
        WHERE id=? AND COALESCE(estado,'activo')='activo'
        """,
        (int(inventario_id),),
    ).fetchone()

    if not row:
        raise ValueError("El producto de inventario no existe.")

    stock_actual = float(row["stock_actual"] or 0.0)
    if stock_actual < float(cantidad):
        raise ValueError("Stock insuficiente para registrar la merma.")

    conn.execute(
        """
        INSERT INTO movimientos_inventario(
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
            require_text(usuario, "Usuario"),
            int(inventario_id),
            -abs(float(cantidad)),
            max(0.0, float(costo_unitario_usd)),
            clean_text(referencia),
        ),
    )

    conn.execute(
        """
        UPDATE inventario
        SET stock_actual = stock_actual - ?
        WHERE id = ?
        """,
        (float(cantidad), int(inventario_id)),
    )


# ============================================================
# CORE
# ============================================================

def registrar_merma(
    usuario: str,
    inventario_id: int | None,
    producto: str,
    sku: str,
    categoria: str,
    unidad: str,
    cantidad: float,
    costo_unitario_usd: float,
    tipo_merma: str,
    causa: str,
    area: str,
    proceso: str = "",
    orden_produccion: str = "",
    maquina: str = "",
    operador: str = "",
    lote: str = "",
    cliente: str = "",
    observacion: str = "",
    recuperable: bool = False,
    cantidad_recuperada: float = 0.0,
    valor_recuperado_usd: float = 0.0,
    destino_recuperacion: str = "No recuperable",
    evidencia_url: str = "",
) -> int:
    producto = require_text(producto, "Producto")
    tipo_merma = require_text(tipo_merma, "Tipo de merma")
    causa = require_text(causa, "Causa")
    cantidad = as_positive(cantidad, "Cantidad", allow_zero=False)
    costo_unitario_usd = as_positive(costo_unitario_usd, "Costo unitario", allow_zero=True)
    cantidad_recuperada = as_positive(cantidad_recuperada, "Cantidad recuperada", allow_zero=True)
    valor_recuperado_usd = as_positive(valor_recuperado_usd, "Valor recuperado", allow_zero=True)

    if cantidad_recuperada > cantidad:
        raise ValueError("La cantidad recuperada no puede ser mayor a la cantidad perdida.")

    costo_total_usd = round(float(cantidad) * float(costo_unitario_usd), 4)

    referencia = (
        f"Merma registrada · {tipo_merma}"
        f"{' · ' + clean_text(orden_produccion) if clean_text(orden_produccion) else ''}"
        f"{' · ' + clean_text(proceso) if clean_text(proceso) else ''}"
    )

    with db_transaction() as conn:
        if inventario_id is not None:
            _registrar_salida_inventario_por_merma(
                conn=conn,
                usuario=usuario,
                inventario_id=int(inventario_id),
                cantidad=float(cantidad),
                costo_unitario_usd=float(costo_unitario_usd),
                referencia=referencia,
            )

        cur = conn.execute(
            """
            INSERT INTO mermas_desperdicio (
                usuario,
                inventario_id,
                producto,
                sku,
                categoria,
                unidad,
                cantidad,
                costo_unitario_usd,
                costo_total_usd,
                tipo_merma,
                causa,
                area,
                proceso,
                orden_produccion,
                maquina,
                operador,
                lote,
                cliente,
                observacion,
                recuperable,
                cantidad_recuperada,
                valor_recuperado_usd,
                destino_recuperacion,
                evidencia_url,
                estado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activo')
            """,
            (
                usuario,
                int(inventario_id) if inventario_id is not None else None,
                clean_text(producto),
                clean_text(sku),
                clean_text(categoria),
                clean_text(unidad) or "unidad",
                float(cantidad),
                float(costo_unitario_usd),
                float(costo_total_usd),
                clean_text(tipo_merma),
                clean_text(causa),
                clean_text(area),
                clean_text(proceso),
                clean_text(orden_produccion),
                clean_text(maquina),
                clean_text(operador),
                clean_text(lote),
                clean_text(cliente),
                clean_text(observacion),
                1 if bool(recuperable) else 0,
                float(cantidad_recuperada),
                float(valor_recuperado_usd),
                clean_text(destino_recuperacion),
                clean_text(evidencia_url),
            ),
        )
        return int(cur.lastrowid)


# ============================================================
# UI
# ============================================================

def _render_tab_registro(usuario: str) -> None:
    st.subheader("Registrar nueva merma")

    inv_df = _load_inventory_df()
    opciones = ["Manual (sin inventario)"]
    index_to_inv_id: dict[int, int | None] = {0: None}

    if not inv_df.empty:
        for idx, row in inv_df.reset_index(drop=True).iterrows():
            opt = f"{row['nombre']} · SKU {row['sku'] or 'N/A'} · Stock {float(row['stock_actual'] or 0):,.2f}"
            opciones.append(opt)
            index_to_inv_id[idx + 1] = int(row["id"])

    selected = st.selectbox("Producto", opciones, key="merma_producto_select")
    selected_idx = opciones.index(selected)
    inventario_id = index_to_inv_id.get(selected_idx)

    producto_base = st.session_state.get("merma_producto_manual", "")
    sku_base = ""
    categoria_base = ""
    unidad_base = "unidad"
    costo_base = 0.0

    if inventario_id is not None and not inv_df.empty:
        row = inv_df[inv_df["id"] == inventario_id].iloc[0]
        producto_base = str(row["nombre"] or "")
        sku_base = str(row["sku"] or "")
        categoria_base = str(row["categoria"] or "")
        unidad_base = str(row["unidad"] or "unidad")
        costo_base = _safe_float(row["costo_unitario_usd"], 0.0)

    c1, c2, c3, c4 = st.columns(4)
    producto = c1.text_input("Producto", value=producto_base, key="merma_producto")
    sku = c2.text_input("SKU", value=sku_base, key="merma_sku")
    categoria = c3.text_input("Categoría", value=categoria_base, key="merma_categoria")
    unidad = c4.selectbox(
        "Unidad",
        UNIDADES_BASE,
        index=UNIDADES_BASE.index(unidad_base) if unidad_base in UNIDADES_BASE else 0,
        key="merma_unidad",
    )

    d1, d2, d3, d4 = st.columns(4)
    cantidad = d1.number_input("Cantidad", min_value=0.0001, format="%.4f", key="merma_cantidad")
    costo_unitario = d2.number_input(
        "Costo unitario (USD)",
        min_value=0.0,
        value=float(costo_base),
        format="%.4f",
        key="merma_costo_unitario",
    )
    tipo_merma = d3.selectbox("Tipo de merma", TIPOS_MERMA, key="merma_tipo")
    causa = d4.selectbox("Causa", CAUSAS_MERMA, key="merma_causa")

    e1, e2, e3 = st.columns(3)
    area = e1.selectbox("Área", AREAS_MERMA, key="merma_area")
    proceso = e2.text_input("Proceso", value=st.session_state.get("merma_proceso", ""), key="merma_proceso")
    orden = e3.text_input("Orden de producción", value=st.session_state.get("merma_op", ""), key="merma_op")

    f1, f2, f3, f4 = st.columns(4)
    maquina = f1.text_input("Máquina", key="merma_maquina")
    operador = f2.text_input("Operador", key="merma_operador")
    lote = f3.text_input("Lote", key="merma_lote")
    cliente = f4.text_input("Cliente", key="merma_cliente")

    observacion = st.text_area(
        "Observación",
        value=st.session_state.get("merma_observacion", ""),
        key="merma_observacion",
    )
    evidencia_url = st.text_input("URL evidencia (opcional)", key="merma_evidencia")

    r1, r2, r3, r4 = st.columns(4)
    recuperable = r1.checkbox("Recuperable", key="merma_recuperable")
    cantidad_recuperada = r2.number_input("Cant. recuperada", min_value=0.0, format="%.4f", key="merma_recuperada")
    valor_recuperado = r3.number_input("Valor recuperado (USD)", min_value=0.0, format="%.4f", key="merma_valor_rec")
    destino_rec = r4.selectbox("Destino recuperación", DESTINOS_RECUPERACION, key="merma_destino")

    costo_total = float(cantidad) * float(costo_unitario)
    st.caption(f"Impacto económico estimado: **$ {costo_total:,.2f} USD**")

    if st.button("♻️ Registrar merma", use_container_width=True, key="merma_submit"):
        try:
            merma_id = registrar_merma(
                usuario=usuario,
                inventario_id=inventario_id,
                producto=producto,
                sku=sku,
                categoria=categoria,
                unidad=unidad,
                cantidad=float(cantidad),
                costo_unitario_usd=float(costo_unitario),
                tipo_merma=tipo_merma,
                causa=causa,
                area=area,
                proceso=proceso,
                orden_produccion=orden,
                maquina=maquina,
                operador=operador,
                lote=lote,
                cliente=cliente,
                observacion=observacion,
                recuperable=bool(recuperable),
                cantidad_recuperada=float(cantidad_recuperada),
                valor_recuperado_usd=float(valor_recuperado),
                destino_recuperacion=destino_rec,
                evidencia_url=evidencia_url,
            )
            st.success(f"✅ Merma #{merma_id} registrada correctamente")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("Error registrando merma")
            st.exception(exc)


def _render_tab_historial() -> None:
    st.subheader("Historial de mermas")
    df = _load_mermas_df()

    if df.empty:
        st.info("No hay mermas registradas.")
        return

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    buscar = c1.text_input("Buscar")
    tipo = c2.selectbox("Tipo", ["Todos"] + TIPOS_MERMA)
    causa = c3.selectbox("Causa", ["Todas"] + CAUSAS_MERMA)
    area = c4.selectbox("Área", ["Todas"] + AREAS_MERMA)

    view = _filter_mermas(df, buscar, tipo, causa, area)
    st.dataframe(view, use_container_width=True, hide_index=True)

    if not view.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            view.to_excel(writer, index=False, sheet_name="Mermas")
        st.download_button(
            "📥 Exportar Excel",
            buffer.getvalue(),
            file_name="historial_mermas.xlsx",
            use_container_width=True,
        )


def _render_tab_resumen() -> None:
    st.subheader("Resumen de mermas")
    df = _load_mermas_df()

    if df.empty:
        st.info("No hay datos para resumir.")
        return

    total_cantidad = _sum_method(df, "cantidad")
    total_costo = _sum_method(df, "costo_total_usd")
    total_recuperado = _sum_method(df, "valor_recuperado_usd")
    impacto_neto = total_costo - total_recuperado

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cantidad total", f"{total_cantidad:,.2f}")
    k2.metric("Costo total", f"$ {total_costo:,.2f}")
    k3.metric("Valor recuperado", f"$ {total_recuperado:,.2f}")
    k4.metric("Impacto neto", f"$ {impacto_neto:,.2f}")

    by_tipo = df.groupby("tipo_merma", as_index=False)["costo_total_usd"].sum().sort_values("costo_total_usd", ascending=False)
    by_causa = df.groupby("causa", as_index=False)["costo_total_usd"].sum().sort_values("costo_total_usd", ascending=False)
    by_area = df.groupby("area", as_index=False)["costo_total_usd"].sum().sort_values("costo_total_usd", ascending=False)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Impacto por tipo de merma")
        st.bar_chart(by_tipo.set_index("tipo_merma")["costo_total_usd"])
    with c2:
        st.caption("Impacto por causa")
        st.bar_chart(by_causa.set_index("causa")["costo_total_usd"])
    with c3:
        st.caption("Impacto por área")
        st.bar_chart(by_area.set_index("area")["costo_total_usd"])


def render_mermas(usuario: str) -> None:
    _ensure_mermas_tables()

    st.subheader("♻️ Mermas y desperdicio")
    st.caption(
        "Controla pérdidas de material, calcula su impacto económico, "
        "descuenta inventario y analiza causas para mejorar producción."
    )

    def _apply_inbox(inbox: dict) -> None:
        data = dict(inbox.get("payload_data", {}))
        if data.get("orden_id"):
            st.session_state["merma_op"] = str(data.get("orden_id"))
        if data.get("proceso"):
            st.session_state["merma_proceso"] = str(data.get("proceso"))
        if data.get("material"):
            st.session_state["merma_producto_manual"] = str(data.get("material"))
        if data.get("observaciones"):
            st.session_state["merma_observacion"] = str(data.get("observaciones"))
        if data.get("merma") is not None:
            try:
                st.session_state["merma_cantidad"] = float(data.get("merma"))
            except (TypeError, ValueError):
                pass

    render_module_inbox("mermas", apply_callback=_apply_inbox, clear_after_apply=False)

    tabs = st.tabs(
        [
            "📝 Registrar merma",
            "📜 Historial",
            "📊 Resumen",
        ]
    )

    with tabs[0]:
        _render_tab_registro(usuario)

    with tabs[1]:
        _render_tab_historial()

    with tabs[2]:
        _render_tab_resumen()





