from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, require_text
from utils.currency import convert_to_bs, convert_to_usd


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

    tasa_cambio = as_positive(
        tasa_cambio,
        "Tasa de cambio",
        allow_zero=False
    )

    monto = as_positive(
        monto,
        "Monto",
        allow_zero=False
    )

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


# ============================================================
# CANCELAR GASTO
# ============================================================

def cancelar_gasto(gasto_id: int, motivo: str) -> None:

    motivo = require_text(motivo, "Motivo")

    with db_transaction() as conn:

        conn.execute(
            """
            UPDATE gastos
            SET estado='cancelado',
                cancelado_motivo=?
            WHERE id=? AND estado='activo'
            """,
            (motivo, gasto_id),
        )


# ============================================================
# INTERFAZ DE GASTOS
# ============================================================

def render_gastos(usuario: str) -> None:

    st.subheader("💸 Gestión de Gastos")

    # ------------------------------------------------
    # FORMULARIO
    # ------------------------------------------------

    with st.form("nuevo_gasto"):

        st.write("Registrar nuevo gasto")

        c1, c2 = st.columns(2)

        descripcion = c1.text_input("Descripción")

        categoria = c1.selectbox(
            "Categoría",
            [
                "Operativo",
                "Nómina",
                "Servicios",
                "Materia Prima",
                "Marketing"
            ]
        )

        metodo = c2.selectbox(
            "Método de pago",
            [
                "efectivo",
                "transferencia",
                "pago móvil",
                "binance",
                "kontigo"
            ]
        )

        moneda = c2.selectbox(
            "Moneda",
            ["USD", "BS", "USDT", "KONTIGO"]
        )

        tasa = st.number_input(
            "Tasa BCV",
            min_value=0.0001,
            value=36.5
        )

        monto = st.number_input(
            "Monto",
            min_value=0.0
        )

        submit = st.form_submit_button("💾 Registrar gasto")

    if submit:

        try:

            gid = registrar_gasto(
                usuario,
                descripcion,
                categoria,
                metodo,
                moneda,
                tasa,
                monto
            )

            st.success(f"Gasto #{gid} registrado")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error registrando gasto")

            st.exception(e)

    st.divider()

    # ------------------------------------------------
    # RESUMEN
    # ------------------------------------------------

    try:

        with db_transaction() as conn:

            resumen = conn.execute(
                """
                SELECT
                    COALESCE(SUM(monto_usd),0) AS total,
                    COALESCE(
                        SUM(
                            CASE
                            WHEN date(fecha)=date('now')
                            THEN monto_usd
                            ELSE 0
                            END
                        ),
                    0) AS hoy,
                    COUNT(*) AS cantidad
                FROM gastos
                WHERE estado='activo'
                """
            ).fetchone()

            rows = conn.execute(
                """
                SELECT
                    id,
                    fecha,
                    descripcion,
                    categoria,
                    metodo_pago,
                    monto_usd,
                    estado
                FROM gastos
                ORDER BY id DESC
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando gastos")

        st.exception(e)

        return

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Gastos activos",
        int(resumen["cantidad"] or 0)
    )

    c2.metric(
        "Gasto de hoy",
        f"$ {float(resumen['hoy'] or 0):,.2f}"
    )

    c3.metric(
        "Gasto acumulado",
        f"$ {float(resumen['total'] or 0):,.2f}"
    )

    st.divider()

    # ------------------------------------------------
    # TABLA
    # ------------------------------------------------

    if not rows:

        st.info("No hay gastos registrados.")

        return

    df = pd.DataFrame(rows)

    buscar = st.text_input("🔎 Buscar gasto")

    if buscar:

        df = df[
            df["descripcion"]
            .str.contains(buscar, case=False, na=False)
        ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
