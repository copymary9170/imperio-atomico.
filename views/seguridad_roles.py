from __future__ import annotations

import streamlit as st

from security.permissions import (
    assign_role_to_user,
    get_auditoria_seguridad_df,
    get_permissions_catalog_df,
    get_role_permissions_df,
    get_users_roles_df,
    has_permission,
    require_permission,
    set_role_permissions,
)


def render_seguridad_roles(usuario: str) -> None:
    if not require_permission("security.view", "🚫 No tienes acceso al módulo Seguridad / Roles."):
        return

    puede_editar = has_permission("security.edit")

    st.title("🔐 Seguridad / Roles")
    st.caption("Gestión de roles, permisos y auditoría de seguridad.")

    if not puede_editar:
        st.info("Modo solo lectura: puedes consultar usuarios, permisos y auditoría.")

    users_df = get_users_roles_df()
    permissions_df = get_permissions_catalog_df()
    role_permissions_df = get_role_permissions_df()

    tab_users, tab_roles, tab_audit = st.tabs(
        ["👥 Usuarios", "🛡️ Roles y permisos", "🧾 Auditoría de seguridad"]
    )

    with tab_users:
        st.subheader("Usuarios y roles actuales")
        st.dataframe(users_df, use_container_width=True, hide_index=True)

        if users_df.empty:
            st.caption("No hay usuarios registrados.")
        else:
            selected_user = st.selectbox("Usuario", users_df["usuario"].tolist(), key="seg_user")
            current_role = users_df.loc[users_df["usuario"] == selected_user, "rol"].iloc[0]
            available_roles = sorted(role_permissions_df["rol"].dropna().unique().tolist())
            role_index = available_roles.index(current_role) if current_role in available_roles else 0

            new_role = st.selectbox(
                "Nuevo rol",
                available_roles,
                index=role_index,
                disabled=not puede_editar,
                key="seg_user_role",
            )
            if st.button("Asignar rol", disabled=not puede_editar):
                assign_role_to_user(selected_user, new_role, actor_usuario=usuario)
                st.success(f"Rol actualizado para {selected_user}.")
                st.rerun()

    with tab_roles:
        st.subheader("Catálogo de permisos")
        st.dataframe(permissions_df, use_container_width=True, hide_index=True)

        roles = sorted(role_permissions_df["rol"].dropna().unique().tolist())
        if not roles:
            st.caption("No hay roles configurados.")
        else:
            selected_role = st.selectbox("Rol", roles, key="seg_role")
            current_role_permissions = sorted(
                role_permissions_df.loc[
                    role_permissions_df["rol"] == selected_role, "permiso_codigo"
                ].tolist()
            )

            selected_permissions = st.multiselect(
                "Permisos del rol",
                permissions_df["codigo"].tolist() + ["*"],
                default=current_role_permissions,
                disabled=not puede_editar,
                key="seg_role_perms",
            )

            if st.button("Guardar permisos del rol", disabled=not puede_editar):
                set_role_permissions(selected_role, selected_permissions, usuario=usuario)
                st.success(f"Permisos del rol '{selected_role}' actualizados.")
                st.rerun()

    with tab_audit:
        st.subheader("Bitácora")
        audit_df = get_auditoria_seguridad_df()
        if audit_df.empty:
            st.caption("No hay registros de auditoría de seguridad.")
        else:
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
