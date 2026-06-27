from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction

NOTICE_STATES = [
    "Borrador",
    "En revisión",
    "Cambios solicitados",
    "Rechazado",
    "Aprobado",
    "Vigente",
    "Suspendido",
    "Sustituido",
    "Archivado",
]
CHANNELS = ["Web", "WhatsApp", "Instagram", "Cotización", "Factura", "Catálogo", "Atención física", "Correo"]
SERVICES = [
    "Impresiones", "Copias", "Papelería", "Papelería creativa", "Sublimación",
    "Diseño básico", "Venta de impresoras", "Tintas", "Tóner", "Cartuchos",
    "Equipos tecnológicos", "Material escolar", "Material de oficina",
    "Consumibles", "Servicios administrativos", "Servicios digitales", "Comercio electrónico",
]
ALLOWED_EXTENSIONS = {"pdf", "docx", "odt", "png", "jpg", "jpeg", "eml", "msg", "mp3", "mp4", "wav"}
MAX_FILE_MB = 20


def _ensure_schema() -> None:
    with db_transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS legal_notice (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                titulo TEXT NOT NULL,
                tipo_aviso TEXT NOT NULL DEFAULT 'General',
                version_actual TEXT NOT NULL DEFAULT '1.0',
                estado TEXT NOT NULL DEFAULT 'Borrador',
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_vigencia TEXT,
                fecha_proxima_revision TEXT,
                responsable TEXT NOT NULL,
                revisor TEXT,
                aprobador TEXT,
                nivel_riesgo TEXT NOT NULL DEFAULT 'Medio',
                observaciones_internas TEXT,
                nombre_comercial TEXT NOT NULL,
                razon_social TEXT,
                rif TEXT,
                registro_mercantil TEXT,
                direccion_fiscal TEXT,
                direccion_atencion TEXT NOT NULL,
                telefono_oficial TEXT,
                whatsapp_oficial TEXT,
                correo_oficial TEXT,
                horario_atencion TEXT,
                pais TEXT NOT NULL DEFAULT 'Venezuela',
                estado_provincia TEXT,
                ciudad TEXT,
                servicios_json TEXT,
                canales_json TEXT,
                jurisdiccion TEXT NOT NULL DEFAULT 'Venezuela',
                idioma TEXT NOT NULL DEFAULT 'Español',
                publico_objetivo TEXT,
                relaciones_politicas TEXT,
                encabezado_legal TEXT,
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
                publicado_en TEXT,
                hash_vigente TEXT
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
                fecha_revision TEXT,
                fecha_aprobacion TEXT,
                fecha_publicacion TEXT,
                cambios_principales TEXT,
                version_anterior_id INTEGER,
                vigente INTEGER NOT NULL DEFAULT 0,
                UNIQUE(notice_id, version),
                FOREIGN KEY(notice_id) REFERENCES legal_notice(id)
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
                observaciones TEXT,
                UNIQUE(notice_id, canal, version_id),
                FOREIGN KEY(notice_id) REFERENCES legal_notice(id),
                FOREIGN KEY(version_id) REFERENCES legal_notice_versions(id)
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
                versionado INTEGER NOT NULL DEFAULT 1,
                cargado_por TEXT NOT NULL,
                fecha_carga TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(notice_id) REFERENCES legal_notice(id),
                FOREIGN KEY(version_id) REFERENCES legal_notice_versions(id)
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
                resultado TEXT NOT NULL DEFAULT 'Exitoso',
                ip TEXT,
                equipo TEXT,
                navegador TEXT
            );
            CREATE TABLE IF NOT EXISTS legal_notice_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notice_id INTEGER NOT NULL,
                version_id INTEGER,
                usuario TEXT NOT NULL,
                comentario TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Comentario',
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def _next_code() -> str:
    year = date.today().year
    with db_transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM legal_notice WHERE codigo LIKE ?", (f"AL-{year}-%",)).fetchone()
    return f"AL-{year}-{int(row['total'] or 0) + 1:04d}"


def _audit(user: str, action: str, notice_id: int | None, version_id: int | None = None, before: dict | None = None, after: dict | None = None, comment: str = "", result: str = "Exitoso") -> None:
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO legal_notice_audit
            (usuario, accion, notice_id, version_id, antes_json, despues_json, comentario, resultado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user, action, notice_id, version_id, json.dumps(before or {}, ensure_ascii=False, default=str), json.dumps(after or {}, ensure_ascii=False, default=str), comment, result),
        )


def _notice_df() -> pd.DataFrame:
    _ensure_schema()
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM legal_notice ORDER BY id DESC", conn)


def _version_df(notice_id: int) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query("SELECT * FROM legal_notice_versions WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))


def _payload_from_form(values: dict) -> dict:
    values = dict(values)
    values["servicios_json"] = json.dumps(values.pop("servicios", []), ensure_ascii=False)
    values["canales_json"] = json.dumps(values.pop("canales", []), ensure_ascii=False)
    return values


def _content_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _create_notice(values: dict, user: str) -> int:
    payload = _payload_from_form(values)
    payload["codigo"] = _next_code()
    payload["creado_por"] = user
    payload["actualizado_por"] = user
    payload["actualizado_en"] = pd.Timestamp.now().isoformat()
    with db_transaction() as conn:
        keys = list(payload)
        cur = conn.execute(f"INSERT INTO legal_notice ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", [payload[k] for k in keys])
        notice_id = int(cur.lastrowid)
        version_payload = {k: payload.get(k) for k in payload if k not in {"hash_vigente", "publicado_en"}}
        version_hash = _content_hash(version_payload)
        vcur = conn.execute(
            """INSERT INTO legal_notice_versions
            (notice_id, version, estado, contenido_json, hash_contenido, autor, cambios_principales)
            VALUES (?, '1.0', 'Borrador', ?, ?, ?, 'Creación inicial')""",
            (notice_id, json.dumps(version_payload, ensure_ascii=False, default=str), version_hash, user),
        )
        version_id = int(vcur.lastrowid)
    _audit(user, "Crear aviso legal", notice_id, version_id, after=payload)
    return notice_id


def _change_state(notice_id: int, new_state: str, user: str, comment: str) -> None:
    with db_transaction() as conn:
        row = conn.execute("SELECT * FROM legal_notice WHERE id=?", (notice_id,)).fetchone()
        before = dict(row) if row else {}
        if not row:
            raise ValueError("Aviso legal no encontrado.")
        current = str(row["estado"])
        allowed = {
            "Borrador": {"En revisión"},
            "En revisión": {"Cambios solicitados", "Aprobado", "Rechazado"},
            "Cambios solicitados": {"En revisión"},
            "Aprobado": {"Vigente"},
            "Vigente": {"Suspendido", "Sustituido"},
            "Suspendido": {"Vigente", "Archivado"},
            "Sustituido": {"Archivado"},
        }
        if new_state not in allowed.get(current, set()):
            raise ValueError(f"Transición no permitida: {current} → {new_state}.")
        if new_state in {"Cambios solicitados", "Rechazado", "Suspendido", "Archivado"} and not comment.strip():
            raise ValueError("Debes indicar el motivo.")
        published_at = pd.Timestamp.now().isoformat() if new_state == "Vigente" else row["publicado_en"]
        conn.execute("UPDATE legal_notice SET estado=?, actualizado_por=?, actualizado_en=?, publicado_en=? WHERE id=?", (new_state, user, pd.Timestamp.now().isoformat(), published_at, notice_id))
        version = conn.execute("SELECT * FROM legal_notice_versions WHERE notice_id=? ORDER BY id DESC LIMIT 1", (notice_id,)).fetchone()
        version_id = int(version["id"]) if version else None
        conn.execute("UPDATE legal_notice_versions SET estado=?, fecha_revision=CASE WHEN ?='En revisión' THEN CURRENT_TIMESTAMP ELSE fecha_revision END, fecha_aprobacion=CASE WHEN ?='Aprobado' THEN CURRENT_TIMESTAMP ELSE fecha_aprobacion END, fecha_publicacion=CASE WHEN ?='Vigente' THEN CURRENT_TIMESTAMP ELSE fecha_publicacion END, revisor=CASE WHEN ? IN ('En revisión','Cambios solicitados') THEN ? ELSE revisor END, aprobador=CASE WHEN ?='Aprobado' THEN ? ELSE aprobador END, vigente=CASE WHEN ?='Vigente' THEN 1 ELSE vigente END WHERE id=?", (new_state, new_state, new_state, new_state, new_state, user, new_state, user, new_state, version_id))
        if new_state == "Vigente":
            conn.execute("UPDATE legal_notice_versions SET vigente=0 WHERE notice_id=? AND id<>?", (notice_id, version_id))
    _audit(user, f"Cambiar estado a {new_state}", notice_id, version_id, before=before, after={"estado": new_state}, comment=comment)


def _upload_files(notice_id: int, version_id: int | None, files, document_type: str, signed: bool, user: str) -> int:
    root = Path("data/legal_notice_files") / str(notice_id)
    root.mkdir(parents=True, exist_ok=True)
    saved = 0
    for item in files or []:
        extension = item.name.rsplit(".", 1)[-1].lower() if "." in item.name else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Formato no permitido: {item.name}")
        content = item.getvalue()
        if len(content) > MAX_FILE_MB * 1024 * 1024:
            raise ValueError(f"{item.name} supera {MAX_FILE_MB} MB.")
        digest = hashlib.sha256(content).hexdigest()
        safe_name = f"{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}_{digest[:10]}_{Path(item.name).name}"
        target = root / safe_name
        target.write_bytes(content)
        with db_transaction() as conn:
            existing = conn.execute("SELECT id FROM legal_notice_files WHERE hash_sha256=? AND notice_id=?", (digest, notice_id)).fetchone()
            if existing:
                target.unlink(missing_ok=True)
                continue
            conn.execute(
                """INSERT INTO legal_notice_files
                (notice_id, version_id, nombre_archivo, extension, tamano_bytes, hash_sha256, ruta, tipo_documento, firmado, cargado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (notice_id, version_id, item.name, extension, len(content), digest, str(target), document_type, int(signed), user),
            )
        saved += 1
        _audit(user, "Cargar archivo", notice_id, version_id, after={"archivo": item.name, "hash": digest, "tipo": document_type})
    return saved


def _render_form(user: str) -> None:
    st.subheader("Nuevo Aviso Legal")
    with st.form("legal_notice_create"):
        tab1, tab2, tab3, tab4 = st.tabs(["Datos generales", "Empresa", "Alcance", "Contenido"])
        with tab1:
            c1, c2, c3 = st.columns(3)
            titulo = c1.text_input("Título *", value="Aviso Legal")
            tipo_aviso = c2.selectbox("Tipo de aviso *", ["General", "Ecommerce", "Atención física", "Redes sociales"])
            nivel_riesgo = c3.selectbox("Nivel de riesgo *", ["Bajo", "Medio", "Alto", "Crítico"], index=1)
            c4, c5, c6 = st.columns(3)
            responsable = c4.text_input("Responsable *", value=user)
            revisor = c5.text_input("Revisor legal")
            aprobador = c6.text_input("Aprobador")
            fecha_vigencia = st.date_input("Fecha de vigencia", value=date.today())
            fecha_proxima_revision = st.date_input("Próxima revisión", value=date.today() + timedelta(days=365))
            observaciones_internas = st.text_area("Observaciones internas")
        with tab2:
            nombre_comercial = st.text_input("Nombre comercial *", value="Copy Mary")
            razon_social = st.text_input("Razón social")
            c1, c2 = st.columns(2)
            rif = c1.text_input("RIF / ID fiscal")
            registro_mercantil = c2.text_input("Registro mercantil")
            direccion_fiscal = st.text_area("Dirección fiscal")
            direccion_atencion = st.text_area("Dirección de atención *", value="Edificio 26, Primera Etapa")
            c3, c4, c5 = st.columns(3)
            telefono_oficial = c3.text_input("Teléfono oficial")
            whatsapp_oficial = c4.text_input("WhatsApp oficial")
            correo_oficial = c5.text_input("Correo oficial")
            horario_atencion = st.text_input("Horario de atención")
            c6, c7, c8 = st.columns(3)
            pais = c6.text_input("País *", value="Venezuela")
            estado_provincia = c7.text_input("Estado / Provincia")
            ciudad = c8.text_input("Ciudad")
        with tab3:
            servicios = st.multiselect("Servicios cubiertos *", SERVICES)
            canales = st.multiselect("Canales de publicación *", CHANNELS)
            jurisdiccion = st.text_input("Jurisdicción aplicable *", value="Venezuela")
            idioma = st.selectbox("Idioma oficial *", ["Español", "Inglés", "Portugués"])
            publico_objetivo = st.text_input("Público objetivo", value="Clientes particulares, empresas y organismos")
            relaciones_politicas = st.multiselect("Políticas relacionadas", ["Términos y Condiciones", "Privacidad", "Cookies", "Garantías", "Devoluciones", "Propiedad Intelectual"])
        with tab4:
            encabezado_legal = st.text_area("Encabezado legal *", value="Aviso Legal")
            identificacion_titular = st.text_area("Identificación del titular *")
            objeto_aviso = st.text_area("Objeto del aviso *")
            condiciones_uso = st.text_area("Condiciones de uso de canales *")
            limitacion_responsabilidad = st.text_area("Limitación de responsabilidad *")
            propiedad_intelectual = st.text_area("Propiedad intelectual *")
            uso_disenos_cliente = st.text_area("Uso de diseños enviados por clientes *")
            proteccion_datos = st.text_area("Protección de datos *")
            comunicaciones_oficiales = st.text_area("Comunicaciones oficiales *")
            legislacion_jurisdiccion = st.text_area("Legislación y jurisdicción *")
        submitted = st.form_submit_button("Crear Aviso Legal", type="primary")
    if submitted:
        required = [titulo, responsable, nombre_comercial, direccion_atencion, pais, jurisdiccion, encabezado_legal, identificacion_titular, objeto_aviso, condiciones_uso, limitacion_responsabilidad, propiedad_intelectual, uso_disenos_cliente, proteccion_datos, comunicaciones_oficiales, legislacion_jurisdiccion]
        if not all(str(v).strip() for v in required) or not servicios or not canales:
            st.error("Completa todos los campos obligatorios y selecciona servicios y canales.")
            return
        notice_id = _create_notice(locals(), user)
        st.success(f"Aviso legal #{notice_id} creado en estado Borrador.")
        st.rerun()


def _render_dashboard() -> None:
    df = _notice_df()
    today = pd.Timestamp.today().normalize()
    active = int((df["estado"] == "Vigente").sum()) if not df.empty else 0
    pending = int(df["estado"].isin(["Borrador", "En revisión", "Cambios solicitados", "Aprobado"]).sum()) if not df.empty else 0
    due = 0
    if not df.empty:
        review_dates = pd.to_datetime(df["fecha_proxima_revision"], errors="coerce")
        due = int((review_dates.notna() & (review_dates <= today + pd.Timedelta(days=30))).sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avisos vigentes", active)
    c2.metric("Pendientes", pending)
    c3.metric("Revisión ≤ 30 días", due)
    c4.metric("Total de versiones", int(df.shape[0]))
    if df.empty:
        st.info("No hay avisos legales registrados.")
    else:
        st.dataframe(df[["id", "codigo", "titulo", "version_actual", "estado", "responsable", "fecha_vigencia", "fecha_proxima_revision", "nivel_riesgo"]], use_container_width=True, hide_index=True)


def _render_record(user: str) -> None:
    df = _notice_df()
    if df.empty:
        st.info("Primero crea un Aviso Legal.")
        return
    labels = {int(r.id): f"{r.codigo} · {r.titulo} · {r.estado}" for _, r in df.iterrows()}
    notice_id = st.selectbox("Aviso legal", list(labels), format_func=lambda x: labels[x])
    row = df[df["id"] == notice_id].iloc[0]
    versions = _version_df(notice_id)
    current_version_id = int(versions.iloc[0]["id"]) if not versions.empty else None
    st.caption(f"Código {row['codigo']} · Versión {row['version_actual']} · Estado {row['estado']}")
    tabs = st.tabs(["Ficha", "Flujo", "Canales", "Archivos", "Versiones", "Auditoría"])
    with tabs[0]:
        st.json({
            "Empresa": row["nombre_comercial"], "Responsable": row["responsable"], "Revisor": row["revisor"],
            "Aprobador": row["aprobador"], "Riesgo": row["nivel_riesgo"], "Jurisdicción": row["jurisdiccion"],
            "Servicios": json.loads(row["servicios_json"] or "[]"), "Canales": json.loads(row["canales_json"] or "[]"),
        })
        st.markdown("### Contenido vigente o en preparación")
        for label, key in [
            ("Identificación del titular", "identificacion_titular"), ("Objeto", "objeto_aviso"),
            ("Condiciones de uso", "condiciones_uso"), ("Limitación de responsabilidad", "limitacion_responsabilidad"),
            ("Propiedad intelectual", "propiedad_intelectual"), ("Diseños del cliente", "uso_disenos_cliente"),
            ("Protección de datos", "proteccion_datos"), ("Comunicaciones oficiales", "comunicaciones_oficiales"),
            ("Jurisdicción", "legislacion_jurisdiccion"),
        ]:
            with st.expander(label):
                st.write(row[key] or "Sin contenido")
    with tabs[1]:
        target_options = {
            "Borrador": ["En revisión"], "En revisión": ["Cambios solicitados", "Aprobado", "Rechazado"],
            "Cambios solicitados": ["En revisión"], "Aprobado": ["Vigente"], "Vigente": ["Suspendido", "Sustituido"],
            "Suspendido": ["Vigente", "Archivado"], "Sustituido": ["Archivado"],
        }.get(str(row["estado"]), [])
        if not target_options:
            st.info("Este estado no permite transiciones adicionales.")
        else:
            target = st.selectbox("Nuevo estado", target_options)
            comment = st.text_area("Comentario o motivo")
            if st.button("Aplicar transición", type="primary"):
                try:
                    _change_state(notice_id, target, user, comment)
                    st.success(f"Estado actualizado a {target}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    with tabs[2]:
        channels = json.loads(row["canales_json"] or "[]")
        with st.form("notice_channel_form"):
            channel = st.selectbox("Canal", channels or CHANNELS)
            location = st.text_input("URL o ubicación")
            channel_state = st.selectbox("Estado", ["Pendiente", "Publicado", "Retirado"])
            evidence = st.text_input("Referencia de evidencia")
            observations = st.text_area("Observaciones")
            save_channel = st.form_submit_button("Guardar canal")
        if save_channel:
            with db_transaction() as conn:
                conn.execute("INSERT OR REPLACE INTO legal_notice_channels (notice_id, version_id, canal, ubicacion, estado, fecha_publicacion, publicado_por, evidencia_referencia, observaciones) VALUES (?, ?, ?, ?, ?, CASE WHEN ?='Publicado' THEN CURRENT_TIMESTAMP ELSE NULL END, ?, ?, ?)", (notice_id, current_version_id, channel, location, channel_state, channel_state, user, evidence, observations))
            _audit(user, "Actualizar canal", notice_id, current_version_id, after={"canal": channel, "estado": channel_state, "ubicacion": location})
            st.success("Canal actualizado.")
        with db_transaction() as conn:
            channel_df = pd.read_sql_query("SELECT * FROM legal_notice_channels WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if not channel_df.empty:
            st.dataframe(channel_df, use_container_width=True, hide_index=True)
    with tabs[3]:
        doc_type = st.selectbox("Tipo de documento", ["Aviso legal PDF", "Editable", "Evidencia de publicación", "Aprobación interna", "Registro mercantil", "Licencia o permiso", "Correo", "Acta", "Audio o video"])
        signed = st.checkbox("Documento firmado")
        files = st.file_uploader("Cargar archivos", accept_multiple_files=True, type=sorted(ALLOWED_EXTENSIONS))
        if st.button("Guardar archivos"):
            try:
                count = _upload_files(notice_id, current_version_id, files, doc_type, signed, user)
                st.success(f"{count} archivo(s) guardado(s).")
            except Exception as exc:
                st.error(str(exc))
        with db_transaction() as conn:
            files_df = pd.read_sql_query("SELECT id, nombre_archivo, extension, tamano_bytes, hash_sha256, tipo_documento, firmado, cargado_por, fecha_carga FROM legal_notice_files WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if not files_df.empty:
            st.dataframe(files_df, use_container_width=True, hide_index=True)
    with tabs[4]:
        if not versions.empty:
            st.dataframe(versions[["id", "version", "estado", "autor", "revisor", "aprobador", "fecha_creacion", "fecha_aprobacion", "fecha_publicacion", "cambios_principales", "vigente"]], use_container_width=True, hide_index=True)
            ids = versions["id"].astype(int).tolist()
            if len(ids) >= 2:
                a, b = st.columns(2)
                left = a.selectbox("Versión A", ids, format_func=lambda x: f"ID {x}")
                right = b.selectbox("Versión B", ids, index=1, format_func=lambda x: f"ID {x}")
                if st.button("Comparar versiones"):
                    left_row = versions[versions["id"] == left].iloc[0]
                    right_row = versions[versions["id"] == right].iloc[0]
                    left_data = json.loads(left_row["contenido_json"])
                    right_data = json.loads(right_row["contenido_json"])
                    diff = []
                    for key in sorted(set(left_data) | set(right_data)):
                        if left_data.get(key) != right_data.get(key):
                            diff.append({"Campo": key, "Versión A": left_data.get(key), "Versión B": right_data.get(key)})
                    st.dataframe(pd.DataFrame(diff), use_container_width=True, hide_index=True)
    with tabs[5]:
        with db_transaction() as conn:
            audit_df = pd.read_sql_query("SELECT * FROM legal_notice_audit WHERE notice_id=? ORDER BY id DESC", conn, params=(notice_id,))
        if audit_df.empty:
            st.info("Sin eventos de auditoría.")
        else:
            st.dataframe(audit_df, use_container_width=True, hide_index=True)


def render_legal_notice(user: str = "Sistema") -> None:
    _ensure_schema()
    st.title("📢 Aviso Legal")
    st.caption("Gestión empresarial del Aviso Legal: creación, aprobación, publicación, canales, archivos, versiones y auditoría.")
    page = st.radio("Vista", ["Dashboard", "Nuevo aviso", "Expediente"], horizontal=True, key="legal_notice_view")
    st.divider()
    if page == "Dashboard":
        _render_dashboard()
    elif page == "Nuevo aviso":
        _render_form(user)
    else:
        _render_record(user)
