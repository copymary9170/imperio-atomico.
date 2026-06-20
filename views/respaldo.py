from __future__ import annotations

import pandas as pd
import streamlit as st

from services.backup_service import (
    create_backup,
    database_has_business_data,
    get_backup_status,
    list_backups,
    persist_database_snapshot,
    restore_backup,
    restore_remote_database_if_needed,
)
from services.protected_backup_restore import restore_protected_backup


def render_respaldo(usuario: str = "Sistema") -> None:
    st.title("💾 Respaldo y restauración")
    st.caption("Protege clientes, proveedores, inventario, ventas, cotizaciones, caja y reportes con copias de seguridad.")

    status = get_backup_status()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Base detectada", "Sí" if status["db_exists"] else "No")
    c2.metric("Tiene datos", "Sí" if status.get("db_has_business_data") else "No")
    c3.metric("Respaldos", status["total_backups"])
    c4.metric("Último respaldo", status["last_backup_at"])
    c5.metric("Última restauración", status["last_restore_at"])

    st.info(f"Base de datos: {status['db_path']}")
    if status.get("github_configured"):
        if status.get("last_external_backup_ok"):
            st.success(f"Respaldo externo OK: {status.get('last_external_backup_message', '')}")
        else:
            st.warning(f"Respaldo externo pendiente o fallido: {status.get('last_external_backup_message', '')}")
    else:
        st.error("GitHub no está configurado en Secrets. Sin respaldo externo, Streamlit puede perder datos al reiniciar.")

    tab_manual, tab_historial, tab_restaurar, tab_github, tab_ayuda = st.tabs([
        "Crear respaldo",
        "Historial",
        "Restaurar archivo",
        "GitHub / Emergencia",
        "Notas importantes",
    ])

    with tab_manual:
        st.subheader("Crear respaldo manual")
        st.caption("Este botón crea un respaldo local y también intenta actualizar GitHub como respaldo persistente.")
        if st.button("💾 Crear respaldo ahora", type="primary", use_container_width=True):
            backup = create_backup("manual", upload_external=True, archive=True)
            if backup:
                st.success(f"Respaldo creado: {backup.name}")
                nuevo_status = get_backup_status()
                if nuevo_status.get("last_external_backup_ok"):
                    st.success(f"También se guardó en GitHub: {nuevo_status.get('last_external_backup_message', '')}")
                else:
                    st.warning(f"Se creó localmente, pero GitHub no confirmó: {nuevo_status.get('last_external_backup_message', '')}")
            else:
                st.error("No se pudo crear el respaldo porque no se detectó la base de datos.")

        st.divider()
        if st.button("☁️ Guardar base actual en GitHub ahora", use_container_width=True):
            if not database_has_business_data():
                st.error("No se envió a GitHub porque la base actual no tiene datos de negocio. Esto evita sobrescribir un respaldo bueno con una base vacía.")
            else:
                ok, mensaje = persist_database_snapshot("manual_github")
                if ok:
                    st.success(f"Base actual guardada en GitHub: {mensaje}")
                else:
                    st.error(f"GitHub no confirmó el respaldo: {mensaje}")

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
        st.subheader("Restaurar respaldo desde archivo")
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

    with tab_github:
        st.subheader("GitHub / Recuperación de emergencia")
        st.info("Usa esto cuando Streamlit abra con el inventario vacío. Trae el último respaldo persistente guardado en la rama data-backups.")
        st.caption(f"Rama de respaldo: {status.get('backup_branch', 'data-backups')}")
        confirmar_remote = st.checkbox("Confirmo que deseo traer el último respaldo de GitHub y reemplazar la base local", key="confirmar_restore_remote")
        if st.button("☁️ Restaurar último respaldo desde GitHub", type="primary", use_container_width=True, disabled=not confirmar_remote):
            ok, mensaje = restore_remote_database_if_needed(force=True)
            if ok:
                st.success(mensaje)
                st.info("La base fue restaurada. La app se recargará para mostrar los datos.")
                st.rerun()
            else:
                st.error(mensaje)

    with tab_ayuda:
        st.subheader("Notas importantes")
        st.markdown(
            """
            - El sistema crea un respaldo automático diario al abrir la app.
            - También crea respaldos antes de restaurar una base.
            - Conserva los 20 respaldos locales más recientes.
            - Los respaldos externos protegidos se guardan en GitHub cuando los Secrets están configurados.
            - Si Streamlit abre vacío, entra en **GitHub / Emergencia** y pulsa **Restaurar último respaldo desde GitHub**.
            - En Streamlit Cloud, el almacenamiento local puede perderse si el servidor se reinicia o redeploya.
            """
        )
