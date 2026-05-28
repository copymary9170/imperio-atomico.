from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

TIPO_EMOJI = {
    "Libro": "📖",
    "Fanfiction": "✍️",
    "Novela": "📚",
    "Novela ligera": "📚",
    "Manga": "🌸",
    "Manhwa": "🌸",
    "Manhua": "🌸",
    "Webnovel": "🌐",
    "Anime": "🌸",
    "Serie": "📺",
    "Kdrama": "💙",
    "Pelicula": "🎬",
    "Documental": "🎞️",
    "Podcast": "🎧",
}


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _month_bounds(year, month):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def _activity_by_day(actividad):
    grouped = defaultdict(list)
    for row in actividad or []:
        d = _parse_date(row.get("fecha"))
        if d:
            grouped[d].append(row)
    return grouped


def _day_stats(rows):
    caps = sum(int(r.get("cantidad") or 0) for r in rows)
    minutes = sum(int(r.get("minutos") or 0) for r in rows)
    obras = {r.get("obra_id") for r in rows if r.get("obra_id")}
    tipos = [r.get("tipo") for r in rows if r.get("tipo")]
    portadas = [r.get("portada_path") for r in rows if r.get("portada_path")]
    moods = [r.get("mood") for r in rows if r.get("mood")]
    return {"caps": caps, "minutes": minutes, "obras": len(obras), "tipos": tipos, "portadas": portadas, "moods": moods}


def _streaks(active_days):
    if not active_days:
        return 0, 0
    days = sorted(active_days)
    best = current = 1
    for prev, cur in zip(days, days[1:]):
        if cur == prev + timedelta(days=1):
            current += 1
        else:
            best = max(best, current)
            current = 1
    best = max(best, current)
    today = date.today()
    current_streak = 0
    cursor = today
    active_set = set(days)
    while cursor in active_set:
        current_streak += 1
        cursor -= timedelta(days=1)
    return current_streak, best


def _render_day_card(day, rows, selected_day, today):
    stats = _day_stats(rows)
    active = bool(rows)
    intensity = min(1, (stats["minutes"] / 120) if stats["minutes"] else (stats["caps"] / 8 if stats["caps"] else 0))
    bg = "rgba(28, 73, 128, 0.92)" if selected_day == day else (f"rgba(44, 105, 176, {0.18 + intensity * 0.55})" if active else "rgba(255,255,255,0.72)")
    color = "white" if selected_day == day else "#17324f"
    border = "2px solid #ffffff" if day == today else "1px solid rgba(30,70,120,.18)"
    emojis = " ".join(sorted(set(TIPO_EMOJI.get(t, "📌") for t in stats["tipos"])))[:16]
    label = f"{day.day}"
    html = f"""
    <div style='min-height:112px;border-radius:16px;padding:10px;background:{bg};color:{color};border:{border};box-shadow:0 8px 20px rgba(20,60,110,.08)'>
      <div style='font-weight:900;font-size:1.05rem'>{label}</div>
      <div style='font-size:.82rem;margin-top:6px'>{emojis or '&nbsp;'}</div>
      <div style='font-size:.78rem;margin-top:6px'>📖 {stats['caps']} caps</div>
      <div style='font-size:.78rem'>⏱️ {stats['minutes']} min</div>
      <div style='font-size:.78rem'>✨ {stats['obras']} obras</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_month_grid(year, month, grouped, selected_day):
    today = date.today()
    cal = calendar.Calendar(firstweekday=0)
    st.markdown("### Vista mensual")
    header_cols = st.columns(7)
    for col, name in zip(header_cols, ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]):
        col.markdown(f"**{name}**")
    for week in cal.monthdatescalendar(year, month):
        cols = st.columns(7)
        for col, day in zip(cols, week):
            with col:
                if day.month != month:
                    st.markdown("<div style='min-height:112px;opacity:.25'></div>", unsafe_allow_html=True)
                else:
                    _render_day_card(day, grouped.get(day, []), selected_day, today)


def _render_heatmap(days, grouped):
    st.markdown("### Heatmap de actividad")
    if not days:
        st.info("No hay días para mostrar.")
        return
    cols = st.columns(min(14, len(days)))
    for idx, day in enumerate(days):
        stats = _day_stats(grouped.get(day, []))
        score = stats["minutes"] + stats["caps"] * 8
        opacity = min(.95, .12 + score / 180)
        with cols[idx % len(cols)]:
            st.markdown(
                f"<div title='{day}' style='height:26px;border-radius:7px;background:rgba(44,105,176,{opacity});margin:3px'></div>",
                unsafe_allow_html=True,
            )


def _render_day_detail(selected_day, rows):
    st.markdown(f"### Detalle del día · {selected_day.isoformat()}")
    if not rows:
        st.info("No hay actividad registrada ese día.")
        return
    stats = _day_stats(rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Capítulos / actividades", stats["caps"])
    c2.metric("Minutos", stats["minutes"])
    c3.metric("Obras", stats["obras"])
    df = pd.DataFrame(rows)
    cols = [c for c in ["titulo", "tipo", "tipo_actividad", "cantidad", "minutos", "mood", "comentario", "premio"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


def _render_by_work(actividad):
    st.markdown("### Calendario por obra")
    if not actividad:
        st.info("No hay actividad.")
        return
    titles = sorted({r.get("titulo") for r in actividad if r.get("titulo")})
    if not titles:
        st.info("No hay títulos en la actividad.")
        return
    title = st.selectbox("Obra", titles, key="calendar_work_select")
    rows = [r for r in actividad if r.get("titulo") == title]
    grouped = _activity_by_day(rows)
    active_days = sorted(grouped.keys())
    if not active_days:
        st.info("No hay días activos para esta obra.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Días activos", len(active_days))
    c2.metric("Minutos", sum(int(r.get("minutos") or 0) for r in rows))
    c3.metric("Caps/actividades", sum(int(r.get("cantidad") or 0) for r in rows))
    chart_df = pd.DataFrame([{"fecha": d, "cantidad": sum(int(r.get("cantidad") or 0) for r in grouped[d]), "minutos": sum(int(r.get("minutos") or 0) for r in grouped[d])} for d in active_days])
    st.line_chart(chart_df.set_index("fecha"))


def render_calendario(list_actividad):
    st.subheader("📅 Calendario visual")
    st.caption("Calendario mensual con actividad por día, portadas/emoji, rachas, filtros, heatmap, detalle diario y vista por obra.")

    actividad = list_actividad() if callable(list_actividad) else (list_actividad or [])
    if not actividad:
        st.info("Todavía no hay actividad registrada. Usa el cronómetro o capítulos para llenar el calendario.")
        return

    today = date.today()
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        year = st.number_input("Año", min_value=2000, max_value=2100, value=today.year, step=1, key="calendar_year")
    with col_b:
        month = st.selectbox("Mes", list(range(1, 13)), index=today.month - 1, format_func=lambda m: calendar.month_name[m], key="calendar_month")
    with col_c:
        mode = st.radio("Modo", ["Mes", "Heatmap", "Por obra", "Timeline"], horizontal=True, key="calendar_mode")

    tipos = sorted({r.get("tipo") for r in actividad if r.get("tipo")})
    obras = sorted({r.get("titulo") for r in actividad if r.get("titulo")})
    with st.expander("Filtros", expanded=False):
        filtro_tipos = st.multiselect("Tipo de obra", tipos, default=tipos, key="calendar_filter_tipos")
        filtro_obras = st.multiselect("Obra", obras, default=[], key="calendar_filter_obras")
        solo_con_notas = st.checkbox("Solo actividad con notas/comentarios", key="calendar_only_notes")

    filtered = []
    for row in actividad:
        if filtro_tipos and row.get("tipo") not in filtro_tipos:
            continue
        if filtro_obras and row.get("titulo") not in filtro_obras:
            continue
        if solo_con_notas and not (row.get("comentario") or row.get("premio") or row.get("mood")):
            continue
        filtered.append(row)

    grouped = _activity_by_day(filtered)
    first, last = _month_bounds(int(year), int(month))
    month_days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    month_active = [d for d in month_days if grouped.get(d)]
    current_streak, best_streak = _streaks(grouped.keys())
    month_rows = [r for d in month_days for r in grouped.get(d, [])]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Días activos del mes", len(month_active))
    m2.metric("Minutos del mes", sum(int(r.get("minutos") or 0) for r in month_rows))
    m3.metric("Caps/actividades", sum(int(r.get("cantidad") or 0) for r in month_rows))
    m4.metric("Mejor racha", best_streak)
    st.caption(f"Racha actual: {current_streak} días")

    selected_day = st.date_input("Día seleccionado", value=today if today.month == int(month) and today.year == int(year) else first, key="calendar_selected_day")

    if mode == "Mes":
        _render_month_grid(int(year), int(month), grouped, selected_day)
        _render_day_detail(selected_day, grouped.get(selected_day, []))
    elif mode == "Heatmap":
        _render_heatmap(month_days, grouped)
        _render_day_detail(selected_day, grouped.get(selected_day, []))
    elif mode == "Por obra":
        _render_by_work(filtered)
    else:
        st.markdown("### Timeline")
        df = pd.DataFrame(filtered)
        if not df.empty:
            cols = [c for c in ["fecha", "titulo", "tipo", "tipo_actividad", "cantidad", "minutos", "mood", "comentario"] if c in df.columns]
            st.dataframe(df[cols].sort_values("fecha", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("No hay actividad con esos filtros.")
