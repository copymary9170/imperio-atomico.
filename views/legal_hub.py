from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from views.areas_empresariales import render_area_empresarial
from views.manuales_sop import render_manuales_sop

ESTADOS_GENERALES = ["Borrador", "Pendiente", "Activo", "En revisión", "Cerrado", "Vencido", "Cancelado"]
TIPOS_CONTRATO = ["Cliente", "Proveedor", "Empleado", "Servicio", "Alquiler", "Licencia", "Otro"]
TIPOS_RECLAMO = ["Garantía", "Devolución", "Incumplimiento", "Daño", "Privacidad", "Otro"]
TIPOS_AUTORIZACION = ["Uso de imagen", "Tratamiento de datos", "Producción", "Entrega", "Uso de marca", "Otro"]
TIPOS_INCIDENTE = ["Reclamo formal", "Privacidad", "Contrato", "Garantía", "Fiscal", "Laboral", "Otro"]


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _ensure_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_contratos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                titulo TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Otro',
                contraparte TEXT,
                responsable TEXT,
                fecha_inicio TEXT,
                fecha_vencimiento TEXT,
                monto_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'Borrador',
                documento_referencia TEXT,
                observaciones TEXT,
                created_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_reclamos_garantias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT NOT NULL DEFAULT 'Garantía',
                cliente TEXT,
                venta_id TEXT,
                descripcion TEXT NOT NULL,
                responsable TEXT,
                fecha_limite TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                solucion TEXT,
                documento_referencia TEXT,
                created_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_politicas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                titulo TEXT NOT NULL,
                categoria TEXT NOT NULL DEFAULT 'Política',
                version TEXT NOT NULL DEFAULT '1.0',
                estado TEXT NOT NULL DEFAULT 'Borrador',
                responsable TEXT,
                fecha_vigencia TEXT,
                contenido TEXT,
                documento_referencia TEXT,
                created_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_autorizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT NOT NULL DEFAULT 'Otro',
                persona_entidad TEXT NOT NULL,
                descripcion TEXT,
                responsable TEXT,
                fecha_vencimiento TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                evidencia TEXT,
                created_by TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_incidentes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                tipo TEXT NOT NULL DEFAULT 'Otro',
                asunto TEXT NOT NULL,
                descripcion TEXT,
                responsable TEXT,
                prioridad TEXT NOT NULL DEFAULT 'Media',
                estado TEXT NOT NULL DEFAULT 'Abierto',
                fecha_limite TEXT,
                accion_tomada TEXT,
                documento_referencia TEXT,
                created_by TEXT
            )
            """
        )


def _read_table(table_name: str) -> pd.DataFrame:
    _ensure_tables()
    with db_transaction() as conn:
        if not _table_exists(conn, table_name):
            return pd.DataFrame()
        return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)


def _insert(table_name: str, data: dict) -> int:
    _ensure_tables()
    with db_transaction() as conn:
        cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        payload = {k: v for k, v in data.items() if k in cols}
        keys = list(payload.keys())
        cur = conn.execute(
            f"INSERT INTO {table_name} ({','.join(keys)}) VALUES ({','.join(['?'] * len(keys))})",
            [payload[k] for k in keys],
        )
        return int(cur.lastrowid)


def _render_resumen(usuario: str) -> None:
    st.subheader("📊 Resumen legal")
    contratos = _read_table("legal_contratos")
    reclamos = _read_table("legal_reclamos_garantias")
    autorizaciones = _read_table("legal_autorizaciones")
    incidentes = _read_table("legal_incidentes")

    hoy = pd.Timestamp.today().normalize()
    contratos_vencen = pd.DataFrame()
    if not contratos.empty:
        fechas = pd.to_datetime(contratos["fecha_vencimiento"], errors="coerce")
        contratos_vencen = contratos[fechas.notna() & (fechas <= hoy + pd.Timedelta(days=30)) & ~contratos["estado"].isin(["Cerrado", "Cancelado"])]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contratos", len(contratos))
    c2.metric("Contratos por vencer", len(contratos_vencen))
    c3.metric("Reclamos abiertos", len(reclamos[~reclamos["estado"].isin(["Cerrado", "Cancelado"])]) if not reclamos.empty else 0)
    c4.metric("Incidentes abiertos", len(incidentes[~incidentes["estado"].isin(["Cerrado", "Cancelado"])]) if not incidentes.empty else 0)

    if not contratos_vencen.empty:
        st.markdown("#### Contratos próximos a vencer")
        st.dataframe(contratos_vencen, use_container_width=True, hide_index=True)
    if not autorizaciones.empty:
        st.markdown("#### Autorizaciones recientes")
        st.dataframe(autorizaciones.head(10), use_container_width=True, hide_index=True)


def _render_contratos(usuario: str) -> None:
    st.subheader("📄 Contratos")
    with st.form("legal_contrato_form"):
        a, b, c = st.columns(3)
        titulo = a.text_input("Título")
        tipo = b.selectbox("Tipo", TIPOS_CONTRATO)
        contraparte = c.text_input("Contraparte")
        d, e, f = st.columns(3)
        responsable = d.text_input("Responsable", value=usuario)
        fecha_inicio = e.date_input("Fecha inicio", value=date.today())
        fecha_vencimiento = f.date_input("Fecha vencimiento", value=date.today() + timedelta(days=365))
        g, h = st.columns(2)
        monto = g.number_input("Monto USD", min_value=0.0, value=0.0, step=1.0)
        estado = h.selectbox("Estado", ESTADOS_GENERALES, index=2)
        documento = st.text_input("Documento / referencia / link")
        observaciones = st.text_area("Observaciones")
        guardar = st.form_submit_button("Guardar contrato", type="primary")
    if guardar:
        if not titulo.strip():
            st.error("El título es obligatorio.")
        else:
            cid = _insert("legal_contratos", {"titulo": titulo.strip(), "tipo": tipo, "contraparte": contraparte.strip(), "responsable": responsable.strip() or usuario, "fecha_inicio": fecha_inicio.isoformat(), "fecha_vencimiento": fecha_vencimiento.isoformat(), "monto_usd": float(monto), "estado": estado, "documento_referencia": documento.strip(), "observaciones": observaciones.strip(), "created_by": usuario})
            st.success(f"Contrato #{cid} guardado.")
            st.rerun()
    df = _read_table("legal_contratos")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay contratos registrados.")


def _render_reclamos(usuario: str) -> None:
    st.subheader("🛡️ Garantías / reclamos")
    with st.form("legal_reclamo_form"):
        a, b, c = st.columns(3)
        tipo = a.selectbox("Tipo", TIPOS_RECLAMO)
        cliente = b.text_input("Cliente")
        venta_id = c.text_input("Venta / referencia")
        descripcion = st.text_area("Descripción")
        d, e, f = st.columns(3)
        responsable = d.text_input("Responsable", value=usuario, key="legal_recl_resp")
        fecha_limite = e.date_input("Fecha límite", value=date.today() + timedelta(days=7))
        estado = f.selectbox("Estado", ESTADOS_GENERALES, index=1, key="legal_recl_estado")
        solucion = st.text_area("Solución / seguimiento")
        documento = st.text_input("Documento / evidencia")
        guardar = st.form_submit_button("Guardar reclamo", type="primary")
    if guardar:
        if not descripcion.strip():
            st.error("La descripción es obligatoria.")
        else:
            rid = _insert("legal_reclamos_garantias", {"tipo": tipo, "cliente": cliente.strip(), "venta_id": venta_id.strip(), "descripcion": descripcion.strip(), "responsable": responsable.strip() or usuario, "fecha_limite": fecha_limite.isoformat(), "estado": estado, "solucion": solucion.strip(), "documento_referencia": documento.strip(), "created_by": usuario})
            st.success(f"Reclamo #{rid} guardado.")
            st.rerun()
    df = _read_table("legal_reclamos_garantias")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay reclamos registrados.")


def _render_politicas(usuario: str) -> None:
    st.subheader("📜 Términos, políticas y privacidad")
    with st.form("legal_politica_form"):
        a, b, c = st.columns(3)
        titulo = a.text_input("Título")
        categoria = b.selectbox("Categoría", ["Términos", "Garantías", "Privacidad", "Cookies", "Política interna", "Otro"])
        version = c.text_input("Versión", value="1.0")
        d, e, f = st.columns(3)
        estado = d.selectbox("Estado", ESTADOS_GENERALES, index=0, key="legal_pol_estado")
        responsable = e.text_input("Responsable", value=usuario, key="legal_pol_resp")
        fecha_vigencia = f.date_input("Fecha vigencia", value=date.today())
        contenido = st.text_area("Contenido / resumen")
        documento = st.text_input("Documento / referencia")
        guardar = st.form_submit_button("Guardar política", type="primary")
    if guardar:
        if not titulo.strip():
            st.error("El título es obligatorio.")
        else:
            pid = _insert("legal_politicas", {"titulo": titulo.strip(), "categoria": categoria, "version": version.strip() or "1.0", "estado": estado, "responsable": responsable.strip() or usuario, "fecha_vigencia": fecha_vigencia.isoformat(), "contenido": contenido.strip(), "documento_referencia": documento.strip(), "created_by": usuario})
            st.success(f"Política #{pid} guardada.")
            st.rerun()
    df = _read_table("legal_politicas")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay políticas registradas.")


def _render_autorizaciones(usuario: str) -> None:
    st.subheader("✅ Autorizaciones")
    with st.form("legal_autorizacion_form"):
        a, b, c = st.columns(3)
        tipo = a.selectbox("Tipo", TIPOS_AUTORIZACION)
        persona = b.text_input("Persona / entidad")
        responsable = c.text_input("Responsable", value=usuario, key="legal_aut_resp")
        descripcion = st.text_area("Descripción")
        d, e = st.columns(2)
        fecha_vencimiento = d.date_input("Fecha vencimiento", value=date.today() + timedelta(days=365))
        estado = e.selectbox("Estado", ESTADOS_GENERALES, index=1, key="legal_aut_estado")
        evidencia = st.text_input("Evidencia / referencia")
        guardar = st.form_submit_button("Guardar autorización", type="primary")
    if guardar:
        if not persona.strip():
            st.error("Persona / entidad es obligatorio.")
        else:
            aid = _insert("legal_autorizaciones", {"tipo": tipo, "persona_entidad": persona.strip(), "descripcion": descripcion.strip(), "responsable": responsable.strip() or usuario, "fecha_vencimiento": fecha_vencimiento.isoformat(), "estado": estado, "evidencia": evidencia.strip(), "created_by": usuario})
            st.success(f"Autorización #{aid} guardada.")
            st.rerun()
    df = _read_table("legal_autorizaciones")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay autorizaciones registradas.")


def _render_incidentes(usuario: str) -> None:
    st.subheader("⚠️ Incidentes legales")
    with st.form("legal_incidente_form"):
        a, b, c = st.columns(3)
        tipo = a.selectbox("Tipo", TIPOS_INCIDENTE)
        asunto = b.text_input("Asunto")
        prioridad = c.selectbox("Prioridad", ["Baja", "Media", "Alta", "Crítica"], index=1)
        descripcion = st.text_area("Descripción")
        d, e, f = st.columns(3)
        responsable = d.text_input("Responsable", value=usuario, key="legal_inc_resp")
        estado = e.selectbox("Estado", ["Abierto", "En seguimiento", "Cerrado", "Cancelado"], key="legal_inc_estado")
        fecha_limite = f.date_input("Fecha límite", value=date.today() + timedelta(days=7))
        accion = st.text_area("Acción tomada / seguimiento")
        documento = st.text_input("Documento / evidencia", key="legal_inc_doc")
        guardar = st.form_submit_button("Guardar incidente", type="primary")
    if guardar:
        if not asunto.strip():
            st.error("El asunto es obligatorio.")
        else:
            iid = _insert("legal_incidentes", {"tipo": tipo, "asunto": asunto.strip(), "descripcion": descripcion.strip(), "responsable": responsable.strip() or usuario, "prioridad": prioridad, "estado": estado, "fecha_limite": fecha_limite.isoformat(), "accion_tomada": accion.strip(), "documento_referencia": documento.strip(), "created_by": usuario})
            st.success(f"Incidente #{iid} guardado.")
            st.rerun()
    df = _read_table("legal_incidentes")
    st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.info("No hay incidentes registrados.")


def _render_alertas(usuario: str) -> None:
    st.subheader("🚨 Alertas legales")
    hoy = pd.Timestamp.today().normalize()
    alertas = []
    datasets = {}
    checks = [
        ("Contratos", _read_table("legal_contratos"), "fecha_vencimiento", "estado"),
        ("Reclamos", _read_table("legal_reclamos_garantias"), "fecha_limite", "estado"),
        ("Autorizaciones", _read_table("legal_autorizaciones"), "fecha_vencimiento", "estado"),
        ("Incidentes", _read_table("legal_incidentes"), "fecha_limite", "estado"),
    ]
    for nombre, df, fecha_col, estado_col in checks:
        if df.empty:
            continue
        fechas = pd.to_datetime(df[fecha_col], errors="coerce")
        abiertos = ~df[estado_col].isin(["Cerrado", "Cancelado"])
        vencidos = df[fechas.notna() & (fechas < hoy) & abiertos]
        por_vencer = df[fechas.notna() & (fechas >= hoy) & (fechas <= hoy + pd.Timedelta(days=30)) & abiertos]
        sin_resp = df[df.get("responsable", pd.Series(dtype=str)).fillna("").astype(str).str.strip().eq("")] if "responsable" in df.columns else pd.DataFrame()
        datasets[f"{nombre} vencidos"] = vencidos
        datasets[f"{nombre} por vencer"] = por_vencer
        if not vencidos.empty:
            alertas.append({"nivel": "Alta", "alerta": f"{nombre} vencidos", "cantidad": len(vencidos), "acción": "Renovar, cerrar o actualizar estado."})
        if not por_vencer.empty:
            alertas.append({"nivel": "Media", "alerta": f"{nombre} por vencer", "cantidad": len(por_vencer), "acción": "Revisar antes del vencimiento."})
        if not sin_resp.empty:
            alertas.append({"nivel": "Media", "alerta": f"{nombre} sin responsable", "cantidad": len(sin_resp), "acción": "Asignar responsable legal."})
            datasets[f"{nombre} sin responsable"] = sin_resp

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas", len(alertas))
    c2.metric("Contratos", len(_read_table("legal_contratos")))
    c3.metric("Reclamos abiertos", len(_read_table("legal_reclamos_garantias")))
    c4.metric("Incidentes", len(_read_table("legal_incidentes")))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas legales críticas.")
    datasets = {k: v for k, v in datasets.items() if not v.empty}
    if datasets:
        tabs = st.tabs(list(datasets.keys()))
        for tab, (nombre, df) in zip(tabs, datasets.items()):
            with tab:
                st.dataframe(df, use_container_width=True, hide_index=True)


def render_legal_hub(usuario: str = "Sistema") -> None:
    _ensure_tables()
    st.title("⚖️ Legal")
    st.caption("Contratos, garantías, reclamos, privacidad, autorizaciones, políticas, incidentes, documentos y alertas legales.")

    secciones = {
        "📊 Resumen legal": lambda: _render_resumen(usuario),
        "📄 Contratos": lambda: _render_contratos(usuario),
        "🛡️ Garantías / reclamos": lambda: _render_reclamos(usuario),
        "🔐 Privacidad / políticas": lambda: _render_politicas(usuario),
        "✅ Autorizaciones": lambda: _render_autorizaciones(usuario),
        "⚠️ Incidentes legales": lambda: _render_incidentes(usuario),
        "📁 Documentos legales": lambda: render_area_empresarial("Legal", usuario, show_title=False),
        "📘 SOP legales": lambda: render_manuales_sop(usuario),
        "🚨 Alertas legales": lambda: _render_alertas(usuario),
    }
    seccion = st.radio("Sección legal", list(secciones.keys()), horizontal=True, key="legal_seccion_activa")
    st.divider()
    secciones[seccion]()
