from datetime import date

import pandas as pd
import streamlit as st

APP_VERSION = "Paz Mental deploy 2026-05-27 v14 - entrypoint seguro"

import src.database as db
from src.styles import apply_styles
from src.utils import (
    ensure_dirs,
    save_uploaded_file,
    PORTADAS_DIR,
    RESPALDOS_DIR,
    buscar_libros_openlibrary,
    buscar_series_tvmaze,
    buscar_peliculas_itunes,
    buscar_peliculas_tmdb,
    buscar_series_tmdb,
    buscar_manga_jikan,
    buscar_webnovel_openlibrary,
    buscar_kdramas_tmdb,
    importar_desde_link,
)
from src.pages.cronometro import render_cronometro, fmt_time
from src.pages.buscador import render_buscador_avanzado
from src.pages.importar_link import render_importar_link
from src.pages.calendario import render_calendario
from src.pages.capitulos import render_capitulos
from src.pages.fanfiction import render_fanfiction_fields, fanfiction_badges
from src.pages.reportes import render_reportes
from src.pages.canons import render_canons
from src.pages.ao3_updates import render_ao3_updates
from src.pages.diagnostico import render_diagnostico

st.set_page_config(page_title="Paz Mental", page_icon="📚", layout="wide")
apply_styles()
ensure_dirs()
db.init_db()
st.caption(APP_VERSION)

TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")
BOOK_TYPES = ["Libro", "Fanfiction", "Novela", "Novela ligera", "Manga", "Manhwa", "Manhua", "Webnovel", "Comic"]
TV_TYPES = ["Anime", "Serie", "Kdrama", "Pelicula", "Documental", "Podcast", "Otro"]
TIPOS = BOOK_TYPES + TV_TYPES
ESTADOS = ["Pendiente", "Leyendo", "Viendo", "Terminado", "Pausado", "Abandonado", "Releyendo", "Rewatch"]
ESTADOS_PUBLICACION = ["En emision", "Terminada", "Hiatus con aviso", "Hiatus sin aviso", "Cancelada", "Abandonada por autor", "No aplica"]


def buscar_global(query, fuente):
    q = query.strip()
    if fuente == "Libros":
        return buscar_libros_openlibrary(q), "book"
    if fuente == "Manga / manhwa / novelas ligeras":
        return (buscar_manga_jikan(q) or buscar_libros_openlibrary(q)), "manga"
    if fuente == "Webnovels":
        return (buscar_webnovel_openlibrary(q) or buscar_manga_jikan(q)), "webnovel"
    if fuente == "Peliculas":
        resultados = buscar_peliculas_tmdb(q, TMDB_API_KEY) if TMDB_API_KEY else []
        return (resultados or buscar_peliculas_itunes(q) or buscar_series_tvmaze(q)), "movie"
    if fuente == "Kdramas":
        resultados = buscar_kdramas_tmdb(q, TMDB_API_KEY) if TMDB_API_KEY else []
        return (resultados or buscar_series_tvmaze(q)), "kdrama"
    resultados = buscar_series_tmdb(q, TMDB_API_KEY) if TMDB_API_KEY else []
    return (resultados or buscar_series_tvmaze(q)), "tv"


def _to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def guardar_importado(item, tipo, estado):
    cap_total = _to_int(item.get("capitulo_total"), 0)
    cap_publicados = _to_int(item.get("capitulos_publicados"), cap_total)
    cap_vistos = _to_int(item.get("capitulos_vistos", item.get("capitulo_actual")), 0)
    temporada_actual = max(1, _to_int(item.get("temporada_actual"), 1))
    temporada_total = max(1, _to_int(item.get("temporada_total"), temporada_actual))
    motivo_extra = []
    if item.get("division_obra"):
        motivo_extra.append(f"División: {item.get('division_obra')}")
    if item.get("ao3_work_id"):
        motivo_extra.append(f"AO3 work ID: {item.get('ao3_work_id')}")
    if item.get("ao3_tracking"):
        motivo_extra.append("Seguimiento AO3 activado")

    data = {
        "titulo": item.get("titulo", "Sin titulo"),
        "autor": item.get("autor", ""),
        "tipo": tipo,
        "obra_original_tipo": item.get("obra_original_tipo", ""),
        "obra_original_nombre": item.get("obra_original_nombre", ""),
        "fandom": item.get("fandom", ""),
        "ship": item.get("ship", ""),
        "universo_au": item.get("universo_au", ""),
        "fuente_fanfic": item.get("fuente_fanfic", ""),
        "es_crossover": _to_int(item.get("es_crossover"), 0),
        "crossover_obras": item.get("crossover_obras", ""),
        "crossover_fandoms": item.get("crossover_fandoms", ""),
        "crossover_tipo": item.get("crossover_tipo", ""),
        "crossover_notas": item.get("crossover_notas", ""),
        "division_obra": item.get("division_obra", ""),
        "ao3_work_id": item.get("ao3_work_id", ""),
        "ao3_tracking": _to_int(item.get("ao3_tracking"), 0),
        "fuente_confiabilidad": _to_int(item.get("fuente_confiabilidad"), 0),
        "calidad_datos": _to_int(item.get("calidad_datos"), 0),
        "ultima_importacion_fuente": item.get("fuente_importacion", ""),
        "clasificacion": 0,
        "estrellas": _to_int(item.get("estrellas"), 0),
        "estado_lectura": estado,
        "estado_publicacion": item.get("estado_publicacion", "No aplica"),
        "fecha_publicacion": item.get("fecha_publicacion", ""),
        "temporada_actual": temporada_actual,
        "temporada_total": temporada_total,
        "capitulo_actual": cap_vistos,
        "capitulo_total": cap_total,
        "capitulos_publicados": cap_publicados,
        "capitulos_vistos": cap_vistos,
        "sinopsis": item.get("sinopsis", ""),
        "etiquetas": item.get("etiquetas", "importado"),
        "link_original": item.get("link_original") or item.get("url_fuente", ""),
        "link_respaldo": "",
        "portada_path": item.get("portada_path", ""),
        "respaldo_path": "",
        "motivo_estado": f"Importado desde {item.get('fuente_importacion', 'fuente externa')}. Año: {item.get('anio') or 'N/D'}. URL: {item.get('url_fuente') or 'N/D'}. {' | '.join(motivo_extra)}",
        "favorito": _to_int(item.get("favorito"), 0),
        "fecha_inicio": str(date.today()),
        "fecha_fin": None,
    }
    db.add_obra(data)


def mini_card(row):
    portada = row.get("portada_path") or ""
    img = f'<img src="{portada}" />' if str(portada).startswith("http") else '<div class="book-empty">📖</div>'
    leidos = row.get("capitulos_vistos") or row.get("capitulo_actual") or 0
    publicados = row.get("capitulos_publicados") or row.get("capitulo_total") or 0
    badges = fanfiction_badges(row)
    sinopsis = (row.get("sinopsis") or "Sin sinopsis todavía.")[:180]
    return f"""
    <div class="bookmory-card">
      <div class="bookmory-cover">{img}</div>
      <div class="bookmory-title">{row.get('titulo','')}</div>
      <div class="bookmory-author">{row.get('autor') or 'Autor no indicado'}</div>
      <div class="bookmory-meta"><span>{row.get('tipo')}</span><span>{row.get('estado_lectura')}</span></div>
      <div class="bookmory-small">{badges}</div>
      <div class="bookmory-small">{sinopsis}</div>
      <div class="bookmory-small">T{row.get('temporada_actual') or 1} · {leidos} / {publicados} caps</div>
      <div class="bookmory-small">Tiempo: {fmt_time(row.get('tiempo_total_minutos'))}</div>
    </div>
    """


obras = db.list_obras()
df = pd.DataFrame(obras)

st.markdown("""
<div class="app-hero">
  <div>
    <div class="hero-label">Bookmory + TV Time personal</div>
    <h1>Paz Mental</h1>
    <p>Biblioteca de libros, fanfics, manga, manhwa, webnovels, kdramas, series, anime y peliculas.</p>
  </div>
</div>
""", unsafe_allow_html=True)

tab_timer, tab_search, tab_link, tab_calendar, tab_ao3, tab_books, tab_reports, tab_canons, tab_add, tab_chapters, tab_diag, tab_export = st.tabs([
    "⏱️ Cronómetro",
    "🔎 Buscar e importar",
    "🔗 Importar link",
    "📅 Calendario",
    "🔔 AO3",
    "📚 Biblioteca",
    "🏆 Wrapped / Reportes",
    "🌌 Canons",
    "➕ Agregar manual",
    "📝 Capitulos",
    "🧰 Diagnóstico",
    "⬇️ Exportar",
])

with tab_timer:
    render_cronometro(obras, db.add_actividad, db.update_obra, db.list_actividad)

with tab_search:
    st.info("Versión del buscador: Fase 8 pro con cache, merge seguro, paginación, tags y preview.")
    render_buscador_avanzado(obras, buscar_global, guardar_importado)

with tab_link:
    render_importar_link(obras, importar_desde_link, guardar_importado, save_uploaded_file, PORTADAS_DIR)

with tab_calendar:
    render_calendario(db.list_actividad)

with tab_ao3:
    render_ao3_updates(obras)

with tab_books:
    st.subheader("Biblioteca")
    if df.empty:
        st.info("Aún no tienes obras registradas.")
    else:
        st.markdown('<div class="bookmory-grid">' + ''.join(mini_card(row) for _, row in df.iterrows()) + '</div>', unsafe_allow_html=True)

with tab_reports:
    render_reportes(obras, db.list_actividad)

with tab_canons:
    render_canons(db.add_canon, db.list_canons)

with tab_add:
    st.subheader("Agregar obra manualmente")
    tipo_preview = st.selectbox("Tipo de obra", TIPOS, key="manual_tipo_visible")
    fanfic_data = {}
    if tipo_preview == "Fanfiction":
        st.info("Seleccionaste Fanfiction. Aquí puedes registrar canon, fandom, ship, AU y crossovers.")
        fanfic_data = render_fanfiction_fields(prefix="manual_visible")

    with st.form("obra_form_manual"):
        titulo = st.text_input("Título *")
        autor = st.text_input("Autor / creador / estudio")
        st.caption(f"Tipo seleccionado: {tipo_preview}")
        sinopsis = st.text_area("Sinopsis / descripción de la obra", height=160)
        etiquetas = st.text_input("Etiquetas / géneros", placeholder="romance, fantasía, kdrama, comfort...")
        estado = st.selectbox("Estado personal", ESTADOS)
        estado_pub = st.selectbox("Estado de publicación", ESTADOS_PUBLICACION)
        cap_vistos = st.number_input("Capítulos leídos/vistos", min_value=0, step=1)
        cap_pub = st.number_input("Capítulos publicados/emitidos", min_value=0, step=1)
        cap_total = st.number_input("Capítulos totales esperados", min_value=0, step=1)
        portada = st.file_uploader("Subir portada", type=["jpg", "jpeg", "png", "webp"])
        st.markdown("### Modo de respaldo")
        modo_respaldo = st.radio("¿Cómo quieres guardar el contenido?", ["Solo registrar la obra", "Subir obra completa", "Subir capítulos uno por uno", "Subir varios capítulos de golpe"])
        respaldo = st.file_uploader("Archivo completo de la obra", type=["pdf", "epub", "txt", "docx", "zip"]) if modo_respaldo == "Subir obra completa" else None
        if st.form_submit_button("Guardar obra"):
            if not titulo.strip():
                st.error("El título es obligatorio")
            else:
                data = {"titulo": titulo.strip(), "autor": autor.strip(), "tipo": tipo_preview, "clasificacion": 0, "estado_lectura": estado, "estado_publicacion": estado_pub, "capitulo_actual": int(cap_vistos), "capitulos_vistos": int(cap_vistos), "capitulos_publicados": int(cap_pub), "capitulo_total": int(cap_total), "sinopsis": sinopsis.strip(), "etiquetas": etiquetas.strip(), "link_original": "", "link_respaldo": "", "portada_path": save_uploaded_file(portada, PORTADAS_DIR), "respaldo_path": save_uploaded_file(respaldo, RESPALDOS_DIR), "motivo_estado": modo_respaldo, "favorito": 0, "fecha_inicio": str(date.today()), "fecha_fin": None}
                if tipo_preview == "Fanfiction":
                    data.update(fanfic_data)
                db.add_obra(data)
                st.success("Obra guardada.")

with tab_chapters:
    render_capitulos(obras, db.list_capitulos, db.get_obra, db.add_capitulo)

with tab_diag:
    render_diagnostico()

with tab_export:
    st.subheader("Exportar biblioteca")
    if df.empty:
        st.info("No hay datos.")
    else:
        st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8"), "paz-mental.csv", "text/csv")
        st.dataframe(df, use_container_width=True)
