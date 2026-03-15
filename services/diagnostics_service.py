from __future__ import annotations

import re
import json
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Any

from database.connection import db_transaction


_COLOR_ORDER = ("Cyan", "Magenta", "Yellow", "Black")
COLOR_KEYS = ("black", "cyan", "magenta", "yellow")
MEASUREMENT_SOURCES = {"photo", "software", "report", "manual"}
ESTIMATION_MODES = {"none", "visual", "software", "manual"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
INK_SYSTEM_TYPES = {"factory_tank", "cartridge", "adapted_external_tank"}
INK_USAGE_TYPES = {"standard", "sublimation"}
DIAGNOSTIC_ACCURACY = {"exact", "estimated", "mixed"}
CRITICAL_LEVEL = 10
LOW_LEVEL = 25
PERCENT_REGEX = re.compile(r"(\d{1,3})\s*%")
COLOR_PATTERNS = {
    "Cyan": [re.compile(r"(?:cyan|cian)\D{0,20}(\d{1,3})\s*%", re.I), re.compile(r"(\d{1,3})\s*%\D{0,20}(?:cyan|cian)", re.I)],
    "Magenta": [re.compile(r"magenta\D{0,20}(\d{1,3})\s*%", re.I), re.compile(r"(\d{1,3})\s*%\D{0,20}magenta", re.I)],
    "Yellow": [re.compile(r"(?:yellow|amarillo)\D{0,20}(\d{1,3})\s*%", re.I), re.compile(r"(\d{1,3})\s*%\D{0,20}(?:yellow|amarillo)", re.I)],
    "Black": [re.compile(r"(?:black|negro|bk)\D{0,20}(\d{1,3})\s*%", re.I), re.compile(r"(\d{1,3})\s*%\D{0,20}(?:black|negro|bk)", re.I)],
}
COUNTER_PATTERNS = [
    re.compile(r"(?:total\s*(?:(?:de|do|ds)\s*)?(?:pages?|pags?|paginas?|p[aá]ginas?)\s*(?:imp\w*)?)\D{0,30}([\d][\d\s.,]{0,15})", re.I),
    re.compile(r"(?:pages?\s*printed|printed\s*pages?)\D{0,15}([\d][\d\s.,]{0,15})", re.I),
    re.compile(r"(?:total\s*(?:prints?|impresiones?)|print\s*count|contador)\D{0,10}([\d][\d\s.,]{0,15})", re.I),
    re.compile(r"(?:pages?|pags?|paginas?|p[aá]ginas?)\D{0,30}([\d][\d\s.,]{0,15})", re.I),
]
IGNORE_COUNTER_CONTEXT = [
    re.compile(r"\bpin\b", re.I),
    re.compile(r"serial", re.I),
    re.compile(r"imei", re.I),
]
COMPONENT_LIFE_PATTERNS = {
    "cabezal": [re.compile(r"(?:head|cabezal)[^\d]{0,20}(\d{1,3})\s*%", re.I)],
    "rodillo": [re.compile(r"(?:roller|rodillo(?:s)?)[^\d]{0,20}(\d{1,3})\s*%", re.I)],
    "almohadillas": [re.compile(r"(?:pad(?:s)?|almohadilla(?:s)?|waste\s*ink)[^\d]{0,20}(\d{1,3})\s*%", re.I)],
}


def _normalizar_texto_busqueda(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = re.sub(r"[^a-zA-Z0-9]+", " ", base).strip().lower()
    return re.sub(r"\s+", " ", base)


def _normalizar_numero_contador(raw: str) -> int | None:
    txt = str(raw or "").strip()
    if not txt:
        return None

    txt = re.sub(r"[^\d.,]", "", txt)
    if not txt or not re.search(r"\d", txt):
        return None

    if "," in txt and "." in txt:
        last_sep = "," if txt.rfind(",") > txt.rfind(".") else "."
        decimal_pos = txt.rfind(last_sep)
        dec_part = txt[decimal_pos + 1 :]
        if 0 < len(dec_part) <= 2:
            txt = txt[:decimal_pos]
    elif "," in txt:
        chunks = txt.split(",")
        if len(chunks) > 1 and len(chunks[-1]) <= 2:
            txt = "".join(chunks[:-1])
        else:
            txt = "".join(chunks)
    elif "." in txt:
        chunks = txt.split(".")
        if len(chunks) > 1 and len(chunks[-1]) <= 2:
            txt = "".join(chunks[:-1])
        else:
            txt = "".join(chunks)

    digits = re.sub(r"\D", "", txt)
    if not digits:
        return None

    try:
        valor = int(digits)
    except ValueError:
        return None

    return valor if valor > 0 else None


def _extraer_numeros_linea(linea: str) -> list[int]:
    candidatos = re.findall(r"\d[\d\s.,]{0,15}", linea or "")
    valores: list[int] = []
    for raw in candidatos:
        valor = _normalizar_numero_contador(raw)
        if valor is not None:
            valores.append(valor)
            valores.append(valor)
    return valores


def _linea_parece_contador(linea: str) -> bool:
    normalizada = _normalizar_texto_busqueda(linea)
    if not normalizada:
        return False

    tiene_paginas = "pag" in normalizada or "page" in normalizada
    tiene_impresion = "imp" in normalizada or "print" in normalizada or "contador" in normalizada
    return tiene_paginas and tiene_impresion


def _clamp_percentage(value: float | int | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_color(color: str) -> str:
    txt = str(color or "").strip().lower()
    aliases = {
        "bk": "black",
        "negro": "black",
        "cian": "cyan",
        "amarillo": "yellow",
    }
    return aliases.get(txt, txt)


def extraer_desgaste_componentes(texto_ocr: str | None) -> dict[str, float | None]:
    texto = str(texto_ocr or "")
    componentes: dict[str, float | None] = {"cabezal": None, "rodillo": None, "almohadillas": None}
    for nombre, patrones in COMPONENT_LIFE_PATTERNS.items():
        for patron in patrones:
            match = patron.search(texto)
            if not match:
                continue
            try:
                componentes[nombre] = _clamp_percentage(float(match.group(1)))
            except Exception:
                componentes[nombre] = None
            break
    return componentes


class DiagnosticsService:
    """Utility methods to infer diagnostic metrics from OCR signals."""

    @staticmethod
    def merge_levels(
        capacidad: dict[str, float],
        porcentajes_texto: list[float] | None = None,
        porcentajes_foto: dict[str, float] | None = None,
    ) -> dict[str, float | None]:
        porcentajes_texto = list(porcentajes_texto or [])
        porcentajes_foto = dict(porcentajes_foto or {})

        merged: dict[str, float | None] = {}
        for idx, color in enumerate(_COLOR_ORDER):
            pct_text = _clamp_percentage(porcentajes_texto[idx]) if idx < len(porcentajes_texto) else None
            pct_foto = _clamp_percentage(porcentajes_foto.get(color))
            pct = pct_foto if pct_foto is not None else pct_text

            if pct is None:
                merged[color] = None
                continue

            capacidad_color = float(capacidad.get(color, 0.0) or 0.0)
            merged[color] = round((capacidad_color * pct) / 100.0, 2)
        return merged

    @staticmethod
    def resolve_head_life(
        detected_value: float | int | None,
        porcentajes_foto: dict[str, float] | None = None,
    ) -> float:
        detected = _clamp_percentage(detected_value)
        if detected is not None:
            return float(detected)

        foto = dict(porcentajes_foto or {})
        valid = [_clamp_percentage(v) for v in foto.values()]
        valid = [float(v) for v in valid if v is not None]
        if valid:
            return round(sum(valid) / len(valid), 2)

        return 100.0

    @staticmethod
    def summarize(resultados: dict[str, float | None], vida_cabezal_pct: float | int | None) -> dict[str, Any]:
        valores = [float(v) for v in resultados.values() if v is not None]
        min_ml = min(valores) if valores else 0.0
        max_ml = max(valores) if valores else 0.0

        if not valores:
            estado_tintas = "Sin datos"
        elif min_ml <= CRITICAL_LEVEL:
            estado_tintas = "Crítico"
        elif min_ml <= LOW_LEVEL:
            estado_tintas = "Bajo"
        else:
            estado_tintas = "Óptimo"

        vida = _clamp_percentage(vida_cabezal_pct)
        if vida is None:
            estado_cabezal = "Sin datos"
            vida = 100.0
        elif vida <= CRITICAL_LEVEL:
            estado_cabezal = "Crítico"
        elif vida <= LOW_LEVEL:
            estado_cabezal = "Bajo"
        else:
            estado_cabezal = "Óptimo"

        return {
            "estado_tintas": estado_tintas,
            "estado_cabezal": estado_cabezal,
            "vida_cabezal_pct": float(vida),
            "min_ml": round(min_ml, 2),
            "max_ml": round(max_ml, 2),
        }


def _extraer_porcentajes_por_color(texto: str) -> list[float | None]:
    salida: list[float | None] = []
    for color in _COLOR_ORDER:
        valor: float | None = None
        for patron in COLOR_PATTERNS[color]:
            match = patron.search(texto)
            if not match:
                continue
            valor = _clamp_percentage(float(match.group(1)))
            if valor is not None:
                break
        salida.append(valor)
    return salida


def extraer_texto_diagnostico(texto_ocr: str | None) -> dict[str, Any]:
    texto = str(texto_ocr or "")
    porcentajes_globales = [_clamp_percentage(float(v)) for v in PERCENT_REGEX.findall(texto)]
    porcentajes_color = _extraer_porcentajes_por_color(texto)

    porcentajes: list[float] = []
    usados_global = 0
    for val_color in porcentajes_color:
        if val_color is not None:
            porcentajes.append(float(val_color))
            continue

        while usados_global < len(porcentajes_globales):
            candidato = porcentajes_globales[usados_global]
            usados_global += 1
            if candidato is None:
                continue
            porcentajes.append(float(candidato))
            break

    while len(porcentajes) < len(_COLOR_ORDER) and usados_global < len(porcentajes_globales):
        candidato = porcentajes_globales[usados_global]
        usados_global += 1
        if candidato is not None:
            porcentajes.append(float(candidato))

    return {
        "porcentajes": porcentajes,
        "contadores": extraer_contador_impresiones(texto),
    }


def extraer_contador_impresiones(texto_ocr: str | None) -> dict[str, int]:
    texto = str(texto_ocr or "")
    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]

    for linea in lineas:
        if any(p.search(linea) for p in IGNORE_COUNTER_CONTEXT):
            continue

        if _linea_parece_contador(linea):
            candidatos_linea = _extraer_numeros_linea(linea)
            if candidatos_linea:
                return {"contador_impresiones": max(candidatos_linea)}

        for patron in COUNTER_PATTERNS:
            match = patron.search(linea)
            if match:
                candidatos = _extraer_numeros_linea(match.group(1))
                if candidatos:
                    return {"contador_impresiones": max(candidatos)}

    for patron in COUNTER_PATTERNS:

        match = patron.search(texto)
        if match:
            candidatos = _extraer_numeros_linea(match.group(1))
            if candidatos:
                return {"contador_impresiones": max(candidatos)}

    lineas_sospechosas = [
        ln
        for ln in lineas
        if not any(p.search(ln) for p in IGNORE_COUNTER_CONTEXT)
        and ("pag" in _normalizar_texto_busqueda(ln) or "page" in _normalizar_texto_busqueda(ln) or "print" in _normalizar_texto_busqueda(ln))
    ]
    numeros: list[int] = []
    for linea in lineas_sospechosas:
        numeros.extend(_extraer_numeros_linea(linea))

    return {"contador_impresiones": max(numeros) if numeros else 0}


def analizar_hoja_diagnostico(
    texto_ocr: str | None,
    capacidad: dict[str, float],
    porcentajes_foto: dict[str, float] | None = None,
    vida_cabezal_detectada: float | None = None,
) -> dict[str, Any]:
    extraido = extraer_texto_diagnostico(texto_ocr)
    resultados = DiagnosticsService.merge_levels(
        capacidad=capacidad,
        porcentajes_texto=extraido.get("porcentajes", []),
        porcentajes_foto=porcentajes_foto,
    )
    componentes = extraer_desgaste_componentes(texto_ocr)
    vida_cabezal = DiagnosticsService.resolve_head_life(
        detected_value=vida_cabezal_detectada if vida_cabezal_detectada is not None else componentes.get("cabezal"),
        porcentajes_foto=porcentajes_foto,
    )
    componentes["cabezal"] = vida_cabezal
    resumen = DiagnosticsService.summarize(resultados=resultados, vida_cabezal_pct=vida_cabezal)
    return {
        "resultados": resultados,
        "vida_cabezal_pct": vida_cabezal,
        "desgaste_componentes": componentes,
        "contador_impresiones": int(extraido.get("contadores", {}).get("contador_impresiones", 0)),
        "resumen": resumen,
    }


def listar_impresoras_activas() -> list[dict[str, Any]]:
    with db_transaction() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id, equipo, modelo, categoria, unidad
                FROM activos
                WHERE COALESCE(activo, 1) = 1
                  AND (
                    lower(COALESCE(categoria, '')) LIKE '%impres%'
                    OR lower(COALESCE(unidad, '')) LIKE '%impres%'
                    OR lower(COALESCE(equipo, '')) LIKE '%epson%'
                    OR lower(COALESCE(modelo, '')) LIKE '%epson%'
                    OR lower(COALESCE(equipo, '')) LIKE '%l805%'
                    OR lower(COALESCE(equipo, '')) LIKE '%l3250%'
                    OR lower(COALESCE(modelo, '')) LIKE '%l805%'
                    OR lower(COALESCE(modelo, '')) LIKE '%l3250%'
                  )
                ORDER BY id DESC
                """
            ).fetchall()
        except Exception:
            return []

    return [dict(r) for r in rows]


def listar_activos_disponibles() -> list[dict[str, Any]]:
    with db_transaction() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id, equipo, modelo, categoria, unidad
                FROM activos
                WHERE COALESCE(activo, 1) = 1
                ORDER BY id DESC
                """
            ).fetchall()
        except Exception:
            return []

    return [dict(r) for r in rows]


def _ensure_diagnostics_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL UNIQUE,
            brand TEXT,
            model TEXT,
            serial_number TEXT,
            ink_system_type TEXT NOT NULL DEFAULT 'factory_tank',
            ink_usage_type TEXT NOT NULL DEFAULT 'standard',
            head_system_type TEXT,
            valuation_method TEXT,
            purchase_value REAL DEFAULT 0,
            current_value REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            initial_fill_known INTEGER NOT NULL DEFAULT 1,
            estimation_mode TEXT NOT NULL DEFAULT 'none',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES activos(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_tank_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            capacity_ml REAL NOT NULL DEFAULT 0,
            source_type TEXT DEFAULT 'manual',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(printer_id, color),
            FOREIGN KEY (printer_id) REFERENCES printers(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            diagnostic_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            total_pages INTEGER DEFAULT 0,
            color_pages INTEGER DEFAULT 0,
            bw_pages INTEGER DEFAULT 0,
            borderless_pages INTEGER DEFAULT 0,
            scanned_pages INTEGER DEFAULT 0,
            diagnostic_accuracy TEXT NOT NULL DEFAULT 'estimated',
            notes TEXT,
            created_by TEXT,
            estimation_mode TEXT NOT NULL DEFAULT 'none',
            confidence_level TEXT NOT NULL DEFAULT 'medium',
            initial_fill_known INTEGER NOT NULL DEFAULT 1,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (printer_id) REFERENCES printers(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_diagnostic_tank_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnostic_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            estimated_percent REAL,
            estimated_ml REAL,
            source_of_measurement TEXT,
            confidence_level TEXT,
            is_estimated INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (diagnostic_id) REFERENCES printer_diagnostics(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_diagnostic_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnostic_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT,
            description TEXT,
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (diagnostic_id) REFERENCES printer_diagnostics(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_refills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            added_ml REAL NOT NULL DEFAULT 0,
            refill_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            bottle_reference TEXT,
            unit_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (printer_id) REFERENCES printers(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_head_wear_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            diagnostic_id INTEGER,
            wear_percent REAL NOT NULL DEFAULT 0,
            pages_basis INTEGER NOT NULL DEFAULT 0,
            calculation_method TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (printer_id) REFERENCES printers(id),
            FOREIGN KEY (diagnostic_id) REFERENCES printer_diagnostics(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_cost_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            diagnostic_id INTEGER NOT NULL,
            estimated_ink_black_ml_used REAL DEFAULT 0,
            estimated_ink_cyan_ml_used REAL DEFAULT 0,
            estimated_ink_magenta_ml_used REAL DEFAULT 0,
            estimated_ink_yellow_ml_used REAL DEFAULT 0,
            estimated_head_wear_percent REAL DEFAULT 0,
            depreciation_amount REAL DEFAULT 0,
            reliability TEXT NOT NULL DEFAULT 'estimated',
            calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (printer_id) REFERENCES printers(id),
            FOREIGN KEY (diagnostic_id) REFERENCES printer_diagnostics(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS printer_maintenance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printer_id INTEGER NOT NULL,
            maintenance_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            maintenance_type TEXT NOT NULL,
            cost REAL DEFAULT 0,
            notes TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (printer_id) REFERENCES printers(id)
        )
        """
    )

    # Legacy tables kept for backward compatibility
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnosticos_impresora (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            activo_id INTEGER,
            impresora TEXT,
            vida_cabezal_pct REAL,
            contador_impresiones INTEGER DEFAULT 0,
            cyan_ml REAL,
            magenta_ml REAL,
            yellow_ml REAL,
            black_ml REAL,
            observacion TEXT,
            vida_rodillo_pct REAL,
            vida_almohadillas_pct REAL,
            total_pages INTEGER DEFAULT 0,
            color_pages INTEGER DEFAULT 0,
            bw_pages INTEGER DEFAULT 0,
            borderless_pages INTEGER DEFAULT 0,
            scanned_pages INTEGER DEFAULT 0,
            estimation_mode TEXT DEFAULT 'none',
            confidence_level TEXT DEFAULT 'medium',
            initial_fill_known INTEGER DEFAULT 1,
            is_estimated INTEGER DEFAULT 0,
            depreciation_amount REAL DEFAULT 0,
            head_wear_pct REAL DEFAULT 0,
            payload_json TEXT,
            FOREIGN KEY (activo_id) REFERENCES activos(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostico_tanques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnostico_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            estimated_percent REAL,
            estimated_ml REAL,
            source_of_measurement TEXT,
            confidence_level TEXT,
            is_estimated INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (diagnostico_id) REFERENCES diagnosticos_impresora(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostico_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnostico_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT,
            file_category TEXT,
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (diagnostico_id) REFERENCES diagnosticos_impresora(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS impresora_tanque_capacidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id INTEGER NOT NULL,
            color TEXT NOT NULL,
            capacity_ml REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(activo_id, color),
            FOREIGN KEY (activo_id) REFERENCES activos(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostico_recargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            activo_id INTEGER NOT NULL,
            diagnostico_id INTEGER,
            color TEXT NOT NULL,
            ml_added REAL NOT NULL DEFAULT 0,
            costo_unitario_usd REAL DEFAULT 0,
            costo_total_usd REAL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (activo_id) REFERENCES activos(id),
            FOREIGN KEY (diagnostico_id) REFERENCES diagnosticos_impresora(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnostico_consumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            activo_id INTEGER NOT NULL,
            diagnostico_id INTEGER,
            color TEXT NOT NULL,
            consumed_ml REAL NOT NULL DEFAULT 0,
            source TEXT,
            inventory_item_id INTEGER,
            notes TEXT,
            FOREIGN KEY (activo_id) REFERENCES activos(id),
            FOREIGN KEY (diagnostico_id) REFERENCES diagnosticos_impresora(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS costos_operativos_impresora (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            activo_id INTEGER NOT NULL,
            diagnostico_id INTEGER,
            tipo_costo TEXT NOT NULL,
            monto_usd REAL NOT NULL DEFAULT 0,
            detalle TEXT,
            FOREIGN KEY (activo_id) REFERENCES activos(id),
            FOREIGN KEY (diagnostico_id) REFERENCES diagnosticos_impresora(id)
        )
        """
    )

    diag_cols = {row[1] for row in conn.execute("PRAGMA table_info(diagnosticos_impresora)").fetchall()}
    optional_diag_cols = {
        "vida_rodillo_pct": "ALTER TABLE diagnosticos_impresora ADD COLUMN vida_rodillo_pct REAL",
        "vida_almohadillas_pct": "ALTER TABLE diagnosticos_impresora ADD COLUMN vida_almohadillas_pct REAL",
        "contador_impresiones": "ALTER TABLE diagnosticos_impresora ADD COLUMN contador_impresiones INTEGER DEFAULT 0",
        "activo_id": "ALTER TABLE diagnosticos_impresora ADD COLUMN activo_id INTEGER",
        "total_pages": "ALTER TABLE diagnosticos_impresora ADD COLUMN total_pages INTEGER DEFAULT 0",
        "color_pages": "ALTER TABLE diagnosticos_impresora ADD COLUMN color_pages INTEGER DEFAULT 0",
        "bw_pages": "ALTER TABLE diagnosticos_impresora ADD COLUMN bw_pages INTEGER DEFAULT 0",
        "borderless_pages": "ALTER TABLE diagnosticos_impresora ADD COLUMN borderless_pages INTEGER DEFAULT 0",
        "scanned_pages": "ALTER TABLE diagnosticos_impresora ADD COLUMN scanned_pages INTEGER DEFAULT 0",
        "estimation_mode": "ALTER TABLE diagnosticos_impresora ADD COLUMN estimation_mode TEXT DEFAULT 'none'",
        "confidence_level": "ALTER TABLE diagnosticos_impresora ADD COLUMN confidence_level TEXT DEFAULT 'medium'",
        "initial_fill_known": "ALTER TABLE diagnosticos_impresora ADD COLUMN initial_fill_known INTEGER DEFAULT 1",
        "is_estimated": "ALTER TABLE diagnosticos_impresora ADD COLUMN is_estimated INTEGER DEFAULT 0",
        "depreciation_amount": "ALTER TABLE diagnosticos_impresora ADD COLUMN depreciation_amount REAL DEFAULT 0",
        "head_wear_pct": "ALTER TABLE diagnosticos_impresora ADD COLUMN head_wear_pct REAL DEFAULT 0",
        "payload_json": "ALTER TABLE diagnosticos_impresora ADD COLUMN payload_json TEXT",
    }
    for col, alter_sql in optional_diag_cols.items():
        if col not in diag_cols:
            conn.execute(alter_sql)

def _ensure_activos_sync_columns(conn) -> None:
    activos_cols = {row[1] for row in conn.execute("PRAGMA table_info(activos)").fetchall()}
    optional_cols = {
        "vida_cabezal_pct": "ALTER TABLE activos ADD COLUMN vida_cabezal_pct REAL",
        "vida_rodillo_pct": "ALTER TABLE activos ADD COLUMN vida_rodillo_pct REAL",
        "vida_almohadillas_pct": "ALTER TABLE activos ADD COLUMN vida_almohadillas_pct REAL",
        "paginas_impresas": "ALTER TABLE activos ADD COLUMN paginas_impresas INTEGER DEFAULT 0",
    }
    for col, alter_sql in optional_cols.items():
        if col not in activos_cols:
            conn.execute(alter_sql)


def _buscar_item_tinta(conn, color: str) -> dict[str, Any] | None:
    color_txt = str(color or "").strip().lower()
    if not color_txt:
        return None

    filas = conn.execute(
        """
        SELECT id, nombre, categoria, unidad, stock_actual, costo_unitario_usd
        FROM inventario
        WHERE estado='activo'
        """
    ).fetchall()

    tokens_objetivo = {color_txt, f"tinta {color_txt}", f"{color_txt} ink"}
    mejor: dict[str, Any] | None = None
    mejor_puntaje = 0

    for row in filas:
        data = dict(row)
        nombre = _normalizar_texto_busqueda(str(data.get("nombre") or ""))
        categoria = _normalizar_texto_busqueda(str(data.get("categoria") or ""))
        unidad = _normalizar_texto_busqueda(str(data.get("unidad") or ""))

        puntaje = 0
        if "tinta" in categoria or "ink" in categoria:
            puntaje += 3
        if "ml" in unidad:
            puntaje += 2
        if any(tok in nombre for tok in tokens_objetivo):
            puntaje += 4
        if color_txt in nombre:
            puntaje += 2
        if color_txt[0:1] and re.search(rf"\b{re.escape(color_txt[0:1])}\b", nombre):
            puntaje += 1

        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor = data

    return mejor if mejor_puntaje >= 4 else None




def _resolver_activo_impresora(conn, activo_id: int | None, impresora: str) -> int | None:
    if activo_id:
        return int(activo_id)

    nombre_obj = _normalizar_texto_busqueda(impresora)
    if not nombre_obj:
        return None

    filas = conn.execute(
        """
        SELECT id, equipo, modelo, categoria, unidad
        FROM activos
        WHERE COALESCE(activo, 1) = 1
        """
    ).fetchall()

    mejor_id = None
    mejor_puntaje = 0
    tokens_obj = set(nombre_obj.split())

    for row in filas:
        data = dict(row)
        equipo = _normalizar_texto_busqueda(str(data.get("equipo") or ""))
        modelo = _normalizar_texto_busqueda(str(data.get("modelo") or ""))
        categoria = _normalizar_texto_busqueda(str(data.get("categoria") or ""))
        unidad = _normalizar_texto_busqueda(str(data.get("unidad") or ""))

        puntaje = 0
        if "impres" in categoria or "impres" in unidad:
            puntaje += 3

        for campo in (equipo, modelo):
            if not campo:
                continue
            if campo in nombre_obj or nombre_obj in campo:
                puntaje += 4

            tokens_campo = set(campo.split())
            coincidencias = len(tokens_obj & tokens_campo)
            puntaje += coincidencias

        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor_id = int(data["id"])

    return mejor_id if mejor_puntaje >= 4 else None


def aplicar_resultado_diagnostico(
    usuario: str,
    impresora: str,
    resultados: dict[str, float | None],
    vida_cabezal_pct: float,
    contador_impresiones: int = 0,
    activo_id: int | None = None,
    desgaste_componentes: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    resumen = {
        "diagnostico_guardado": False,
        "activos_actualizados": False,
        "movimientos_tinta": [],
    }

    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)

        activo_objetivo_id = _resolver_activo_impresora(conn, activo_id, impresora)

        previo = None
        if activo_objetivo_id:
            _ensure_activos_sync_columns(conn)
            previo = conn.execute(
                """
                SELECT cyan_ml, magenta_ml, yellow_ml, black_ml
                FROM diagnosticos_impresora
                WHERE activo_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(activo_objetivo_id),),
            ).fetchone()
        elif impresora:
            previo = conn.execute(
                """
                SELECT cyan_ml, magenta_ml, yellow_ml, black_ml
                FROM diagnosticos_impresora
                WHERE lower(COALESCE(impresora, '')) = lower(?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(impresora),),
            ).fetchone()

        componentes = dict(desgaste_componentes or {})
        vida_rodillo = _clamp_percentage(componentes.get("rodillo"))
        vida_almohadillas = _clamp_percentage(componentes.get("almohadillas"))

        conn.execute(
            """
            INSERT INTO diagnosticos_impresora
            (usuario, activo_id, impresora, vida_cabezal_pct, contador_impresiones, cyan_ml, magenta_ml, yellow_ml, black_ml, observacion, vida_rodillo_pct, vida_almohadillas_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                int(activo_objetivo_id) if activo_objetivo_id else None,
                str(impresora),
                float(vida_cabezal_pct),
                int(contador_impresiones or 0),
                float(resultados.get("Cyan") or 0.0),
                float(resultados.get("Magenta") or 0.0),
                float(resultados.get("Yellow") or 0.0),
                float(resultados.get("Black") or 0.0),
                "Registro automático desde Diagnóstico IA",
                float(vida_rodillo) if vida_rodillo is not None else None,
                float(vida_almohadillas) if vida_almohadillas is not None else None,
            ),
        )
        resumen["diagnostico_guardado"] = True

        if activo_objetivo_id:
            vidas_componentes = [_clamp_percentage(vida_cabezal_pct), vida_rodillo, vida_almohadillas]
            vidas_validas = [float(v) for v in vidas_componentes if v is not None]
            vida_general = min(vidas_validas) if vidas_validas else None
            conn.execute(
                """
                UPDATE activos
                SET desgaste = CASE
                    WHEN ? IS NOT NULL THEN ROUND((100.0 - ?) / 100.0, 6)
                    ELSE desgaste
                END,
                    vida_cabezal_pct = ?,
                    vida_rodillo_pct = COALESCE(?, vida_rodillo_pct),
                    vida_almohadillas_pct = COALESCE(?, vida_almohadillas_pct),
                    paginas_impresas = CASE
                        WHEN ? > 0 THEN ?
                        ELSE COALESCE(paginas_impresas, 0)
                    END,
                    usuario = ?
                WHERE id = ?
                """,
                (
                    float(vida_general) if vida_general is not None else None,
                    float(vida_general) if vida_general is not None else None,
                    float(vida_cabezal_pct),
                    float(vida_rodillo) if vida_rodillo is not None else None,
                    float(vida_almohadillas) if vida_almohadillas is not None else None,
                    int(contador_impresiones or 0),
                    int(contador_impresiones or 0),
                    usuario,
                    int(activo_objetivo_id),
                ),
            )
            conn.execute(
                """
                INSERT INTO activos_historial(activo, accion, detalle, costo, usuario)
                VALUES (?, 'DIAGNÓSTICO IA', ?, 0, ?)
                """,
                (
                    str(impresora),
                    (
                        f"Vida cabezal: {float(vida_cabezal_pct):.2f}%"
                        + (f" | rodillo: {float(vida_rodillo):.2f}%" if vida_rodillo is not None else "")
                        + (f" | almohadillas: {float(vida_almohadillas):.2f}%" if vida_almohadillas is not None else "")
                        + f" | contador: {int(contador_impresiones or 0)}"
                    ),
                    usuario,
                ),
            )
            resumen["activos_actualizados"] = True

        if previo:
            previo_map = {
                "Cyan": float(previo["cyan_ml"] or 0.0),
                "Magenta": float(previo["magenta_ml"] or 0.0),
                "Yellow": float(previo["yellow_ml"] or 0.0),
                "Black": float(previo["black_ml"] or 0.0),
            }
            for color in _COLOR_ORDER:
                actual = float(resultados.get(color) or 0.0)
                consumido = round(max(0.0, previo_map.get(color, 0.0) - actual), 2)
                if consumido <= 0:
                    continue

                item = _buscar_item_tinta(conn, color)
                if not item:
                    continue

                stock = float(item.get("stock_actual") or 0.0)
                salida = min(stock, consumido)
                if salida <= 0:
                    continue

                conn.execute(
                    """
                    INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
                    VALUES (?, ?, 'salida', ?, ?, ?)
                    """,
                    (
                        usuario,
                        int(item["id"]),
                        -float(salida),
                        float(item.get("costo_unitario_usd") or 0.0),
                        f"Diagnóstico IA {impresora} - consumo {color}",
                    ),
                )
                conn.execute(
                    "UPDATE inventario SET stock_actual = stock_actual - ? WHERE id = ?",
                    (float(salida), int(item["id"])),
                )
                resumen["movimientos_tinta"].append(
                    {
                        "color": color,
                        "inventario_id": int(item["id"]),
                        "consumo_ml": float(salida),
                    }
                )

    return resumen




def save_tank_capacities(activo_id: int, capacities_ml: dict[str, float]) -> None:
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        for color, value in (capacities_ml or {}).items():
            c = _normalize_color(color)
            if c not in COLOR_KEYS:
                continue
            conn.execute(
                """
                INSERT INTO impresora_tanque_capacidad(activo_id, color, capacity_ml, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(activo_id, color)
                DO UPDATE SET capacity_ml=excluded.capacity_ml, updated_at=CURRENT_TIMESTAMP
                """,
                (int(activo_id), c, max(0.0, _to_float(value))),
            )


def get_tank_capacities(activo_id: int | None, fallback_name: str = "") -> dict[str, float]:
    if not activo_id:
        return _obtener_capacidades_por_nombre(fallback_name)

    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        rows = conn.execute(
            "SELECT color, capacity_ml FROM impresora_tanque_capacidad WHERE activo_id=?",
            (int(activo_id),),
        ).fetchall()

    if not rows:
        return _obtener_capacidades_por_nombre(fallback_name)

    data = {str(r['color']).lower(): _to_float(r['capacity_ml']) for r in rows}
    return {
        "black": data.get("black", 70.0),
        "cyan": data.get("cyan", 70.0),
        "magenta": data.get("magenta", 70.0),
        "yellow": data.get("yellow", 70.0),
    }


def _obtener_capacidades_por_nombre(nombre: str) -> dict[str, float]:
    model = (nombre or "").lower()
    if "580" in model or "590" in model:
        return {"black": 135.0, "cyan": 70.0, "magenta": 70.0, "yellow": 70.0}
    if "j210" in model or "deskjet 2000" in model:
        return {"black": 100.0, "cyan": 70.0, "magenta": 70.0, "yellow": 70.0}
    if "l1250" in model:
        return {"black": 70.0, "cyan": 70.0, "magenta": 70.0, "yellow": 70.0}

    return {"black": 70.0, "cyan": 70.0, "magenta": 70.0, "yellow": 70.0}


def _infer_brand_model(printer_name: str) -> tuple[str, str]:
    name = str(printer_name or "").strip()
    if not name:
        return "", ""
    tokens = name.split()
    brand = tokens[0].upper() if tokens else ""
    model = " ".join(tokens[1:]) if len(tokens) > 1 else name
    return brand, model


def ensure_printer_profile(
    conn,
    asset_id: int,
    printer_name: str,
    ink_system_type: str = "factory_tank",
    ink_usage_type: str = "standard",
    head_system_type: str = "integrated",
    valuation_method: str = "usage_based",
    purchase_value: float = 0.0,
    current_value: float = 0.0,
    status: str = "active",
    notes: str = "",
    initial_fill_known: bool = True,
    estimation_mode: str = "none",
) -> int:
    if ink_system_type not in INK_SYSTEM_TYPES:
        raise ValueError("ink_system_type inválido")
    if ink_usage_type not in INK_USAGE_TYPES:
        raise ValueError("ink_usage_type inválido")
    if estimation_mode not in ESTIMATION_MODES:
        raise ValueError("estimation_mode inválido")

    brand, model = _infer_brand_model(printer_name)
    row = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(asset_id),)).fetchone()
    if row:
        conn.execute(
            """
            UPDATE printers
            SET brand=?, model=?, ink_system_type=?, ink_usage_type=?, head_system_type=?, valuation_method=?,
                purchase_value=?, current_value=?, status=?, notes=?, initial_fill_known=?, estimation_mode=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE asset_id=?
            """,
            (
                brand,
                model,
                ink_system_type,
                ink_usage_type,
                head_system_type,
                valuation_method,
                max(0.0, _to_float(purchase_value)),
                max(0.0, _to_float(current_value)),
                status,
                notes,
                1 if initial_fill_known else 0,
                estimation_mode,
                int(asset_id),
            ),
        )
        return int(row["id"])

    cur = conn.execute(
        """
        INSERT INTO printers(
            asset_id, brand, model, ink_system_type, ink_usage_type, head_system_type, valuation_method,
            purchase_value, current_value, status, notes, initial_fill_known, estimation_mode
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(asset_id),
            brand,
            model,
            ink_system_type,
            ink_usage_type,
            head_system_type,
            valuation_method,
            max(0.0, _to_float(purchase_value)),
            max(0.0, _to_float(current_value)),
            status,
            notes,
            1 if initial_fill_known else 0,
            estimation_mode,
        ),
    )
    return int(cur.lastrowid)


def save_printer_tank_configs(conn, printer_id: int, capacities_ml: dict[str, float], source_type: str = "manual") -> None:
    for color, value in (capacities_ml or {}).items():
        c = _normalize_color(color)
        if c not in COLOR_KEYS:
            continue
        ml = max(0.0, _to_float(value))
        conn.execute(
            """
            INSERT INTO printer_tank_configs(printer_id, color, capacity_ml, source_type, is_active, updated_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(printer_id, color)
            DO UPDATE SET capacity_ml=excluded.capacity_ml, source_type=excluded.source_type, is_active=1, updated_at=CURRENT_TIMESTAMP
            """,
            (int(printer_id), c, ml, source_type),
        )


def _calculate_head_wear(total_pages: int, ink_system_type: str, ink_usage_type: str) -> tuple[float, str]:
    pages = max(0, int(total_pages or 0))
    base_divisor = 12000.0 if ink_system_type == "factory_tank" else 8000.0
    if ink_system_type == "adapted_external_tank":
        base_divisor = 7000.0
    if ink_usage_type == "sublimation":
        base_divisor *= 0.85
    wear = min(100.0, round((pages / base_divisor) * 100.0, 2))
    return wear, f"pages/{base_divisor:.0f}"


def _calculate_depreciation(total_pages: int, wear_pct: float, maintenance_cost: float = 0.0) -> float:
    pages = max(0, int(total_pages or 0))
    op_factor = round(pages * 0.002, 4)
    wear_factor = round(max(0.0, _to_float(wear_pct)) * 0.01, 4)
    return round(op_factor + wear_factor + max(0.0, _to_float(maintenance_cost)), 4)


def _determine_accuracy(estimation_mode: str, initial_fill_known: bool, tank_levels: dict[str, dict[str, Any]]) -> str:
    sources = {str((v or {}).get("source_of_measurement") or "manual").lower() for v in (tank_levels or {}).values()}
    uses_multiple_sources = len(sources) > 1
    if not initial_fill_known:
        return "estimated" if not uses_multiple_sources else "mixed"
    if estimation_mode == "none" and not uses_multiple_sources:
        return "exact"
    return "mixed" if uses_multiple_sources else "estimated"


def _sum_refills_between(conn, printer_id: int, previous_diag_id: int | None, current_diag_id: int) -> dict[str, float]:
    if not previous_diag_id:
        return {c: 0.0 for c in COLOR_KEYS}
    rows = conn.execute(
        """
        SELECT color, SUM(added_ml) AS added_ml
        FROM printer_refills
        WHERE printer_id=?
          AND refill_date >= COALESCE((SELECT diagnostic_date FROM printer_diagnostics WHERE id=?), '1970-01-01')
          AND refill_date <= COALESCE((SELECT diagnostic_date FROM printer_diagnostics WHERE id=?), CURRENT_TIMESTAMP)
        GROUP BY color
        """,
        (int(printer_id), int(previous_diag_id), int(current_diag_id)),
    ).fetchall()
    acc = {c: 0.0 for c in COLOR_KEYS}
    for r in rows:
        c = _normalize_color(str(r["color"]))
        if c in acc:
            acc[c] = max(0.0, _to_float(r["added_ml"]))
    return acc


def _apply_inventory_discount(conn, usuario: str, printer_name: str, color: str, consumed_ml: float) -> int | None:
    item = _buscar_item_tinta(conn, color)
    if not item:
        return None
    salida = min(_to_float(item.get("stock_actual")), max(0.0, _to_float(consumed_ml)))
    if salida <= 0:
        return int(item["id"])
    conn.execute(
        "INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia) VALUES (?, ?, 'salida', ?, ?, ?)",
        (usuario, int(item["id"]), -float(salida), _to_float(item.get("costo_unitario_usd")), f"Consumo diagnóstico {printer_name} {color}"),
    )
    conn.execute("UPDATE inventario SET stock_actual = stock_actual - ? WHERE id = ?", (float(salida), int(item["id"])))
    return int(item["id"])


def register_printer_refill(
    usuario: str,
    activo_id: int,
    color: str,
    added_ml: float,
    refill_date: str,
    bottle_reference: str = "",
    unit_cost: float = 0.0,
    notes: str = "",
) -> int:
    c = _normalize_color(color)
    if c not in COLOR_KEYS:
        raise ValueError("color inválido")
    ml = max(0.0, _to_float(added_ml))
    if ml <= 0:
        raise ValueError("added_ml debe ser mayor que cero")

    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        row = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(activo_id),)).fetchone()
        if row:
            printer_id = int(row["id"])
        else:
            asset = conn.execute("SELECT equipo, modelo FROM activos WHERE id=?", (int(activo_id),)).fetchone()
            printer_name = str((asset["modelo"] if asset and asset["modelo"] else (asset["equipo"] if asset else "")) or "")
            printer_id = ensure_printer_profile(conn, int(activo_id), printer_name or "Impresora")
        total_cost = round(ml * max(0.0, _to_float(unit_cost)), 4)
        cur = conn.execute(
            """
            INSERT INTO printer_refills(printer_id, color, added_ml, refill_date, bottle_reference, unit_cost, total_cost, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (printer_id, c, ml, refill_date, bottle_reference, max(0.0, _to_float(unit_cost)), total_cost, notes, usuario),
        )
        return int(cur.lastrowid)


def list_printer_refills(activo_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        row = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(activo_id),)).fetchone()
        if not row:
            return []
        rows = conn.execute(
            "SELECT * FROM printer_refills WHERE printer_id=? ORDER BY id DESC LIMIT ?",
            (int(row["id"]), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


def register_printer_maintenance(
    usuario: str,
    activo_id: int,
    maintenance_date: str,
    maintenance_type: str,
    cost: float,
    notes: str = "",
) -> int:
    if not str(maintenance_type or "").strip():
        raise ValueError("maintenance_type es requerido")
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        row = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(activo_id),)).fetchone()
        if row:
            printer_id = int(row["id"])
        else:
            asset = conn.execute("SELECT equipo, modelo FROM activos WHERE id=?", (int(activo_id),)).fetchone()
            printer_name = str((asset["modelo"] if asset and asset["modelo"] else (asset["equipo"] if asset else "")) or "")
            printer_id = ensure_printer_profile(conn, int(activo_id), printer_name or "Impresora")
        cur = conn.execute(
            """
            INSERT INTO printer_maintenance_logs(printer_id, maintenance_date, maintenance_type, cost, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (printer_id, maintenance_date, maintenance_type.strip(), max(0.0, _to_float(cost)), notes, usuario),
        )
        return int(cur.lastrowid)


def list_printer_maintenance(activo_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        row = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(activo_id),)).fetchone()
        if not row:
            return []
        rows = conn.execute(
            "SELECT * FROM printer_maintenance_logs WHERE printer_id=? ORDER BY id DESC LIMIT ?",
            (int(row["id"]), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

def create_diagnostic_record(
    usuario: str,
    activo_id: int,
    printer_name: str,
    counters: dict[str, int],
    tank_levels: dict[str, dict[str, Any]],
    notes: str = "",
    files: list[dict[str, Any]] | None = None,
    estimation_mode: str = "none",
    confidence_level: str = "medium",
    initial_fill_known: bool = True,
    ink_system_type: str = "factory_tank",
    ink_usage_type: str = "standard",
    head_system_type: str = "integrated",
    valuation_method: str = "usage_based",
    purchase_value: float = 0.0,
    current_value: float = 0.0,
) -> dict[str, Any]:
    if estimation_mode not in ESTIMATION_MODES:
        raise ValueError("estimation_mode inválido")
    if confidence_level not in CONFIDENCE_LEVELS:
        raise ValueError("confidence_level inválido")
    if ink_system_type not in INK_SYSTEM_TYPES:
        raise ValueError("ink_system_type inválido")
    if ink_usage_type not in INK_USAGE_TYPES:
        raise ValueError("ink_usage_type inválido")

    files = list(files or [])
    counters = dict(counters or {})

    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        _ensure_activos_sync_columns(conn)

        printer_id = ensure_printer_profile(
            conn=conn,
            asset_id=int(activo_id),
            printer_name=printer_name,
            ink_system_type=ink_system_type,
            ink_usage_type=ink_usage_type,
            head_system_type=head_system_type,
            valuation_method=valuation_method,
            purchase_value=purchase_value,
            current_value=current_value,
            notes=notes,
            initial_fill_known=initial_fill_known,
            estimation_mode=estimation_mode,
        )

        total_pages = int(counters.get("total_pages") or 0)
        color_pages = int(counters.get("color_pages") or 0)
        bw_pages = int(counters.get("bw_pages") or 0)
        borderless_pages = int(counters.get("borderless_pages") or 0)
        scanned_pages = int(counters.get("scanned_pages") or 0)
        if min(total_pages, color_pages, bw_pages, borderless_pages, scanned_pages) < 0:
            raise ValueError("Los contadores de páginas no pueden ser negativos")

        capacities = get_tank_capacities(int(activo_id), printer_name)
        save_printer_tank_configs(conn, printer_id, capacities, source_type="manual")

        configured_colors = {str(r['color']).lower() for r in conn.execute("SELECT color FROM printer_tank_configs WHERE printer_id=? AND is_active=1", (printer_id,)).fetchall()}
        incoming_colors = {_normalize_color(c) for c in (tank_levels or {}).keys()}
        if incoming_colors - configured_colors:
            raise ValueError("Hay colores fuera de la configuración de la impresora")

        if (not initial_fill_known) and estimation_mode == "none":
            raise ValueError("No se puede marcar cálculo exacto con initial_fill_known = false")

        for values in (tank_levels or {}).values():
            pct = values.get("estimated_percent")
            if pct is not None and (_to_float(pct) < 0 or _to_float(pct) > 100):
                raise ValueError("Los porcentajes deben estar entre 0 y 100")
            if _to_float(values.get("estimated_ml")) < 0:
                raise ValueError("Los ml no pueden ser negativos")

        prev = conn.execute(
            "SELECT id, diagnostic_date FROM printer_diagnostics WHERE printer_id=? ORDER BY id DESC LIMIT 1",
            (printer_id,),
        ).fetchone()
        previous_diag_id = int(prev["id"]) if prev else None
        prev_levels_rows = conn.execute(
            """
            SELECT t.color, t.estimated_ml
            FROM printer_diagnostic_tank_levels t
            WHERE t.diagnostic_id = ?
            """,
            (previous_diag_id,),
        ).fetchall() if previous_diag_id else []
        prev_levels = {_normalize_color(r["color"]): _to_float(r["estimated_ml"]) for r in prev_levels_rows}

        diagnostic_accuracy = _determine_accuracy(estimation_mode, initial_fill_known, tank_levels)
        payload = {
            "counters": counters,
            "tank_levels": tank_levels,
            "notes": notes,
            "estimation_mode": estimation_mode,
            "confidence_level": confidence_level,
            "initial_fill_known": bool(initial_fill_known),
            "ink_system_type": ink_system_type,
            "ink_usage_type": ink_usage_type,
        }

        cur = conn.execute(
            """
            INSERT INTO printer_diagnostics(
                printer_id, total_pages, color_pages, bw_pages, borderless_pages, scanned_pages,
                diagnostic_accuracy, notes, created_by, estimation_mode, confidence_level, initial_fill_known, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                printer_id,
                total_pages,
                color_pages,
                bw_pages,
                borderless_pages,
                scanned_pages,
                diagnostic_accuracy,
                notes,
                usuario,
                estimation_mode,
                confidence_level,
                1 if initial_fill_known else 0,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        diagnostic_id = int(cur.lastrowid)

        current_map: dict[str, float] = {c: 0.0 for c in COLOR_KEYS}
        for color, values in tank_levels.items():
            c = _normalize_color(color)
            if c not in COLOR_KEYS:
                continue
            source = str(values.get("source_of_measurement") or "manual").lower()
            if source not in MEASUREMENT_SOURCES:
                source = "manual"
            confidence = str(values.get("confidence_level") or confidence_level).lower()
            if confidence not in CONFIDENCE_LEVELS:
                confidence = confidence_level
            est_ml = max(0.0, _to_float(values.get("estimated_ml")))
            current_map[c] = est_ml
            conn.execute(
                """
                INSERT INTO printer_diagnostic_tank_levels
                (diagnostic_id, color, estimated_percent, estimated_ml, source_of_measurement, confidence_level, is_estimated, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    diagnostic_id,
                    c,
                    _clamp_percentage(values.get("estimated_percent")),
                    est_ml,
                    source,
                    confidence,
                    1 if values.get("is_estimated", estimation_mode != "none") else 0,
                    str(values.get("notes") or ""),
                ),
            )

        for f in files:
            conn.execute(
                """
                INSERT INTO printer_diagnostic_files
                (diagnostic_id, file_path, file_type, description, file_name, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    diagnostic_id,
                    str(f.get("file_path") or ""),
                    str(f.get("file_type") or "application/octet-stream"),
                    str(f.get("file_category") or "evidencia"),
                    str(f.get("file_name") or "archivo"),
                    int(f.get("file_size") or 0),
                ),
            )

        # mirror legacy file/tank tables
        conn.execute(
            """
            INSERT INTO diagnosticos_impresora
            (usuario, activo_id, impresora, vida_cabezal_pct, contador_impresiones, cyan_ml, magenta_ml, yellow_ml, black_ml, observacion,
             total_pages, color_pages, bw_pages, borderless_pages, scanned_pages, estimation_mode, confidence_level, initial_fill_known,
             is_estimated, depreciation_amount, head_wear_pct, payload_json)
            VALUES (?, ?, ?, 100, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                usuario,
                int(activo_id),
                printer_name,
                total_pages,
                current_map.get("cyan", 0.0),
                current_map.get("magenta", 0.0),
                current_map.get("yellow", 0.0),
                current_map.get("black", 0.0),
                notes,
                total_pages,
                color_pages,
                bw_pages,
                borderless_pages,
                scanned_pages,
                estimation_mode,
                confidence_level,
                1 if initial_fill_known else 0,
                0 if estimation_mode == "none" else 1,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        legacy_diag_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

        for color in COLOR_KEYS:
            level = tank_levels.get(color, {})
            conn.execute(
                """
                INSERT INTO diagnostico_tanques(diagnostico_id, color, estimated_percent, estimated_ml, source_of_measurement, confidence_level, is_estimated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy_diag_id,
                    color,
                    _clamp_percentage(level.get("estimated_percent")),
                    current_map.get(color, 0.0),
                    str(level.get("source_of_measurement") or "manual"),
                    str(level.get("confidence_level") or confidence_level),
                    1 if estimation_mode != "none" else 0,
                ),
            )

        for f in files:
            conn.execute(
                """
                INSERT INTO diagnostico_archivos(diagnostico_id, file_name, file_type, file_category, file_path, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    legacy_diag_id,
                    str(f.get("file_name") or "archivo"),
                    str(f.get("file_type") or "application/octet-stream"),
                    str(f.get("file_category") or "evidencia"),
                    str(f.get("file_path") or ""),
                    int(f.get("file_size") or 0),
                ),
            )

        refill_between = _sum_refills_between(conn, printer_id, previous_diag_id, diagnostic_id)
        consumed_by_color: dict[str, float] = {}
        for color in COLOR_KEYS:
            prev_ml = _to_float(prev_levels.get(color))
            current_ml = _to_float(current_map.get(color))
            consumed = round(max(0.0, prev_ml - current_ml + _to_float(refill_between.get(color))), 2)
            consumed_by_color[color] = consumed
            if consumed <= 0:
                continue
            inv_id = _apply_inventory_discount(conn, usuario, printer_name, color, consumed)
            conn.execute(
                "INSERT INTO diagnostico_consumos(usuario, activo_id, diagnostico_id, color, consumed_ml, source, inventory_item_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (usuario, int(activo_id), legacy_diag_id, color, consumed, "diagnostico", inv_id, f"Consumo entre diagnósticos ({diagnostic_accuracy})"),
            )

        wear_pct, wear_method = _calculate_head_wear(total_pages, ink_system_type, ink_usage_type)
        maintenance_cost = conn.execute(
            "SELECT COALESCE(SUM(cost),0) AS total FROM printer_maintenance_logs WHERE printer_id=?",
            (printer_id,),
        ).fetchone()["total"]
        depreciation_amount = _calculate_depreciation(total_pages, wear_pct, _to_float(maintenance_cost))

        conn.execute(
            """
            INSERT INTO printer_head_wear_logs(printer_id, diagnostic_id, wear_percent, pages_basis, calculation_method, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (printer_id, diagnostic_id, wear_pct, total_pages, wear_method, f"{ink_system_type}/{ink_usage_type}"),
        )
        conn.execute(
            """
            INSERT INTO printer_cost_snapshots(
                printer_id, diagnostic_id, estimated_ink_black_ml_used, estimated_ink_cyan_ml_used,
                estimated_ink_magenta_ml_used, estimated_ink_yellow_ml_used, estimated_head_wear_percent,
                depreciation_amount, reliability
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                printer_id,
                diagnostic_id,
                consumed_by_color.get("black", 0.0),
                consumed_by_color.get("cyan", 0.0),
                consumed_by_color.get("magenta", 0.0),
                consumed_by_color.get("yellow", 0.0),
                wear_pct,
                depreciation_amount,
                diagnostic_accuracy,
            ),
        )

        conn.execute(
            """
            UPDATE activos
            SET paginas_impresas = CASE WHEN ? > paginas_impresas THEN ? ELSE paginas_impresas END,
                vida_cabezal_pct = ?,
                desgaste = ROUND(? / 100.0, 6),
                usuario = ?
            WHERE id = ?
            """,
            (total_pages, total_pages, round(max(0.0, 100.0 - wear_pct), 2), wear_pct, usuario, int(activo_id)),
        )

        conn.execute(
            "UPDATE printers SET current_value = CASE WHEN purchase_value > ? THEN purchase_value - ? ELSE 0 END, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (depreciation_amount, depreciation_amount, printer_id),
        )
        conn.execute(
            "UPDATE diagnosticos_impresora SET depreciation_amount=?, head_wear_pct=?, vida_cabezal_pct=? WHERE id=?",
            (depreciation_amount, wear_pct, round(max(0.0, 100.0 - wear_pct), 2), legacy_diag_id),
        )

        return {
            "diagnostico_id": diagnostic_id,
            "legacy_diagnostico_id": legacy_diag_id,
            "depreciation_amount": depreciation_amount,
            "head_wear_pct": wear_pct,
            "diagnostic_accuracy": diagnostic_accuracy,
        }


def save_uploaded_file(file_obj, diagnostico_id: int, category: str = "evidencia") -> dict[str, Any] | None:
    if file_obj is None:
        return None
    root = Path("uploads") / "diagnosticos" / str(diagnostico_id)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_obj.name or "archivo")
    final_path = root / f"{timestamp}_{safe_name}"
    content = file_obj.getvalue()
    final_path.write_bytes(content)
    return {
        "file_name": file_obj.name,
        "file_type": getattr(file_obj, "type", "application/octet-stream"),
        "file_category": category,
        "file_path": str(final_path),
        "file_size": len(content),
    }


def get_printer_diagnostic_summary(activo_id: int) -> dict[str, Any]:
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        row = conn.execute(
            """
            SELECT a.id AS asset_id, a.equipo, a.modelo, a.paginas_impresas, a.vida_cabezal_pct,
                   p.id AS printer_id, p.brand, p.serial_number, p.ink_system_type, p.ink_usage_type,
                   p.head_system_type, p.valuation_method, p.purchase_value, p.current_value, p.status,
                   p.initial_fill_known, p.estimation_mode,
                   d.id AS diagnostico_id, d.diagnostic_date AS fecha, d.total_pages, d.color_pages, d.bw_pages,
                   d.borderless_pages, d.scanned_pages, d.diagnostic_accuracy, d.confidence_level,
                   c.depreciation_amount, c.estimated_head_wear_percent AS head_wear_pct,
                   t.black_ml, t.cyan_ml, t.magenta_ml, t.yellow_ml
            FROM activos a
            LEFT JOIN printers p ON p.asset_id=a.id
            LEFT JOIN printer_diagnostics d ON d.id = (
                SELECT id FROM printer_diagnostics WHERE printer_id=p.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN printer_cost_snapshots c ON c.diagnostic_id=d.id
            LEFT JOIN (
                SELECT diagnostic_id,
                       SUM(CASE WHEN color='black' THEN estimated_ml ELSE 0 END) AS black_ml,
                       SUM(CASE WHEN color='cyan' THEN estimated_ml ELSE 0 END) AS cyan_ml,
                       SUM(CASE WHEN color='magenta' THEN estimated_ml ELSE 0 END) AS magenta_ml,
                       SUM(CASE WHEN color='yellow' THEN estimated_ml ELSE 0 END) AS yellow_ml
                FROM printer_diagnostic_tank_levels
                GROUP BY diagnostic_id
            ) t ON t.diagnostic_id=d.id
            WHERE a.id=?
            """,
            (int(activo_id),),
        ).fetchone()
        if not row:
            return {}

        data = dict(row)
        printer_id = data.get("printer_id")
        if printer_id:
            consumos = conn.execute(
                """
                SELECT color,
                       SUM(COALESCE(c.estimated_ink_black_ml_used,0) * CASE WHEN color='black' THEN 1 ELSE 0 END
                           + COALESCE(c.estimated_ink_cyan_ml_used,0) * CASE WHEN color='cyan' THEN 1 ELSE 0 END
                           + COALESCE(c.estimated_ink_magenta_ml_used,0) * CASE WHEN color='magenta' THEN 1 ELSE 0 END
                           + COALESCE(c.estimated_ink_yellow_ml_used,0) * CASE WHEN color='yellow' THEN 1 ELSE 0 END) AS consumed_ml
                FROM (
                    SELECT 'black' AS color UNION ALL SELECT 'cyan' UNION ALL SELECT 'magenta' UNION ALL SELECT 'yellow'
                ) colors
                LEFT JOIN printer_cost_snapshots c ON c.printer_id=?
                GROUP BY color
                """,
                (int(printer_id),),
            ).fetchall()
            data["consumos"] = {str(r["color"]): _to_float(r["consumed_ml"]) for r in consumos}
            data["low_ink_alerts"] = [
                c for c in COLOR_KEYS if _to_float(data.get(f"{c}_ml")) <= LOW_LEVEL
            ]
        else:
            data["consumos"] = {}
            data["low_ink_alerts"] = []
    return data


def list_printer_diagnostics(activo_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with db_transaction() as conn:
        _ensure_diagnostics_schema(conn)
        printer = conn.execute("SELECT id FROM printers WHERE asset_id=?", (int(activo_id),)).fetchone()
        if not printer:
            return []
        rows = conn.execute(
            """
            SELECT d.*,
                   (SELECT COUNT(1) FROM printer_diagnostic_files f WHERE f.diagnostic_id=d.id) AS files_count,
                   (SELECT COUNT(1) FROM printer_diagnostic_tank_levels t WHERE t.diagnostic_id=d.id) AS tank_rows,
                   c.estimated_ink_black_ml_used,
                   c.estimated_ink_cyan_ml_used,
                   c.estimated_ink_magenta_ml_used,
                   c.estimated_ink_yellow_ml_used,
                   c.estimated_head_wear_percent,
                   c.depreciation_amount,
                   c.reliability
            FROM printer_diagnostics d
            LEFT JOIN printer_cost_snapshots c ON c.diagnostic_id=d.id
            WHERE d.printer_id=?
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (int(printer["id"]), int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
