from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text


def create_cliente(
    usuario: str,
    nombre: str,
    telefono: str,
    email: str,
    direccion: str,
    limite_credito_usd: float,
    categoria: str = "General",
) -> int:
    nombre = require_text(nombre, "Nombre")
    telefono = "".join(filter(str.isdigit, clean_text(telefono)))
    email = clean_text(email)
    direccion = clean_text(direccion)
    limite_credito_usd = as_positive(limite_credito_usd, "Límite de crédito")

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO clientes (
                usuario,
                nombre,
                telefono,
                email,
                direccion,
                limite_credito_usd,
                categoria
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                nombre,
                telefono,
                email,
                direccion,
                limite_credito_usd,
                categoria,
            ),
        )

        return int(cur.lastrowid)


def _ensure_clientes_schema() -> None:
    with db_transaction() as conn:
        cols = conn.execute("PRAGMA table_info(clientes)").fetchall()
        col_names = {row["name"] for row in cols}

        if "categoria" not in col_names:
            conn.execute("ALTER TABLE clientes ADD COLUMN categoria TEXT DEFAULT 'General'")


def _cargar_clientes() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                c.id,
                c.fecha,
                c.nombre,
                COALESCE(c.telefono, '') AS whatsapp,
                COALESCE(c.email, '') AS email,
                COALESCE(c.direccion, '') AS direccion,
                COALESCE(c.categoria, 'General') AS categoria,
                c.limite_credito_usd,
                c.saldo_por_cobrar_usd,
                COALESCE(COUNT(v.id), 0) AS operaciones,
                COALESCE(SUM(v.total_usd), 0) AS total,
                COALESCE(MAX(v.fecha), c.fecha) AS ultima_compra,
                COALESCE(pxc.deuda_total, 0) AS deuda
            FROM clientes c
            LEFT JOIN ventas v
                ON v.cliente_id = c.id
                AND v.estado = 'registrada'
            LEFT JOIN (
                SELECT cliente_id, SUM(saldo_usd) AS deuda_total
                FROM cuentas_por_cobrar
                WHERE estado = 'pendiente'
                GROUP BY cliente_id
            ) pxc
                ON pxc.cliente_id = c.id
            WHERE c.estado = 'activo'
            GROUP BY c.id
            ORDER BY total DESC
            """
        , conn)


def render_clientes(usuario: str) -> None:
    _ensure_clientes_schema()

    st.subheader("👥 CRM Profesional de Clientes")
    st.caption("ERP • Finanzas • Inteligencia Comercial")

    try:
        df = _cargar_clientes()
    except Exception as e:
        st.error("Error cargando clientes")
        st.exception(e)
        return

    st.divider()
    st.subheader("➕ Registro y edición")

    modo = st.radio("Modo", ["Registrar", "Editar"], horizontal=True)

    if modo == "Registrar":
        with st.form("form_registro_cliente"):
            c1, c2, c3 = st.columns(3)
            nombre = c1.text_input("Nombre")
            whatsapp = c2.text_input("WhatsApp")
            categoria = c3.selectbox("Categoría", ["General", "VIP", "Revendedor"])

            c4, c5 = st.columns(2)
            email = c4.text_input("Email")
            limite_credito = c5.number_input("Límite de crédito ($)", min_value=0.0, step=1.0)
            direccion = st.text_area("Dirección")

            guardar = st.form_submit_button("Guardar")

        if guardar:
            try:
                nombre = str(nombre).strip()
                if not nombre:
                    st.error("Nombre obligatorio")
                    return

                with db_transaction() as conn:
                    existe = conn.execute(
                        "SELECT COUNT(*) AS n FROM clientes WHERE nombre=? AND estado='activo'",
                        (nombre,),
                    ).fetchone()["n"]

                if existe:
                    st.error("Cliente ya existe")
                    return

                cid = create_cliente(
                    usuario=usuario,
                    nombre=nombre,
                    telefono=whatsapp,
                    email=email,
                    direccion=direccion,
                    limite_credito_usd=limite_credito,
                    categoria=categoria,
                )

                st.success(f"Cliente #{cid} registrado")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as e:
                st.error("Error registrando cliente")
                st.exception(e)

    else:
        if df.empty:
            st.info("No hay clientes para editar")
            return

        ids = df[["id", "nombre"]]
        cliente_id = st.selectbox(
            "Seleccionar cliente",
            ids["id"],
            format_func=lambda x: ids.loc[ids["id"] == x, "nombre"].values[0],
            key="cliente_edicion_id",
        )

        row = df[df["id"] == cliente_id].iloc[0]

        with st.form("form_editar_cliente"):
            c1, c2, c3 = st.columns(3)
            nombre_n = c1.text_input("Nombre", str(row["nombre"]))
            whatsapp_n = c2.text_input("WhatsApp", str(row["whatsapp"] or ""))
            categoria_n = c3.selectbox(
                "Categoría",
                ["General", "VIP", "Revendedor"],
                index=["General", "VIP", "Revendedor"].index(row["categoria"])
                if row["categoria"] in ["General", "VIP", "Revendedor"]
                else 0,
            )

            c4, c5 = st.columns(2)
            email_n = c4.text_input("Email", str(row.get("email", "") or ""))
            limite_credito_n = c5.number_input(
                "Límite de crédito ($)",
                min_value=0.0,
                step=1.0,
                value=float(row.get("limite_credito_usd", 0) or 0),
            )
            direccion_n = st.text_area("Dirección", str(row.get("direccion", "") or ""))

            actualizar = st.form_submit_button("Actualizar")

        if actualizar:
            try:
                nombre_n = require_text(nombre_n, "Nombre")
                whatsapp_n = "".join(filter(str.isdigit, str(whatsapp_n or "")))

                with db_transaction() as conn:
                    existe_otro = conn.execute(
                        """
                        SELECT COUNT(*) AS n
                        FROM clientes
                        WHERE nombre=?
                          AND id<>?
                          AND estado='activo'
                        """,
                        (nombre_n, int(cliente_id)),
                    ).fetchone()["n"]

                    if existe_otro:
                        st.error("Ya existe otro cliente con ese nombre")
                        return

                    conn.execute(
                        """
                        UPDATE clientes
                        SET nombre=?, telefono=?, categoria=?, email=?, direccion=?, limite_credito_usd=?
                        WHERE id=?
                        """,
                        (
                            nombre_n,
                            whatsapp_n,
                            categoria_n,
                            clean_text(email_n),
                            clean_text(direccion_n),
                            as_positive(limite_credito_n, "Límite de crédito"),
                            int(cliente_id),
                        ),
                    )

                st.success("Cliente actualizado")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as e:
                st.error("Error actualizando cliente")
                st.exception(e)

    if df.empty:
        st.warning("Sin clientes")
        return

    st.divider()
    st.subheader("🔎 Búsqueda y filtros")
    colf1, colf2 = st.columns([2, 1])
    buscador = colf1.text_input("Buscar por nombre o WhatsApp", placeholder="Ej: Juan / 58412...")
    categorias = ["Todas"] + sorted([str(x) for x in df["categoria"].dropna().unique().tolist()])
    filtro_categoria = colf2.selectbox("Categoría", categorias)

    if str(buscador or "").strip():
        q = str(buscador).strip()
        mask_nombre = df["nombre"].astype(str).str.contains(q, case=False, na=False)
        mask_whatsapp = df["whatsapp"].astype(str).str.contains(q, case=False, na=False)
        df = df[mask_nombre | mask_whatsapp]

    if filtro_categoria != "Todas":
        df = df[df["categoria"].astype(str).eq(str(filtro_categoria))]

    if df.empty:
        st.info("No hay clientes para los filtros seleccionados")
        return

    df["ultima_compra"] = pd.to_datetime(df["ultima_compra"], errors="coerce")
    df["recencia"] = (datetime.now() - df["ultima_compra"]).dt.days
    df["score"] = df["total"] * 0.5 + df["operaciones"] * 10 + (100 - df["recencia"].fillna(100))
    df["credito_disponible"] = (df["limite_credito_usd"] - df["deuda"]).clip(lower=0)
    df["uso_credito_pct"] = (
        (df["deuda"] / df["limite_credito_usd"].replace({0: pd.NA})) * 100
    ).fillna(0)

    df["segmento"] = "Riesgo"
    df.loc[df["score"] > 200, "segmento"] = "Ocasional"
    df.loc[df["score"] > 500, "segmento"] = "Frecuente"
    df.loc[df["score"] > 1000, "segmento"] = "VIP"

    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Clientes", len(df))
    m2.metric("Ventas", f"$ {float(df['total'].sum()):,.2f}")
    m3.metric("Deuda", f"$ {float(df['deuda'].sum()):,.2f}")
    operaciones = float(df["operaciones"].sum() or 0)
    ticket_prom = float(df["total"].sum()) / operaciones if operaciones > 0 else 0.0
    m4.metric("Ticket", f"$ {ticket_prom:,.2f}")
    m5.metric("Crédito disponible", f"$ {float(df['credito_disponible'].sum()):,.2f}")

    clientes_sobre_limite = df[df["deuda"] > df["limite_credito_usd"]]
    if not clientes_sobre_limite.empty:
        nombres = ", ".join(clientes_sobre_limite["nombre"].astype(str).head(5).tolist())
        sufijo = "..." if len(clientes_sobre_limite) > 5 else ""
        st.warning(
            f"{len(clientes_sobre_limite)} cliente(s) superan su límite de crédito: {nombres}{sufijo}"
        )

    seg = df.groupby("segmento", as_index=False).agg(clientes=("id", "count"))
    fig = px.bar(seg, x="segmento", y="clientes", color="segmento", title="Segmentación de clientes")
    st.plotly_chart(fig, use_container_width=True)

    if st.button("📥 Exportar Excel", key="exportar_clientes_excel"):
        columnas_export = [
            "id",
            "nombre",
            "whatsapp",
            "email",
            "direccion",
            "categoria",
            "limite_credito_usd",
            "operaciones",
            "total",
            "deuda",
            "credito_disponible",
            "uso_credito_pct",
            "ultima_compra",
            "segmento",
            "score",
        ]
        export_df = df[[c for c in columnas_export if c in df.columns]].copy()

        buffer = io.BytesIO()
        export_df.to_excel(buffer, index=False)

        st.download_button(
            "Descargar Excel",
            buffer.getvalue(),
            "clientes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_clientes_excel",
        )

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("Contacto")
    ids = df[["id", "nombre"]]
    cliente_contacto = st.selectbox(
        "Seleccionar cliente",
        ids["id"],
        format_func=lambda x: ids.loc[ids["id"] == x, "nombre"].values[0],
        key="contacto_cliente_id",
    )

    contacto_row = df[df["id"] == cliente_contacto].iloc[0]
    wa = "".join(filter(str.isdigit, str(contacto_row["whatsapp"] or "")))
    if wa:
        if not wa.startswith("58"):
            wa = "58" + wa
        st.link_button("💬 WhatsApp", f"https://wa.me/{wa}")
    else:
        st.caption("Este cliente no tiene teléfono registrado.")

    if st.button("🗑 Eliminar Cliente", key="eliminar_cliente"):
        with db_transaction() as conn:
            conn.execute(
                "UPDATE clientes SET estado='inactivo' WHERE id=?",
                (int(cliente_contacto),),
            )
        st.success("Cliente eliminado")
        st.rerun()




