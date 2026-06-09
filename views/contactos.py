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
        conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})", [payload[k] for k in keys])


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
            selected = {"id":"id","nombre":"nombre","telefono":"telefono","email":"email","rif":"rif","cedula":"cedula","direccion":"direccion","categoria":"categoria","estado":"estado","saldo_por_cobrar_usd":"saldo_por_cobrar_usd","limite_credito_usd":"limite_credito_usd","fecha":"fecha"}
            parts=[]
            for out,col in selected.items():
                if col in cols:
                    parts.append(f"COALESCE({col}, '') AS {out}" if col not in {"id","saldo_por_cobrar_usd","limite_credito_usd"} else f"COALESCE({col}, 0) AS {out}")
                else:
                    parts.append(("0" if out in {"id","saldo_por_cobrar_usd","limite_credito_usd"} else "''") + f" AS {out}")
            df = pd.read_sql_query(f"SELECT {', '.join(parts)} FROM clientes ORDER BY id DESC LIMIT 1500", conn)
    except Exception:
        return pd.DataFrame()
    if df.empty: return df
    df.insert(0,"tipo","Cliente")
    df["relacion"]="CxC / Ventas"
    df["documento"]=df.get("rif","").astype(str)
    df["documento"]=df["documento"].mask(df["documento"].eq(""), df.get("cedula","").astype(str))
    return df


def _load_proveedores() -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "proveedores"):
                return pd.DataFrame()
            cols = _columns(conn, "proveedores")
            selected = {"id":"id","nombre":"nombre","telefono":"telefono","email":"email","rif":"rif","direccion":"direccion","categoria":"tipo_proveedor","contacto":"contacto","estado":"activo","dias_credito":"dias_credito_default","banco":"banco"}
            parts=[]
            for out,col in selected.items():
                if col in cols:
                    parts.append(f"COALESCE({col}, '') AS {out}" if col not in {"id","estado","dias_credito"} else f"COALESCE({col}, 0) AS {out}")
                else:
                    parts.append(("0" if out in {"id","estado","dias_credito"} else "''") + f" AS {out}")
            df = pd.read_sql_query(f"SELECT {', '.join(parts)} FROM proveedores ORDER BY id DESC LIMIT 1500", conn)
    except Exception:
        return pd.DataFrame()
    if df.empty: return df
    df.insert(0,"tipo","Proveedor")
    df["relacion"]="CxP / Compras"
    df["documento"]=df.get("rif","").astype(str)
    df["saldo_por_cobrar_usd"]=0.0
    df["limite_credito_usd"]=0.0
    df["fecha"]=""
    df["estado"]=df["estado"].apply(lambda x: "activo" if str(x) in {"1","1.0","activo","Activo","True"} else "inactivo")
    return df


def _unified_contacts() -> pd.DataFrame:
    frames=[df for df in [_load_clientes(), _load_proveedores()] if not df.empty]
    if not frames: return pd.DataFrame()
    df=pd.concat(frames, ignore_index=True, sort=False).fillna("")
    cols=["tipo","nombre","telefono","email","documento","direccion","categoria","estado","relacion","contacto","saldo_por_cobrar_usd","limite_credito_usd","dias_credito","banco","fecha"]
    for col in cols:
        if col not in df.columns: df[col]=""
    return df[cols]


def _contactos_incompletos(df):
    if df.empty: return df
    return df[df["telefono"].astype(str).str.strip().eq("") | df["email"].astype(str).str.strip().eq("") | df["documento"].astype(str).str.strip().eq("") | df["direccion"].astype(str).str.strip().eq("")].copy()


def _duplicados(df):
    if df.empty: return df
    temp=df.copy()
    temp["telefono_norm"]=temp["telefono"].astype(str).str.replace(r"\D+", "", regex=True)
    temp["email_norm"]=temp["email"].astype(str).str.lower().str.strip()
    mask_tel=temp["telefono_norm"].ne("") & temp["telefono_norm"].duplicated(keep=False)
    mask_email=temp["email_norm"].ne("") & temp["email_norm"].duplicated(keep=False)
    return temp[mask_tel | mask_email].drop(columns=["telefono_norm","email_norm"], errors="ignore")


def _cxp_proveedores(): return _safe_df("SELECT * FROM cuentas_por_pagar_proveedores ORDER BY id DESC LIMIT 500", "cuentas_por_pagar_proveedores")
def _cxc_clientes(): return _safe_df("SELECT * FROM cuentas_por_cobrar ORDER BY id DESC LIMIT 500", "cuentas_por_cobrar")


def _render_registrar_cliente():
    st.subheader("➕ Registrar cliente")
    with st.form("form_contacto_cliente"):
        a,b=st.columns(2)
        nombre=a.text_input("Nombre del cliente *")
        telefono=b.text_input("Teléfono / WhatsApp")
        email=a.text_input("Email")
        documento=b.text_input("Cédula / RIF")
        categoria=a.selectbox("Categoría", ["General","Frecuente","VIP","Revendedor","Empresa","Otro"])
        limite=b.number_input("Límite de crédito USD", min_value=0.0, step=1.0, format="%.2f")
        direccion=st.text_area("Dirección")
        obs=st.text_area("Observaciones")
        guardar=st.form_submit_button("Guardar cliente", type="primary", use_container_width=True)
    if guardar:
        if not nombre.strip():
            st.error("El nombre del cliente es obligatorio.")
            return
        _insert_flexible("clientes", {"nombre":nombre.strip(),"telefono":telefono.strip(),"email":email.strip(),"rif":documento.strip(),"cedula":documento.strip(),"direccion":direccion.strip(),"categoria":categoria,"estado":"activo","limite_credito_usd":float(limite),"observaciones":obs.strip()})
        st.success("Cliente registrado.")
        st.rerun()


def _render_registrar_proveedor():
    st.subheader("➕ Registrar proveedor")
    with st.form("form_contacto_proveedor"):
        a,b=st.columns(2)
        nombre=a.text_input("Nombre / Razón social *")
        rif=b.text_input("RIF / Identificación")
        telefono=a.text_input("Teléfono")
        email=b.text_input("Email")
        contacto=a.text_input("Persona de contacto / vendedor")
        tipo=b.selectbox("Tipo proveedor", ["Insumos","Servicios","Maquinaria","Papelería","Transporte","Otro"])
        direccion=st.text_area("Dirección", key="dir_proveedor_contactos")
        c,d,e=st.columns(3)
        dias=c.number_input("Días de crédito", min_value=0, step=1)
        moneda=d.selectbox("Moneda", ["USD","VES","COP","EUR"])
        banco=e.text_input("Banco")
        obs=st.text_area("Observaciones", key="obs_proveedor_contactos")
        guardar=st.form_submit_button("Guardar proveedor", type="primary", use_container_width=True)
    if guardar:
        if not nombre.strip():
            st.error("El nombre del proveedor es obligatorio.")
            return
        _insert_flexible("proveedores", {"nombre":nombre.strip(),"rif":rif.strip(),"telefono":telefono.strip(),"email":email.strip(),"contacto":contacto.strip(),"tipo_proveedor":tipo,"direccion":direccion.strip(),"dias_credito_default":int(dias),"moneda_default":moneda,"banco":banco.strip(),"datos_bancarios":banco.strip(),"observaciones":obs.strip(),"activo":1})
        st.success("Proveedor registrado.")
        st.rerun()


def render_contactos(usuario: str = "Sistema") -> None:
    st.title("📇 Contactos")
    st.caption("Agenda central de clientes y proveedores: registro, teléfonos, correos, documentos, dirección, crédito, cobranza y pagos.")

    tab_registrar, tab_agenda, tab_incompletos, tab_duplicados, tab_cartera = st.tabs(["➕ Registrar", "Agenda", "Contactos incompletos", "Duplicados", "Cobranza / CxP"])

    with tab_registrar:
        col1,col2=st.columns(2)
        with col1: _render_registrar_cliente()
        with col2: _render_registrar_proveedor()

    df=_unified_contacts()
    cxc=_cxc_clientes(); cxp=_cxp_proveedores()
    if df.empty:
        with tab_agenda: st.info("Todavía no hay clientes ni proveedores registrados. Usa la pestaña ➕ Registrar para crearlos.")
        with tab_incompletos: st.info("Sin datos para revisar.")
        with tab_duplicados: st.info("Sin datos para revisar.")
        with tab_cartera: st.info("Sin cartera registrada.")
        return

    incompletos=_contactos_incompletos(df); duplicados=_duplicados(df)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Total contactos", len(df)); c2.metric("Clientes", int(df["tipo"].eq("Cliente").sum())); c3.metric("Proveedores", int(df["tipo"].eq("Proveedor").sum())); c4.metric("Incompletos", len(incompletos))
    c5,c6,c7,c8=st.columns(4)
    c5.metric("Duplicados", len(duplicados)); c6.metric("Sin teléfono", int(df["telefono"].astype(str).str.strip().eq("").sum())); c7.metric("CxC clientes", len(cxc)); c8.metric("CxP proveedores", len(cxp))

    with tab_agenda:
        busqueda=st.text_input("🔎 Buscar contacto", placeholder="Nombre, teléfono, email, RIF, dirección...")
        vista=df.copy()
        if busqueda.strip():
            mask=vista.astype(str).apply(lambda col: col.str.contains(busqueda, case=False, na=False)).any(axis=1)
            vista=vista[mask]
        sub1,sub2,sub3=st.tabs(["Todos","Clientes","Proveedores"])
        with sub1: st.dataframe(vista, use_container_width=True, hide_index=True)
        with sub2:
            cli=vista[vista["tipo"].eq("Cliente")]
            st.dataframe(cli, use_container_width=True, hide_index=True) if not cli.empty else st.info("Sin clientes para mostrar.")
        with sub3:
            prov=vista[vista["tipo"].eq("Proveedor")]
            st.dataframe(prov, use_container_width=True, hide_index=True) if not prov.empty else st.info("Sin proveedores para mostrar.")

    with tab_incompletos:
        st.warning("Contactos sin teléfono, email, documento o dirección.")
        st.dataframe(incompletos, use_container_width=True, hide_index=True) if not incompletos.empty else st.success("No hay contactos incompletos detectados.")

    with tab_duplicados:
        st.caption("Detecta coincidencias por teléfono o email.")
        st.dataframe(duplicados, use_container_width=True, hide_index=True) if not duplicados.empty else st.success("No hay duplicados detectados por teléfono o email.")

    with tab_cartera:
        a,b=st.columns(2)
        with a:
            st.markdown("#### 💳 Cuentas por cobrar clientes")
            st.dataframe(cxc, use_container_width=True, hide_index=True) if not cxc.empty else st.success("Sin cuentas por cobrar registradas.")
        with b:
            st.markdown("#### 🧾 Cuentas por pagar proveedores")
            st.dataframe(cxp, use_container_width=True, hide_index=True) if not cxp.empty else st.success("Sin cuentas por pagar registradas.")
