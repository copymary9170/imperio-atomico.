from __future__ import annotations

import io
import textwrap
import zipfile
from typing import List, Tuple
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

from modules.cmyk.analyzer import normalizar_imagenes

MAX_DOCX_PAGES = 80
DOCX_PAGE_WIDTH = 1240
DOCX_PAGE_HEIGHT = 1754
DOCX_MARGIN = 90
DOCX_LINE_HEIGHT = 28
DOCX_CHARS_PER_LINE = 92


def _font(size: int = 18):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _optimize_image(img: Image.Image) -> Image.Image:
    if img.width > 1500 or img.height > 1500:
        img = img.copy()
        img.thumbnail((1500, 1500))
    return img


def _extract_docx_text(zf: zipfile.ZipFile) -> str:
    try:
        xml = zf.read("word/document.xml")
    except KeyError:
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for p in root.findall(".//w:p", ns):
        texts = [node.text or "" for node in p.findall(".//w:t", ns)]
        if texts:
            paragraphs.append("".join(texts))
    return "\n".join(paragraphs)


def _render_text_pages(nombre: str, texto: str) -> List[Tuple[str, Image.Image]]:
    texto = str(texto or "").strip()
    if not texto:
        return []
    lines = []
    for paragraph in texto.splitlines():
        lines.extend(textwrap.wrap(paragraph, width=DOCX_CHARS_PER_LINE) or [""])
    max_lines = max(1, int((DOCX_PAGE_HEIGHT - DOCX_MARGIN * 2) / DOCX_LINE_HEIGHT))
    paginas: List[Tuple[str, Image.Image]] = []
    font = _font(18)
    for start in range(0, min(len(lines), max_lines * MAX_DOCX_PAGES), max_lines):
        img = Image.new("RGB", (DOCX_PAGE_WIDTH, DOCX_PAGE_HEIGHT), "white")
        draw = ImageDraw.Draw(img)
        y = DOCX_MARGIN
        for line in lines[start:start + max_lines]:
            draw.text((DOCX_MARGIN, y), line, fill="black", font=font)
            y += DOCX_LINE_HEIGHT
        paginas.append((f"{nombre} (texto P{len(paginas) + 1})", _optimize_image(img.convert("CMYK"))))
    return paginas


def _normalizar_docx(nombre: str, bytes_data: bytes) -> List[Tuple[str, Image.Image]]:
    paginas: List[Tuple[str, Image.Image]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(bytes_data)) as zf:
            texto = _extract_docx_text(zf)
            paginas.extend(_render_text_pages(nombre, texto))

            media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
            for index, media_name in enumerate(media_files[:MAX_DOCX_PAGES], start=1):
                try:
                    media_bytes = zf.read(media_name)
                    with Image.open(io.BytesIO(media_bytes)) as img_obj:
                        paginas.append((f"{nombre} (imagen {index})", _optimize_image(img_obj.convert("CMYK"))))
                except Exception:
                    continue
    except zipfile.BadZipFile as exc:
        raise ValueError("El archivo Word no parece ser un DOCX válido.") from exc

    if not paginas:
        raise ValueError("El DOCX no contiene texto o imágenes analizables.")
    return paginas[:MAX_DOCX_PAGES]


def normalizar_archivo_impresion(archivo):
    """Normaliza PDF, DOCX, PNG y JPG/JPEG a páginas CMYK analizables."""
    nombre = getattr(archivo, "name", "archivo")
    nombre_lower = nombre.lower()

    if nombre_lower.endswith(".docx"):
        bytes_data = archivo.read()
        if not bytes_data:
            raise ValueError(f"El archivo '{nombre}' está vacío o no se pudo leer.")
        return _normalizar_docx(nombre, bytes_data)

    if nombre_lower.endswith(".doc"):
        raise ValueError("Los .doc antiguos no se analizan directo. Guárdalo como .docx o PDF y vuelve a cargarlo.")

    return normalizar_imagenes(archivo)
