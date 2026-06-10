from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.configuracion import get_current_config, DEFAULT_CONFIG, set_config_values
from services.backup_service import get_backup_status, create_backup


APP_ROOT = Path(__file__).resolve().parents[1]


RATE_FIELDS = [
    ("tasa_bcv", "BCV", "Bs/$", "diaria", 2),
    ("tasa_binance", "Binance", "Bs/$", "variable", 2),
    ("iva_perc", "IVA", "%", "legal", 2),
    ("igtf_perc", "IGTF", "%", "legal", 2),
    ("banco_perc", "Banco", "%", "variable", 3),
    ("kontigo_perc", "Kontigo", "%", "variable", 3),
]


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


def _to_float_value(config: dict, key: str) -> float:
    try:
        return float(config.get(key, DEFAULT_CONFIG.get(key, 0)) or 0)
    except Exception:
        return float(DEFAULT_CONFIG.get(key, 0) or 0)


def _historial_config(limit: int = 50) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "historial_config"):
                return pd.DataFrame()
            return pd.read_sql_query(
                """
                SELECT parametro, valor_anterior, valor_nuevo, usuario, fecha
                FROM historial_config
                WHERE parametro IN ('tasa_bcv','tasa_binance','iva_perc','igtf_perc','banco_perc','kontigo_perc')
                ORDER BY fecha DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
    except Exception:
        return pd.DataFrame()


def _ultima_actualizacion(parametro: str) -> str:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "historial_config"):
                return "Sin historial"
            row = conn.execute(
                """
                SELECT fecha
                FROM historial_config
                WHERE parametro = ?
                ORDER BY fecha DESC
                LIMIT 1
                """,
                (parametro,),
            ).fetchone()
            return row["fecha"] if row else "Sin historial"
    except Exception:
        return "Sin historial"


def _horas_desde(fecha_texto: str) -> float | None:
    if not fecha_texto or fecha_texto == "Sin historial":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(str(fecha_texto)[:19], fmt)
            return (datetime.now() - dt).total_seconds() / 3600
        except Exception:
            pass
    return None


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


def _render_tasas(usuario: str) -> None:
    st.subheader("💱 Tasas y comisiones")
    st.caption("Actualiza aquí las tasas que cambian diario o incluso cada hora. Los cambios se guardan con historial.")
    config = _safe_config()

    st.markdown("#### Vista rápida")
    cols = st.columns(3)
    for idx, (key, label, unit, frecuencia, decimales) in enumerate(RATE_FIELDS):
        value = _to_float_value(config, key)
        ultima = _ultima_actualizacion(key)
        horas = _horas_desde(ultima)
        ayuda = "Sin historial"
        if horas is not None:
            ayuda = f"Actualizada hace {horas:.1f} h"
        cols[idx % 3].metric(label, f"{value:.{decimales}f} {unit}", ayuda)

    st.markdown("#### Editar valores")
    with st.form("form_editar_tasas"):
        c1, c2, c3 = st.columns(3)
        nuevos = {}
        for idx, (key, label, unit, frecuencia, decimales) in enumerate(RATE_FIELDS):
            col = [c1, c2, c3][idx % 3]
            nuevos[key] = col.number_input(
                f"{label} ({unit})",
                min_value=0.0,
                value=float(_to_float_value(config, key)),
                step=0.01 if decimales <= 2 else 0.001,
                format=f"%.{decimales}f",
                key=f"editar_{key}",
            )

        st.markdown("#### Atajos")
        a1, a2 = st.columns(2)
        usar_binance = a1.checkbox("Usar Binance como referencia para BCV")
        usar_bcv = a2.checkbox("Usar BCV como referencia para Binance")

        submitted = st.form_submit_button("💾 Guardar tasas y comisiones", type="primary", use_container_width=True)
        if submitted:
            if usar_binance:
                nuevos["tasa_bcv"] = nuevos["tasa_binance"]
            if usar_bcv:
                nuevos["tasa_binance"] = nuevos["tasa_bcv"]
            set_config_values(nuevos, usuario)
            create_backup("cambio_tasas", upload_external=True)
            st.success("Tasas actualizadas y respaldo creado.")
            st.rerun()

    st.markdown("#### Alertas de actualización")
    alertas = []
    for key, label, unit, frecuencia, _decimales in RATE_FIELDS:
        ultima = _ultima_actualizacion(key)
        horas = _horas_desde(ultima)
        if frecuencia == "variable" and (horas is None or horas >= 4):
            alertas.append(f"⚠️ {label} tiene más de 4 horas sin actualización o no tiene historial.")
        if frecuencia == "diaria" and (horas is None or horas >= 24):
            alertas.append(f"⚠️ {label} tiene más de 24 horas sin actualización o no tiene historial.")
    if alertas:
        for alerta in alertas:
            st.warning(alerta)
    else:
        st.success("Las tasas principales están actualizadas según su frecuencia.")

    st.markdown("#### Historial reciente")
    historial = _historial_config(80)
    if historial.empty:
        st.info("Aún no hay historial de cambios de tasas.")
    else:
        st.dataframe(historial, use_container_width=True, hide_index=True)


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
    c1.text_input("Nombre comercial", value=str(config.get("nombre_negocio", config.get("empresa_nombre", "Copy Mary"))), disabled=True)
    c2.text_input("Sistema", value="Imperio Atómico ERP", disabled=True)

    st.info("La edición de datos del negocio puede agregarse después. Las tasas ya se editan en la pestaña 💱 Tasas.")


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

    tab_estado, tab_tasas, tab_secrets, tab_negocio, tab_db, tab_mantenimiento = st.tabs([
        "Estado general",
        "💱 Tasas",
        "Secrets",
        "Negocio",
        "Base de datos",
        "Mantenimiento",
    ])

    with tab_estado:
        _render_estado_general()
    with tab_tasas:
        _render_tasas(usuario)
    with tab_secrets:
        _render_secrets()
    with tab_negocio:
        _render_negocio()
    with tab_db:
        _render_base_datos()
    with tab_mantenimiento:
        _render_mantenimiento()
