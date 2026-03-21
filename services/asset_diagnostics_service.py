from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from database.connection import db_transaction

VISUAL_LEVEL_SCORES = {
    "Óptimo": 0,
    "Leve desgaste": 25,
    "En seguimiento": 60,
    "Crítico": 90,
}

NOTE_SIGNAL_WEIGHTS = {
    "adhesive_low": 18,
    "replace_now": 25,
    "cut_failure": 20,
    "heat_issue": 22,
    "residue": 10,
    "surface_damage": 12,
    "safety_risk": 18,
}


def _normalize_text(text: str | None) -> str:
    base = unicodedata.normalize("NFKD", str(text or ""))
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = re.sub(r"[^a-zA-Z0-9\s]+", " ", base).strip().lower()
    return re.sub(r"\s+", " ", base)


def get_asset_profile(asset: dict[str, Any] | None) -> dict[str, Any]:
    asset = dict(asset or {})
    unidad = _normalize_text(asset.get("unidad"))
    detalle = _normalize_text(asset.get("tipo_detalle"))
    equipo = _normalize_text(asset.get("equipo"))
    tipo_cuchilla = _normalize_text(asset.get("tipo_cuchilla"))
    bag = " ".join(x for x in [unidad, detalle, equipo, tipo_cuchilla] if x)

    if "tapete" in bag and ("cameo" in bag or "corte" in bag):
        return {
            "key": "tapete_corte",
            "label": "Tapete de corte / Cameo",
            "intro": "Ideal para evaluar adherencia, contaminación de la superficie y deformación del tapete.",
            "factors": [
                {"key": "adhesion_state", "label": "Agarre / pegajosidad", "help": "Si el material se levanta, marca un nivel alto de desgaste."},
                {"key": "surface_state", "label": "Rayas y cortes en superficie", "help": "Considera profundidad de marcas, zonas peladas o surcos."},
                {"key": "edge_state", "label": "Bordes y deformación", "help": "Evalúa si los bordes se doblan o el tapete perdió rigidez."},
                {"key": "cleanliness_state", "label": "Residuos / suciedad", "help": "Pelusa, vinil, papel o pegamento viejo afectan el desempeño."},
            ],
        }
    if "plancha" in bag and "sublim" in bag:
        return {
            "key": "plancha_sublimacion",
            "label": "Plancha de sublimación",
            "intro": "Permite estimar desgaste por teflón, presión, calor irregular y residuos.",
            "factors": [
                {"key": "heat_uniformity", "label": "Uniformidad de calor", "help": "Si hay zonas frías, manchas o transferencias incompletas, sube el desgaste."},
                {"key": "teflon_state", "label": "Estado del teflón / superficie", "help": "Observa peladuras, quemaduras o manchas en la placa."},
                {"key": "pressure_state", "label": "Presión y cierre", "help": "Si no prensa parejo o hay juego, marca un estado más crítico."},
                {"key": "residue_state", "label": "Residuos / contaminación", "help": "Restos de tinta, papel o pegamento reducen la calidad."},
            ],
        }
    if "cuchilla" in bag:
        return {
            "key": "cuchilla_corte",
            "label": "Cuchilla de corte",
            "intro": "Evalúa filo, precisión de corte, residuos y estabilidad del montaje.",
            "factors": [
                {"key": "edge_state", "label": "Filo / punta", "help": "Busca mellas, punta roma o desgaste visible."},
                {"key": "cut_precision", "label": "Precisión de corte", "help": "Si arrastra, rompe fibras o no termina el corte, aumenta el desgaste."},
                {"key": "residue_state", "label": "Residuos adheridos", "help": "Pegamento, vinil o papel acumulado aceleran la falla."},
                {"key": "mount_state", "label": "Montaje / sujeción", "help": "Evalúa vibración, juego o mala fijación en el carro."},
            ],
        }
    if any(term in bag for term in ("exacto", "bisturi", "norman")):
        return {
            "key": "herramienta_corte_manual",
            "label": "Herramienta de corte manual",
            "intro": "Sirve para exactos, bisturíes y tapetes/manuales de escritorio que dependen del filo y seguridad.",
            "factors": [
                {"key": "edge_state", "label": "Filo visible", "help": "Marca crítico si la hoja está roma, doblada o presenta óxido."},
                {"key": "cut_precision", "label": "Precisión manual", "help": "Si rasga o requiere demasiada fuerza, está próximo a cambio."},
                {"key": "body_state", "label": "Mango / cuerpo", "help": "Revisa holguras, grietas o falta de estabilidad."},
                {"key": "safety_state", "label": "Seguridad de uso", "help": "Evalúa si representa riesgo por aflojamiento o daño."},
            ],
        }
    return {
        "key": "generico",
        "label": "Activo general",
        "intro": "Diagnóstico visual asistido para cualquier activo que requiera seguimiento por evidencia fotográfica y notas.",
        "factors": [
            {"key": "visual_state", "label": "Estado visual general", "help": "Desgaste, golpes, corrosión o fatiga."},
            {"key": "performance_state", "label": "Desempeño observado", "help": "Resultado operativo percibido."},
            {"key": "cleanliness_state", "label": "Limpieza / residuos", "help": "Acumulación que afecte el uso."},
            {"key": "safety_state", "label": "Riesgo operativo", "help": "Holguras, calor anormal o deterioro peligroso."},
        ],
    }


def _extract_note_signals(notes: str | None) -> list[str]:
    text = _normalize_text(notes)
    if not text:
        return []

    patterns = {
        "adhesive_low": [r"no pega", r"perdio agarre", r"pierde agarre", r"se despega", r"se levanta", r"ponerle pegamento", r"mas pegamento"],
        "replace_now": [r"cambio urgente", r"cambiar ya", r"vida util", r"ya no sirve", r"muy gastad", r"peligr", r"riesgo"],
        "cut_failure": [r"corta mal", r"no corta", r"corte incompleto", r"arrastra", r"rasga", r"deshilacha"],
        "heat_issue": [r"no calienta", r"calienta desigual", r"zona fria", r"mancha", r"quema", r"no sublima parejo"],
        "residue": [r"residu", r"pegamento", r"pelusa", r"suciedad", r"adhesivo viejo"],
        "surface_damage": [r"raya", r"surco", r"pelad", r"doblad", r"torcid", r"oxid"],
        "safety_risk": [r"floja", r"holgura", r"vibra", r"insegur", r"se afloja"],
    }

    found: list[str] = []
    for signal, exprs in patterns.items():
        if any(re.search(expr, text) for expr in exprs):
            found.append(signal)
    return found


def analyze_asset_diagnostic(
    asset: dict[str, Any],
    observations: dict[str, str | int | float | None] | None = None,
    notes: str | None = None,
    photos_count: int = 0,
) -> dict[str, Any]:
    profile = get_asset_profile(asset)
    observations = dict(observations or {})

    factor_scores: dict[str, int] = {}
    for factor in profile["factors"]:
        raw_value = observations.get(factor["key"])
        if isinstance(raw_value, str):
            factor_scores[factor["key"]] = int(VISUAL_LEVEL_SCORES.get(raw_value, 0))
        else:
            try:
                factor_scores[factor["key"]] = max(0, min(100, int(raw_value or 0)))
            except (TypeError, ValueError):
                factor_scores[factor["key"]] = 0

    visual_wear = round(sum(factor_scores.values()) / max(len(factor_scores), 1), 2)
    tracked_remaining = asset.get("vida_restante_pct")
    tracked_wear = None
    try:
        tracked_wear = max(0.0, min(100.0, 100.0 - float(tracked_remaining)))
    except (TypeError, ValueError):
        tracked_wear = None

    note_signals = _extract_note_signals(notes)
    note_penalty = sum(NOTE_SIGNAL_WEIGHTS.get(signal, 0) for signal in note_signals)
    note_penalty = min(35, note_penalty)

    if tracked_wear is None:
        estimated_wear = min(100.0, visual_wear + note_penalty)
    else:
        estimated_wear = min(100.0, (tracked_wear * 0.35) + (visual_wear * 0.65) + note_penalty)
    estimated_wear = round(estimated_wear, 2)
    remaining_life = round(max(0.0, 100.0 - estimated_wear), 2)

    recommendation_parts: list[str] = []
    profile_key = profile["key"]
    if profile_key == "tapete_corte":
        adhesion_score = factor_scores.get("adhesion_state", 0)
        if adhesion_score >= 60 or "adhesive_low" in note_signals:
            recommendation_parts.append("Aplicar limpieza profunda y renovar pegamento/adhesivo del tapete.")
        if estimated_wear >= 75:
            recommendation_parts.append("Planificar cambio del tapete porque su vida útil está comprometida.")
    elif profile_key == "plancha_sublimacion":
        if factor_scores.get("heat_uniformity", 0) >= 60 or "heat_issue" in note_signals:
            recommendation_parts.append("Revisar temperatura real, resistencia y presión de la plancha.")
        if factor_scores.get("teflon_state", 0) >= 60:
            recommendation_parts.append("Cambiar teflón/protección o reacondicionar la superficie antes de seguir produciendo.")
    elif profile_key in {"cuchilla_corte", "herramienta_corte_manual"}:
        if factor_scores.get("edge_state", 0) >= 60 or "cut_failure" in note_signals:
            recommendation_parts.append("Programar cambio o afilado de cuchilla por pérdida de filo.")
        if factor_scores.get("residue_state", 0) >= 60:
            recommendation_parts.append("Limpiar residuos adheridos antes de volver a evaluar.")

    if estimated_wear >= 85:
        severity = "Crítico"
        recommendation_parts.append("Sacar de operación o usar solo bajo contingencia hasta reemplazo.")
    elif estimated_wear >= 65:
        severity = "Alto"
        recommendation_parts.append("Programar mantenimiento/cambio a corto plazo.")
    elif estimated_wear >= 40:
        severity = "Medio"
        recommendation_parts.append("Mantener seguimiento y registrar nueva foto en la próxima revisión.")
    else:
        severity = "Bajo"
        recommendation_parts.append("Activo operativo; continuar seguimiento preventivo.")

    if photos_count <= 0:
        recommendation_parts.append("Sube al menos una foto para dejar evidencia visual del estado.")

    return {
        "profile_key": profile_key,
        "profile_label": profile["label"],
        "estimated_wear_pct": estimated_wear,
        "remaining_life_pct": remaining_life,
        "severity": severity,
        "recommendation": " ".join(dict.fromkeys(recommendation_parts)),
        "factor_scores": factor_scores,
        "note_signals": note_signals,
        "photos_count": int(max(0, photos_count)),
        "confidence": "media" if photos_count else "baja",
    }


def _ensure_asset_diagnostics_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activo_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            profile_key TEXT,
            estimated_wear_pct REAL NOT NULL DEFAULT 0,
            remaining_life_pct REAL NOT NULL DEFAULT 100,
            severity TEXT NOT NULL DEFAULT 'Bajo',
            recommendation TEXT,
            notes TEXT,
            factor_scores_json TEXT,
            note_signals_json TEXT,
            files_json TEXT,
            photos_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(asset_diagnostics)").fetchall()}
    optional_cols = {
        "profile_key": "ALTER TABLE asset_diagnostics ADD COLUMN profile_key TEXT",
        "estimated_wear_pct": "ALTER TABLE asset_diagnostics ADD COLUMN estimated_wear_pct REAL NOT NULL DEFAULT 0",
        "remaining_life_pct": "ALTER TABLE asset_diagnostics ADD COLUMN remaining_life_pct REAL NOT NULL DEFAULT 100",
        "severity": "ALTER TABLE asset_diagnostics ADD COLUMN severity TEXT NOT NULL DEFAULT 'Bajo'",
        "recommendation": "ALTER TABLE asset_diagnostics ADD COLUMN recommendation TEXT",
        "notes": "ALTER TABLE asset_diagnostics ADD COLUMN notes TEXT",
        "factor_scores_json": "ALTER TABLE asset_diagnostics ADD COLUMN factor_scores_json TEXT",
        "note_signals_json": "ALTER TABLE asset_diagnostics ADD COLUMN note_signals_json TEXT",
        "files_json": "ALTER TABLE asset_diagnostics ADD COLUMN files_json TEXT",
        "photos_count": "ALTER TABLE asset_diagnostics ADD COLUMN photos_count INTEGER NOT NULL DEFAULT 0",
    }
    for col, sql in optional_cols.items():
        if col not in cols:
            conn.execute(sql)


def save_asset_diagnostic_file(file_obj, activo_id: int, category: str = "foto") -> dict[str, Any] | None:
    if file_obj is None:
        return None

    root = Path("uploads") / "activos_diagnosticos" / str(int(activo_id))
    root.mkdir(parents=True, exist_ok=True)
    suffix = Path(getattr(file_obj, "name", "")).suffix or ".bin"
    raw = file_obj.getvalue()
    digest = hashlib.sha1(raw).hexdigest()[:12]
    file_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{category}_{digest}{suffix}"
    target = root / file_name
    target.write_bytes(raw)
    return {
        "file_name": getattr(file_obj, "name", file_name),
        "file_path": str(target),
        "file_type": getattr(file_obj, "type", ""),
        "file_size": len(raw),
        "category": category,
    }


def create_asset_diagnostic(
    activo: dict[str, Any],
    usuario: str,
    observations: dict[str, str | int | float | None] | None = None,
    notes: str | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    activo = dict(activo or {})
    files = [dict(item) for item in (files or []) if item]
    analysis = analyze_asset_diagnostic(activo, observations=observations, notes=notes, photos_count=len(files))

    with db_transaction() as conn:
        _ensure_asset_diagnostics_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO asset_diagnostics(
                activo_id, created_by, profile_key, estimated_wear_pct, remaining_life_pct,
                severity, recommendation, notes, factor_scores_json, note_signals_json, files_json, photos_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(activo["id"]),
                usuario,
                analysis["profile_key"],
                float(analysis["estimated_wear_pct"]),
                float(analysis["remaining_life_pct"]),
                analysis["severity"],
                analysis["recommendation"],
                str(notes or "").strip() or None,
                json.dumps(analysis["factor_scores"], ensure_ascii=False),
                json.dumps(analysis["note_signals"], ensure_ascii=False),
                json.dumps(files, ensure_ascii=False) if files else None,
                len(files),
            ),
        )
        analysis["id"] = int(cur.lastrowid)
    return analysis


def list_asset_diagnostics(activo_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with db_transaction() as conn:
        _ensure_asset_diagnostics_schema(conn)
        rows = conn.execute(
            """
            SELECT id, activo_id, created_at, created_by, profile_key, estimated_wear_pct,
                   remaining_life_pct, severity, recommendation, notes, factor_scores_json,
                   note_signals_json, files_json, photos_count
            FROM asset_diagnostics
            WHERE activo_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(activo_id), int(limit)),
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("factor_scores_json", "note_signals_json", "files_json"):
            raw = item.get(key)
            try:
                item[key.replace("_json", "")] = json.loads(raw) if raw else [] if "signals" in key or "files" in key else {}
            except json.JSONDecodeError:
                item[key.replace("_json", "")] = [] if "signals" in key or "files" in key else {}
        result.append(item)
    return result


def get_latest_asset_diagnostic(activo_id: int) -> dict[str, Any] | None:
    rows = list_asset_diagnostics(activo_id, limit=1)
    return rows[0] if rows else None
