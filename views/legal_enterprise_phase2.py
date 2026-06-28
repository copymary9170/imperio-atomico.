import pandas as pd
import streamlit as st


def render_legal_enterprise_phase2(user: str = "Sistema") -> None:
    st.title("Departamento Jurídico Enterprise")
    st.caption("Panel ejecutivo, arquitectura, permisos, reglas y catálogo funcional.")

    section = st.radio(
        "Área",
        ["Dashboard", "Arquitectura", "Campos", "Permisos", "Reglas"],
        horizontal=True,
        key="legal_enterprise_phase2_view",
    )
    st.divider()

    if section == "Dashboard":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Módulos jurídicos", 29)
        c2.metric("Roles definidos", 5)
        c3.metric("Controles base", 8)
        c4.metric("Usuario", user)
        st.success("Estructura Enterprise habilitada.")

    elif section == "Arquitectura":
        areas = {
            "Dirección": "KPIs, alertas, semáforos y riesgos",
            "Cumplimiento": "Aviso legal, términos, privacidad, cookies y consentimientos",
            "Contratos": "Clientes, proveedores, laborales y renovaciones",
            "Propiedad intelectual": "Marcas, derechos de autor, diseños y licencias",
            "Riesgos y litigios": "Riesgos, demandas, litigios y evidencias",
            "Gestión documental": "Documentos, versiones, archivo y retención",
            "Gobierno": "Auditoría, firma digital, roles y permisos",
        }
        for area, detail in areas.items():
            with st.expander(area):
                st.write(detail)

    elif section == "Campos":
        st.dataframe(pd.DataFrame([
            ["codigo", "Texto automático", True, False],
            ["titulo", "Texto", True, True],
            ["responsable", "Usuario", True, True],
            ["estado", "Lista", True, False],
            ["riesgo", "Lista", True, True],
            ["archivo", "Adjunto", False, True],
            ["hash_sha256", "Automático", True, False],
        ], columns=["Campo", "Tipo", "Obligatorio", "Editable"]), use_container_width=True, hide_index=True)

    elif section == "Permisos":
        st.dataframe(pd.DataFrame([
            ["Legal Admin", "legal.*"],
            ["Legal Reviewer", "legal.review"],
            ["Compliance Officer", "legal.audit"],
            ["Dirección", "legal.approve"],
            ["Ventas Lectura", "legal.read"],
        ], columns=["Rol", "Permiso"]), use_container_width=True, hide_index=True)

    else:
        st.dataframe(pd.DataFrame([
            ["Documentos", "No eliminar documentos firmados o publicados", "Crítica"],
            ["Contratos", "No editar contratos aprobados; crear nueva versión", "Crítica"],
            ["Cumplimiento", "No publicar documentos incompletos", "Alta"],
            ["Auditoría", "Registrar usuario, fecha, antes y después", "Crítica"],
        ], columns=["Área", "Regla", "Severidad"]), use_container_width=True, hide_index=True)
