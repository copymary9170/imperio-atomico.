from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, require_text
from utils.currency import convert_to_bs, convert_to_usd


CATEGORIAS_GASTO = [
    "Materia Prima",
    "Mantenimiento de Equipos",
    "Servicios (Luz/Internet)",
    "Publicidad",
    "Sueldos/Retiros",
    "Logística",
    "Otros",
]

METODOS_GASTO = [
    "efectivo",
    "transferencia",
    "pago móvil",
    "zelle",
    "binance",
    "kontigo",
]


# ============================================================
# REGISTRAR GASTO
# ============================================================

def registrar_gasto(
    usuario: str,
    descripcion: str,
    categoria: str,
    metodo_pago: str,
    moneda: str,
    tasa_cambio: float,
    monto: float,
) -> int:
    descripcion = require_text(descripcion, "Descripción")
    categoria = require_text(categoria, "Categoría")
    metodo_pago = require_text(metodo_pago, "Método de pago")

    tasa_cambio = as_positive(tasa_cambio, "Tasa de cambio", allow_zero=False)
    monto = as_positive(monto, "Monto", allow_zero=False)

    monto_usd = convert_to_usd(monto, moneda, tasa_cambio)
    monto_bs = convert_to_bs(monto_usd, tasa_cambio)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO gastos (
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                monto_usd,
                monto_bs
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                monto_usd,
                monto_bs,
            ),
        )

        return int(cur.lastrowid)


def _render_tab_registro(usuario: str) -> None:
    with st.form("form_gastos_pro", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])

        descripcion = c1.text_input("Descripción del gasto")
        categoria = c2.selectbox("Categoría", CATEGORIAS_GASTO)

        c3, c4, c5, c6 = st.columns(4)
        monto = c3.number_input("Monto", min_value=0.01, format="%.2f")
        metodo = c4.selectbox("Método de pago", METODOS_GASTO)
        moneda = c5.selectbox("Moneda", ["USD", "BS", "USDT", "KONTIGO"])
        tasa = c6.number_input("Tasa", min_value=0.0001, value=36.5)

        monto_usd = convert_to_usd(float(monto), moneda, float(tasa))
        monto_bs = convert_to_bs(monto_usd, float(tasa))

        p1, p2 = st.columns(2)
        p1.metric("Equivalente USD", f"$ {monto_usd:,.2f}")
        p2.metric("Equivalente Bs", f"Bs {monto_bs:,.2f}")

        submit = st.form_submit_button("📉 Registrar egreso")

    if not submit:
        return

    try:
        gid = registrar_gasto(
            usuario=usuario,
            descripcion=descripcion,
            categoria=categoria,
            metodo_pago=metodo,
            moneda=moneda,
            tasa_cambio=float(tasa),
            monto=float(monto),
        )
        st.success(f"✅ Gasto #{gid} registrado")
        st.balloons()
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
    except Exception as e:
        st.error("Error registrando gasto")
        st.exception(e)


def _load_gastos() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                fecha,
                usuario,
                descripcion,
                categoria,
                metodo_pago,
                moneda,
                tasa_cambio,
                monto_usd,
                monto_bs,
                estado
            FROM gastos
            WHERE estado='activo'
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )


def _render_tab_historial() -> None:
    st.subheader("Historial de gastos")

    try:
        df = _load_gastos()
    except Exception as e:
        st.error("Error cargando historial")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay gastos registrados.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["metodo_pago"] = df["metodo_pago"].fillna("sin definir")

    c1, c2, c3, c4, c5 = st.columns([1, 1, 2, 1, 1])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="gastos_desde")
    hasta = c2.date_input("Hasta", date.today(), key="gastos_hasta")
    buscar = c3.text_input("Buscar por descripción")
    categoria_f = c4.selectbox("Categoría", ["Todas"] + sorted(df["categoria"].dropna().unique().tolist()))
    metodo_f = c5.selectbox("Método", ["Todos"] + sorted(df["metodo_pago"].str.title().unique().tolist()))

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if buscar:
        df_fil = df_fil[df_fil["descripcion"].str.contains(buscar, case=False, na=False)]
    if categoria_f != "Todas":
        df_fil = df_fil[df_fil["categoria"] == categoria_f]
    if metodo_f != "Todos":
        df_fil = df_fil[df_fil["metodo_pago"].str.lower() == metodo_f.lower()]

    k1, k2, k3 = st.columns(3)
    k1.metric("Total del periodo", f"$ {float(df_fil['monto_usd'].sum()):,.2f}")
    k2.metric("N° gastos", str(len(df_fil)))
    promedio = float(df_fil["monto_usd"].mean()) if not df_fil.empty else 0.0
    k3.metric("Promedio por gasto", f"$ {promedio:,.2f}")

    st.dataframe(df_fil, use_container_width=True, hide_index=True)

    if not df_fil.empty:
        g1, g2 = st.columns(2)
        with g1:
            por_cat = df_fil.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
            st.caption("Distribución por categoría")
            st.bar_chart(por_cat.set_index("categoria")["monto_usd"])
        with g2:
            diaria = (
                df_fil.assign(dia=df_fil["fecha"].dt.date)
                .groupby("dia", as_index=False)["monto_usd"]
                .sum()
                .sort_values("dia")
            )
            st.caption("Tendencia de egresos")
            st.line_chart(diaria.set_index("dia")["monto_usd"])

    st.subheader("Gestión de gastos")

    if not df_fil.empty:
        opciones = {f"#{int(r['id'])} · {r['descripcion']}": int(r["id"]) for _, r in df_fil.iterrows()}
        gasto_sel = st.selectbox("Seleccionar gasto", list(opciones.keys()))
        gasto_id = opciones[gasto_sel]

        row = df_fil[df_fil["id"] == gasto_id].iloc[0]

        with st.expander("✏️ Editar gasto"):
            e1, e2 = st.columns([2, 1])
            nueva_desc = e1.text_input("Descripción", value=str(row["descripcion"]), key=f"desc_gasto_{gasto_id}")
            nueva_cat = e2.selectbox(
                "Categoría",
                CATEGORIAS_GASTO,
                index=CATEGORIAS_GASTO.index(row["categoria"]) if row["categoria"] in CATEGORIAS_GASTO else 0,
                key=f"cat_gasto_{gasto_id}",
            )

            e3, e4, e5, e6 = st.columns(4)
            nuevo_metodo = e3.selectbox(
                "Método de pago",
                METODOS_GASTO,
                index=METODOS_GASTO.index(row["metodo_pago"]) if row["metodo_pago"] in METODOS_GASTO else 0,
                key=f"metodo_gasto_{gasto_id}",
            )
            nueva_moneda = e4.selectbox(
                "Moneda",
                ["USD", "BS", "USDT", "KONTIGO"],
                index=["USD", "BS", "USDT", "KONTIGO"].index(row["moneda"]) if row["moneda"] in ["USD", "BS", "USDT", "KONTIGO"] else 0,
                key=f"moneda_gasto_{gasto_id}",
            )
            monto_referencia = float(row["monto_bs"]) if row["moneda"] == "BS" else float(row["monto_usd"])
            nuevo_monto = e5.number_input(
                "Monto",
                min_value=0.01,
                value=monto_referencia,
                format="%.2f",
                key=f"monto_gasto_{gasto_id}",
            )
            nueva_tasa = e6.number_input(
                "Tasa",
                min_value=0.0001,
                value=float(row["tasa_cambio"] or 1.0),
                format="%.4f",
                key=f"tasa_gasto_{gasto_id}",
            )

            monto_edit_usd = convert_to_usd(float(nuevo_monto), nueva_moneda, float(nueva_tasa))
            monto_edit_bs = convert_to_bs(monto_edit_usd, float(nueva_tasa))
            p1, p2 = st.columns(2)
            p1.metric("Equivalente USD", f"$ {monto_edit_usd:,.2f}")
            p2.metric("Equivalente Bs", f"Bs {monto_edit_bs:,.2f}")

            if st.button("💾 Guardar cambios", key=f"edit_gasto_{gasto_id}"):
                try:
                    with db_transaction() as conn:
                        conn.execute(
                            """
                            UPDATE gastos
                            SET descripcion=?, categoria=?, metodo_pago=?, moneda=?, tasa_cambio=?, monto_usd=?, monto_bs=?
                            WHERE id=?
                            """,
                            (
                                require_text(nueva_desc, "Descripción"),
                                nueva_cat,
                                require_text(nuevo_metodo, "Método de pago"),
                                nueva_moneda,
                                as_positive(float(nueva_tasa), "Tasa de cambio", allow_zero=False),
                                monto_edit_usd,
                                monto_edit_bs,
                                int(gasto_id),
                            ),
                        )
                    st.success("Actualizado")
                    st.rerun()
                except Exception as e:
                    st.error("Error actualizando")
                    st.exception(e)

        with st.expander("🗑️ Eliminar gasto"):
            confirmar = st.checkbox("Confirmo eliminación", key=f"confirm_gasto_{gasto_id}")
            if st.button("Eliminar", key=f"del_gasto_{gasto_id}"):
                if not confirmar:
                    st.warning("Debes confirmar para eliminar")
                else:
                    try:
                        with db_transaction() as conn:
                            conn.execute(
                                "UPDATE gastos SET estado='cancelado', cancelado_motivo='Eliminado desde interfaz' WHERE id=?",
                                (int(gasto_id),),
                            )
                        st.success("Gasto eliminado")
                        st.rerun()
                    except Exception as e:
                        st.error("Error eliminando")
                        st.exception(e)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_fil.to_excel(writer, index=False, sheet_name="Gastos")

    st.download_button(
        "📥 Exportar Excel",
        buffer.getvalue(),
        file_name="historial_gastos.xlsx",
    )


def _render_tab_resumen() -> None:
    st.subheader("Resumen financiero de egresos")

    try:
        df = _load_gastos()
    except Exception as e:
        st.error("Error cargando resumen")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay gastos para analizar.")
        return

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    total = float(df["monto_usd"].sum())
    por_cat = df.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)
    por_metodo = df.groupby("metodo_pago", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)

    periodo_30 = df[df["fecha"].dt.date >= (date.today() - timedelta(days=30))]
    periodo_prev = df[
        (df["fecha"].dt.date < (date.today() - timedelta(days=30)))
        & (df["fecha"].dt.date >= (date.today() - timedelta(days=60)))
    ]
    actual_30 = float(periodo_30["monto_usd"].sum())
    anterior_30 = float(periodo_prev["monto_usd"].sum())
    delta = actual_30 - anterior_30

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total gastado", f"$ {total:,.2f}")
    c2.metric("Categoría principal", str(por_cat.iloc[0]["categoria"]))
    c3.metric("Últimos 30 días", f"$ {actual_30:,.2f}", delta=f"{delta:,.2f}")
    c4.metric("Ticket promedio", f"$ {float(df['monto_usd'].mean()):,.2f}")

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Gastos por categoría")
        st.bar_chart(por_cat.set_index("categoria")["monto_usd"])
    with g2:
        st.caption("Gastos por método")
        st.bar_chart(por_metodo.set_index("metodo_pago")["monto_usd"])

    st.subheader("Control de presupuesto")
    presupuesto = st.number_input("Presupuesto mensual objetivo (USD)", min_value=0.0, value=max(actual_30, 1.0), step=50.0)
    uso = (actual_30 / presupuesto * 100) if presupuesto > 0 else 0.0
    st.progress(min(int(uso), 100))
    if uso >= 100:
        st.error(f"🚨 Presupuesto excedido: {uso:,.1f}%")
    elif uso >= 80:
        st.warning(f"⚠️ Presupuesto en zona de riesgo: {uso:,.1f}%")
    else:
        st.success(f"✅ Uso saludable del presupuesto: {uso:,.1f}%")


# ============================================================
# INTERFAZ DE GASTOS
# ============================================================

def render_gastos(usuario: str) -> None:
    st.subheader("📉 Control integral de gastos")

    rol = st.session_state.get("rol", "Admin")
    if rol not in ["Admin", "Administration", "Administracion"]:
        st.error("🚫 Solo administración puede gestionar gastos.")
        return

    tab1, tab2, tab3 = st.tabs([
        "📝 Registrar gasto",
        "📜 Historial",
        "📊 Resumen",
    ])

    with tab1:
        _render_tab_registro(usuario)

    with tab2:
        _render_tab_historial()

    with tab3:
        _render_tab_resumen()
