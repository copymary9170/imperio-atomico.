from pathlib import Path
from datetime import datetime

import streamlit as st

from modules.catalogo_visual import render_catalogo_hub


ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOG_IMAGES_DIR = ROOT_DIR / "data" / "catalogo_fotos"


def _save_quick_catalog_photo(uploaded_file, sku: str) -> str | None:
    if uploaded_file is None:
        return None

    CATALOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        st.error("La foto debe ser PNG, JPG, JPEG o WEBP.")
        return None

    safe_sku = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(sku or "producto"))
    filename = f"{safe_sku}-{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    path = CATALOG_IMAGES_DIR / filename
    path.write_bytes(uploaded_file.getbuffer())
    return str(path)


def render_catalogo(usuario):
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem !important; }
        .photo-upload-hero {
            padding: 1.25rem 1.4rem;
            border-radius: 24px;
            background: linear-gradient(135deg, #ff4d00, #ff006e, #6d28d9);
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 22px 58px rgba(0,0,0,.28);
        }
        .photo-upload-hero h1 {
            margin: 0;
            font-size: 2.1rem;
            font-weight: 900;
            letter-spacing: -0.04em;
        }
        .photo-upload-hero p {
            margin: .45rem 0 0 0;
            opacity: .92;
            max-width: 850px;
        }
        </style>
        <div class="photo-upload-hero">
            <h1>📸 Catálogo con fotos activo</h1>
            <p>Sube fotos para identificar visualmente cada producto. También puedes crear o editar productos con foto en la sección de abajo.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("📸 Subir foto rápida de producto", expanded=True):
        c1, c2 = st.columns([1, 2])
        quick_sku = c1.text_input("SKU o nombre del producto", placeholder="Ej: CAT-001")
        quick_photo = c2.file_uploader(
            "Selecciona una foto PNG, JPG o WEBP",
            type=["png", "jpg", "jpeg", "webp"],
            key="catalogo_quick_photo_upload",
        )

        if quick_photo is not None:
            st.image(quick_photo, caption="Vista previa de la foto", width=260)

        if st.button("💾 Guardar foto rápida", use_container_width=True, disabled=quick_photo is None):
            saved_path = _save_quick_catalog_photo(quick_photo, quick_sku)
            if saved_path:
                st.success(f"Foto guardada correctamente: {saved_path}")
                st.info("Para asociarla al producto, entra en la pestaña 📸 Fotos y edición y guarda el producto con esta foto o vuelve a subirla allí.")

    render_catalogo_hub(usuario)
