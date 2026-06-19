from __future__ import annotations

import pandas as pd
import streamlit as st

from services.backup_service import (
    create_backup,
    get_backup_status,
    list_backups,
    restore_backup,
)
from services.protected_backup_restore import restore_protected_backup


def render_respaldo(usuario: str = "Sistema") -> None:
    st.title("💾 Respaldo y restauración")
    st.caption("Protege clientes, proveedores, inventario, ventas, cotizaciones, caja y reportes con copias de seguridad.")

    status = get_backup_status()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Base detectada", "Sí" if status["db_exists"] else "No")
    c2.metric("Respaldos", status["total_backups"])
    c3.metric("Último respaldo", status["last_backup_at"])
    c4.metric("Última restauración", status["last_restore_at"])

    st.info(f"Base de datos: {status['db_path']}")

    tab_manual, tab_historial, tab_restaurar, tab_ayuda = st.tabs([
        "Crear respaldo",
        "Historial",
        "Restaurar",
        "Notas importantes",
    ])

    with tab_manual:
        st.subheader("Crear respaldo manual")
        if st.button("💾 Crear respaldo ahora", type="primary", use_container_width=True):
            backup = create_backup("manual")
            if backup:
                st.success(f"Respaldo creado: {backup.name}")
                st.rerun()
            else:
                st.error("No se pudo crear el respaldo porque no se detectó la base de datos.")

        backups = list_backups()
        if backups:
            latest = backups[0]
            st.markdown("#### Descargar respaldo más reciente")
            st.download_button(
                "⬇️ Descargar último respaldo",
                latest.read_bytes(),
                file_name=latest.name,
                mime="application/octet-stream",
                use_container_width=True,
                key="download_latest_backup",
            )

    with tab_historial:
        st.subheader("Historial de respaldos")
        backups = list_backups()
        if not backups:
            st.info("Aún no hay respaldos locales disponibles.")
        else:
            rows = []
            for p in backups:
                rows.append({
                    "archivo": p.name,
                    "tamaño_kb": round(p.stat().st_size / 1024, 2),
                    "fecha_modificación": pd.to_datetime(p.stat().st_mtime, unit="s"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            seleccionado = st.selectbox("Seleccionar respaldo para descargar", [p.name for p in backups])
            elegido = next((p for p in backups if p.name == seleccionado), None)
            if elegido:
                st.download_button(
                    "⬇️ Descargar respaldo seleccionado",
                    elegido.read_bytes(),
                    file_name=elegido.name,
                    mime="application/octet-stream",
                    use_container_width=True,
                    key=f"download_backup_{elegido.name}",
                )

    with tab_restaurar:
        st.subheader("Restaurar respaldo")
        st.warning("Restaurar reemplaza la base actual. Antes de restaurar, el sistema crea un respaldo automático de seguridad.")
        st.info("Puedes subir un respaldo local .db o un respaldo protegido .json descargado desde GitHub.")
        uploaded = st.file_uploader(
            "Subir archivo de respaldo",
            type=["db", "sqlite", "sqlite3", "json"],
        )
        confirmar = st.checkbox("Confirmo que deseo reemplazar la base actual por este respaldo")
        if st.button("♻️ Restaurar respaldo", type="primary", use_container_width=True):
            if not uploaded:
                st.error("Primero sube un archivo de respaldo.")
            elif not confirmar:
                st.error("Debes confirmar la restauración.")
            else:
                nombre = str(getattr(uploaded, "name", "")).lower()
                if nombre.endswith(".json"):
                    ok, mensaje = restore_protected_backup(uploaded)
                    if ok:
                        st.success(mensaje)
                        st.info("Reinicia la app para cargar los datos restaurados.")
                    else:
                        st.error(mensaje)
                else:
                    ok = restore_backup(uploaded)
                    if ok:
                        st.success("Respaldo restaurado. Reinicia la app para cargar los datos restaurados.")
                    else:
                        st.error("No se pudo restaurar el respaldo.")

    with tab_ayuda:
        st.subheader("Notas importantes")
        st.markdown(
            """
            - El sistema crea un respaldo automático diario al abrir la app.
            - También crea respaldos antes de restaurar una base.
            - Conserva los 20 respaldos locales más recientes.
            - Los respaldos externos protegidos se guardan en GitHub cuando los Secrets están configurados.
            - En Streamlit Cloud, el almacenamiento local puede perderse si el servidor se reinicia o redeploya.
            - Descarga respaldos importantes regularmente aunque también exista copia externa.
            """
        )
