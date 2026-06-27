from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction

STATES = ["Borrador", "En revisión", "Cambios solicitados", "Rechazado", "Aprobado", "Vigente", "Suspendido", "Sustituido", "Archivado"]
CHANNELS = ["Web", "WhatsApp", "Instagram", "Cotización", "Factura", "Catálogo", "Atención física", "Correo"]
SERVICES = ["Impresiones", "Copias", "Papelería", "Papelería creativa", "Sublimación", "Diseño básico", "Venta de impresoras", "Tintas", "Tóner", "Cartuchos", "Equipos tecnológicos", "Material escolar", "Material de oficina", "Consumibles", "Servicios administrativos", "Servicios digitales", "Comercio electrónico"]
ALLOWED = {"pdf", "docx", "odt", "png", "jpg", "jpeg", "eml", "msg", "mp3", "mp4", "wav"}


def _ensure() -> None:
    with db_transaction() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS legal_notice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            titulo TEXT NOT NULL,
            version_actual TEXT NOT NULL DEFAULT '1.0',
            estado TEXT NOT NULL DEFAULT 'Borrador',
            fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_vigencia TEXT,
            fecha_proxima_revision TEXT,
            responsable TEXT NOT NULL,
            revisor TEXT,
            aprobador TEXT,
            nivel_riesgo TEXT NOT NULL DEFAULT 'Medio',
            nombre_comercial TEXT NOT NULL,
            razon_social TEXT,
            rif TEXT,
            direccion_atencion TEXT NOT NULL,
            telefono_oficial TEXT,
            whatsapp_oficial TEXT,
            correo_oficial TEXT,
            horario_atencion TEXT,
            pais TEXT NOT NULL DEFAULT 'Venezuela',
            ciudad TEXT,
            servicios_json TEXT,
            canales_json TEXT,
            jurisdiccion TEXT NOT NULL DEFAULT 'Venezuela',
            relaciones_politicas TEXT,
            identificacion_titular TEXT,
            objeto_aviso TEXT,
            condiciones_uso TEXT,
            limitacion_responsabilidad TEXT,
            propiedad_intelectual TEXT,
            uso_disenos_cliente TEXT,
            proteccion_datos TEXT,
            comunicaciones_oficiales TEXT,
            legislacion_jurisdiccion TEXT,
            creado_por TEXT,
            actualizado_por TEXT,
            actualizado_en TEXT,
            publicado_en TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_notice_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            estado TEXT NOT NULL,
            contenido_json TEXT NOT NULL,
            hash_contenido TEXT NOT NULL,
            autor TEXT NOT NULL,
            revisor TEXT,
            aprobador TEXT,
            fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_aprobacion TEXT,
            fecha_publicacion TEXT,
            cambios_principales TEXT,
            vigente INTEGER NOT NULL DEFAULT 0,
            UNIQUE(notice_id, version)
        );
        CREATE TABLE IF NOT EXISTS legal_notice_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            version_id INTEGER,
            canal TEXT NOT NULL,
            ubicacion TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            fecha_publicacion TEXT,
            publicado_por TEXT,
            evidencia_referencia TEXT,
            observaciones TEXT
        );
        CREATE TABLE IF NOT EXISTS legal_notice_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            version_id INTEGER,
            nombre_archivo TEXT NOT NULL,
            extension TEXT NOT NULL,
            tamano_bytes INTEGER NOT NULL,
            hash_sha256 TEXT NOT NULL,
            ruta TEXT NOT NULL,
            tipo_documento TEXT NOT NULL,
            firmado INTEGER NOT NULL DEFAULT 0,
            cargado_por TEXT NOT NULL,
            fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS legal_notice_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT NOT NULL,
            accion TEXT NOT NULL,
            notice_id INTEGER,
            version_id INTEGER,
            antes_json TEXT,
            despues_json TEXT,
            comentario TEXT,
            resultado TEXT NOT NULL DEFAULT 'Exitoso'
        );
        """)


def _audit(user: str, action: str, notice_id: int | None, version_id: int | None = None, before: dict | None = None, after: dict | None = None, comment: str = "") -> None:
    with db_transaction() as conn:
        conn.execute("INSERT INTO legal_notice_audit (usuario,accion,notice_id,version_id,antes_json,despues_json,comentario) VALUES (?,?,?,?,?,?,?)", (user, action, notice_id, version_id, json.dumps(before or {}, ensure_ascii=False, default=str), json.dumps(after or {}, ensure_ascii=False, default=str), comment))


def _hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _next_code() -> str:
    year = date.today().year
    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) total FROM legal_notice WHERE codigo LIKE ?", (f"AL-{year}-%",)).fetchone()
    return f"AL-{year}-{int(row['total'] or 0)+1:04d}"


def _read_notices() -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM legal_notice ORDER BY id DESC", conn)


def _create_notice(data: dict, user: str) -> int:
    payload = dict(data)
    payload.update({"codigo": _next_code(), "version_actual": "1.0", "estado": "Borrador", "creado_por": user, "actualizado_por": user, "actualizado_en": pd.Timestamp.now().isoformat()})
    with db_transaction() as conn:
        allowed = {str(r[1]) for r in conn.execute("PRAGMA table_info(legal_notice)")}
        payload = {k: v for k, v in payload.items() if k in allowed}
        keys = list(payload)
        cur = conn.execute(f"INSERT INTO legal_notice ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [payload[k] for k in keys])
        notice_id = int(cur.lastrowid)
        vcur = conn.execute("INSERT INTO legal_notice_versions (notice_id,version,estado,contenido_json,hash_contenido,autor,cambios_principales) VALUES (?,'1.0','Borrador',?,?,?,'Creación inicial')", (notice_id, json.dumps(payload, ensure_ascii=False, default=str), _hash(payload), user))
        version_id = int(vcur.lastrowid)
    _audit(user, "Crear aviso", notice_id, version_id, after=payload)
    return notice_id


def _change_state(notice_id: int, target: str, user: str, comment: str) -> None:
    transitions = {
        "Borrador": {"En revisión"},
        "En revisión": {"Cambios solicitados", "Aprobado", "Rechazado"},
        "Cambios solicitados": {"En revisión"},
        "Aprobado": {"Vigente"},
        "Vigente": {"Suspendido", "Sustituido"},
        "Suspendido": {"Vigente", "Archivado"},
        "Sustituido": {"Archivado"},
    }
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM legal_notice WHERE id=?", (notice_id,)).fetchone()
        if not row:
            raise ValueError("Aviso no encontrado.")
        current = str(row["estado"])
        if target not in transitions.get(current, set()):
            raise ValueError(f"Transición no permitida: {current} → {target}")
        if target in {"Cambios solicitados", "Rechazado", "Suspendido", "Archivado"} and not comment.strip():
            raise ValueError("Debes indicar el motivo.")
        conn.execute("UPDATE legal_notice SET estado=?, actualizado_por=?, actualizado_en=?, publicado_en=CASE WHEN ?='Vigente' THEN CURRENT_TIMESTAMP ELSE publicado_en END WHERE id=?", (target, user, pd.Timestamp.now().isoformat(), target, notice_id))
        version = conn.execute("SELECT * FROM legal_notice_versions WHERE notice_id=? ORDER BY id DESC LIMIT 1", (notice_id,)).fetchone()
        version_id = int(version["id"]) if version else None
        conn.execute("UPDATE legal_notice_versions SET estado=?, revisor=CASE WHEN ? IN ('En revisión','Cambios solicitados') THEN ? ELSE revisor END, aprobador=CASE WHEN ?='Aprobado' THEN ? ELSE aprobador END, fecha_aprobacion=CASE WHEN ?='Aprobado' THEN CURRENT_TIMESTAMP ELSE fecha_aprobacion END, fecha_publicacion=CASE WHEN ?='Vigente' THEN CURRENT_TIMESTAMP ELSE fecha_publicacion END, vigente=CASE WHEN ?='Vigente' THEN 1 ELSE vigente END WHERE id=?", (target, target, user, target, user, target, target, target, version_id))
    _audit(user, f"Cambiar estado a {target}", notice_id, version_id, before={"estado": current}, after={"estado": target}, comment=comment)


def _save_files(notice_id: int, version_id: int | None, files, doc_type: str, signed: bool, user: str) -> int:
    root = Path("data/legal_notice_files") / str(notice_id)
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in files or []:
        ext = item.name.rsplit(".", 1)[-1].lower() if "." in item.name else ""
        if ext not in ALLOWED:
            raise ValueError(f"Formato no permitido: {item.name}")
        content = item.getvalue()
        if len(content) > 20 * 1024 * 1024:
            raise ValueError(f"{item.name} supera 20 MB")
        digest = hashlib.sha256(content).hexdigest()
        target = root / f"{digest[:12]}_{Path(item.name).name}"
        with db_transaction() as conn:
            if conn.execute("SELECT id FROM legal_notice_files WHERE notice_id=? AND hash_sha256=?", (notice_id, digest)).fetchone():
                continue
            target.write_bytes(content)
            conn.execute("INSERT INTO legal_notice_files (notice_id,version_id,nombre_archivo,extension,tamano_bytes,hash_sha256,ruta,tipo_documento,firmado,cargado_por) VALUES (?,?,?,?,?,?,?,?,?,?)", (notice_id, version_id, item.name, ext, len(content), digest, str(target), doc_type, int(signed), user))
        count += 1
        _audit(user, "Cargar archivo", notice_id, version_id, after={"archivo": item.name, "hash": digest})
    return count


def _render_new(user: str) -> None:
    with st.form("legal_notice_new"):
        t1, t2, t3, t4 = st.tabs(["General", "Empresa", "Alcance", "Contenido"])
        with t1:
            titulo = st.text_input("Título *", value="Aviso Legal")
            c1, c2, c3 = st.columns(3)
            responsable = c1.text_input("Responsable *", value=user)
            revisor = c2.text_input("Revisor")
            aprobador = c3.text_input("Aprobador")
            riesgo = st.selectbox("Nivel de riesgo", ["Bajo", "Medio", "Alto", "Crítico"], index=1)
            vigencia = st.date_input("Fecha de vigencia", value=date.today())
            revision = st.date_input("Próxima revisión", value=date.today()+timedelta(days=365))
        with t2:
            nombre = st.text_input("Nombre comercial *", value="Copy Mary")
            razon = st.text_input("Razón social")
            rif = st.text_input("RIF / ID fiscal")
            direccion = st.text_area("Dirección de atención *", value="Edificio 26, Primera Etapa")
            c4, c5, c6 = st.columns(3)
            telefono = c4.text_input("Teléfono")
            whatsapp = c5.text_input("WhatsApp")
            correo = c6.text_input("Correo")
            horario = st.text_input("Horario")
            pais = st.text_input("País *", value="Venezuela")
            ciudad = st.text_input("Ciudad")
        with t3:
            servicios = st.multiselect("Servicios cubiertos *", SERVICES)
            canales = st.multiselect("Canales *", CHANNELS)
            jurisdiccion = st.text_input("Jurisdicción *", value="Venezuela")
            relaciones = st.multiselect("Políticas relacionadas", ["Términos y Condiciones", "Privacidad", "Cookies", "Garantías", "Devoluciones", "Propiedad Intelectual"])
        with t4:
            titular = st.text_area("Identificación del titular *")
            objeto = st.text_area("Objeto del aviso *")
            condiciones = st.text_area("Condiciones de uso *")
            limitacion = st.text_area("Limitación de responsabilidad *")
            propiedad = st.text_area("Propiedad intelectual *")
            disenos = st.text_area("Uso de diseños del cliente *")
            privacidad = st.text_area("Protección de datos *")
            comunicaciones = st.text_area("Comunicaciones oficiales *")
            legislacion = st.text_area("Legislación y jurisdicción *")
        submit = st.form_submit_button("Crear Aviso Legal", type="primary")
    if submit:
        required = [titulo, responsable, nombre, direccion, pais, jurisdiccion, titular, objeto, condiciones, limitacion, propiedad, disenos, privacidad, comunicaciones, legislacion]
        if not all(str(v).strip() for v in required) or not servicios or not canales:
            st.error("Completa todos los campos obligatorios.")
            return
        data = {
            "titulo": titulo, "fecha_vigencia": vigencia.isoformat(), "fecha_proxima_revision": revision.isoformat(),
            "responsable": responsable, "revisor": revisor, "aprobador": aprobador, "nivel_riesgo": riesgo,
            "nombre_comercial": nombre, "razon_social": razon, "rif": rif, "direccion_atencion": direccion,
            "telefono_oficial": telefono, "whatsapp_oficial": whatsapp, "correo_oficial": correo,
            "horario_atencion": horario, "pais": pais, "ciudad": ciudad,
            "servicios_json": json.dumps(servicios, ensure_ascii=False), "canales_json": json.dumps(canales, ensure_ascii=False),
            "jurisdiccion": jurisdiccion, "relaciones_politicas": json.dumps(relaciones, ensure_ascii=False),
            "identificacion_titular": titular, "objeto_aviso": objeto, "condiciones_uso": condiciones,
            "limitacion_responsabilidad": limitacion, "propiedad_intelectual": propiedad,
            "uso_disenos_cliente": disenos, "proteccion_datos": privacidad,
            "comunicaciones_oficiales": comunicaciones, "legislacion_jurisdiccion": legislacion,
        }
        notice_id = _create_notice(data, user)
        st.success(f"Aviso #{notice_id} creado en estado Borrador.")
        st.rerun()


def _render_dashboard() -> None:
    df = _read_notices()
    today = pd.Timestamp.today().normalize()
    review = pd.to_datetime(df["fecha_proxima_revision"], errors="coerce") if not df.empty else pd.Series(dtype="datetime64[ns]")
    a, b, c, d = st.columns(4)
    a.metric("Vigentes", int((df["estado"] == "Vigente").sum()) if not df.empty else 0)
    b.metric("Pendientes", int(df["estado"].isin(["Borrador", "En revisión", "Cambios solicitados", "Aprobado"]).sum()) if not df.empty else 0)
    c.metric("Revisión ≤ 30 días", int((review.notna() & (review <= today + pd.Timedelta(days=30))).sum()) if not df.empty else 0)
    d.metric("Total", len(df))
    if not df.empty:
        st.dataframe(df[["id", "codigo", "titulo", "version_actual", "estado", "responsable", "fecha_vigencia", "fecha_proxima_revision", "nivel_riesgo"]], use_container_width=True, hide_index=True)
    else:
        st.info("No hay avisos legales registrados.")


def _render_record(user: str) -> None:
    df = _read_notices()
    if df.empty:
        st.info("Primero crea un Aviso Legal.")
        return
    labels = {int(r.id): f"{r.codigo} · {r.titulo} · {r.estado}" for _, r in df.iterrows()}
    notice_id = st.selectbox("Aviso", list(labels), format_func=lambda x: labels[x])
    row = df[df["id"] == notice_id].iloc[0]
    with db_transaction() as conn:
        versions = pd.read_sql_query("SELECT * FROM legal_notice_versions WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
    version_id = int(versions.iloc[0]["id"]) if not versions.empty else None
    st.caption(f"{row['codigo']} · Versión {row['version_actual']} · Estado {row['estado']}")
    tabs = st.tabs(["Ficha", "Flujo", "Canales", "Archivos", "Versiones", "Auditoría"])
    with tabs[0]:
        st.json({"Empresa": row["nombre_comercial"], "Responsable": row["responsable"], "Revisor": row["revisor"], "Aprobador": row["aprobador"], "Riesgo": row["nivel_riesgo"], "Servicios": json.loads(row["servicios_json"] or "[]"), "Canales": json.loads(row["canales_json"] or "[]")})
        for label, field in [("Titular", "identificacion_titular"), ("Objeto", "objeto_aviso"), ("Condiciones", "condiciones_uso"), ("Limitación", "limitacion_responsabilidad"), ("Propiedad intelectual", "propiedad_intelectual"), ("Diseños del cliente", "uso_disenos_cliente"), ("Privacidad", "proteccion_datos"), ("Comunicaciones", "comunicaciones_oficiales"), ("Jurisdicción", "legislacion_jurisdiccion")]:
            with st.expander(label):
                st.write(row[field] or "Sin contenido")
    with tabs[1]:
        options = {"Borrador":["En revisión"], "En revisión":["Cambios solicitados","Aprobado","Rechazado"], "Cambios solicitados":["En revisión"], "Aprobado":["Vigente"], "Vigente":["Suspendido","Sustituido"], "Suspendido":["Vigente","Archivado"], "Sustituido":["Archivado"]}.get(str(row["estado"]), [])
        if options:
            target = st.selectbox("Nuevo estado", options)
            comment = st.text_area("Comentario o motivo")
            if st.button("Aplicar transición", type="primary"):
                try:
                    _change_state(notice_id, target, user, comment)
                    st.success(f"Estado actualizado a {target}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.info("Sin transiciones disponibles.")
    with tabs[2]:
        channels = json.loads(row["canales_json"] or "[]")
        with st.form("notice_channel"):
            channel = st.selectbox("Canal", channels or CHANNELS)
            location = st.text_input("URL o ubicación")
            state = st.selectbox("Estado", ["Pendiente", "Publicado", "Retirado"])
            evidence = st.text_input("Evidencia")
            observations = st.text_area("Observaciones")
            save = st.form_submit_button("Guardar canal")
        if save:
            with db_transaction() as conn:
                conn.execute("INSERT INTO legal_notice_channels (notice_id,version_id,canal,ubicacion,estado,fecha_publicacion,publicado_por,evidencia_referencia,observaciones) VALUES (?,?,?,?,?,CASE WHEN ?='Publicado' THEN CURRENT_TIMESTAMP ELSE NULL END,?,?,?)", (notice_id, version_id, channel, location, state, state, user, evidence, observations))
            _audit(user, "Actualizar canal", notice_id, version_id, after={"canal": channel, "estado": state})
            st.success("Canal guardado.")
        with db_transaction() as conn:
            cdf = pd.read_sql_query("SELECT * FROM legal_notice_channels WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if not cdf.empty:
            st.dataframe(cdf, use_container_width=True, hide_index=True)
    with tabs[3]:
        doc_type = st.selectbox("Tipo de documento", ["Aviso PDF", "Editable", "Evidencia", "Aprobación", "Registro mercantil", "Licencia", "Correo", "Acta", "Audio o video"])
        signed = st.checkbox("Firmado")
        files = st.file_uploader("Archivos", accept_multiple_files=True, type=sorted(ALLOWED))
        if st.button("Guardar archivos"):
            try:
                st.success(f"{_save_files(notice_id, version_id, files, doc_type, signed, user)} archivo(s) guardado(s).")
            except Exception as exc:
                st.error(str(exc))
        with db_transaction() as conn:
            fdf = pd.read_sql_query("SELECT id,nombre_archivo,extension,tamano_bytes,hash_sha256,tipo_documento,firmado,cargado_por,fecha_carga FROM legal_notice_files WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if not fdf.empty:
            st.dataframe(fdf, use_container_width=True, hide_index=True)
    with tabs[4]:
        if not versions.empty:
            st.dataframe(versions[["id","version","estado","autor","revisor","aprobador","fecha_creacion","fecha_aprobacion","fecha_publicacion","cambios_principales","vigente"]], use_container_width=True, hide_index=True)
    with tabs[5]:
        with db_transaction() as conn:
            adf = pd.read_sql_query("SELECT * FROM legal_notice_audit WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if not adf.empty:
            st.dataframe(adf, use_container_width=True, hide_index=True)
        else:
            st.info("Sin auditoría.")


def render_legal_notice(user: str = "Sistema") -> None:
    _ensure()
    st.title("📢 Aviso Legal")
    st.caption("Creación, aprobación, publicación, archivos, versiones y auditoría del Aviso Legal.")
    view = st.radio("Vista", ["Dashboard", "Nuevo aviso", "Expediente"], horizontal=True, key="legal_notice_view")
    st.divider()
    if view == "Dashboard":
        _render_dashboard()
    elif view == "Nuevo aviso":
        _render_new(user)
    else:
        _render_record(user)
