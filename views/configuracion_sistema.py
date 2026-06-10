from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import get_current_config, DEFAULT_CONFIG
from services.backup_service import get_backup_status, create_backup


APP_ROOT = Path(__file__).resolve().parents[1]


def _secret_exists(name: str) -> bool:
    try:
        return bool(str(st.secrets.get(name, "")).strip())
    except Exception:
        return False


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _count_table(table: str) -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0
            row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return 0


def _safe_config() -> dict:
    try:
        return get_current_config()
    except Exception:
        return DEFAULT_CONFIG


def _render_estado_general() -> None:
    st.subheader("Estado general")
    backup = get_backup_status()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Base de datos", "Detectada" if backup.get("db_exists") else "No detectada")
    c2.metric("Respaldos locales", backup.get("total_backups", 0))
    c3.metric("GitHub Backup", "Configurado" if backup.get("github_configured") else "No configurado")
    c4.metric("Último respaldo", backup.get("last_backup_at", "Nunca"))

    st.info(f"Ruta de base: {backup.get('db_path', 'No detectada')}")

    if backup.get("last_external_backup_ok"):
        st.success(f"Último respaldo externo OK: {backup.get('last_external_backup_message')}")
    else:
        st.warning(f"Último respaldo externo: {backup.get('last_external_backup_message', 'Sin información')}")

    if st.button("💾 Probar respaldo ahora", type="primary", use_container_width=True):
        nuevo = create_backup("prueba_configuracion", upload_external=True)
        if nuevo:
            st.success(f"Respaldo de prueba creado: {nuevo.name}")
            st.rerun()
        else:
            st.error("No se pudo crear el respaldo de prueba.")


def _render_secrets() -> None:
    st.subheader("Secrets y seguridad")
    rows = []
    for name, desc in [
        ("GITHUB_TOKEN", "Permite subir respaldos protegidos a GitHub."),
        ("GITHUB_REPO", "Repositorio destino de los respaldos."),
        ("BACKUP_PASSWORD", "Clave usada para proteger respaldos."),
        ("APP_SECRET_KEY", "Llave interna de seguridad del ERP."),
        ("DATABASE_URL", "Base externa PostgreSQL/Supabase, opcional."),
    ]:
        rows.append({
            "secret": name,
            "estado": "✅ Configurado" if _secret_exists(name) else "❌ Falta",
            "uso": desc,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Los valores no se muestran por seguridad. Solo se valida si existen.")


def _render_negocio() -> None:
    st.subheader("Datos del negocio")
    config = _safe_config()

    c1, c2 = st.columns(2)
    c1.text_input("Nombre comercial", value=str(config.get("nombre_negocio", "Copy Mary")), disabled=True)
    c2.text_input("Sistema", value="Imperio Atómico ERP", disabled=True)

    st.markdown("#### Tasas y comisiones activas")
    campos = [
        ("tasa_bcv", "BCV Bs/$"),
        ("tasa_binance", "Binance Bs/$"),
        ("iva_perc", "IVA %"),
        ("igtf_perc", "IGTF %"),
        ("banco_perc", "Banco %"),
        ("kontigo_perc", "Kontigo %"),
    ]
    cols = st.columns(3)
    for idx, (key, label) in enumerate(campos):
        cols[idx % 3].metric(label, config.get(key, DEFAULT_CONFIG.get(key, 0)))

    st.info("Esta ventana muestra la configuración actual. La edición directa puede agregarse en una siguiente mejora.")


def _render_base_datos() -> None:
    st.subheader("Base de datos y tablas")
    tablas = [
        "clientes",
        "proveedores",
        "inventario",
        "ventas",
        "cotizaciones",
        "movimientos_tesoreria",
        "cuentas_por_cobrar",
        "cuentas_por_pagar_proveedores",
        "servicios",
        "stock",
    ]
    rows = [{"tabla": t, "registros": _count_table(t)} for t in tablas]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    backup = get_backup_status()
    st.markdown("#### Información técnica")
    st.code(
        f"App root: {APP_ROOT}\n"
        f"Base: {backup.get('db_path')}\n"
        f"Carpeta respaldos: {backup.get('backup_dir')}\n"
        f"Última revisión: {datetime.now().isoformat(timespec='seconds')}",
        language="text",
    )


def _render_mantenimiento() -> None:
    st.subheader("Mantenimiento")
    st.markdown(
        """
        Acciones recomendadas:

        1. Crear respaldo manual antes de hacer cambios grandes.
        2. Verificar que GitHub Backup esté configurado.
        3. Descargar un respaldo importante al finalizar la semana.
        4. No subir bases `.db` sin proteger al repositorio.
        5. Revisar errores en Streamlit Cloud si la app no inicia.
        """
    )

    if st.button("🧪 Crear respaldo de mantenimiento", use_container_width=True):
        nuevo = create_backup("mantenimiento", upload_external=True)
        if nuevo:
            st.success(f"Respaldo de mantenimiento creado: {nuevo.name}")
        else:
            st.error("No se pudo crear el respaldo de mantenimiento.")


def render_configuracion_sistema(usuario: str = "Sistema") -> None:
    st.title("⚙️ Configuración del sistema")
    st.caption("Centro de control técnico y administrativo del ERP de Copy Mary.")

    tab_estado, tab_secrets, tab_negocio, tab_db, tab_mantenimiento = st.tabs([
        "Estado general",
        "Secrets",
        "Negocio",
        "Base de datos",
        "Mantenimiento",
    ])

    with tab_estado:
        _render_estado_general()
    with tab_secrets:
        _render_secrets()
    with tab_negocio:
        _render_negocio()
    with tab_db:
        _render_base_datos()
    with tab_mantenimiento:
        _render_mantenimiento()
