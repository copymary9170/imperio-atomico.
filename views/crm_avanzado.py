from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

ETAPAS = ["Lead", "Contactado", "Calificado", "Cotizando", "Negociacion", "Ganado", "Perdido"]
ORIGENES = ["Mostrador", "WhatsApp", "Instagram", "Facebook", "Referido", "Web", "Correo", "Otro"]
ACCIONES = ["Llamar", "WhatsApp", "Enviar cotizacion", "Visitar", "Reunir", "Esperar respuesta", "Cerrar venta", "Otro"]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_oportunidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                nombre TEXT NOT NULL,
                telefono TEXT,
                email TEXT,
                empresa TEXT,
                origen TEXT NOT NULL DEFAULT 'Mostrador',
                etapa TEXT NOT NULL DEFAULT 'Lead',
                valor_estimado_usd REAL NOT NULL DEFAULT 0,
                probabilidad_pct REAL NOT NULL DEFAULT 10,
                producto_interes TEXT,
                proxima_accion TEXT,
                fecha_proxima_accion TEXT,
                responsable TEXT,
                cliente_id INTEGER,
                cotizacion_id INTEGER,
                venta_id INTEGER,
                estado TEXT NOT NULL DEFAULT 'Abierta',
                motivo_perdida TEXT,
                observaciones TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_seguimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                oportunidad_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL,
                tipo_accion TEXT NOT NULL,
                resultado TEXT,
                proxima_accion TEXT,
                fecha_proxima_accion TEXT,
                comentario TEXT,
                FOREIGN KEY (oportunidad_id) REFERENCES crm_oportunidades(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_etapa ON crm_oportunidades(etapa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crm_fecha_accion ON crm_oportunidades(fecha_proxima_accion)")


def _load_oportunidades() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM crm_oportunidades ORDER BY id DESC LIMIT 1000", conn)


def _load_seguimientos() -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM crm_seguimientos ORDER BY id DESC LIMIT 1000", conn)


def _create_oportunidad(data: dict[str, Any]) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO crm_oportunidades(
                usuario, nombre, telefono, email, empresa, origen, etapa, valor_estimado_usd,
                probabilidad_pct, producto_interes, proxima_accion, fecha_proxima_accion,
                responsable, observaciones
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["usuario"], data["nombre"], data.get("telefono"), data.get("email"), data.get("empresa"),
                data.get("origen", "Mostrador"), data.get("etapa", "Lead"), float(data.get("valor_estimado_usd", 0)),
                float(data.get("probabilidad_pct", 10)), data.get("producto_interes"), data.get("proxima_accion"),
                data.get("fecha_proxima_accion"), data.get("responsable"), data.get("observaciones"),
            ),
        )
        return int(cur.lastrowid)


def _add_seguimiento(data: dict[str, Any]) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO crm_seguimientos(
                oportunidad_id, usuario, tipo_accion, resultado, proxima_accion,
                fecha_proxima_accion, comentario
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(data["oportunidad_id"]), data["usuario"], data["tipo_accion"], data.get("resultado"),
                data.get("proxima_accion"), data.get("fecha_proxima_accion"), data.get("comentario"),
            ),
        )
        conn.execute(
            """
            UPDATE crm_oportunidades
            SET proxima_accion=?, fecha_proxima_accion=?
            WHERE id=?
            """,
            (data.get("proxima_accion"), data.get("fecha_proxima_accion"), int(data["oportunidad_id"])),
        )


def _update_stage(opp_id: int, etapa: str, estado: str, motivo: str | None = None) -> None:
    _ensure_tables()
    with db_transaction() as conn:
        conn.execute(
            "UPDATE crm_oportunidades SET etapa=?, estado=?, motivo_perdida=? WHERE id=?",
            (etapa, estado, motivo, int(opp_id)),
        )


def render_crm_avanzado(usuario: str = "Sistema") -> None:
    st.subheader("🤝 CRM / Prospectos")
    st.caption("Embudo comercial, oportunidades, próximos seguimientos, probabilidad de cierre y conversión.")
    _ensure_tables()

    oportunidades = _load_oportunidades()
    seguimientos = _load_seguimientos()
    abiertas = oportunidades[oportunidades["estado"].eq("Abierta")] if not oportunidades.empty else pd.DataFrame()
    ganadas = oportunidades[oportunidades["etapa"].eq("Ganado")] if not oportunidades.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Oportunidades", len(oportunidades))
    c2.metric("Abiertas", len(abiertas))
    c3.metric("Ganadas", len(ganadas))
    c4.metric("Pipeline", f"${float(pd.to_numeric(abiertas.get('valor_estimado_usd', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()) if not abiertas.empty else 0:,.2f}")

    tab_nueva, tab_embudo, tab_seguimiento, tab_historial = st.tabs([
        "Nueva oportunidad",
        "Embudo",
        "Seguimientos",
        "Historial",
    ])

    with tab_nueva:
        with st.form("form_crm_oportunidad"):
            a, b, c = st.columns(3)
            nombre = a.text_input("Nombre prospecto / cliente")
            telefono = b.text_input("Telefono")
            email = c.text_input("Email")
            d, e, f = st.columns(3)
            empresa = d.text_input("Empresa")
            origen = e.selectbox("Origen", ORIGENES)
            etapa = f.selectbox("Etapa inicial", ETAPAS)
            g, h, i = st.columns(3)
            valor = g.number_input("Valor estimado USD", min_value=0.0, value=0.0, step=1.0)
            prob = h.number_input("Probabilidad %", min_value=0.0, max_value=100.0, value=10.0, step=5.0)
            responsable = i.text_input("Responsable", value=usuario)
            producto = st.text_input("Producto / servicio de interes")
            j, k = st.columns(2)
            prox_accion = j.selectbox("Proxima accion", ACCIONES)
            fecha_accion = k.date_input("Fecha proxima accion", value=date.today())
            obs = st.text_area("Observaciones")
            guardar = st.form_submit_button("Crear oportunidad")
        if guardar:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            else:
                opp_id = _create_oportunidad({
                    "usuario": usuario,
                    "nombre": nombre.strip(),
                    "telefono": telefono.strip(),
                    "email": email.strip(),
                    "empresa": empresa.strip(),
                    "origen": origen,
                    "etapa": etapa,
                    "valor_estimado_usd": valor,
                    "probabilidad_pct": prob,
                    "producto_interes": producto.strip(),
                    "proxima_accion": prox_accion,
                    "fecha_proxima_accion": fecha_accion.isoformat(),
                    "responsable": responsable.strip(),
                    "observaciones": obs.strip(),
                })
                st.success(f"Oportunidad #{opp_id} creada.")
                st.rerun()

    with tab_embudo:
        if oportunidades.empty:
            st.info("No hay oportunidades registradas.")
        else:
            resumen = oportunidades.groupby("etapa", as_index=False).agg(
                oportunidades=("id", "count"),
                valor=("valor_estimado_usd", "sum"),
            )
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            st.bar_chart(resumen.set_index("etapa")["valor"])
            st.dataframe(oportunidades, use_container_width=True, hide_index=True)

            ids = oportunidades["id"].astype(int).tolist()
            opp_id = st.selectbox("Cambiar etapa", [0] + ids, format_func=lambda x: "Selecciona" if x == 0 else f"#{x} · {oportunidades.loc[oportunidades['id'].eq(x), 'nombre'].iloc[0]}")
            if opp_id:
                col1, col2, col3 = st.columns(3)
                nueva_etapa = col1.selectbox("Nueva etapa", ETAPAS, key="crm_nueva_etapa")
                nuevo_estado = col2.selectbox("Estado", ["Abierta", "Cerrada"], index=1 if nueva_etapa in ["Ganado", "Perdido"] else 0)
                motivo = col3.text_input("Motivo si perdido")
                if st.button("Actualizar etapa"):
                    _update_stage(int(opp_id), nueva_etapa, nuevo_estado, motivo.strip())
                    st.success("Etapa actualizada.")
                    st.rerun()

    with tab_seguimiento:
        if oportunidades.empty:
            st.info("No hay oportunidades para seguimiento.")
        else:
            abiertas_ids = abiertas["id"].astype(int).tolist() if not abiertas.empty else oportunidades["id"].astype(int).tolist()
            opp_id = st.selectbox("Oportunidad", abiertas_ids, format_func=lambda x: f"#{x} · {oportunidades.loc[oportunidades['id'].eq(x), 'nombre'].iloc[0]}")
            with st.form("form_seguimiento_crm"):
                a, b, c = st.columns(3)
                tipo = a.selectbox("Accion realizada", ACCIONES)
                resultado = b.text_input("Resultado")
                prox = c.selectbox("Proxima accion", ACCIONES, key="prox_seg")
                fecha_prox = st.date_input("Fecha proxima accion", value=date.today(), key="fecha_prox_seg")
                comentario = st.text_area("Comentario")
                guardar_seg = st.form_submit_button("Guardar seguimiento")
            if guardar_seg:
                _add_seguimiento({
                    "oportunidad_id": int(opp_id),
                    "usuario": usuario,
                    "tipo_accion": tipo,
                    "resultado": resultado.strip(),
                    "proxima_accion": prox,
                    "fecha_proxima_accion": fecha_prox.isoformat(),
                    "comentario": comentario.strip(),
                })
                st.success("Seguimiento guardado.")
                st.rerun()

            st.markdown("#### Próximas acciones")
            prox_df = abiertas.copy() if not abiertas.empty else oportunidades.copy()
            if not prox_df.empty and "fecha_proxima_accion" in prox_df.columns:
                prox_df["fecha_proxima_accion"] = pd.to_datetime(prox_df["fecha_proxima_accion"], errors="coerce")
                prox_df = prox_df.sort_values("fecha_proxima_accion")
            st.dataframe(prox_df, use_container_width=True, hide_index=True)

    with tab_historial:
        if seguimientos.empty:
            st.info("No hay seguimientos registrados.")
        else:
            st.dataframe(seguimientos, use_container_width=True, hide_index=True)
