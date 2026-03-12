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
        st.metric("Equivalente USD", f"$ {monto_usd:,.2f}")

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

    c1, c2, c3 = st.columns([1, 1, 2])
    desde = c1.date_input("Desde", date.today() - timedelta(days=30), key="gastos_desde")
    hasta = c2.date_input("Hasta", date.today(), key="gastos_hasta")
    buscar = c3.text_input("Buscar por descripción")

    filtro_fecha = (df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)
    df_fil = df[filtro_fecha].copy()

    if buscar:
        df_fil = df_fil[df_fil["descripcion"].str.contains(buscar, case=False, na=False)]

    st.dataframe(df_fil, use_container_width=True, hide_index=True)
    st.metric("Total del periodo", f"$ {float(df_fil['monto_usd'].sum()):,.2f}")

    st.subheader("Gestión de gastos")

    if not df_fil.empty:
        opciones = {f"#{int(r['id'])} · {r['descripcion']}": int(r["id"]) for _, r in df_fil.iterrows()}
        gasto_sel = st.selectbox("Seleccionar gasto", list(opciones.keys()))
        gasto_id = opciones[gasto_sel]

        row = df_fil[df_fil["id"] == gasto_id].iloc[0]

        with st.expander("✏️ Editar monto"):
            nuevo_monto = st.number_input(
                "Nuevo monto USD",
                min_value=0.01,
                value=float(row["monto_usd"]),
                format="%.2f",
            )
            if st.button("💾 Guardar cambios", key=f"edit_gasto_{gasto_id}"):
                try:
                    with db_transaction() as conn:
                        tasa = float(row["tasa_cambio"] or 1.0)
                        conn.execute(
                            "UPDATE gastos SET monto_usd=?, monto_bs=? WHERE id=?",
                            (float(nuevo_monto), convert_to_bs(float(nuevo_monto), tasa), int(gasto_id)),
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
    st.subheader("Resumen de egresos")

    try:
        df = _load_gastos()
    except Exception as e:
        st.error("Error cargando resumen")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay gastos para analizar.")
        return

    total = float(df["monto_usd"].sum())
    por_cat = df.groupby("categoria", as_index=False)["monto_usd"].sum().sort_values("monto_usd", ascending=False)

    c1, c2 = st.columns(2)
    c1.metric("Total gastado", f"$ {total:,.2f}")
    c2.metric("Categoría principal", str(por_cat.iloc[0]["categoria"]))

    st.subheader("Gastos por categoría")
    st.bar_chart(por_cat.set_index("categoria")["monto_usd"])


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
