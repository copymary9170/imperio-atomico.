from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _safe_df(sql: str, table: str) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def _load_clientes() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "clientes"):
                return pd.DataFrame()
            cols = _columns(conn, "clientes")
            selected = {
                "id": "id",
                "nombre": "nombre",
                "telefono": "telefono",
                "email": "email",
                "rif": "rif",
                "cedula": "cedula",
                "direccion": "direccion",
                "categoria": "categoria",
                "estado": "estado",
                "saldo_por_cobrar_usd": "saldo_por_cobrar_usd",
                "limite_credito_usd": "limite_credito_usd",
                "fecha": "fecha",
            }
            select_parts = []
            for out, col in selected.items():
                if col in cols:
                    select_parts.append(f"COALESCE({col}, '') AS {out}" if col not in {"id", "saldo_por_cobrar_usd", "limite_credito_usd"} else f"COALESCE({col}, 0) AS {out}")
                else:
                    default = "0" if out in {"id", "saldo_por_cobrar_usd", "limite_credito_usd"} else "''"
                    select_parts.append(f"{default} AS {out}")
            sql = f"SELECT {', '.join(select_parts)} FROM clientes ORDER BY id DESC LIMIT 1500"
            df = pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df.insert(0, "tipo", "Cliente")
    df["relacion"] = "CxC / Ventas"
    df["documento"] = df.get("rif", "").astype(str)
    if "cedula" in df.columns:
        df["documento"] = df["documento"].mask(df["documento"].eq(""), df["cedula"].astype(str))
    return df


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
            }
            select_parts = []
            for out, col in selected.items():
                if col in cols:
                    select_parts.append(f"COALESCE({col}, '') AS {out}" if col not in {"id", "estado", "dias_credito"} else f"COALESCE({col}, 0) AS {out}")
                else:
                    default = "0" if out in {"id", "estado", "dias_credito"} else "''"
                    select_parts.append(f"{default} AS {out}")
            sql = f"SELECT {', '.join(select_parts)} FROM proveedores ORDER BY id DESC LIMIT 1500"
            df = pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df.insert(0, "tipo", "Proveedor")
    df["relacion"] = "CxP / Compras"
    df["documento"] = df.get("rif", "").astype(str)
    df["saldo_por_cobrar_usd"] = 0.0
    df["limite_credito_usd"] = 0.0
    df["fecha"] = ""
    df["estado"] = df["estado"].apply(lambda x: "activo" if str(x) in {"1", "1.0", "activo", "Activo", "True"} else "inactivo")
    return df


def _unified_contacts() -> pd.DataFrame:
    clientes = _load_clientes()
    proveedores = _load_proveedores()
    frames = [df for df in [clientes, proveedores] if not df.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    cols = ["tipo", "nombre", "telefono", "email", "documento", "direccion", "categoria", "estado", "relacion", "contacto", "saldo_por_cobrar_usd", "limite_credito_usd", "dias_credito", "banco", "fecha"]
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols]


def _contactos_incompletos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    mask = (
        df["telefono"].astype(str).str.strip().eq("") |
        df["email"].astype(str).str.strip().eq("") |
        df["documento"].astype(str).str.strip().eq("") |
        df["direccion"].astype(str).str.strip().eq("")
    )
    return df[mask].copy()


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
    return _safe_df("SELECT * FROM cuentas_por_pagar_proveedores ORDER BY id DESC LIMIT 500", "cuentas_por_pagar_proveedores")


def _cxc_clientes() -> pd.DataFrame:
    return _safe_df("SELECT * FROM cuentas_por_cobrar ORDER BY id DESC LIMIT 500", "cuentas_por_cobrar")


def render_contactos(usuario: str = "Sistema") -> None:
    st.title("📇 Contactos")
    st.caption("Agenda central de clientes y proveedores: teléfonos, correos, documentos, dirección, crédito, cobranza y pagos.")

    df = _unified_contacts()
    if df.empty:
        st.info("Todavía no hay clientes ni proveedores registrados.")
        return

    incompletos = _contactos_incompletos(df)
    duplicados = _duplicados(df)
    cxc = _cxc_clientes()
    cxp = _cxp_proveedores()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total contactos", len(df))
    c2.metric("Clientes", int(df["tipo"].eq("Cliente").sum()))
    c3.metric("Proveedores", int(df["tipo"].eq("Proveedor").sum()))
    c4.metric("Incompletos", len(incompletos))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Duplicados", len(duplicados))
    c6.metric("Sin teléfono", int(df["telefono"].astype(str).str.strip().eq("").sum()))
    c7.metric("CxC clientes", len(cxc))
    c8.metric("CxP proveedores", len(cxp))

    busqueda = st.text_input("🔎 Buscar contacto", placeholder="Nombre, teléfono, email, RIF, dirección...")
    vista = df.copy()
    if busqueda.strip():
        mask = vista.astype(str).apply(lambda col: col.str.contains(busqueda, case=False, na=False)).any(axis=1)
        vista = vista[mask]

    tab_todos, tab_clientes, tab_proveedores, tab_incompletos, tab_duplicados, tab_cartera = st.tabs([
        "Todos",
        "Clientes",
        "Proveedores",
        "Contactos incompletos",
        "Duplicados",
        "Cobranza / CxP",
    ])

    with tab_todos:
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_clientes:
        clientes = vista[vista["tipo"].eq("Cliente")]
        st.dataframe(clientes, use_container_width=True, hide_index=True) if not clientes.empty else st.info("Sin clientes para mostrar.")

    with tab_proveedores:
        proveedores = vista[vista["tipo"].eq("Proveedor")]
        st.dataframe(proveedores, use_container_width=True, hide_index=True) if not proveedores.empty else st.info("Sin proveedores para mostrar.")

    with tab_incompletos:
        st.warning("Contactos sin teléfono, email, documento o dirección.")
        st.dataframe(incompletos, use_container_width=True, hide_index=True) if not incompletos.empty else st.success("No hay contactos incompletos detectados.")

    with tab_duplicados:
        st.caption("Detecta coincidencias por teléfono o email.")
        st.dataframe(duplicados, use_container_width=True, hide_index=True) if not duplicados.empty else st.success("No hay duplicados detectados por teléfono o email.")

    with tab_cartera:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 💳 Cuentas por cobrar clientes")
            st.dataframe(cxc, use_container_width=True, hide_index=True) if not cxc.empty else st.success("Sin cuentas por cobrar registradas.")
        with col_b:
            st.markdown("#### 🧾 Cuentas por pagar proveedores")
            st.dataframe(cxp, use_container_width=True, hide_index=True) if not cxp.empty else st.success("Sin cuentas por pagar registradas.")
