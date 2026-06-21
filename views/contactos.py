from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _insert_flexible(table: str, data: dict) -> None:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            st.error(f"No existe la tabla {table}.")
            return
        cols = _columns(conn, table)
        payload = {k: v for k, v in data.items() if k in cols}
        if not payload:
            st.error(f"No hay columnas compatibles para guardar en {table}.")
            return
        keys = list(payload.keys())
        placeholders = ",".join(["?"] * len(keys))
        conn.execute(
            f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})",
            [payload[k] for k in keys],
        )


def _safe_df(sql: str, table: str) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def _load_proveedores() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "proveedores"):
                return pd.DataFrame()
            cols = _columns(conn, "proveedores")
            selected = {
                "id": "id",
                "nombre": "nombre",
                "telefono": "telefono",
                "email": "email",
                "rif": "rif",
                "direccion": "direccion",
                "categoria": "tipo_proveedor",
                "contacto": "contacto",
                "estado": "activo",
                "dias_credito": "dias_credito_default",
                "banco": "banco",
                "fecha": "fecha_creacion",
            }
            parts = []
            for out, col in selected.items():
                if col in cols:
                    if out in {"id", "estado", "dias_credito"}:
                        parts.append(f"COALESCE({col}, 0) AS {out}")
                    else:
                        parts.append(f"COALESCE({col}, '') AS {out}")
                else:
                    parts.append(("0" if out in {"id", "estado", "dias_credito"} else "''") + f" AS {out}")
            df = pd.read_sql_query(
                f"SELECT {', '.join(parts)} FROM proveedores ORDER BY id DESC LIMIT 1500",
                conn,
            )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["tipo"] = "Proveedor"
    df["relacion"] = "CxP / Compras"
    df["documento"] = df.get("rif", "").astype(str)
    df["estado"] = df["estado"].apply(
        lambda x: "activo" if str(x) in {"1", "1.0", "activo", "Activo", "True"} else "inactivo"
    )
    cols = [
        "tipo", "nombre", "telefono", "email", "documento", "direccion",
        "categoria", "estado", "relacion", "contacto", "dias_credito",
        "banco", "fecha",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols]


def _contactos_incompletos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[
        df["telefono"].astype(str).str.strip().eq("")
        | df["email"].astype(str).str.strip().eq("")
        | df["documento"].astype(str).str.strip().eq("")
        | df["direccion"].astype(str).str.strip().eq("")
    ].copy()


def _duplicados(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    temp = df.copy()
    temp["telefono_norm"] = temp["telefono"].astype(str).str.replace(r"\D+", "", regex=True)
    temp["email_norm"] = temp["email"].astype(str).str.lower().str.strip()
    mask_tel = temp["telefono_norm"].ne("") & temp["telefono_norm"].duplicated(keep=False)
    mask_email = temp["email_norm"].ne("") & temp["email_norm"].duplicated(keep=False)
    return temp[mask_tel | mask_email].drop(columns=["telefono_norm", "email_norm"], errors="ignore")


def _cxp_proveedores() -> pd.DataFrame:
    return _safe_df(
        "SELECT * FROM cuentas_por_pagar_proveedores ORDER BY id DESC LIMIT 500",
        "cuentas_por_pagar_proveedores",
    )


def _render_registrar_proveedor() -> None:
    st.subheader("➕ Registrar proveedor")
    with st.form("form_contacto_proveedor"):
        a, b = st.columns(2)
        nombre = a.text_input("Nombre / Razón social *")
        rif = b.text_input("RIF / Identificación")
        telefono = a.text_input("Teléfono")
        email = b.text_input("Email")
        contacto = a.text_input("Persona de contacto / vendedor")
        tipo = b.selectbox("Tipo proveedor", ["Insumos", "Servicios", "Maquinaria", "Papelería", "Transporte", "Otro"])
        direccion = st.text_area("Dirección", key="dir_proveedor_contactos")
        c, d, e = st.columns(3)
        dias = c.number_input("Días de crédito", min_value=0, step=1)
        moneda = d.selectbox("Moneda", ["USD", "VES", "COP", "EUR"])
        banco = e.text_input("Banco")
        obs = st.text_area("Observaciones", key="obs_proveedor_contactos")
        guardar = st.form_submit_button("Guardar proveedor", type="primary", use_container_width=True)
    if guardar:
        if not nombre.strip():
            st.error("El nombre del proveedor es obligatorio.")
            return
        _insert_flexible(
            "proveedores",
            {
                "nombre": nombre.strip(),
                "rif": rif.strip(),
                "telefono": telefono.strip(),
                "email": email.strip(),
                "contacto": contacto.strip(),
                "tipo_proveedor": tipo,
                "direccion": direccion.strip(),
                "dias_credito_default": int(dias),
                "moneda_default": moneda,
                "banco": banco.strip(),
                "datos_bancarios": banco.strip(),
                "observaciones": obs.strip(),
                "activo": 1,
            },
        )
        st.success("Proveedor registrado. Ya estará disponible para compras e inventario.")
        st.rerun()


def render_contactos(usuario: str = "Sistema") -> None:
    st.title("📇 Proveedores")
    st.caption("Registro y agenda central de proveedores para compras, cuentas por pagar e inventario.")

    tab_registrar, tab_agenda, tab_incompletos, tab_duplicados, tab_cxp = st.tabs([
        "➕ Registrar proveedor",
        "Agenda de proveedores",
        "Datos incompletos",
        "Duplicados",
        "Cuentas por pagar",
    ])

    with tab_registrar:
        _render_registrar_proveedor()

    df = _load_proveedores()
    cxp = _cxp_proveedores()
    if df.empty:
        with tab_agenda:
            st.info("Todavía no hay proveedores registrados. Usa la pestaña ➕ Registrar proveedor.")
        with tab_incompletos:
            st.info("Sin datos para revisar.")
        with tab_duplicados:
            st.info("Sin datos para revisar.")
        with tab_cxp:
            st.info("Sin cuentas por pagar registradas.")
        return

    incompletos = _contactos_incompletos(df)
    duplicados = _duplicados(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proveedores", len(df))
    c2.metric("Activos", int(df["estado"].eq("activo").sum()))
    c3.metric("Incompletos", len(incompletos))
    c4.metric("Duplicados", len(duplicados))

    with tab_agenda:
        busqueda = st.text_input("🔎 Buscar proveedor", placeholder="Nombre, teléfono, email, RIF, dirección...")
        vista = df.copy()
        if busqueda.strip():
            mask = vista.astype(str).apply(lambda col: col.str.contains(busqueda, case=False, na=False)).any(axis=1)
            vista = vista[mask]
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_incompletos:
        st.warning("Proveedores sin teléfono, email, RIF o dirección.")
        st.dataframe(incompletos, use_container_width=True, hide_index=True) if not incompletos.empty else st.success("No hay proveedores incompletos detectados.")

    with tab_duplicados:
        st.caption("Detecta coincidencias por teléfono o email.")
        st.dataframe(duplicados, use_container_width=True, hide_index=True) if not duplicados.empty else st.success("No hay duplicados detectados por teléfono o email.")

    with tab_cxp:
        st.markdown("#### 🧾 Cuentas por pagar proveedores")
        st.dataframe(cxp, use_container_width=True, hide_index=True) if not cxp.empty else st.success("Sin cuentas por pagar registradas.")
