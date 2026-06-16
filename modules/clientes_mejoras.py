from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.common import clean_text, require_text


CATEGORIAS_CLIENTE = [
    "General",
    "VIP",
    "Revendedor",
    "Estudiante",
    "Representante",
    "Docente",
    "Negocio",
    "Emprendedor",
    "Mayorista",
    "Cliente de impresión",
    "Cliente de papelería",
    "Cliente de sublimación",
]

ORIGENES_CLIENTE = [
    "No definido",
    "WhatsApp",
    "Instagram",
    "Facebook",
    "Referido",
    "Presencial",
    "Vecino",
    "Catálogo",
    "Estado de WhatsApp",
    "Cliente antiguo",
    "Otro",
]

SERVICIOS_INTERES = [
    "No definido",
    "Impresiones",
    "Copias",
    "Papelería",
    "Papelería creativa",
    "Sublimación",
    "Fotos carnet",
    "Títulos / fondo negro",
    "Diseño gráfico",
    "Encuadernado",
    "Servicios digitales",
    "Otro",
]

COMPORTAMIENTOS_PAGO = [
    "No definido",
    "Buen pagador",
    "Paga tarde",
    "Deudor frecuente",
    "Solo contado",
    "Crédito aprobado",
    "Crédito suspendido",
]

PREFERENCIAS_CONTACTO = [
    "WhatsApp",
    "Llamada",
    "Instagram",
    "Facebook",
    "Presencial",
    "No contactar",
]


def _table_exists(conn: Any, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_clientes_mejoras_schema() -> None:
    """Amplía la tabla clientes sin romper bases SQLite existentes."""
    with db_transaction() as conn:
        if not _table_exists(conn, "clientes"):
            return
        cols = _columns(conn, "clientes")
        nuevos_campos = {
            "origen": "TEXT DEFAULT 'No definido'",
            "tipo_cliente": "TEXT DEFAULT 'General'",
            "servicio_interes": "TEXT DEFAULT 'No definido'",
            "comportamiento_pago": "TEXT DEFAULT 'No definido'",
            "preferencia_contacto": "TEXT DEFAULT 'WhatsApp'",
            "acepta_promociones": "INTEGER DEFAULT 1",
            "cumpleanos": "TEXT DEFAULT ''",
            "fecha_especial": "TEXT DEFAULT ''",
            "observaciones_comerciales": "TEXT DEFAULT ''",
            "descuento_pct": "REAL DEFAULT 0",
            "lista_precio": "TEXT DEFAULT 'Normal'",
        }
        for campo, definicion in nuevos_campos.items():
            if campo not in cols:
                conn.execute(f"ALTER TABLE clientes ADD COLUMN {campo} {definicion}")


def _normalizar_telefono(value: str) -> str:
    return "".join(filter(str.isdigit, clean_text(value)))


def validar_cliente_duplicado(nombre: str, telefono: str, cliente_id: int | None = None) -> list[str]:
    """Devuelve advertencias/bloqueos por duplicados de nombre o teléfono."""
    ensure_clientes_mejoras_schema()
    nombre_clean = require_text(nombre, "Nombre")
    telefono_clean = _normalizar_telefono(telefono)
    filtros_extra = "AND id<>?" if cliente_id else ""
    params_extra: tuple[Any, ...] = (int(cliente_id),) if cliente_id else ()
    alertas: list[str] = []

    with db_transaction() as conn:
        if telefono_clean:
            row_tel = conn.execute(
                f"""
                SELECT id, nombre, telefono
                FROM clientes
                WHERE estado='activo'
                  AND REPLACE(REPLACE(REPLACE(COALESCE(telefono,''), ' ', ''), '-', ''), '+', '')=?
                  {filtros_extra}
                LIMIT 1
                """,
                (telefono_clean, *params_extra),
            ).fetchone()
            if row_tel:
                alertas.append(f"Teléfono ya registrado en cliente #{row_tel['id']} - {row_tel['nombre']}.")

        row_nombre = conn.execute(
            f"""
            SELECT id, nombre
            FROM clientes
            WHERE estado='activo'
              AND lower(trim(nombre))=lower(trim(?))
              {filtros_extra}
            LIMIT 1
            """,
            (nombre_clean, *params_extra),
        ).fetchone()
        if row_nombre:
            alertas.append(f"Nombre ya registrado en cliente #{row_nombre['id']} - {row_nombre['nombre']}.")

    return alertas


def cargar_clientes_mejorados() -> pd.DataFrame:
    ensure_clientes_mejoras_schema()
    with db_transaction() as conn:
        if not _table_exists(conn, "clientes"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT
                c.id,
                c.fecha,
                c.nombre,
                COALESCE(c.telefono,'') AS whatsapp,
                COALESCE(c.email,'') AS email,
                COALESCE(c.direccion,'') AS direccion,
                COALESCE(c.categoria,'General') AS categoria,
                COALESCE(c.tipo_cliente,'General') AS tipo_cliente,
                COALESCE(c.origen,'No definido') AS origen,
                COALESCE(c.servicio_interes,'No definido') AS servicio_interes,
                COALESCE(c.comportamiento_pago,'No definido') AS comportamiento_pago,
                COALESCE(c.preferencia_contacto,'WhatsApp') AS preferencia_contacto,
                COALESCE(c.acepta_promociones,1) AS acepta_promociones,
                COALESCE(c.cumpleanos,'') AS cumpleanos,
                COALESCE(c.fecha_especial,'') AS fecha_especial,
                COALESCE(c.observaciones_comerciales,'') AS observaciones_comerciales,
                COALESCE(c.descuento_pct,0) AS descuento_pct,
                COALESCE(c.lista_precio,'Normal') AS lista_precio,
                COALESCE(c.limite_credito_usd,0) AS limite_credito_usd,
                COALESCE(c.saldo_por_cobrar_usd,0) AS saldo_por_cobrar_usd,
                COALESCE(COUNT(v.id),0) AS operaciones,
                COALESCE(SUM(v.total_usd),0) AS total_ventas_usd,
                COALESCE(MAX(v.fecha), c.fecha) AS ultima_compra,
                COALESCE(pxc.deuda_total,0) AS deuda_usd
            FROM clientes c
            LEFT JOIN ventas v
                ON v.cliente_id = c.id
               AND COALESCE(v.estado,'registrada') NOT IN ('anulada','cancelada')
            LEFT JOIN (
                SELECT cliente_id, SUM(saldo_usd) AS deuda_total
                FROM cuentas_por_cobrar
                WHERE estado IN ('pendiente','parcial','vencida','incobrable')
                GROUP BY cliente_id
            ) pxc ON pxc.cliente_id = c.id
            WHERE COALESCE(c.estado,'activo')='activo'
            GROUP BY c.id
            ORDER BY total_ventas_usd DESC, operaciones DESC
            """,
            conn,
        )


def actualizar_datos_comerciales_cliente(
    cliente_id: int,
    *,
    categoria: str,
    tipo_cliente: str,
    origen: str,
    servicio_interes: str,
    comportamiento_pago: str,
    preferencia_contacto: str,
    acepta_promociones: bool,
    cumpleanos: str,
    fecha_especial: str,
    observaciones_comerciales: str,
    descuento_pct: float,
    lista_precio: str,
) -> None:
    ensure_clientes_mejoras_schema()
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE clientes
            SET categoria=?, tipo_cliente=?, origen=?, servicio_interes=?, comportamiento_pago=?,
                preferencia_contacto=?, acepta_promociones=?, cumpleanos=?, fecha_especial=?,
                observaciones_comerciales=?, descuento_pct=?, lista_precio=?
            WHERE id=?
            """,
            (
                clean_text(categoria),
                clean_text(tipo_cliente),
                clean_text(origen),
                clean_text(servicio_interes),
                clean_text(comportamiento_pago),
                clean_text(preferencia_contacto),
                1 if acepta_promociones else 0,
                clean_text(cumpleanos),
                clean_text(fecha_especial),
                clean_text(observaciones_comerciales),
                max(float(descuento_pct or 0), 0),
                clean_text(lista_precio) or "Normal",
                int(cliente_id),
            ),
        )


def render_mejoras_clientes(usuario: str = "Sistema") -> None:
    ensure_clientes_mejoras_schema()
    st.subheader("🧩 Datos comerciales avanzados")
    st.caption("Origen, tipo, servicio principal, comportamiento de pago, promociones y reactivación.")

    try:
        df = cargar_clientes_mejorados()
    except Exception as exc:
        st.error("No se pudieron cargar los datos comerciales avanzados.")
        st.exception(exc)
        return

    if df.empty:
        st.info("No hay clientes activos para mejorar.")
        return

    tab_editar, tab_reportes, tab_reactivar, tab_calidad = st.tabs([
        "Editar ficha comercial",
        "Reportes comerciales",
        "Reactivación",
        "Calidad de datos",
    ])

    with tab_editar:
        opciones = df["id"].astype(int).tolist()
        cliente_id = st.selectbox(
            "Cliente",
            opciones,
            format_func=lambda x: df.loc[df["id"].eq(x), "nombre"].iloc[0],
            key="cliente_mejoras_id",
        )
        row = df[df["id"].eq(cliente_id)].iloc[0]

        with st.form("form_datos_comerciales_cliente"):
            c1, c2, c3 = st.columns(3)
            categoria = c1.selectbox("Categoría", CATEGORIAS_CLIENTE, index=CATEGORIAS_CLIENTE.index(row["categoria"]) if row["categoria"] in CATEGORIAS_CLIENTE else 0)
            tipo_cliente = c2.selectbox("Tipo de cliente", CATEGORIAS_CLIENTE, index=CATEGORIAS_CLIENTE.index(row["tipo_cliente"]) if row["tipo_cliente"] in CATEGORIAS_CLIENTE else 0)
            origen = c3.selectbox("Origen", ORIGENES_CLIENTE, index=ORIGENES_CLIENTE.index(row["origen"]) if row["origen"] in ORIGENES_CLIENTE else 0)

            c4, c5, c6 = st.columns(3)
            servicio_interes = c4.selectbox("Servicio principal", SERVICIOS_INTERES, index=SERVICIOS_INTERES.index(row["servicio_interes"]) if row["servicio_interes"] in SERVICIOS_INTERES else 0)
            comportamiento_pago = c5.selectbox("Comportamiento de pago", COMPORTAMIENTOS_PAGO, index=COMPORTAMIENTOS_PAGO.index(row["comportamiento_pago"]) if row["comportamiento_pago"] in COMPORTAMIENTOS_PAGO else 0)
            preferencia_contacto = c6.selectbox("Preferencia de contacto", PREFERENCIAS_CONTACTO, index=PREFERENCIAS_CONTACTO.index(row["preferencia_contacto"]) if row["preferencia_contacto"] in PREFERENCIAS_CONTACTO else 0)

            c7, c8, c9 = st.columns(3)
            acepta_promociones = c7.checkbox("Acepta promociones", value=bool(row["acepta_promociones"]))
            cumpleanos = c8.text_input("Cumpleaños", str(row["cumpleanos"] or ""), placeholder="YYYY-MM-DD")
            fecha_especial = c9.text_input("Fecha especial", str(row["fecha_especial"] or ""), placeholder="Evento, graduación, regreso a clases...")

            c10, c11 = st.columns(2)
            descuento_pct = c10.number_input("Descuento especial (%)", min_value=0.0, max_value=100.0, step=1.0, value=float(row["descuento_pct"] or 0))
            lista_precio = c11.text_input("Lista de precio", str(row["lista_precio"] or "Normal"))
            observaciones = st.text_area("Observaciones comerciales", str(row["observaciones_comerciales"] or ""))

            guardar = st.form_submit_button("Guardar ficha comercial")

        if guardar:
            actualizar_datos_comerciales_cliente(
                int(cliente_id),
                categoria=categoria,
                tipo_cliente=tipo_cliente,
                origen=origen,
                servicio_interes=servicio_interes,
                comportamiento_pago=comportamiento_pago,
                preferencia_contacto=preferencia_contacto,
                acepta_promociones=acepta_promociones,
                cumpleanos=cumpleanos,
                fecha_especial=fecha_especial,
                observaciones_comerciales=observaciones,
                descuento_pct=float(descuento_pct),
                lista_precio=lista_precio,
            )
            st.success("Ficha comercial actualizada")
            st.rerun()

    with tab_reportes:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Clientes", len(df))
        c2.metric("Ventas históricas", f"$ {float(df['total_ventas_usd'].sum()):,.2f}")
        c3.metric("Deuda", f"$ {float(df['deuda_usd'].sum()):,.2f}")
        c4.metric("Aceptan promociones", int(df["acepta_promociones"].fillna(0).astype(int).sum()))

        for campo, titulo in [
            ("origen", "Clientes por origen"),
            ("tipo_cliente", "Clientes por tipo"),
            ("servicio_interes", "Clientes por servicio principal"),
            ("comportamiento_pago", "Clientes por comportamiento de pago"),
        ]:
            st.markdown(f"#### {titulo}")
            resumen = df.groupby(campo, as_index=False).agg(
                clientes=("id", "count"),
                ventas=("total_ventas_usd", "sum"),
                deuda=("deuda_usd", "sum"),
            ).sort_values("ventas", ascending=False)
            st.dataframe(resumen, use_container_width=True, hide_index=True)

    with tab_reactivar:
        work = df.copy()
        work["ultima_compra"] = pd.to_datetime(work["ultima_compra"], errors="coerce")
        work["fecha"] = pd.to_datetime(work["fecha"], errors="coerce")
        base_fecha = work["ultima_compra"].fillna(work["fecha"])
        work["dias_sin_compra"] = (pd.Timestamp(datetime.now()) - base_fecha).dt.days.fillna(999).astype(int)
        rango = st.selectbox("Rango", [30, 60, 90, 180], index=2)
        reactivar = work[(work["operaciones"] > 0) & (work["dias_sin_compra"] >= int(rango))].copy()
        reactivar = reactivar[reactivar["acepta_promociones"].fillna(0).astype(int).eq(1)]
        cols = ["id", "nombre", "whatsapp", "origen", "servicio_interes", "ultima_compra", "dias_sin_compra", "total_ventas_usd", "preferencia_contacto"]
        st.dataframe(reactivar[[c for c in cols if c in reactivar.columns]].sort_values("dias_sin_compra", ascending=False), use_container_width=True, hide_index=True)
        csv = reactivar.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Exportar reactivación CSV", csv, f"clientes_reactivar_{rango}_dias.csv", "text/csv")

    with tab_calidad:
        telefono_norm = df["whatsapp"].astype(str).str.replace(r"\D+", "", regex=True)
        duplicados_tel = df[telefono_norm.ne("") & telefono_norm.duplicated(keep=False)].copy()
        sin_tel = df[telefono_norm.eq("")].copy()
        sin_origen = df[df["origen"].fillna("No definido").eq("No definido")].copy()
        sin_servicio = df[df["servicio_interes"].fillna("No definido").eq("No definido")].copy()

        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Teléfonos duplicados", len(duplicados_tel))
        q2.metric("Sin teléfono", len(sin_tel))
        q3.metric("Sin origen", len(sin_origen))
        q4.metric("Sin servicio", len(sin_servicio))

        st.markdown("#### Teléfonos duplicados")
        st.dataframe(duplicados_tel, use_container_width=True, hide_index=True)
        st.markdown("#### Clientes sin datos comerciales completos")
        incompletos = pd.concat([sin_tel, sin_origen, sin_servicio]).drop_duplicates(subset=["id"])
        st.dataframe(incompletos, use_container_width=True, hide_index=True)
