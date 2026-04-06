rom __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text
from services.cxc_cobranza_service import (
    CobranzaInput,
    marcar_cuenta_incobrable,
    obtener_reporte_cartera,
    registrar_abono_cuenta_por_cobrar,
    registrar_gestion_cobranza,
)


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
                WHERE estado IN ('pendiente','parcial','vencida','incobrable')
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

    st.divider()
    st.subheader("💳 Cuentas por cobrar y cobranza")

    try:
        with db_transaction() as conn:
            reporte = obtener_reporte_cartera(conn)
    except Exception as exc:
        st.error("No se pudo cargar la cartera.")
        st.exception(exc)
        return

    cartera = reporte["cartera"]
    if cartera.empty:
        st.info("No hay cartera activa para gestionar.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cartera total", f"$ {float(cartera['saldo_usd'].sum()):,.2f}")
    c2.metric("Vencida", f"$ {float(cartera[cartera['estado'] == 'vencida']['saldo_usd'].sum()):,.2f}")
    c3.metric("Incobrable", f"$ {float(cartera[cartera['estado'] == 'incobrable']['saldo_usd'].sum()):,.2f}")
    c4.metric("Cuentas", int(cartera["id"].nunique()))

    st.caption("Top deudores")
    st.dataframe(reporte["top_deudores"], use_container_width=True, hide_index=True)

    g1, g2 = st.columns(2)
    with g1:
        st.caption("Antigüedad de saldos")
        if not reporte["antiguedad"].empty:
            st.bar_chart(reporte["antiguedad"].set_index("rango")["saldo_usd"])
        else:
            st.info("Sin datos de antigüedad.")
    with g2:
        st.caption("Vencimientos")
        cols = ["id", "cliente", "venta_id", "estado", "saldo_usd", "fecha_vencimiento", "dias_mora"]
        st.dataframe(reporte["vencimientos"][cols], use_container_width=True, hide_index=True)

    st.caption("Detalle por cliente / cuenta")
    st.dataframe(cartera, use_container_width=True, hide_index=True)

    export_csv = cartera.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Exportar cartera CSV",
        export_csv,
        "cartera_clientes.csv",
        "text/csv",
        key="download_cartera_csv",
    )

    cuentas_options = cartera["id"].astype(int).tolist()
    cuenta_sel = st.selectbox("Cuenta por cobrar", cuentas_options, key="cxc_selector")
    cuenta_row = cartera[cartera["id"] == cuenta_sel].iloc[0]
    st.caption(
        f"Cliente: {cuenta_row['cliente']} · Venta: #{int(cuenta_row['venta_id'] or 0)} · "
        f"Saldo: $ {float(cuenta_row['saldo_usd']):,.2f} · Estado: {cuenta_row['estado']}"
    )

    f1, f2 = st.columns(2)
    with f1:
        with st.form("form_abono_cxc"):
            monto_abono = st.number_input("Abono USD", min_value=0.01, step=1.0)
            metodo_abono = st.selectbox("Método", ["efectivo", "transferencia", "zelle", "binance", "kontigo"])
            referencia_abono = st.text_input("Referencia")
            obs_abono = st.text_area("Observaciones de abono")
            promesa_abono = st.text_input("Promesa de pago (YYYY-MM-DD)")
            proxima_abono = st.text_input("Próxima gestión (YYYY-MM-DD)")
            send_abono = st.form_submit_button("Registrar abono")
        if send_abono:
            try:
                with db_transaction() as conn:
                    result = registrar_abono_cuenta_por_cobrar(
                        conn,
                        usuario=usuario,
                        payload=CobranzaInput(
                            cuenta_por_cobrar_id=int(cuenta_sel),
                            monto_usd=float(monto_abono),
                            metodo_pago=str(metodo_abono),
                            referencia=str(referencia_abono),
                            observaciones=str(obs_abono),
                            promesa_pago_fecha=str(promesa_abono).strip() or None,
                            proxima_gestion_fecha=str(proxima_abono).strip() or None,
                        ),
                    )
                st.success(
                    f"Abono registrado. Pago #{result['pago_id']} · Nuevo saldo: $ {result['nuevo_saldo_usd']:,.2f} "
                    f"· Estado: {result['nuevo_estado']}"
                )
                st.rerun()
            except Exception as exc:
                st.error("No se pudo registrar el abono.")
                st.exception(exc)

    with f2:
        with st.form("form_gestion_cobranza"):
            obs_gestion = st.text_area("Observaciones de cobranza")
            promesa = st.text_input("Promesa de pago (YYYY-MM-DD)", key="gestion_promesa")
            proxima = st.text_input("Próxima gestión (YYYY-MM-DD)", key="gestion_proxima")
            save_gestion = st.form_submit_button("Guardar gestión")
        if save_gestion:
            try:
                with db_transaction() as conn:
                    gid = registrar_gestion_cobranza(
                        conn,
                        usuario=usuario,
                        cuenta_por_cobrar_id=int(cuenta_sel),
                        observaciones=str(obs_gestion),
                        promesa_pago_fecha=str(promesa).strip() or None,
                        proxima_gestion_fecha=str(proxima).strip() or None,
                    )
                st.success(f"Gestión registrada #{gid}")
            except Exception as exc:
                st.error("No se pudo guardar la gestión.")
                st.exception(exc)

        motivo_incobrable = st.text_input("Motivo incobrable", key="motivo_incobrable")
        if st.button("⚠️ Marcar incobrable", key="btn_incobrable"):
            try:
                with db_transaction() as conn:
                    marcar_cuenta_incobrable(
                        conn,
                        cuenta_por_cobrar_id=int(cuenta_sel),
                        usuario=usuario,
                        motivo=str(motivo_incobrable),
                    )
                st.success("Cuenta marcada como incobrable.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo marcar como incobrable.")
                st.exception(exc)

    st.caption("Últimos abonos registrados")
    st.dataframe(reporte["historial_abonos"], use_container_width=True, hide_index=True)


