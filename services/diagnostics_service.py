from __future__ import annotations

import re
import unicodedata
from typing import Any

from database.connection import db_transaction


_COLOR_ORDER = ("Cyan", "Magenta", "Yellow", "Black")
CRITICAL_LEVEL = 10
LOW_LEVEL = 25
PERCENT_REGEX = re.compile(r"(\d{1,3})\s*%")
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


def _extraer_numeros_linea(linea: str) -> list[int]:
    candidatos = re.findall(r"\d[\d\s.,]{0,15}", linea or "")
    valores: list[int] = []
    for raw in candidatos:
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        try:
            valor = int(digits)
        except ValueError:
            continue
        if valor > 0:
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



def extraer_texto_diagnostico(texto_ocr: str | None) -> dict[str, Any]:
    texto = str(texto_ocr or "")
    porcentajes = [float(v) for v in PERCENT_REGEX.findall(texto)]
    return {
        "porcentajes": [_clamp_percentage(v) for v in porcentajes],
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
                  )
                ORDER BY id DESC
                """
            ).fetchall()
        except Exception:
            return []

    return [dict(r) for r in rows]


def _ensure_diagnostics_schema(conn) -> None:
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
            vida_almohadillas_pct REAL
        )
        """
    )

    diag_cols = {row[1] for row in conn.execute("PRAGMA table_info(diagnosticos_impresora)").fetchall()}
    if "vida_rodillo_pct" not in diag_cols:
        conn.execute("ALTER TABLE diagnosticos_impresora ADD COLUMN vida_rodillo_pct REAL")
    if "vida_almohadillas_pct" not in diag_cols:
        conn.execute("ALTER TABLE diagnosticos_impresora ADD COLUMN vida_almohadillas_pct REAL")

    activos_cols = {row[1] for row in conn.execute("PRAGMA table_info(activos)").fetchall()}
    if "paginas_impresas" not in activos_cols:
        conn.execute("ALTER TABLE activos ADD COLUMN paginas_impresas INTEGER NOT NULL DEFAULT 0")
    if "vida_cabezal_pct" not in activos_cols:
        conn.execute("ALTER TABLE activos ADD COLUMN vida_cabezal_pct REAL")
    if "vida_rodillo_pct" not in activos_cols:
        conn.execute("ALTER TABLE activos ADD COLUMN vida_rodillo_pct REAL")
    if "vida_almohadillas_pct" not in activos_cols:
        conn.execute("ALTER TABLE activos ADD COLUMN vida_almohadillas_pct REAL")



def _buscar_item_tinta(conn, color: str) -> dict[str, Any] | None:
    terms = {
        "Cyan": ["cyan", "cian", "azul"],
        "Magenta": ["magenta", "fucsia"],
        "Yellow": ["yellow", "amarillo"],
        "Black": ["black", "negro"],
    }.get(color, [color.lower()])

    for term in terms:
        row = conn.execute(
            """
            SELECT id, nombre, unidad, stock_actual, costo_unitario_usd
            FROM inventario
            WHERE estado='activo'
              AND lower(COALESCE(categoria, '')) LIKE '%tinta%'
              AND lower(COALESCE(nombre, '')) LIKE ?
            ORDER BY stock_actual DESC, id DESC
            LIMIT 1
            """,
            (f"%{term.lower()}%",),
        ).fetchone()
        if row:
            return dict(row)
    return None


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

        previo = None
        if activo_id:
            previo = conn.execute(
                """
                SELECT cyan_ml, magenta_ml, yellow_ml, black_ml
                FROM diagnosticos_impresora
                WHERE activo_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(activo_id),),
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
                int(activo_id) if activo_id else None,
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

        if activo_id:
            vidas_componentes = [
                _clamp_percentage(vida_cabezal_pct),
                vida_rodillo,
                vida_almohadillas,
            ]
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
                    int(activo_id),
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
