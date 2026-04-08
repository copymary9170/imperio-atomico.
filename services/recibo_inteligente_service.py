from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text

logger = logging.getLogger(__name__)


@dataclass
class ReceiptHeader:
    proveedor: str = ""
    fecha: str | None = None
    numero_factura: str = ""
    moneda: str = "USD"
    subtotal: float = 0.0
    total: float = 0.0


def normalizar_texto_producto(texto: str) -> str:
    txt = unicodedata.normalize("NFD", str(texto or ""))
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    txt = txt.lower()
    txt = re.sub(r"(\d+)\s*(kg|gr|g|lt|l|ml)\b", r"\1 ", txt)
    txt = re.sub(r"\bx\s*(\d+)\b", r" \1 ", txt)
    txt = re.sub(r"\b(und|unidad|unidades|kg|gr|g|lt|l|ml|x|pack|paq|pz|pza)\b", " ", txt)
    txt = re.sub(r"[^a-z0-9 ]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def extract_text_from_receipt(file_obj) -> str:
    """Extrae texto desde PDF o imagen.

    Para imágenes se deja una interfaz desacoplada para conectar OCR real luego.
    """
    if file_obj is None:
        return ""

    name = str(getattr(file_obj, "name", "")).lower()
    mime = str(getattr(file_obj, "type", "")).lower()
    data = file_obj.getvalue()

    if name.endswith(".pdf") or "pdf" in mime:
        for lib in ("pypdf", "PyPDF2"):
            try:
                module = __import__(lib)
                reader_cls = getattr(module, "PdfReader", None)
                if reader_cls is None:
                    continue
                reader = reader_cls(io.BytesIO(data))
                pages = []
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
                text = "\n".join(pages).strip()
                if text:
                    return text
            except Exception as exc:
                logger.warning("Fallo extracción PDF con %s: %s", lib, exc)

    # Placeholder desacoplado para OCR real (Tesseract, PaddleOCR, etc.)
    logger.info("No OCR habilitado para archivo %s. Se retorna texto vacío.", name)
    return ""


def _parse_money(value: str) -> float:
    txt = str(value or "").strip()
    txt = txt.replace("Bs.", "").replace("Bs", "").replace("$", "")
    txt = txt.replace(" ", "")
    if txt.count(",") > 0 and txt.count(".") > 0:
        txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def parse_receipt_text(text: str) -> tuple[ReceiptHeader, list[dict[str, Any]]]:
    lines = [clean_text(ln) for ln in str(text or "").splitlines() if clean_text(ln)]
    header = ReceiptHeader()
    items: list[dict[str, Any]] = []

    if not lines:
        return header, items

    header.proveedor = lines[0][:120]

    full_text = "\n".join(lines)
    if re.search(r"\b(bs|bolivar|bolivares)\b", full_text, re.IGNORECASE):
        header.moneda = "VES"
    elif "$" in full_text or "usd" in full_text.lower():
        header.moneda = "USD"

    date_match = re.search(r"(\d{2}[/-]\d{2}[/-]\d{2,4})", full_text)
    if date_match:
        raw = date_match.group(1).replace("-", "/")
        dd, mm, yy = raw.split("/")
        if len(yy) == 2:
            yy = f"20{yy}"
        try:
            header.fecha = date(int(yy), int(mm), int(dd)).isoformat()
        except ValueError:
            header.fecha = None

    factura_match = re.search(r"(?:factura|nro|ref|control)\s*[:#-]?\s*([a-zA-Z0-9-]{4,})", full_text, re.IGNORECASE)
    if factura_match:
        header.numero_factura = factura_match.group(1)

    subtotal_match = re.search(r"subtotal\s*[: ]\s*([\d\.,]+)", full_text, re.IGNORECASE)
    total_match = re.search(r"\btotal\s*[: ]\s*([\d\.,]+)", full_text, re.IGNORECASE)
    if subtotal_match:
        header.subtotal = _parse_money(subtotal_match.group(1))
    if total_match:
        header.total = _parse_money(total_match.group(1))

    product_patterns = [
        re.compile(r"^(?P<desc>.+?)\s+(?P<qty>\d+[\.,]?\d*)\s+(?P<unit>\d+[\.,]?\d*)\s+(?P<line>\d+[\.,]?\d*)$"),
        re.compile(r"^(?P<qty>\d+[\.,]?\d*)\s+[xX]\s+(?P<desc>.+?)\s+(?P<line>\d+[\.,]?\d*)$"),
    ]

    ignore_tokens = ("r.i.f", "cajero", "telefono", "gracias", "iva", "subtotal", "total", "vuelto", "efectivo")
    for ln in lines:
        low = ln.lower()
        if any(tok in low for tok in ignore_tokens):
            continue
        for pattern in product_patterns:
            m = pattern.search(ln)
            if not m:
                continue
            desc = clean_text(m.groupdict().get("desc", ""))
            if len(desc) < 3:
                continue
            qty = _parse_money(m.groupdict().get("qty", "1")) or 1.0
            unit = _parse_money(m.groupdict().get("unit", "0"))
            line_total = _parse_money(m.groupdict().get("line", "0"))
            if unit <= 0 and line_total > 0 and qty > 0:
                unit = line_total / qty
            items.append(
                {
                    "descripcion_detectada": desc,
                    "cantidad": float(qty),
                    "precio_unitario_detectado": float(unit),
                    "precio_linea_detectado": float(line_total or (unit * qty)),
                }
            )
            break

    return header, items


def load_existing_products() -> pd.DataFrame:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, nombre, sku, COALESCE(unidad, 'unidad') AS unidad, COALESCE(categoria, 'General') AS categoria
            FROM inventario
            WHERE COALESCE(estado,'activo')='activo'
            """
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def _load_aliases() -> list[dict[str, Any]]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT inventario_id, alias_normalizado, alias_original
            FROM mapeos_alias_productos
            WHERE COALESCE(activo,1)=1
            """
        ).fetchall()
    return [dict(r) for r in rows]


def suggest_product_match(nombre_detectado: str, threshold_auto: float = 0.88, threshold_review: float = 0.70) -> dict[str, Any]:
    detected_norm = normalizar_texto_producto(nombre_detectado)
    inv = load_existing_products()
    aliases = _load_aliases()

    best: dict[str, Any] = {
        "inventario_id": None,
        "producto_sugerido": "",
        "score": 0.0,
        "decision": "nuevo",
    }

    if inv.empty or not detected_norm:
        return best

    for _, row in inv.iterrows():
        candidate_norm = normalizar_texto_producto(str(row["nombre"]))
        score = SequenceMatcher(None, detected_norm, candidate_norm).ratio()
        if score > best["score"]:
            best = {
                "inventario_id": int(row["id"]),
                "producto_sugerido": str(row["nombre"]),
                "score": float(score),
                "decision": "auto" if score >= threshold_auto else ("revisar" if score >= threshold_review else "nuevo"),
            }

    for alias in aliases:
        alias_norm = normalizar_texto_producto(alias.get("alias_normalizado") or alias.get("alias_original") or "")
        score = SequenceMatcher(None, detected_norm, alias_norm).ratio()
        if score > best["score"]:
            inv_row = inv[inv["id"] == int(alias["inventario_id"])]
            producto = str(inv_row.iloc[0]["nombre"]) if not inv_row.empty else ""
            best = {
                "inventario_id": int(alias["inventario_id"]),
                "producto_sugerido": producto,
                "score": float(score),
                "decision": "auto" if score >= threshold_auto else ("revisar" if score >= threshold_review else "nuevo"),
            }

    return best


def build_receipt_review_df(items: list[dict[str, Any]], threshold_auto: float = 0.88, threshold_review: float = 0.70) -> pd.DataFrame:
    rows = []
    for item in items:
        suggestion = suggest_product_match(str(item.get("descripcion_detectada", "")), threshold_auto, threshold_review)
        qty = float(item.get("cantidad") or 0)
        unit = float(item.get("precio_unitario_detectado") or 0)
        line_total = float(item.get("precio_linea_detectado") or (qty * unit))
        rows.append(
            {
                "descripcion_detectada": item.get("descripcion_detectada", ""),
                "cantidad": qty,
                "precio_unitario_detectado": unit,
                "precio_linea_detectado": line_total,
                "inventario_id": suggestion["inventario_id"] or 0,
                "producto_sugerido": suggestion["producto_sugerido"],
                "score_match": round(float(suggestion["score"]), 4),
                "decision": suggestion["decision"],
                "crear_producto_nuevo": suggestion["decision"] == "nuevo",
                "nombre_producto_nuevo": item.get("descripcion_detectada", ""),
                "delivery_manual_usd": 0.0,
                "guardar": True,
            }
        )
    return pd.DataFrame(rows)


def allocate_delivery(df: pd.DataFrame, delivery_usd: float, metodo: str) -> pd.DataFrame:
    out = df.copy()
    out["delivery_asignado_usd"] = 0.0
    total_delivery = float(delivery_usd or 0.0)
    if total_delivery <= 0 or out.empty:
        return out

    if metodo == "manual":
        manual_sum = float(out["delivery_manual_usd"].fillna(0).sum())
        if manual_sum > 0:
            out["delivery_asignado_usd"] = out["delivery_manual_usd"].fillna(0) * (total_delivery / manual_sum)
        return out

    if metodo == "proporcional_cantidad":
        basis = out["cantidad"].fillna(0)
    else:
        basis = out["precio_linea_detectado"].fillna(0)

    denom = float(basis.sum())
    if denom <= 0:
        out["delivery_asignado_usd"] = total_delivery / max(len(out), 1)
        return out

    out["delivery_asignado_usd"] = basis * (total_delivery / denom)
    return out


def save_alias_producto(inventario_id: int, alias_original: str, usuario: str = "sistema") -> None:
    alias_norm = normalizar_texto_producto(alias_original)
    if not alias_norm:
        return
    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id FROM mapeos_alias_productos WHERE inventario_id=? AND alias_normalizado=?",
            (int(inventario_id), alias_norm),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE mapeos_alias_productos SET alias_original=?, activo=1, actualizado_por=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (alias_original, usuario, int(row["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO mapeos_alias_productos(inventario_id, alias_original, alias_normalizado, creado_por, actualizado_por, activo)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (int(inventario_id), alias_original, alias_norm, usuario, usuario),
            )


def invoice_already_processed(numero_factura: str, proveedor_id: int | None, fecha_compra: str | None) -> bool:
    if not clean_text(numero_factura):
        return False
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT id FROM recibos_procesados
            WHERE numero_factura=?
              AND COALESCE(proveedor_id,0)=COALESCE(?,0)
              AND COALESCE(fecha_compra,'')=COALESCE(?, '')
            LIMIT 1
            """,
            (clean_text(numero_factura), proveedor_id, fecha_compra),
        ).fetchone()
    return bool(row)


def save_processed_purchase(
    usuario: str,
    header: ReceiptHeader,
    proveedor_id: int | None,
    df_review: pd.DataFrame,
    tasa_cambio: float,
    delivery_usd: float,
    create_product_fn,
    registrar_compra_fn,
) -> dict[str, Any]:
    """Persistencia desacoplada: recibe callbacks del módulo actual."""
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO recibos_procesados(
                fecha_compra, proveedor_id, proveedor_detectado, numero_factura, moneda_detectada,
                subtotal_detectado, total_detectado, tasa_cambio_usada, delivery_usd, texto_extraido,
                usuario
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                header.fecha,
                proveedor_id,
                clean_text(header.proveedor),
                clean_text(header.numero_factura),
                clean_text(header.moneda) or "USD",
                float(header.subtotal or 0.0),
                float(header.total or 0.0),
                float(tasa_cambio or 1.0),
                float(delivery_usd or 0.0),
                "",
                usuario,
            ),
        )
        recibo_id = int(cur.lastrowid)

    processed = 0
    for _, row in df_review.iterrows():
        if not bool(row.get("guardar", True)):
            continue

        inventario_id = int(row.get("inventario_id") or 0)
        crear_nuevo = bool(row.get("crear_producto_nuevo", False)) or inventario_id <= 0
        if crear_nuevo:
            inventario_id = int(
                create_product_fn(
                    usuario=usuario,
                    sku_base=str(row.get("nombre_producto_nuevo") or row.get("descripcion_detectada") or "nuevo"),
                    nombre=str(row.get("nombre_producto_nuevo") or row.get("descripcion_detectada") or "Producto nuevo"),
                    categoria="General",
                    unidad="unidad",
                    minimo=0.0,
                    costo_inicial=float(row.get("precio_unitario_final_usd") or row.get("precio_unitario_detectado") or 0.0),
                    precio_inicial=float(row.get("precio_unitario_final_usd") or row.get("precio_unitario_detectado") or 0.0) * 1.35,
                )
            )

        qty = float(row.get("cantidad") or 0.0)
        base_line_usd = float(row.get("precio_linea_detectado") or (qty * float(row.get("precio_unitario_detectado") or 0.0)))
        delivery_line_usd = float(row.get("delivery_asignado_usd") or 0.0)

        compra_id = int(
            registrar_compra_fn(
                usuario=usuario,
                inventario_id=inventario_id,
                cantidad=max(qty, 0.0001),
                costo_base_usd=max(base_line_usd, 0.0001),
                proveedor_id=proveedor_id,
                proveedor_nombre=header.proveedor,
                impuestos_pct=0.0,
                delivery_usd=max(delivery_line_usd, 0.0),
                tasa_usada=float(tasa_cambio or 1.0),
                moneda_pago=header.moneda,
                metodo_pago="transferencia",
                referencia_extra=f"Recibo inteligente #{recibo_id}",
            )
        )

        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO compras_importadas_items(
                    recibo_id, compra_id, inventario_id, descripcion_detectada, cantidad,
                    precio_unitario_detectado, precio_linea_detectado, delivery_asignado_usd,
                    costo_unitario_final_usd, costo_total_final_usd, costo_unitario_final_bs, costo_total_final_bs,
                    score_match, decision_match
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recibo_id,
                    compra_id,
                    inventario_id,
                    clean_text(row.get("descripcion_detectada")),
                    qty,
                    float(row.get("precio_unitario_detectado") or 0.0),
                    base_line_usd,
                    delivery_line_usd,
                    float(row.get("precio_unitario_final_usd") or 0.0),
                    float(row.get("precio_linea_final_usd") or 0.0),
                    float(row.get("precio_unitario_final_bs") or 0.0),
                    float(row.get("precio_linea_final_bs") or 0.0),
                    float(row.get("score_match") or 0.0),
                    clean_text(row.get("decision") or ""),
                ),
            )

        save_alias_producto(inventario_id, str(row.get("descripcion_detectada") or ""), usuario=usuario)
        processed += 1

    return {"recibo_id": recibo_id, "lineas_procesadas": processed}
