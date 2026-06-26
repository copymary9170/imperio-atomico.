from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from views.areas_empresariales import render_area_empresarial
from views.manuales_sop import render_manuales_sop

STATES = ["Borrador", "Pendiente", "Activo", "En revisión", "Cerrado", "Vencido", "Cancelado"]
SECTIONS = {
    "Contratos": ("legal_contratos", "titulo", "fecha_vencimiento"),
    "Garantías / reclamos": ("legal_reclamos_garantias", "descripcion", "fecha_limite"),
    "Privacidad / políticas": ("legal_politicas", "titulo", "fecha_vigencia"),
    "Autorizaciones": ("legal_autorizaciones", "persona_entidad", "fecha_vencimiento"),
    "Incidentes legales": ("legal_incidentes", "asunto", "fecha_limite"),
    "Documentos legales": ("legal_documentos", "titulo", "fecha_vigencia"),
}


def _ensure() -> None:
    with db_transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS legal_contratos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, titulo TEXT NOT NULL, tipo TEXT DEFAULT 'Otro', contraparte TEXT, responsable TEXT, fecha_inicio TEXT, fecha_vencimiento TEXT, monto_usd REAL DEFAULT 0, moneda TEXT DEFAULT 'USD', estado TEXT DEFAULT 'Borrador', documento_referencia TEXT, observaciones TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_reclamos_garantias (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, tipo TEXT DEFAULT 'Garantía', cliente TEXT, venta_id TEXT, descripcion TEXT NOT NULL, responsable TEXT, fecha_limite TEXT, estado TEXT DEFAULT 'Pendiente', solucion TEXT, documento_referencia TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_politicas (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, titulo TEXT NOT NULL, categoria TEXT DEFAULT 'Política', version TEXT DEFAULT '1.0', estado TEXT DEFAULT 'Borrador', responsable TEXT, fecha_vigencia TEXT, contenido TEXT, documento_referencia TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_autorizaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, tipo TEXT DEFAULT 'Otro', persona_entidad TEXT NOT NULL, descripcion TEXT, responsable TEXT, fecha_vencimiento TEXT, estado TEXT DEFAULT 'Pendiente', evidencia TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_incidentes (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, tipo TEXT DEFAULT 'Otro', asunto TEXT NOT NULL, descripcion TEXT, responsable TEXT, prioridad TEXT DEFAULT 'Media', estado TEXT DEFAULT 'Abierto', fecha_limite TEXT, accion_tomada TEXT, documento_referencia TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_documentos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP, codigo TEXT, titulo TEXT NOT NULL, tipo TEXT DEFAULT 'Documento', version TEXT DEFAULT '1.0', estado TEXT DEFAULT 'Borrador', confidencialidad TEXT DEFAULT 'Interno', responsable TEXT, fecha_vigencia TEXT, referencia TEXT, observaciones TEXT, created_by TEXT, actualizado_en TEXT, actualizado_por TEXT);
        CREATE TABLE IF NOT EXISTS legal_auditoria (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT DEFAULT CURRENT_TIMESTAMP, usuario TEXT NOT NULL, entidad TEXT NOT NULL, entidad_id INTEGER, accion TEXT NOT NULL, datos_json TEXT, motivo TEXT);
        """)
        additions = {
            "legal_contratos": {"codigo":"TEXT", "moneda":"TEXT DEFAULT 'USD'", "actualizado_en":"TEXT", "actualizado_por":"TEXT"},
            "legal_reclamos_garantias": {"codigo":"TEXT", "actualizado_en":"TEXT", "actualizado_por":"TEXT"},
            "legal_politicas": {"codigo":"TEXT", "actualizado_en":"TEXT", "actualizado_por":"TEXT"},
            "legal_autorizaciones": {"codigo":"TEXT", "actualizado_en":"TEXT", "actualizado_por":"TEXT"},
            "legal_incidentes": {"codigo":"TEXT", "actualizado_en":"TEXT", "actualizado_por":"TEXT"},
        }
        for table, columns in additions.items():
            existing = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")


def _read(table: str) -> pd.DataFrame:
    _ensure()
    with db_transaction() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id DESC", conn)


def _save(table: str, payload: dict, user: str) -> int:
    with db_transaction() as conn:
        allowed = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
        data = {k: v for k, v in payload.items() if k in allowed}
        keys = list(data)
        cur = conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [data[k] for k in keys])
        row_id = int(cur.lastrowid)
        conn.execute("INSERT INTO legal_auditoria(usuario,entidad,entidad_id,accion,datos_json) VALUES (?,?,?,?,?)", (user, table, row_id, "crear", json.dumps(data, ensure_ascii=False, default=str)))
        return row_id


def _update(table: str, row_id: int, state: str, owner: str, note: str, user: str) -> None:
    with db_transaction() as conn:
        cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
        values = {"estado": state, "responsable": owner, "actualizado_en": pd.Timestamp.now().isoformat(), "actualizado_por": user}
        if table == "legal_reclamos_garantias": values["solucion"] = note
        if table == "legal_incidentes": values["accion_tomada"] = note
        values = {k: v for k, v in values.items() if k in cols}
        conn.execute(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in values)} WHERE id=?", [values[k] for k in values] + [row_id])
        conn.execute("INSERT INTO legal_auditoria(usuario,entidad,entidad_id,accion,datos_json,motivo) VALUES (?,?,?,?,?,?)", (user, table, row_id, "actualizar", json.dumps(values, ensure_ascii=False), note))


def _summary() -> None:
    today = pd.Timestamp.today().normalize()
    contracts, claims, incidents = _read("legal_contratos"), _read("legal_reclamos_garantias"), _read("legal_incidentes")
    due = pd.DataFrame()
    if not contracts.empty:
        dates = pd.to_datetime(contracts["fecha_vencimiento"], errors="coerce")
        due = contracts[dates.notna() & (dates >= today) & (dates <= today + pd.Timedelta(days=30)) & ~contracts["estado"].isin(["Cerrado", "Cancelado"])]
    open_claims = claims[~claims["estado"].isin(["Cerrado", "Cancelado"])] if not claims.empty else claims
    open_incidents = incidents[~incidents["estado"].isin(["Cerrado", "Cancelado"])] if not incidents.empty else incidents
    a,b,c,d = st.columns(4)
    a.metric("Contratos", len(contracts)); b.metric("Por vencer", len(due)); c.metric("Reclamos abiertos", len(open_claims)); d.metric("Incidentes abiertos", len(open_incidents))
    if not due.empty: st.dataframe(due, use_container_width=True, hide_index=True)


def _section(label: str, table: str, main_field: str, date_field: str, user: str) -> None:
    st.subheader(label)
    with st.form(f"new_{table}"):
        code = st.text_input("Código", key=f"code_{table}")
        title = st.text_input("Título / asunto / persona", key=f"title_{table}")
        detail = st.text_area("Descripción / contenido", key=f"detail_{table}")
        a,b,c = st.columns(3)
        owner = a.text_input("Responsable", value=user, key=f"owner_{table}")
        due = b.date_input("Fecha límite / vigencia", value=date.today()+timedelta(days=30), key=f"due_{table}")
        state = c.selectbox("Estado", STATES, index=1, key=f"state_{table}")
        reference = st.text_input("Documento / evidencia / referencia", key=f"ref_{table}")
        submit = st.form_submit_button("Guardar", type="primary")
    if submit:
        if not title.strip(): st.error("El título o asunto es obligatorio.")
        else:
            payload = {"codigo":code, main_field:title, "responsable":owner or user, date_field:due.isoformat(), "estado":state, "created_by":user}
            for field in ("descripcion","contenido","observaciones"):
                if field in _read(table).columns or table in {"legal_reclamos_garantias","legal_autorizaciones","legal_incidentes"} and field=="descripcion": payload[field]=detail
            if table=="legal_documentos": payload["referencia"]=reference
            elif table=="legal_autorizaciones": payload["evidencia"]=reference
            else: payload["documento_referencia"]=reference
            st.success(f"Registro #{_save(table,payload,user)} guardado."); st.rerun()
    df = _read(table)
    if not df.empty:
        with st.expander("Actualizar seguimiento"):
            row_id = st.selectbox("Registro", df["id"].astype(int).tolist(), key=f"edit_{table}")
            new_state = st.selectbox("Nuevo estado", STATES, key=f"edit_state_{table}")
            new_owner = st.text_input("Responsable", value=user, key=f"edit_owner_{table}")
            note = st.text_area("Seguimiento / motivo", key=f"edit_note_{table}")
            if st.button("Guardar actualización", key=f"edit_save_{table}"):
                _update(table,int(row_id),new_state,new_owner,note,user); st.success("Actualizado con auditoría."); st.rerun()
        st.dataframe(df,use_container_width=True,hide_index=True)
    else: st.info("No hay registros.")
    if table=="legal_documentos": render_area_empresarial("Legal",user,show_title=False)


def _alerts() -> None:
    today = pd.Timestamp.today().normalize(); rows=[]
    for label,(table,_,date_field) in SECTIONS.items():
        df=_read(table)
        if df.empty or date_field not in df.columns: continue
        dates=pd.to_datetime(df[date_field],errors="coerce"); active=~df["estado"].isin(["Cerrado","Cancelado"])
        expired=df[dates.notna()&(dates<today)&active]; upcoming=df[dates.notna()&(dates>=today)&(dates<=today+pd.Timedelta(days=30))&active]
        if len(expired): rows.append({"Nivel":"Alto","Alerta":f"{label} vencidos","Cantidad":len(expired)})
        if len(upcoming): rows.append({"Nivel":"Medio","Alerta":f"{label} próximos","Cantidad":len(upcoming)})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True) if rows else st.success("Sin alertas legales críticas.")


def render_legal_hub(usuario: str="Sistema") -> None:
    _ensure(); st.title("⚖️ Legal"); st.caption("Contratos, reclamos, privacidad, autorizaciones, incidentes, documentos, auditoría y alertas.")
    options=["Resumen legal",*SECTIONS.keys(),"SOP legales","Alertas legales","Auditoría legal"]
    selected=st.radio("Sección legal",options,horizontal=True,key="legal_seccion_activa"); st.divider()
    if selected=="Resumen legal": _summary()
    elif selected=="SOP legales": render_manuales_sop(usuario)
    elif selected=="Alertas legales": _alerts()
    elif selected=="Auditoría legal":
        df=_read("legal_auditoria"); st.dataframe(df,use_container_width=True,hide_index=True) if not df.empty else st.info("Sin auditoría todavía.")
    else:
        table,field,date_field=SECTIONS[selected]; _section(selected,table,field,date_field,usuario)
