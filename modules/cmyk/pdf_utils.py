import io
from typing import List, Tuple
from PIL import Image

from modules.utils.image_utils import optimize_image


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

MAX_PDF_PAGES = 50
PDF_RENDER_DPI = 150


# ==========================================================
# CONVERTIR PDF A IMÁGENES CMYK
# ==========================================================

def pdf_to_images(file_bytes: bytes, filename: str) -> List[Tuple[str, Image.Image]]:
    """
    Convierte un PDF en una lista de imágenes CMYK optimizadas.

    Limita el número de páginas para evitar consumo excesivo
    de memoria cuando se suben PDFs muy grandes.
    """

    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError:
        raise RuntimeError(
            "PyMuPDF (fitz) no está instalado. Instálalo con: pip install pymupdf"
        )

    paginas: List[Tuple[str, Image.Image]] = []

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    total_pages = min(len(doc), MAX_PDF_PAGES)

    for i in range(total_pages):

        page = doc.load_page(i)

        pix = page.get_pixmap(
            colorspace=fitz.csCMYK,
            dpi=PDF_RENDER_DPI
        )

        img = Image.frombytes(
            "CMYK",
            [pix.width, pix.height],
            pix.samples
        )

        img = optimize_image(img)

        paginas.append((f"{filename} (P{i+1})", img))

    doc.close()

    return paginas


# ==========================================================
# DETECTAR PDF GRANDE
# ==========================================================

def pdf_is_large(file_bytes: bytes) -> bool:
    """
    Detecta si un PDF tiene más páginas que el límite permitido.
    """

    try:
        import fitz
    except ModuleNotFoundError:
        return False

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    total = len(doc)
    doc.close()

    return total > MAX_PDF_PAGES
