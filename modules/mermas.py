from __future__ import annotations

import io
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text


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
# UI - REGISTRO
# ============================================================

def _render_tab_registro(usuario: str) -> None:
    st.subheader("Registrar merma o desperdicio")

    df_inv = _load_inventory_df()
    usar_inventario = st.checkbox("Vincular a inventario", value=True, key="merma_usar_inventario")

    inventario_id: int | None = None
    producto = ""
    sku = ""
    categoria = ""
    unidad = "unidad"
    costo_unitario_usd = 0.0
    stock_actual = 0.0

    if usar_inventario and not df_inv.empty:
        inventario_id = st.selectbox(
            "Producto de inventario",
            df_inv["id"].tolist(),
            format_func=lambda i: (
                f"{df_inv.loc[df_inv['id'] == i, 'nombre'].iloc[0]} "
                f"({df_inv.loc[df_inv['id'] == i, 'sku'].iloc[0]})"
            ),
            key="merma_inventario_id",
        )

        row = df_inv[df_inv["id"] == inventario_id].iloc[0]
        producto = str(row["nombre"])
        sku = str(row["sku"])
        categoria = str(row["categoria"])
        unidad = str(row["unidad"] or "unidad")
        costo_unitario_usd = float(row["costo_unitario_usd"] or 0.0)
        stock_actual = float(row["stock_actual"] or 0.0)

        cinfo1, cinfo2, cinfo3 = st.columns(3)
        cinfo1.metric("Stock actual", f"{stock_actual:,.3f}")
        cinfo2.metric("Costo unitario", f"$ {costo_unitario_usd:,.4f}")
        cinfo3.metric("Unidad", unidad)

    elif usar_inventario and df_inv.empty:
        st.warning("No hay productos activos en inventario. Puedes registrar una merma manual.")
        usar_inventario = False

    if not usar_inventario:
        m1, m2, m3, m4 = st.columns(4)
        producto = m1.text_input("Producto", key="merma_producto_manual")
        sku = m2.text_input("SKU", key="merma_sku_manual")
        categoria = m3.text_input("Categoría", key="merma_categoria_manual")
        unidad = m4.selectbox("Unidad", UNIDADES_BASE, key="merma_unidad_manual")
        costo_unitario_usd = st.number_input(
            "Costo unitario USD",
            min_value=0.0,
            value=0.0,
            format="%.4f",
            key="merma_costo_manual",
        )

    c1, c2, c3, c4 = st.columns(4)
    cantidad = c1.number_input("Cantidad perdida", min_value=0.001, value=1.0, format="%.3f", key="merma_cantidad")
    tipo_merma = c2.selectbox("Tipo de merma", TIPOS_MERMA, key="merma_tipo")
    causa = c3.selectbox("Causa", CAUSAS_MERMA, key="merma_causa")
    area = c4.selectbox("Área", AREAS_MERMA, key="merma_area")

    c5, c6, c7, c8 = st.columns(4)
    proceso = c5.text_input("Proceso", key="merma_proceso")
    orden_produccion = c6.text_input("Orden de producción", key="merma_op")
    maquina = c7.text_input("Máquina / equipo", key="merma_maquina")
    operador = c8.text_input("Operador", key="merma_operador")

    c9, c10, c11 = st.columns(3)
    lote = c9.text_input("Lote", key="merma_lote")
    cliente = c10.text_input("Cliente / trabajo", key="merma_cliente")
    evidencia_url = c11.text_input("Evidencia / URL", key="merma_evidencia")

    observacion = st.text_area("Observación", key="merma_observacion")

    st.markdown("### Recuperación")
    r1, r2, r3, r4 = st.columns(4)
    recuperable = r1.checkbox("¿Se recupera algo?", key="merma_recuperable")
    cantidad_recuperada = r2.number_input(
        "Cantidad recuperada",
        min_value=0.0,
        value=0.0,
        format="%.3f",
        key="merma_cantidad_recuperada",
        disabled=not recuperable,
    )
    valor_recuperado_usd = r3.number_input(
        "Valor recuperado USD",
        min_value=0.0,
        value=0.0,
        format="%.4f",
        key="merma_valor_recuperado",
        disabled=not recuperable,
    )
    destino_recuperacion = r4.selectbox(
        "Destino recuperación",
        DESTINOS_RECUPERACION,
        key="merma_destino_recuperacion",
        disabled=not recuperable,
    )

    costo_total = round(float(cantidad) * float(costo_unitario_usd), 4)
    costo_neto = max(costo_total - float(valor_recuperado_usd), 0.0)

    p1, p2, p3 = st.columns(3)
    p1.metric("Costo bruto merma", f"$ {costo_total:,.2f}")
    p2.metric("Valor recuperado", f"$ {float(valor_recuperado_usd):,.2f}")
    p3.metric("Costo neto impacto", f"$ {costo_neto:,.2f}")

    if st.button("♻️ Registrar merma", use_container_width=True):
        try:
            if usar_inventario and inventario_id is not None and float(cantidad) > float(stock_actual):
                raise ValueError("La cantidad perdida supera el stock actual.")

            merma_id = registrar_merma(
                usuario=usuario,
                inventario_id=int(inventario_id) if usar_inventario and inventario_id is not None else None,
                producto=producto,
                sku=sku,
                categoria=categoria,
                unidad=unidad,
                cantidad=float(cantidad),
                costo_unitario_usd=float(costo_unitario_usd),
                tipo_merma=tipo_merma,
                causa=causa,
                area=area,
                proceso=proceso,
                orden_produccion=orden_produccion,
                maquina=maquina,
                operador=operador,
                lote=lote,
                cliente=cliente,
                observacion=observacion,
                recuperable=bool(recuperable),
                cantidad_recuperada=float(cantidad_recuperada),
                valor_recuperado_usd=float(valor_recuperado_usd),
                destino_recuperacion=destino_recuperacion if recuperable else "No recuperable",
                evidencia_url=evidencia_url,
            )
            st.success(f"Merma #{merma_id} registrada correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo registrar la merma: {exc}")


# ============================================================
# UI - HISTORIAL
# ============================================================

def _render_tab_historial() -> None:
    st.subheader("Historial de mermas y desperdicio")

    try:
        df = _load_mermas_df()
    except Exception as exc:
        st.error("Error cargando historial de mermas.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay registros de merma todavía.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    f1, f2, f3, f4, f5 = st.columns([1, 1, 2, 1, 1])
    desde = f1.date_input("Desde", date.today() - timedelta(days=30), key="mermas_desde")
    hasta = f2.date_input("Hasta", date.today(), key="mermas_hasta")
    buscar = f3.text_input("Buscar", key="mermas_buscar")
    tipo = f4.selectbox("Tipo", ["Todos"] + TIPOS_MERMA, key="mermas_tipo_filtro")
    area = f5.selectbox("Área", ["Todas"] + AREAS_MERMA, key="mermas_area_filtro")

    causa = st.selectbox("Causa", ["Todas"] + CAUSAS_MERMA, key="mermas_causa_filtro")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    view = df[filtro_fecha].copy()
    view = _filter_mermas(view, buscar, tipo, causa, area)

    view["costo_neto_usd"] = view["costo_total_usd"].fillna(0.0) - view["valor_recuperado_usd"].fillna(0.0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Registros", len(view))
    k2.metric("Costo bruto", f"$ {_sum_method(view, 'costo_total_usd'):,.2f}")
    k3.metric("Valor recuperado", f"$ {_sum_method(view, 'valor_recuperado_usd'):,.2f}")
    k4.metric("Costo neto", f"$ {_sum_method(view, 'costo_neto_usd'):,.2f}")

    st.dataframe(
        view[
            [
                "fecha",
                "usuario",
                "producto",
                "sku",
                "cantidad",
                "unidad",
                "tipo_merma",
                "causa",
                "area",
                "proceso",
                "orden_produccion",
                "operador",
                "costo_unitario_usd",
                "costo_total_usd",
                "valor_recuperado_usd",
                "costo_neto_usd",
                "observacion",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_unitario_usd": st.column_config.NumberColumn("Costo unitario", format="%.4f"),
            "costo_total_usd": st.column_config.NumberColumn("Costo bruto", format="%.2f"),
            "valor_recuperado_usd": st.column_config.NumberColumn("Recuperado", format="%.2f"),
            "costo_neto_usd": st.column_config.NumberColumn("Costo neto", format="%.2f"),
        },
    )

    if not view.empty:
        opciones = {f"#{int(r['id'])} · {r['producto']}": int(r["id"]) for _, r in view.iterrows()}
        seleccion = st.selectbox("Registro a eliminar", list(opciones.keys()), key="mermas_sel_delete")
        merma_id = opciones[seleccion]

        if st.button("🗑️ Eliminar registro de merma", key="mermas_delete_btn"):
            try:
                with db_transaction() as conn:
                    conn.execute(
                        "UPDATE mermas_desperdicio SET estado='cancelado' WHERE id=?",
                        (int(merma_id),),
                    )
                st.success("Registro eliminado.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo eliminar el registro.")
                st.exception(exc)

    buffer = io.BytesIO()
    export_df = view.copy()
    export_df["fecha"] = export_df["fecha"].astype(str)
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Mermas")

    st.download_button(
        "📥 Exportar historial",
        data=buffer.getvalue(),
        file_name="historial_mermas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ============================================================
# UI - RESUMEN
# ============================================================

def _render_tab_resumen() -> None:
    st.subheader("Resumen de mermas")

    try:
        df = _load_mermas_df()
    except Exception as exc:
        st.error("Error cargando resumen de mermas.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay mermas registradas para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["costo_total_usd"] = pd.to_numeric(df["costo_total_usd"], errors="coerce").fillna(0.0)
    df["valor_recuperado_usd"] = pd.to_numeric(df["valor_recuperado_usd"], errors="coerce").fillna(0.0)
    df["costo_neto_usd"] = df["costo_total_usd"] - df["valor_recuperado_usd"]

    ultimos_30 = df[df["fecha"].dt.date >= (date.today() - timedelta(days=30))].copy()

    total_registros = len(df)
    costo_total = float(df["costo_total_usd"].sum())
    recuperado = float(df["valor_recuperado_usd"].sum())
    costo_neto = float(df["costo_neto_usd"].sum())

    tipo_top = "N/A"
    causa_top = "N/A"
    if not df.empty:
        top_tipos = df.groupby("tipo_merma", as_index=False)["costo_neto_usd"].sum().sort_values("costo_neto_usd", ascending=False)
        top_causas = df.groupby("causa", as_index=False)["costo_neto_usd"].sum().sort_values("costo_neto_usd", ascending=False)
        if not top_tipos.empty:
            tipo_top = str(top_tipos.iloc[0]["tipo_merma"])
        if not top_causas.empty:
            causa_top = str(top_causas.iloc[0]["causa"])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Registros", total_registros)
    k2.metric("Costo bruto", f"$ {costo_total:,.2f}")
    k3.metric("Recuperado", f"$ {recuperado:,.2f}")
    k4.metric("Costo neto", f"$ {costo_neto:,.2f}")
    k5.metric("Últimos 30 días", f"$ {float(ultimos_30['costo_neto_usd'].sum()):,.2f}")

    st.caption(f"Tipo con mayor impacto: {tipo_top} · Causa principal: {causa_top}")

    g1, g2 = st.columns(2)

    with g1:
        por_tipo = (
            df.groupby("tipo_merma", as_index=False)["costo_neto_usd"]
            .sum()
            .sort_values("costo_neto_usd", ascending=False)
        )
        st.markdown("#### Impacto por tipo")
        if not por_tipo.empty:
            st.bar_chart(por_tipo.set_index("tipo_merma")["costo_neto_usd"])

    with g2:
        por_causa = (
            df.groupby("causa", as_index=False)["costo_neto_usd"]
            .sum()
            .sort_values("costo_neto_usd", ascending=False)
        )
        st.markdown("#### Impacto por causa")
        if not por_causa.empty:
            st.bar_chart(por_causa.set_index("causa")["costo_neto_usd"])

    g3, g4 = st.columns(2)

    with g3:
        por_area = (
            df.groupby("area", as_index=False)["costo_neto_usd"]
            .sum()
            .sort_values("costo_neto_usd", ascending=False)
        )
        st.markdown("#### Impacto por área")
        if not por_area.empty:
            st.bar_chart(por_area.set_index("area")["costo_neto_usd"])

    with g4:
        por_producto = (
            df.groupby("producto", as_index=False)["costo_neto_usd"]
            .sum()
            .sort_values("costo_neto_usd", ascending=False)
            .head(10)
        )
        st.markdown("#### Top productos con más merma")
        if not por_producto.empty:
            st.bar_chart(por_producto.set_index("producto")["costo_neto_usd"])

    tendencia = (
        df.assign(dia=df["fecha"].dt.date)
        .groupby("dia", as_index=False)["costo_neto_usd"]
        .sum()
        .sort_values("dia")
    )
    st.markdown("#### Tendencia")
    if not tendencia.empty:
        st.line_chart(tendencia.set_index("dia")["costo_neto_usd"])

    st.markdown("#### Tabla resumen")
    resumen = (
        df.groupby(["tipo_merma", "causa", "area"], as_index=False)
        .agg(
            registros=("id", "count"),
            cantidad_total=("cantidad", "sum"),
            costo_bruto=("costo_total_usd", "sum"),
            recuperado=("valor_recuperado_usd", "sum"),
            costo_neto=("costo_neto_usd", "sum"),
        )
        .sort_values("costo_neto", ascending=False)
    )
    st.dataframe(
        resumen,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cantidad_total": st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "costo_bruto": st.column_config.NumberColumn("Costo bruto", format="%.2f"),
            "recuperado": st.column_config.NumberColumn("Recuperado", format="%.2f"),
            "costo_neto": st.column_config.NumberColumn("Costo neto", format="%.2f"),
        },
    )


# ============================================================
# UI
# ============================================================

def render_mermas(usuario: str) -> None:
    _ensure_mermas_tables()

    st.subheader("♻️ Mermas y desperdicio")
    st.caption(
        "Controla pérdidas de material, calcula su impacto económico, "
        "descuenta inventario y analiza causas para mejorar producción."
    )

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
