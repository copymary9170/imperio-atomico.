from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]

AREAS_EMPRESARIALES = {
    "Finanzas": {"icono": "💼", "carpeta": "finanzas", "descripcion": "Control financiero, flujo de caja, cuentas por cobrar, cuentas por pagar, presupuesto y rentabilidad."},
    "Marketing": {"icono": "📣", "carpeta": "marketing", "descripcion": "Calendario de contenido, campañas, promociones, embudo comercial y métricas de marketing."},
    "Recursos Humanos": {"icono": "👥", "carpeta": "recursos_humanos", "descripcion": "Colaboradores, roles, asistencia, nómina, capacitación, evaluaciones e incidencias."},
    "Tesorería y Cobranza": {"icono": "🏦", "carpeta": "tesoreria", "descripcion": "Caja diaria, agenda de cobranza, promesas de pago, comprobantes, bancos y conciliación."},
    "Administración": {"icono": "🗂️", "carpeta": "administracion", "descripcion": "Panel administrativo, agenda, tareas internas, documentos, proveedores y obligaciones."},
    "Contabilidad": {"icono": "📚", "carpeta": "contabilidad", "descripcion": "Catálogo contable, pólizas, comprobantes fiscales, impuestos y cierre mensual."},
    "Legal": {"icono": "⚖️", "carpeta": "legal", "descripcion": "Términos, garantías, contratos, autorizaciones, privacidad e incidentes legales."},
    "Almacén": {"icono": "📦", "carpeta": "almacen", "descripcion": "Kardex, entradas, salidas, ubicaciones, stock mínimo, inventario físico y mermas."},
    "Producción": {"icono": "🏭", "carpeta": "produccion", "descripcion": "Órdenes de producción, etapas, plan diario, avances, materiales, tiempos y calidad."},
}


def _leer_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, encoding="latin-1")
        except Exception as exc:
            st.error(f"No se pudo leer {path.name}: {exc}")
            return pd.DataFrame()


def _render_archivo(path: Path) -> None:
    with st.expander(path.name, expanded=False):
        if path.suffix.lower() == ".csv":
            df = _leer_csv(path)
            st.caption(f"Registros: {len(df)} | Columnas: {len(df.columns)}")
            if df.empty:
                st.info("Este archivo no tiene registros todavía.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
        elif path.suffix.lower() == ".md":
            try:
                st.markdown(path.read_text(encoding="utf-8"))
            except Exception as exc:
                st.error(f"No se pudo abrir {path.name}: {exc}")
        else:
            st.write(path.name)


def _render_existente_seguro(render_existente, usuario: str) -> None:
    try:
        render_existente(usuario)
    except TypeError as exc:
        if "positional" in str(exc) or "argument" in str(exc):
            render_existente()
        else:
            raise


def render_area_empresarial(nombre_area: str, usuario: str = "Sistema", *, show_title: bool = True) -> None:
    area = AREAS_EMPRESARIALES[nombre_area]
    carpeta = BASE_DIR / area["carpeta"]

    if show_title:
        st.title(f"{area['icono']} {nombre_area}")
    else:
        st.subheader(f"{area['icono']} Archivos y controles nuevos")
    st.caption(area["descripcion"])

    col1, col2, col3 = st.columns(3)
    archivos = []
    if carpeta.exists():
        archivos = sorted([p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".md"}], key=lambda p: p.name)

    col1.metric("Archivos", len(archivos))
    col2.metric("Carpeta", area["carpeta"])
    col3.metric("Usuario", usuario)

    st.divider()

    if not carpeta.exists():
        st.warning(f"No existe la carpeta `{area['carpeta']}` en el repositorio.")
        return

    if not archivos:
        st.info("Esta área todavía no tiene archivos CSV o Markdown para mostrar.")
        return

    resumen = pd.DataFrame([{"archivo": p.name, "tipo": p.suffix.lower().replace(".", ""), "ruta": str(p.relative_to(BASE_DIR))} for p in archivos])
    st.subheader("Resumen de archivos")
    st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.subheader("Contenido")
    for path in archivos:
        _render_archivo(path)


def render_area_combinada(nombre_area: str, render_existente, usuario: str = "Sistema") -> None:
    tab_sistema, tab_archivos = st.tabs(["Sistema operativo", "Archivos nuevos"])
    with tab_sistema:
        _render_existente_seguro(render_existente, usuario)
    with tab_archivos:
        render_area_empresarial(nombre_area, usuario, show_title=False)
