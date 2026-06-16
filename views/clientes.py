from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.clientes_mejoras import render_mejoras_clientes
from views.clientes_inteligencia import render_clientes_inteligencia
from views.crm_avanzado import render_crm_avanzado
from views.erp_nuevos_modulos import render_fidelizacion


@contextmanager
def _clean_clientes_inner_titles():
    """Adapta títulos heredados del módulo operativo para que no parezca otro CRM."""
    original_subheader = st.subheader
    original_caption = st.caption

    def patched_subheader(body: Any, *args: Any, **kwargs: Any):
        replacements = {
            "👥 CRM Profesional de Clientes": "👤 Maestro de clientes / cartera",
            "➕ Registro y edición": "Registro y edición de clientes",
            "🔎 Búsqueda y filtros": "Búsqueda, filtros y cartera",
            "💳 Cuentas por cobrar y cobranza": "💳 Cobranza por cliente",
        }
        body_clean = str(body).strip()
        if body_clean in replacements:
            return original_subheader(replacements[body_clean], *args, **kwargs)
        return original_subheader(body, *args, **kwargs)

    def patched_caption(body: Any, *args: Any, **kwargs: Any):
        if str(body).strip() == "ERP • Finanzas • Inteligencia Comercial":
            return original_caption("Maestro operativo, crédito, contacto, cartera y cobranza por cliente.", *args, **kwargs)
        return original_caption(body, *args, **kwargs)

    st.subheader = patched_subheader
    st.caption = patched_caption
    try:
        yield
    finally:
        st.subheader = original_subheader
        st.caption = original_caption


def _safe_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _load_clientes_alertas() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    clientes = _safe_df(
        """
        SELECT id, nombre, COALESCE(telefono,'') AS telefono, COALESCE(email,'') AS email,
               COALESCE(categoria,'General') AS categoria,
               COALESCE(limite_credito_usd,0) AS limite_credito_usd,
               COALESCE(saldo_por_cobrar_usd,0) AS saldo_por_cobrar_usd,
               COALESCE(fecha,'') AS fecha
        FROM clientes
        WHERE COALESCE(estado,'activo')='activo'
        ORDER BY id DESC
        """
    )
    cxc = _safe_df(
        """
        SELECT cxc.id, cxc.cliente_id, COALESCE(c.nombre,'') AS cliente, cxc.venta_id,
               COALESCE(cxc.estado,'') AS estado, COALESCE(cxc.saldo_usd,0) AS saldo_usd,
               COALESCE(cxc.fecha_vencimiento,'') AS fecha_vencimiento,
               COALESCE(cxc.dias_mora,0) AS dias_mora
        FROM cuentas_por_cobrar cxc
        LEFT JOIN clientes c ON c.id = cxc.cliente_id
        WHERE COALESCE(cxc.estado,'') IN ('pendiente','parcial','vencida','incobrable')
        ORDER BY saldo_usd DESC
        """
    )
    crm = _safe_df(
        """
        SELECT id, nombre, telefono, email, origen, etapa, estado, valor_estimado_usd,
               fecha_proxima_accion, responsable, producto_interes
        FROM crm_oportunidades
        WHERE COALESCE(estado,'Abierta')='Abierta'
        ORDER BY fecha_proxima_accion ASC, id DESC
        """
    )
    return clientes, cxc, crm


def _render_alertas_clientes() -> None:
    st.subheader("🚨 Alertas comerciales")
    st.caption("Clientes duplicados, datos incompletos, riesgo de crédito, cobranza vencida y prospectos sin seguimiento.")

    clientes, cxc, crm = _load_clientes_alertas()
    if clientes.empty:
        st.info("No hay clientes activos para analizar.")
        return

    telefono_norm = clientes["telefono"].astype(str).str.replace(r"\D+", "", regex=True)
    duplicados_tel = clientes[telefono_norm.ne("") & telefono_norm.duplicated(keep=False)].copy()
    sin_whatsapp = clientes[telefono_norm.eq("")].copy()
    sin_categoria = clientes[clientes["categoria"].fillna("").astype(str).str.strip().isin(["", "General"])].copy()

    sobre_limite = pd.DataFrame()
    if not cxc.empty:
        deuda = cxc.groupby("cliente_id", as_index=False).agg(deuda_usd=("saldo_usd", "sum"), cuentas=("id", "count"))
        sobre_limite = clientes.merge(deuda, left_on="id", right_on="cliente_id", how="inner")
        sobre_limite = sobre_limite[sobre_limite["deuda_usd"] > sobre_limite["limite_credito_usd"]]
    vencidas = cxc[cxc["estado"].eq("vencida") | (pd.to_numeric(cxc.get("dias_mora", 0), errors="coerce").fillna(0) > 0)] if not cxc.empty else pd.DataFrame()

    crm_vencido = pd.DataFrame()
    if not crm.empty and "fecha_proxima_accion" in crm.columns:
        fechas = pd.to_datetime(crm["fecha_proxima_accion"], errors="coerce")
        crm_vencido = crm[fechas.notna() & (fechas.dt.date < pd.Timestamp.today().date())]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clientes activos", len(clientes))
    c2.metric("Duplicados teléfono", len(duplicados_tel))
    c3.metric("Cuentas vencidas", len(vencidas))
    c4.metric("CRM vencido", len(crm_vencido))

    alertas = []
    if not duplicados_tel.empty:
        alertas.append({"nivel": "Alta", "alerta": "Clientes con teléfono duplicado", "cantidad": len(duplicados_tel), "acción": "Unificar ficha o validar cuál es el cliente correcto."})
    if not sin_whatsapp.empty:
        alertas.append({"nivel": "Media", "alerta": "Clientes sin WhatsApp/teléfono", "cantidad": len(sin_whatsapp), "acción": "Completar contacto para ventas, entregas y cobranza."})
    if not sobre_limite.empty:
        alertas.append({"nivel": "Alta", "alerta": "Clientes sobre límite de crédito", "cantidad": len(sobre_limite), "acción": "Bloquear crédito o gestionar abono antes de vender."})
    if not vencidas.empty:
        alertas.append({"nivel": "Alta", "alerta": "Cuentas por cobrar vencidas", "cantidad": len(vencidas), "acción": "Priorizar cobranza y promesa de pago."})
    if not crm_vencido.empty:
        alertas.append({"nivel": "Media", "alerta": "Prospectos con seguimiento vencido", "cantidad": len(crm_vencido), "acción": "Actualizar próxima acción del CRM."})
    if not sin_categoria.empty:
        alertas.append({"nivel": "Baja", "alerta": "Clientes sin categoría específica", "cantidad": len(sin_categoria), "acción": "Clasificar General/VIP/Revendedor u otra categoría."})

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas comerciales críticas con la información disponible.")

    tabs = st.tabs([
        "Duplicados",
        "Sin contacto",
        "Crédito / cobranza",
        "CRM vencido",
        "Categorías",
    ])
    with tabs[0]:
        st.dataframe(duplicados_tel, use_container_width=True, hide_index=True) if not duplicados_tel.empty else st.success("Sin teléfonos duplicados.")
    with tabs[1]:
        st.dataframe(sin_whatsapp, use_container_width=True, hide_index=True) if not sin_whatsapp.empty else st.success("Todos tienen teléfono/WhatsApp registrado.")
    with tabs[2]:
        if not sobre_limite.empty:
            st.markdown("#### Sobre límite de crédito")
            st.dataframe(sobre_limite, use_container_width=True, hide_index=True)
        if not vencidas.empty:
            st.markdown("#### Cuentas vencidas")
            st.dataframe(vencidas, use_container_width=True, hide_index=True)
        if sobre_limite.empty and vencidas.empty:
            st.success("Sin alertas de crédito/cobranza.")
    with tabs[3]:
        st.dataframe(crm_vencido, use_container_width=True, hide_index=True) if not crm_vencido.empty else st.success("Sin seguimientos CRM vencidos.")
    with tabs[4]:
        st.dataframe(sin_categoria, use_container_width=True, hide_index=True) if not sin_categoria.empty else st.success("Todos los clientes tienen categoría específica.")


def _render_maestro_cartera(usuario: str) -> None:
    # Fallback temporal: evita importar modules.clientes mientras tenga IndentationError.
    render_mejoras_clientes(usuario)


def _render_fidelizacion_wrapper(usuario: str) -> None:
    st.subheader("⭐ Fidelización")
    st.caption("Plantilla rescatada: pendiente de convertir a programa operativo de puntos, referidos, cupones y beneficios VIP.")
    render_fidelizacion(usuario)


def render_clientes(usuario):
    st.title("👥 Clientes")
    st.caption("Clientes operativos, CRM, inteligencia comercial, datos comerciales y fidelización.")

    tab_maestro, tab_alertas, tab_crm, tab_inteligencia, tab_comercial, tab_fidelizacion = st.tabs([
        "👤 Maestro comercial",
        "🚨 Alertas comerciales",
        "🤝 CRM / Prospectos",
        "🧠 Inteligencia comercial",
        "🧩 Datos comerciales",
        "⭐ Fidelización / plantilla",
    ])

    with tab_maestro:
        _render_maestro_cartera(usuario)

    with tab_alertas:
        _render_alertas_clientes()

    with tab_crm:
        render_crm_avanzado(usuario)

    with tab_inteligencia:
        render_clientes_inteligencia(usuario)

    with tab_comercial:
        render_mejoras_clientes(usuario)

    with tab_fidelizacion:
        _render_fidelizacion_wrapper(usuario)
