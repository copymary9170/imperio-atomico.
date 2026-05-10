import streamlit as st

from modules.catalogo_next import render_catalogo_hub


def render_catalogo(usuario):
    st.markdown(
        """
        <style>
        .catalogo-hero {
            padding: 1.4rem 1.6rem;
            border-radius: 1.35rem;
            background:
                radial-gradient(circle at top left, rgba(255, 69, 0, 0.32), transparent 32%),
                linear-gradient(135deg, rgba(28, 28, 35, 0.98), rgba(16, 16, 22, 0.98));
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.28);
            margin-bottom: 1.2rem;
        }
        .catalogo-hero h1 {
            margin: 0;
            font-size: 2.2rem;
            letter-spacing: -0.04em;
        }
        .catalogo-hero p {
            margin: 0.45rem 0 0 0;
            max-width: 820px;
            color: rgba(255, 255, 255, 0.72);
            font-size: 1rem;
            line-height: 1.55;
        }
        .catalogo-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        .catalogo-pill {
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.14);
            background: rgba(255, 255, 255, 0.07);
            color: rgba(255, 255, 255, 0.86);
            font-size: 0.82rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.09);
            border-radius: 1rem;
            padding: 0.9rem 1rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 1.15rem !important;
        }
        </style>

        <div class="catalogo-hero">
            <h1>🛍️ Catálogo Pro</h1>
            <p>
                Showroom comercial de Imperio Atómico: productos, servicios, precios,
                márgenes, rutas de producción, visibilidad pública y readiness para ventas.
            </p>
            <div class="catalogo-pill-row">
                <span class="catalogo-pill">✨ Product Studio</span>
                <span class="catalogo-pill">📊 Score comercial</span>
                <span class="catalogo-pill">💸 Pricing mayorista</span>
                <span class="catalogo-pill">🏭 Ruta productiva</span>
                <span class="catalogo-pill">⬇️ Import / Export</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_catalogo_hub(usuario)
