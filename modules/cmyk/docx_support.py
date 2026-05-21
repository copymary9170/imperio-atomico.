from __future__ import annotations

import io
import re
import textwrap
import zipfile
from typing import List, Tuple
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

from modules.cmyk.analyzer import normalizar_imagenes

MAX_OFFICE_PAGES = 100
PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
PAGE_MARGIN = 90
LINE_HEIGHT = 28
CHARS_PER_LINE = 92


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


def _xml_text(xml: bytes) -> str:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    texts = []
    for node in root.iter():
        tag = str(node.tag).split("}")[-1]
        if tag in {"t", "v"} and node.text:
            texts.append(str(node.text))
    return " ".join(texts)


def _render_text_pages(nombre: str, texto: str, etiqueta: str = "texto") -> List[Tuple[str, Image.Image]]:
    texto = str(texto or "").strip()
    if not texto:
        return []
    lines = []
    for paragraph in texto.splitlines() or [texto]:
        lines.extend(textwrap.wrap(paragraph, width=CHARS_PER_LINE) or [""])
    max_lines = max(1, int((PAGE_HEIGHT - PAGE_MARGIN * 2) / LINE_HEIGHT))
    paginas: List[Tuple[str, Image.Image]] = []
    font = _font(18)
    for start in range(0, min(len(lines), max_lines * MAX_OFFICE_PAGES), max_lines):
        img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
        draw = ImageDraw.Draw(img)
        y = PAGE_MARGIN
        for line in lines[start:start + max_lines]:
            draw.text((PAGE_MARGIN, y), line, fill="black", font=font)
            y += LINE_HEIGHT
        paginas.append((f"{nombre} ({etiqueta} P{len(paginas) + 1})", _optimize_image(img.convert("CMYK"))))
    return paginas


def _media_pages(zf: zipfile.ZipFile, nombre: str, prefixes: tuple[str, ...]) -> List[Tuple[str, Image.Image]]:
    paginas: List[Tuple[str, Image.Image]] = []
    media_files = [n for n in zf.namelist() if n.startswith(prefixes)]
    for index, media_name in enumerate(media_files[:MAX_OFFICE_PAGES], start=1):
        try:
            media_bytes = zf.read(media_name)
            with Image.open(io.BytesIO(media_bytes)) as img_obj:
                paginas.append((f"{nombre} (imagen {index})", _optimize_image(img_obj.convert("CMYK"))))
        except Exception:
            continue
    return paginas


def _normalizar_docx(nombre: str, bytes_data: bytes) -> List[Tuple[str, Image.Image]]:
    paginas: List[Tuple[str, Image.Image]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(bytes_data)) as zf:
            texto = _xml_text(zf.read("word/document.xml")) if "word/document.xml" in zf.namelist() else ""
            paginas.extend(_render_text_pages(nombre, texto, "texto Word"))
            paginas.extend(_media_pages(zf, nombre, ("word/media/",)))
    except zipfile.BadZipFile as exc:
        raise ValueError("El archivo Word no parece ser un DOCX válido.") from exc
    if not paginas:
        raise ValueError("El DOCX no contiene texto o imágenes analizables.")
    return paginas[:MAX_OFFICE_PAGES]


def _normalizar_pptx(nombre: str, bytes_data: bytes) -> List[Tuple[str, Image.Image]]:
    paginas: List[Tuple[str, Image.Image]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(bytes_data)) as zf:
            slide_names = sorted([n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)])
            for idx, slide_name in enumerate(slide_names[:MAX_OFFICE_PAGES], start=1):
                texto = _xml_text(zf.read(slide_name))
                if texto.strip():
                    paginas.extend(_render_text_pages(f"{nombre} (diapositiva {idx})", texto, "texto PPT"))
            paginas.extend(_media_pages(zf, nombre, ("ppt/media/",)))
    except zipfile.BadZipFile as exc:
        raise ValueError("El archivo PowerPoint no parece ser un PPTX válido.") from exc
    if not paginas:
        raise ValueError("El PPTX no contiene texto o imágenes analizables.")
    return paginas[:MAX_OFFICE_PAGES]


def _normalizar_xlsx(nombre: str, bytes_data: bytes) -> List[Tuple[str, Image.Image]]:
    paginas: List[Tuple[str, Image.Image]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(bytes_data)) as zf:
            names = zf.namelist()
            shared_strings = []
            if "xl/sharedStrings.xml" in names:
                shared_raw = _xml_text(zf.read("xl/sharedStrings.xml"))
                shared_strings = shared_raw.split()
            sheet_names = sorted([n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)])
            for idx, sheet_name in enumerate(sheet_names[:MAX_OFFICE_PAGES], start=1):
                texto = _xml_text(zf.read(sheet_name))
                if shared_strings:
                    texto = f"{texto}\n" + " ".join(shared_strings[:1500])
                if texto.strip():
                    paginas.extend(_render_text_pages(f"{nombre} (hoja {idx})", texto, "texto Excel"))
            paginas.extend(_media_pages(zf, nombre, ("xl/media/",)))
    except zipfile.BadZipFile as exc:
        raise ValueError("El archivo Excel no parece ser un XLSX válido.") from exc
    if not paginas:
        raise ValueError("El XLSX no contiene texto o imágenes analizables.")
    return paginas[:MAX_OFFICE_PAGES]


def normalizar_archivo_impresion(archivo):
    """Normaliza PDF, Office moderno e imágenes a páginas CMYK analizables."""
    nombre = getattr(archivo, "name", "archivo")
    nombre_lower = nombre.lower()

    if nombre_lower.endswith((".docx", ".pptx", ".xlsx")):
        bytes_data = archivo.read()
        if not bytes_data:
            raise ValueError(f"El archivo '{nombre}' está vacío o no se pudo leer.")
        if nombre_lower.endswith(".docx"):
            return _normalizar_docx(nombre, bytes_data)
        if nombre_lower.endswith(".pptx"):
            return _normalizar_pptx(nombre, bytes_data)
        return _normalizar_xlsx(nombre, bytes_data)

    if nombre_lower.endswith((".doc", ".ppt", ".xls")):
        raise ValueError("Los formatos antiguos .doc/.ppt/.xls no se analizan directo. Guárdalos como .docx/.pptx/.xlsx o PDF.")

    return normalizar_imagenes(archivo)
