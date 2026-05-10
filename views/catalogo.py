import streamlit as st

from modules.catalogo_next import render_catalogo_hub


def render_catalogo(usuario):
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.6rem !important;
        }
        .catalogo-hero-v2 {
            width: 100%;
            padding: 2rem 2.2rem;
            border-radius: 28px;
            background: linear-gradient(135deg, #ff4d00 0%, #ff006e 38%, #6d28d9 72%, #08111f 100%) !important;
            border: 2px solid rgba(255, 255, 255, 0.24);
            box-shadow: 0 28px 75px rgba(255, 77, 0, 0.22), 0 16px 45px rgba(0, 0, 0, 0.45);
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
        }
        .catalogo-hero-v2:before {
            content: "";
            position: absolute;
            inset: -80px -120px auto auto;
            width: 280px;
            height: 280px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.22);
            filter: blur(8px);
        }
        .catalogo-hero-v2 h1 {
            margin: 0;
            color: white !important;
            font-size: 3rem;
            line-height: 1.05;
            letter-spacing: -0.06em;
            font-weight: 900;
            text-shadow: 0 4px 22px rgba(0, 0, 0, 0.35);
        }
        .catalogo-hero-v2 .subtitle {
            margin-top: 0.75rem;
            max-width: 880px;
            color: rgba(255, 255, 255, 0.92) !important;
            font-size: 1.08rem;
            line-height: 1.65;
        }
        .catalogo-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            color: #fff;
            background: rgba(0, 0, 0, 0.24);
            border: 1px solid rgba(255, 255, 255, 0.25);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.9rem;
        }
        .catalogo-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-top: 1.25rem;
        }
        .catalogo-pill {
            padding: 0.52rem 0.9rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.28);
            background: rgba(255, 255, 255, 0.16);
            color: white !important;
            font-size: 0.88rem;
            font-weight: 700;
            backdrop-filter: blur(10px);
        }
        .catalogo-version-badge {
            margin: -0.35rem 0 1rem 0;
            padding: 0.7rem 1rem;
            border-radius: 16px;
            background: rgba(255, 193, 7, 0.13);
            border: 1px solid rgba(255, 193, 7, 0.38);
            color: inherit;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.085), rgba(255,255,255,0.025)) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 18px !important;
            padding: 1rem !important;
            box-shadow: 0 12px 32px rgba(0,0,0,0.16);
        }
        div[data-testid="stTabs"] button {
            font-weight: 800 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 20px !important;
            box-shadow: 0 10px 26px rgba(0,0,0,0.12);
        }
        </style>

        <div class="catalogo-hero-v2">
            <div class="catalogo-kicker">⚛️ Imperio Atómico · Catálogo 2.0 activo</div>
            <h1>🛍️ Catálogo Pro</h1>
            <div class="subtitle">
                Un showroom comercial para vender mejor: productos, servicios, combos,
                márgenes, precios mínimos, mayoristas, rutas productivas, visibilidad pública,
                exportación e insights de rentabilidad.
            </div>
            <div class="catalogo-pill-row">
                <span class="catalogo-pill">✨ Product Studio</span>
                <span class="catalogo-pill">📊 Score comercial</span>
                <span class="catalogo-pill">💸 Pricing inteligente</span>
                <span class="catalogo-pill">🏭 Ruta productiva</span>
                <span class="catalogo-pill">📦 Stock objetivo</span>
                <span class="catalogo-pill">⬇️ Import / Export</span>
            </div>
        </div>
        <div class="catalogo-version-badge">
            ✅ Estás viendo la versión visual nueva del Catálogo Pro. Si ves este aviso, el deploy sí tomó el cambio.
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_catalogo_hub(usuario)
